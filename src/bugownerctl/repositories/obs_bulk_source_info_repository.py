"""Bulk OBS source-info repository.

Fetches `/source/<project>?view=info&parse=1` from the OBS API via `osc api`
(SSH-signature auth is delegated to the user's local `osc` install), parses
the response into a `dict[binary_or_subpack → canonical_source]`, and caches
both the raw XML and metadata on disk so subsequent runs avoid the network.

This module requires the `osc` (openSUSE Commander) command-line tool to be
installed and available in PATH. Install it with:
    zypper install osc
or
    pip install osc

Authentication rationale: `api.suse.de` requires SSH-signature auth that
HTTP Basic auth cannot supply; delegating to `osc api` reuses the user's
existing credential manager configuration. See SOURCE_NAME_RESOLUTION_REFACTOR_PLAN.md
section 9 for the full discussion.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

from bugownerctl.domain.bulk_map import BulkMap

logger = logging.getLogger(__name__)

OBS_HOST = "https://api.suse.de"
CACHE_TTL = timedelta(days=7)
DEFAULT_TIMEOUT = 120  # seconds for the osc api subprocess

# Hard ceiling on raw XML size accepted from OBS. Real bulk responses are
# ~4 MB; 50 MB leaves comfortable headroom while bounding the worst case so
# a hostile/corrupted response cannot exhaust process memory before parsing.
MAX_XML_BYTES = 50 * 1024 * 1024  # 50 MB

XML_FILENAME = "obs_bulk_map.xml"
META_FILENAME = "obs_bulk_map.meta.json"

# Allow only characters that are safe both in a URL path segment and in an argv.
# Project names look like "SUSE:SLFO:Main"; this rejects shell metachars,
# whitespace, slashes (path traversal), and any other surprises. The length
# bound (1..200) caps argv/URL growth — real OBS project names are <100 chars.
_PROJECT_RE = re.compile(r"^[A-Za-z0-9:_.+\-]{1,200}$")


class ObsBulkSourceInfoRepository(Protocol):
    """Fetch and parse OBS bulk source-info into a binary→source name map.

    One HTTP round-trip per cache-miss run; on cache hit the on-disk XML is
    re-parsed (no network).
    """

    def load_bulk_map(
        self,
        project: str,
        cache_dir: Path,
        *,
        force_refresh: bool = False,
    ) -> BulkMap:
        """Return a BulkMap for `project`, fetching from OBS if cache is stale.

        Cache layout under cache_dir:
            obs_bulk_map.xml         # raw OBS response body
            obs_bulk_map.meta.json   # {"project", "fetched_at", "sha256"}

        Args:
            project: OBS project name, e.g. "SUSE:SLFO:Main". Must match
                [A-Za-z0-9:_.+-]{1,200} (validated before any subprocess call).
            cache_dir: Absolute path to the cache root directory.
            force_refresh: If True, bypass cache freshness check and re-fetch.

        Returns:
            BulkMap resolving both source-package identity (apache2 → apache2)
            and binary/subpack/multibuild aliases (apache2-devel → apache2,
            kernel-azure → kernel-source-azure-base).

        Raises:
            ValueError: If `project` contains characters outside [A-Za-z0-9:_.+-]
                or exceeds 200 chars, or `cache_dir` is not absolute.
            RuntimeError: If `osc api` exits non-zero, times out, `osc` is not
                installed, or the response is not parseable as <sourceinfolist>.
        """
        ...


class ObsBulkSourceInfoRepositoryImpl:
    """Adapter implementation backed by `osc api` and an on-disk XML cache."""

    def load_bulk_map(
        self,
        project: str,
        cache_dir: Path,
        *,
        force_refresh: bool = False,
    ) -> BulkMap:
        self._validate_inputs(project, cache_dir)

        xml_path = cache_dir / XML_FILENAME
        meta_path = cache_dir / META_FILENAME

        # Refuse to read or write through a symlink. Mirrors false_positives_repository
        # precedent: an attacker who can plant a symlink in cache_dir could otherwise
        # redirect the cache write to an arbitrary file (e.g. ~/.ssh/authorized_keys).
        # Check before any read or write touches these paths.
        if xml_path.is_symlink():
            raise RuntimeError(f"Refusing to read/write symlink cache file: {xml_path}")
        if meta_path.is_symlink():
            raise RuntimeError(f"Refusing to read/write symlink cache file: {meta_path}")

        cached = None if force_refresh else self._read_fresh_cache(xml_path, meta_path, project)
        if cached is not None:
            xml_body, fetched_at = cached
            logger.debug("OBS bulk cache hit for %s (fetched_at=%s)", project, fetched_at)
        else:
            logger.info("Fetching OBS bulk source-info for project %s", project)
            xml_body = self._fetch_via_osc_api(project)
            fetched_at = datetime.now(timezone.utc)
            cache_dir.mkdir(parents=True, exist_ok=True)
            # Restrict the cache directory to owner-only (mirrors
            # false_positives_repository pattern). Cached XML may include
            # internal project metadata that other local users should not read.
            os.chmod(cache_dir, 0o700)
            # Parse FIRST so a malformed body never leaves a partial cache.
            mapping = self._build_bulk_map(xml_body)
            self._write_cache_atomic(xml_path, meta_path, project, xml_body, fetched_at)
            return BulkMap(mapping=mapping, project=project, fetched_at=fetched_at)

        mapping = self._build_bulk_map(xml_body)
        return BulkMap(mapping=mapping, project=project, fetched_at=fetched_at)

    # ------------------------------------------------------------------
    # Validation

    @staticmethod
    def _validate_inputs(project: str, cache_dir: Path) -> None:
        if not isinstance(cache_dir, Path) or not cache_dir.is_absolute():
            raise ValueError(f"cache_dir must be an absolute Path, got: {cache_dir!r}")
        if not project or not _PROJECT_RE.match(project):
            raise ValueError(f"project name must match [A-Za-z0-9:_.+-]{{1,200}}, got: {project!r}")

    # ------------------------------------------------------------------
    # Cache I/O

    def _read_fresh_cache(
        self, xml_path: Path, meta_path: Path, project: str
    ) -> tuple[bytes, datetime] | None:
        """Return (xml_body, fetched_at) when both files exist, the meta hash
        matches the on-disk XML, the cached project matches `project`, and the
        timestamp is within the TTL window."""
        if not xml_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cache meta unreadable (%s); refetching", exc)
            return None

        fetched_raw = meta.get("fetched_at")
        sha_expected = meta.get("sha256")
        cached_project = meta.get("project")
        if not isinstance(fetched_raw, str) or not isinstance(sha_expected, str):
            logger.warning("Cache meta missing required fields; refetching")
            return None
        if cached_project != project:
            logger.info(
                "OBS bulk cache project mismatch (cached=%r, requested=%r); refetching",
                cached_project,
                project,
            )
            return None
        try:
            fetched_at = datetime.fromisoformat(fetched_raw)
        except ValueError:
            logger.warning("Cache meta has invalid fetched_at; refetching")
            return None

        if datetime.now(timezone.utc) - fetched_at > CACHE_TTL:
            logger.info("OBS bulk cache stale (age > %s); refetching", CACHE_TTL)
            return None

        try:
            xml_body = xml_path.read_bytes()
        except OSError as exc:
            logger.warning("Cache XML unreadable (%s); refetching", exc)
            return None

        sha_actual = hashlib.sha256(xml_body).hexdigest()
        if sha_actual != sha_expected:
            logger.warning(
                "OBS bulk cache XML sha256 mismatch (expected=%s, actual=%s); refetching",
                sha_expected,
                sha_actual,
            )
            return None

        return xml_body, fetched_at

    @staticmethod
    def _write_cache_atomic(
        xml_path: Path,
        meta_path: Path,
        project: str,
        xml_body: bytes,
        fetched_at: datetime,
    ) -> None:
        """Write XML + meta JSON via tmp-then-rename to avoid partial files.

        Each tmp file is chmod 0o600 BEFORE os.replace so the final file is
        never observable in the filesystem with a wider mode.
        """
        xml_tmp = xml_path.with_suffix(xml_path.suffix + ".tmp")
        meta_tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
        xml_tmp.write_bytes(xml_body)
        os.chmod(xml_tmp, 0o600)
        os.replace(xml_tmp, xml_path)
        meta = {
            "project": project,
            "fetched_at": fetched_at.isoformat(),
            "sha256": hashlib.sha256(xml_body).hexdigest(),
        }
        meta_tmp.write_text(json.dumps(meta, indent=2, sort_keys=True))
        os.chmod(meta_tmp, 0o600)
        os.replace(meta_tmp, meta_path)

    # ------------------------------------------------------------------
    # Subprocess

    @staticmethod
    def _fetch_via_osc_api(project: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
        """Call OBS API via `osc api` subprocess. Argv-style (no shell)."""
        path = f"/source/{project}?view=info&parse=1"
        try:
            proc = subprocess.run(
                ["osc", "-A", OBS_HOST, "api", path],
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "osc executable not found; install with `zypper install osc` or `pip install osc`"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"osc api {path!r} timed out after {timeout}s") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"osc api {path!r} failed (exit {proc.returncode}):\n{stderr}")
        return proc.stdout

    # ------------------------------------------------------------------
    # Parsing

    @staticmethod
    def _build_bulk_map(xml_body: bytes) -> dict[str, str]:
        """Parse <sourceinfolist> XML into a binary→canonical-source map.

        Rules:
          - <sourceinfo package="P"> with <originpackage>X</originpackage>
            → P is a multibuild flavor of X.
          - Each <subpacks>S</subpacks> child → S is a binary built by P.
          - When P is a flavor, every binary attributes to the parent X.
          - Flavor chains resolved recursively with a cycle guard.
          - Collision (two sources claim same binary): identity wins over
            alias; else first-write wins.
        """
        # Size cap: refuse oversized bodies before allocating an ET tree.
        if len(xml_body) > MAX_XML_BYTES:
            raise RuntimeError(
                f"OBS bulk response exceeds {MAX_XML_BYTES} bytes ({len(xml_body)}); "
                "refusing to parse to avoid memory exhaustion"
            )
        # DOCTYPE check: ET.fromstring blocks external-entity (XXE) loads but
        # still expands *internal* entities, so a small DOCTYPE with nested
        # entity definitions ("billion laughs") can OOM the process. Real OBS
        # bulk responses never contain a DOCTYPE; refuse any that do. We scan
        # only the prologue (first 4 KiB) since DOCTYPE must precede the root
        # element per XML 1.0 §2.8.
        if b"<!DOCTYPE" in xml_body[:4096]:
            raise RuntimeError(
                "OBS bulk response contains a DOCTYPE declaration; refusing to parse "
                "(prevents entity-expansion attacks). Real OBS responses never contain DOCTYPE."
            )
        try:
            root = ET.fromstring(xml_body)
        except ET.ParseError as exc:
            snippet = xml_body[:200].decode(errors="replace")
            raise RuntimeError(
                f"OBS bulk response is not valid XML: {exc} (body starts: {snippet!r})"
            ) from exc

        canonical: dict[str, str] = {}  # P → X if flavor else P → P
        subpacks_by_source: dict[str, list[str]] = {}

        for si in root.findall("sourceinfo"):
            pkg = si.get("package", "")
            if not pkg:
                continue
            origin = si.findtext("originpackage")
            if origin:
                canonical[pkg] = origin
            else:
                canonical.setdefault(pkg, pkg)
            # Strip then re-check truthiness: a whitespace-only <subpacks> text
            # would pass `if s.text` (whitespace is truthy) and inject bogus
            # keys like "   " into the mapping.
            subs = [text for s in si.findall("subpacks") if s.text and (text := s.text.strip())]
            if subs:
                subpacks_by_source[pkg] = subs

        # Resolve flavor → root canonical (collapse chains).
        def resolve(name: str, seen: set[str] | None = None) -> str:
            seen = seen if seen is not None else set()
            if name in seen:
                return name  # cycle guard
            seen.add(name)
            target = canonical.get(name, name)
            return target if target == name else resolve(target, seen)

        bulk_map: dict[str, str] = {}
        # Source-side identities first.
        for src in canonical:
            bulk_map[src] = resolve(src)
        # Subpackage → source.
        for src, subs in subpacks_by_source.items():
            root_src = resolve(src)
            for sub in subs:
                existing = bulk_map.get(sub)
                if existing is None:
                    bulk_map[sub] = root_src
                    continue
                if existing == sub:
                    # Identity already wins (sub is its own source);
                    # do not let an alias claim from another source overwrite.
                    continue
                if existing == root_src:
                    continue  # already consistent
                # Two sources claim this binary. Prefer the one where the
                # binary name equals the resolved source name (identity);
                # otherwise first write wins (do nothing).
                if sub == root_src:
                    bulk_map[sub] = root_src

        return bulk_map
