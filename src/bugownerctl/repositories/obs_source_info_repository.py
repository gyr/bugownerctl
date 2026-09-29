"""OBS source-info repository.

Fetches `/source/<project>?view=info&parse=1` from the OBS API via `osc api`
(SSH-signature auth is delegated to the user's local `osc` install), parses
the response in memory into a `dict[binary_or_subpack → canonical_source]`.
Nothing is cached: every run fetches the current state from OBS.

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

import logging
import re
import subprocess
from datetime import UTC, datetime
from typing import Protocol
from xml.etree.ElementTree import Element  # type annotation only; parsing uses defusedxml

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from bugownerctl.domain.obs_source_info import ObsSourceInfo
from bugownerctl.exceptions import MissingBinaryError, NetworkTimeoutError

logger = logging.getLogger(__name__)

OBS_HOST = "https://api.suse.de"
DEFAULT_TIMEOUT = 120  # seconds for the osc api subprocess

# Hard ceiling on raw XML size accepted from OBS. Real source-info responses are
# ~4 MB; 50 MB leaves comfortable headroom while bounding the worst case so
# a hostile/corrupted response cannot exhaust process memory before parsing.
MAX_XML_BYTES = 50 * 1024 * 1024  # 50 MB

# Allow only characters that are safe both in a URL path segment and in an argv.
# Project names look like "SUSE:SLFO:Main"; this rejects shell metachars,
# whitespace, slashes (path traversal), and any other surprises. The length
# bound (1..200) caps argv/URL growth — real OBS project names are <100 chars.
_PROJECT_RE = re.compile(r"^[A-Za-z0-9:_.+\-]{1,200}$")


class ObsSourceInfoRepository(Protocol):
    """Fetch and parse OBS source-info into a binary→source name map.

    One HTTP round-trip per call; the reply is parsed in memory and never
    written to disk.
    """

    def load_source_info(self, project: str) -> ObsSourceInfo:
        """Fetch `project`'s source-info from OBS and return it as an ObsSourceInfo.

        Args:
            project: OBS project name, e.g. "SUSE:SLFO:Main". Must match
                [A-Za-z0-9:_.+-]{1,200} (validated before any subprocess call).

        Returns:
            ObsSourceInfo resolving both source-package identity (apache2 → apache2)
            and binary/subpack/multibuild aliases (apache2-devel → apache2,
            kernel-azure → kernel-source-azure-base).

        Raises:
            ValueError: If `project` contains characters outside [A-Za-z0-9:_.+-]
                or exceeds 200 chars.
            MissingBinaryError: If osc is not in PATH.
            NetworkTimeoutError: If the osc api subprocess exceeds the timeout.
            RuntimeError: If `osc api` exits non-zero, the response is not
                valid XML or not a <sourceinfolist> (e.g. an OBS <status>
                error document), or it lists no <sourceinfo>.
        """
        ...


class ObsSourceInfoRepositoryImpl:
    """Adapter implementation backed by `osc api`."""

    def load_source_info(self, project: str) -> ObsSourceInfo:
        self._validate_inputs(project)
        logger.info("Fetching OBS source-info for project %s", project)
        xml_body = self._fetch_via_osc_api(project)
        fetched_at = datetime.now(UTC)
        root = self._parse_sourceinfolist(xml_body)
        self._validate_sourceinfolist(root, project)
        return ObsSourceInfo(
            mapping=self._build_mapping(root),
            project=project,
            fetched_at=fetched_at,
            packages=self._extract_package_names(root),
        )

    # ------------------------------------------------------------------
    # Validation

    @staticmethod
    def _validate_inputs(project: str) -> None:
        if not project or not _PROJECT_RE.match(project):
            raise ValueError(f"project name must match [A-Za-z0-9:_.+-]{{1,200}}, got: {project!r}")

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
            raise MissingBinaryError("osc") from exc
        except subprocess.TimeoutExpired as exc:
            raise NetworkTimeoutError(f"osc api {path!r}", timeout) from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"osc api {path!r} failed (exit {proc.returncode}):\n{stderr}")
        return proc.stdout

    # ------------------------------------------------------------------
    # Parsing

    @staticmethod
    def _parse_sourceinfolist(xml_body: bytes) -> Element:
        """Parse a raw <sourceinfolist> body into its root element.

        Guards: size cap, DOCTYPE refusal (entity-expansion defence), and
        malformed-XML rejection.

        Args:
            xml_body: Raw response body from the OBS source-info endpoint.

        Returns:
            The parsed root element.

        Raises:
            RuntimeError: If the body is oversized, declares a DOCTYPE, or is
                not valid XML.
        """
        # Size cap: refuse oversized bodies before allocating an ET tree.
        if len(xml_body) > MAX_XML_BYTES:
            raise RuntimeError(
                f"OBS source-info response exceeds {MAX_XML_BYTES} bytes ({len(xml_body)}); "
                "refusing to parse to avoid memory exhaustion"
            )
        try:
            root: Element = ET.fromstring(xml_body, forbid_dtd=True)
        except DefusedXmlException as exc:
            raise RuntimeError(
                "OBS source-info response contains a DOCTYPE declaration; refusing to parse "
                "(prevents entity-expansion attacks). Real OBS responses never contain DOCTYPE."
            ) from exc
        except ET.ParseError as exc:
            snippet = xml_body[:200].decode(errors="replace")
            raise RuntimeError(
                f"OBS source-info response is not valid XML: {exc} (body starts: {snippet!r})"
            ) from exc
        return root

    @staticmethod
    def _validate_sourceinfolist(root: Element, project: str) -> None:
        """Reject a parsed reply that is not a non-empty <sourceinfolist>.

        Args:
            root: Root element returned by `_parse_sourceinfolist`.
            project: The requested OBS project name, used in error messages.

        Raises:
            RuntimeError: If the root element is not <sourceinfolist> (message
                carries the root tag and any <summary> text), or if it has no
                <sourceinfo> children.
        """
        if root.tag != "sourceinfolist":
            message = (
                f"OBS reply for project {project} is not a package list (root element <{root.tag}>)"
            )
            summary = (root.findtext("summary") or "").strip()
            if summary:
                message = f"{message}: {summary}"
            raise RuntimeError(message)
        if root.find("sourceinfo") is None:
            raise RuntimeError(
                f"OBS project {project} lists no packages; check 'obs_project' in your config"
            )

    @staticmethod
    def _extract_package_names(root: Element) -> frozenset[str]:
        """Return the project's source package names from a parsed <sourceinfolist>.

        Names containing `:` are multibuild flavors (`pkg:flav`) and are
        excluded. Surrounding whitespace is stripped; attributes that are
        empty after stripping are skipped. A non-flavor <sourceinfo>
        carrying an <error> child still names a package of the project, so
        it is kept; a warning with the package name and error text is logged.

        Args:
            root: Root element returned by `_parse_sourceinfolist`.

        Returns:
            The set of non-flavor source package names.
        """
        packages: set[str] = set()
        for si in root.findall("sourceinfo"):
            pkg = si.get("package", "").strip()
            if not pkg or ":" in pkg:
                continue
            error = si.find("error")
            if error is not None:
                logger.warning(
                    "OBS reports an error for package %s: %s", pkg, (error.text or "").strip()
                )
            packages.add(pkg)
        return frozenset(packages)

    @staticmethod
    def _build_mapping(root: Element) -> dict[str, str]:
        """Build a binary→canonical-source map from a parsed <sourceinfolist>.

        Rules:
          - Package, originpackage and subpacks names are whitespace-stripped;
            a name that is empty after stripping is treated as absent.
          - <sourceinfo package="P"> with <originpackage>X</originpackage>
            → P is a multibuild flavor of X.
          - Each <subpacks>S</subpacks> child → S is a binary built by P.
          - When P is a flavor, every binary attributes to the parent X.
          - Flavor chains resolved recursively with a cycle guard.
          - Collision (two sources claim same binary): identity wins over
            alias; else first-write wins.
        """
        canonical: dict[str, str] = {}  # P → X if flavor else P → P
        subpacks_by_source: dict[str, list[str]] = {}

        for si in root.findall("sourceinfo"):
            pkg = si.get("package", "").strip()
            if not pkg:
                continue
            origin = (si.findtext("originpackage") or "").strip()
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

        mapping: dict[str, str] = {}
        # Source-side identities first.
        for src in canonical:
            mapping[src] = resolve(src)
        # Subpackage → source.
        for src, subs in subpacks_by_source.items():
            root_src = resolve(src)
            for sub in subs:
                existing = mapping.get(sub)
                if existing is None:
                    mapping[sub] = root_src
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
                    mapping[sub] = root_src

        return mapping
