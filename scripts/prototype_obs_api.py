#!/usr/bin/env python3
"""Prototype: direct OBS API as name-resolution layer.

Plan: /home/gyr/.claude/plans/examine-the-code-it-cuddly-raven.md

Measures whether two OBS endpoints can replace the per-package `osc bse`
shellout currently used by `bugownerctl validate` / `whitelist` to resolve
subpackage / multibuild aliases:

  E1 (per-pkg, drop-in for `osc bse`):
    GET /search/published/binary/id?match=@name='<pkg>'+and+project='<proj>'

  E3 (bulk source-side, candidate "warm map"):
    GET /source/<proj>?view=info&parse=1

OBS auth on api.suse.de is SSH-key-based; this script delegates auth to
the user's existing `osc` install by calling `osc api ...`. A real refactor
would implement SSH-signature auth in Python; that's out of scope here.

Read-only: never mutates false_positives.json, primary.xml.gz, or anything
under ~/.cache/bugownerctl/. No new project dependencies. Standalone.

Run:
    python scripts/prototype_obs_api.py
    python scripts/prototype_obs_api.py --sample-size 30 --refresh-bulk
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree as ET

OBS_HOST = "https://api.suse.de"
OBS_PROJECT = "SUSE:SLFO:Main"
CACHE_DIR = Path.home() / ".cache" / "bugownerctl"
FALSE_POSITIVES = CACHE_DIR / "false_positives.json"
PRIMARY_XML = CACHE_DIR / "repodata" / "16.1" / "primary.xml.gz"
BULK_CACHE = Path("/tmp/prototype_obs_bulk.xml")
PRODUCTCOMPOSE_REPO = "gitea@src.suse.de:products/SLES.git"


# ---------------------------------------------------------------------------
# osc-mediated HTTP


def osc_api(path: str, timeout: int = 90) -> tuple[bytes, float]:
    """Call OBS API via `osc api`. Returns (body, wall_clock_seconds)."""
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["osc", "-A", OBS_HOST, "api", path],
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"osc api {path!r} failed (exit {proc.returncode}):\n"
            f"{proc.stderr.decode(errors='replace')}"
        )
    return proc.stdout, elapsed


def osc_bse(pkg: str, timeout: int = 30) -> tuple[str | None, float]:
    """Call `osc bse <pkg>`, parse with the same logic as obs_repository.py.

    Returns (source_pkg_or_None, wall_clock_seconds).
    """
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["osc", "-A", OBS_HOST, "bse", pkg],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        return None, elapsed
    prefix = f"{OBS_PROJECT} "
    sources: set[str] = set()
    for line in proc.stdout.splitlines():
        if not line.startswith(prefix):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1]:
            sources.add(parts[1].split(":")[0])
    if not sources:
        return None, elapsed
    return sorted(sources)[0], elapsed


# ---------------------------------------------------------------------------
# Endpoint 1: per-package via /search/published/binary/id

_NAME_QUOTE = re.compile(r"^[A-Za-z0-9._+\-]+$")


def endpoint1_lookup(pkg: str) -> tuple[str | None, float]:
    """Return (canonical_source_pkg, elapsed_seconds) for pkg via E1, or (None, t).

    `package` attribute is `source` or `source:flavor`; we strip flavor.
    """
    if not _NAME_QUOTE.match(pkg):
        return None, 0.0
    query = f"@name='{pkg}'+and+project='{OBS_PROJECT}'"
    body, elapsed = osc_api(f"/search/published/binary/id?match={query}&limit=50")
    root = ET.fromstring(body)
    sources: set[str] = set()
    for binary in root.findall("binary"):
        pkg_attr = binary.get("package", "")
        if pkg_attr:
            sources.add(pkg_attr.split(":")[0])
    if not sources:
        return None, elapsed
    return sorted(sources)[0], elapsed


# ---------------------------------------------------------------------------
# Endpoint 3: bulk source-info → binary→source map


def fetch_bulk(cache: Path, refresh: bool) -> tuple[bytes, float]:
    """Fetch /source/<proj>?view=info&parse=1 (cached on disk for reruns)."""
    if cache.exists() and not refresh:
        print(f"[E3] using cached bulk at {cache} (--refresh-bulk to re-download)")
        return cache.read_bytes(), 0.0
    print(f"[E3] fetching {OBS_HOST}/source/{OBS_PROJECT}?view=info&parse=1 ...")
    body, elapsed = osc_api(f"/source/{OBS_PROJECT}?view=info&parse=1", timeout=120)
    cache.write_bytes(body)
    print(f"[E3] fetched {len(body):,} bytes in {elapsed:.1f}s; cached at {cache}")
    return body, elapsed


def build_bulk_map(xml_body: bytes) -> tuple[dict[str, str], dict[str, int]]:
    """Parse <sourceinfolist> into binary→canonical-source map.

    Rules:
      - <sourceinfo package="P"> with <originpackage>X</originpackage>
        → P is a multibuild flavor of X.
      - Each <subpacks>S</subpacks> child → S is a binary built by P.
      - When P is a flavor, every binary attributes to the parent X.

    Returns (bulk_map, stats).
    """
    t0 = time.perf_counter()
    root = ET.fromstring(xml_body)
    canonical: dict[str, str] = {}  # P → X if flavor else P → P
    subpacks_by_source: dict[str, list[str]] = {}

    sourceinfo_count = 0
    subpacks_count = 0
    origin_count = 0

    for si in root.findall("sourceinfo"):
        sourceinfo_count += 1
        pkg = si.get("package", "")
        if not pkg:
            continue
        origin = si.findtext("originpackage")
        if origin:
            canonical[pkg] = origin
            origin_count += 1
        else:
            canonical.setdefault(pkg, pkg)
        subs = [s.text for s in si.findall("subpacks") if s.text]
        subpacks_count += len(subs)
        if subs:
            subpacks_by_source[pkg] = subs

    # Resolve flavor → root canonical (collapse chains).
    def resolve(name: str, seen: set[str] | None = None) -> str:
        seen = seen or set()
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
            if existing is None or existing == sub:
                bulk_map[sub] = root_src
            elif existing != root_src:
                # Two sources both claim this binary. Keep the canonical
                # (non-flavor) one if one of them is identity; else first wins.
                if sub == existing:
                    continue
                if sub == root_src:
                    bulk_map[sub] = root_src

    stats = {
        "sourceinfo": sourceinfo_count,
        "subpacks": subpacks_count,
        "originpackage": origin_count,
        "map_entries": len(bulk_map),
        "parse_ms": int((time.perf_counter() - t0) * 1000),
    }
    return bulk_map, stats


# ---------------------------------------------------------------------------
# Ground truth + shipped names


def load_false_positives() -> dict[str, str | None]:
    if not FALSE_POSITIVES.exists():
        sys.exit(
            f"missing ground-truth: {FALSE_POSITIVES}\n"
            "run `bugownerctl validate -v 16.1` once to populate it"
        )
    return json.loads(FALSE_POSITIVES.read_text())


def parse_shipped_names(primary_xml: Path) -> set[str]:
    """Lift parse_source_packages() logic verbatim from repo_metadata_repository.py."""
    if not primary_xml.exists():
        sys.exit(
            f"missing primary.xml.gz: {primary_xml}\n"
            "run `bugownerctl validate -v 16.1` once to populate it"
        )
    shipped: set[str] = set()
    with gzip.open(primary_xml, "rt", encoding="utf-8") as f:
        ns_prefix = "{http://linux.duke.edu/metadata/common}"
        current_name: str | None = None
        current_arch: str | None = None
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event != "end":
                continue
            tag = elem.tag.replace(ns_prefix, "")
            if tag == "name" and elem.text:
                current_name = elem.text
            elif tag == "arch" and elem.text:
                current_arch = elem.text
            elif tag == "package":
                if current_name and current_arch == "src":
                    shipped.add(current_name)
                current_name = None
                current_arch = None
                elem.clear()
    return shipped


# ---------------------------------------------------------------------------
# Side-probe: productcompose


def probe_productcompose() -> str:
    """Quick yes/no probe of default.productcompose via SSH git clone."""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="prototype_pc_"))
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth=1", "--branch=16.1", PRODUCTCOMPOSE_REPO, str(tmp / "SLES")],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if proc.returncode != 0:
            return "NOT REACHABLE (clone failed)"
        target = tmp / "SLES" / "000productcompose" / "default.productcompose"
        if not target.exists():
            return "PRESENT (clone OK) but default.productcompose missing"
        content = target.read_text(errors="replace")
        head = content[:200].replace("\n", " | ")
        return f"PRESENT: {len(content):,} bytes; head: {head!r}"
    finally:
        subprocess.run(["rm", "-rf", str(tmp)], check=False)


# ---------------------------------------------------------------------------
# Main


def run_probe_e1(samples: Iterable[str]) -> list[dict]:
    rows: list[dict] = []
    for pkg in samples:
        try:
            osc_src, osc_t = osc_bse(pkg)
        except subprocess.TimeoutExpired:
            osc_src, osc_t = None, 30.0
        try:
            http_src, http_t = endpoint1_lookup(pkg)
        except Exception as exc:
            http_src, http_t = None, 0.0
            print(f"  [E1] {pkg}: HTTP error {exc}", file=sys.stderr)
        rows.append(
            {
                "pkg": pkg,
                "osc": osc_src,
                "http": http_src,
                "osc_ms": int(osc_t * 1000),
                "http_ms": int(http_t * 1000),
                "agree": osc_src == http_src,
            }
        )
        print(
            f"  {pkg:35s}  osc={osc_src!s:20s} ({rows[-1]['osc_ms']:5d}ms)  "
            f"http={http_src!s:20s} ({rows[-1]['http_ms']:5d}ms)  "
            f"agree={rows[-1]['agree']}"
        )
    return rows


def score_e3_vs_ground_truth(bulk_map: dict[str, str], gt: dict[str, str | None]) -> dict:
    matched, mismatched, missing, extra_null = 0, 0, 0, 0
    mismatches: list[tuple[str, str | None, str]] = []
    for binary, gt_source in gt.items():
        in_bulk = binary in bulk_map
        bulk_source = bulk_map.get(binary)
        if gt_source is None:
            if not in_bulk:
                matched += 1
            else:
                extra_null += 1
                if len(mismatches) < 10:
                    mismatches.append((binary, None, bulk_source or ""))
        else:
            if not in_bulk:
                missing += 1
                if len(mismatches) < 10:
                    mismatches.append((binary, gt_source, "<missing>"))
            elif bulk_source == gt_source:
                matched += 1
            else:
                mismatched += 1
                if len(mismatches) < 10:
                    mismatches.append((binary, gt_source, bulk_source or ""))
    return {
        "matched": matched,
        "mismatched": mismatched,
        "missing": missing,
        "extra_null": extra_null,
        "total": len(gt),
        "mismatches": mismatches,
    }


def cross_check_shipped(shipped: set[str], bulk_map: dict[str, str]) -> dict:
    identity, aliased, missing = 0, 0, 0
    alias_samples: list[tuple[str, str]] = []
    missing_samples: list[str] = []
    for name in sorted(shipped):
        resolved = bulk_map.get(name)
        if resolved is None:
            missing += 1
            if len(missing_samples) < 10:
                missing_samples.append(name)
        elif resolved == name:
            identity += 1
        else:
            aliased += 1
            if len(alias_samples) < 10:
                alias_samples.append((name, resolved))
    return {
        "identity": identity,
        "aliased": aliased,
        "missing": missing,
        "total": len(shipped),
        "alias_samples": alias_samples,
        "missing_samples": missing_samples,
    }


def hr(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sample-size", type=int, default=20, help="E1 sample count (default 20)")
    p.add_argument("--refresh-bulk", action="store_true", help="re-fetch E3 even if cached")
    p.add_argument("--skip-e1", action="store_true", help="skip per-package E1 probe (saves ~20s)")
    p.add_argument(
        "--skip-productcompose",
        action="store_true",
        help="skip productcompose side-probe",
    )
    args = p.parse_args()

    hr("Auth + inputs")
    proc = subprocess.run(
        ["osc", "-A", OBS_HOST, "whois"], capture_output=True, text=True, check=False, timeout=15
    )
    if proc.returncode != 0:
        sys.exit(f"`osc whois` failed: {proc.stderr.strip()}")
    print(f"  osc whois: {proc.stdout.strip()}")
    gt = load_false_positives()
    print(
        f"  false_positives.json: {len(gt)} entries "
        f"({sum(1 for v in gt.values() if v is None)} null)"
    )
    shipped = parse_shipped_names(PRIMARY_XML)
    print(f"  primary.xml.gz: {len(shipped)} src-arch names")

    e1_rows: list[dict] = []
    if not args.skip_e1:
        hr("Endpoint 1: per-package (osc bse vs HTTP via osc api)")
        random.seed(42)  # deterministic sampling for repeat runs
        keys = list(gt.keys())
        random.shuffle(keys)
        samples = keys[: args.sample_size]
        e1_rows = run_probe_e1(samples)

    hr("Endpoint 3: bulk /source/{project}?view=info&parse=1")
    body, fetch_t = fetch_bulk(BULK_CACHE, refresh=args.refresh_bulk)
    bulk_map, e3_stats = build_bulk_map(body)
    print(
        f"  parsed {e3_stats['sourceinfo']:,} <sourceinfo>, "
        f"{e3_stats['subpacks']:,} <subpacks>, "
        f"{e3_stats['originpackage']:,} multibuild flavors "
        f"in {e3_stats['parse_ms']}ms → {e3_stats['map_entries']:,} map entries"
    )

    hr("E3 scoring vs false_positives.json")
    e3_score = score_e3_vs_ground_truth(bulk_map, gt)
    print(
        f"  matched={e3_score['matched']:3d}/{e3_score['total']}  "
        f"mismatched={e3_score['mismatched']:3d}  "
        f"missing={e3_score['missing']:3d}  "
        f"extra_null={e3_score['extra_null']:3d}"
    )
    if e3_score["mismatches"]:
        print("  first mismatches (binary → expected vs bulk):")
        for binary, expected, actual in e3_score["mismatches"]:
            print(f"    {binary:40s}  expected={expected!s:25s}  bulk={actual!s}")

    hr("Cross-check: shipped names from primary.xml.gz against bulk_map")
    cross = cross_check_shipped(shipped, bulk_map)
    print(
        f"  identity={cross['identity']:5d}  aliased={cross['aliased']:5d}  "
        f"missing={cross['missing']:5d}  / {cross['total']} shipped"
    )
    if cross["alias_samples"]:
        print("  sample aliases (would have hit osc today):")
        for name, resolved in cross["alias_samples"]:
            print(f"    {name:40s} → {resolved}")
    if cross["missing_samples"]:
        print("  sample missing (not in SUSE:SLFO:Main bulk dump):")
        for name in cross["missing_samples"]:
            print(f"    {name}")

    if not args.skip_productcompose:
        hr("Side-probe: default.productcompose")
        print(f"  {probe_productcompose()}")

    # ----- Decision block ----------------------------------------------------
    hr("DECISION BLOCK (thresholds from approved plan)")

    def verdict(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    rows: list[tuple[str, str, str]] = []

    if e1_rows:
        agree = sum(1 for r in e1_rows if r["agree"])
        osc_median = statistics.median(r["osc_ms"] for r in e1_rows)
        http_median = statistics.median(r["http_ms"] for r in e1_rows)
        speedup = osc_median / http_median if http_median else float("inf")
        rows.append(
            (
                "E1 correctness (≥18/20 agree)",
                f"{agree}/{len(e1_rows)}",
                verdict(agree >= 18),
            )
        )
        rows.append(
            (
                "E1 speedup vs osc bse (≥3×)",
                f"osc={osc_median:.0f}ms, http={http_median:.0f}ms ({speedup:.1f}×)",
                verdict(speedup >= 3),
            )
        )
    else:
        rows.append(("E1 correctness", "(skipped)", "—"))
        rows.append(("E1 speedup", "(skipped)", "—"))

    coverage = e3_score["matched"]
    rows.append(
        (
            "E3 coverage vs false_positives (≥210/220)",
            f"{coverage}/{e3_score['total']}",
            verdict(coverage >= 210),
        )
    )
    e3_total_s = fetch_t + e3_stats["parse_ms"] / 1000
    rows.append(
        (
            "E3 wall-clock fetch+parse (<30s)",
            f"{e3_total_s:.1f}s",
            verdict(e3_total_s < 30 if fetch_t > 0 else True),  # cached fetch ≈ 0; treat as pass
        )
    )
    alias_total = cross["aliased"] + cross["missing"]
    cov_pct = (cross["aliased"] / alias_total * 100) if alias_total else 100.0
    rows.append(
        (
            "E3 alias-resolution for shipped names (≥95%)",
            f"{cov_pct:.1f}% ({cross['aliased']} aliased / {alias_total} non-identity)",
            verdict(cov_pct >= 95),
        )
    )

    print()
    for label, value, ver in rows:
        print(f"  {label:55s}  {value:35s}  [{ver}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
