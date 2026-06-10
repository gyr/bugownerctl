# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-06-10

### Added

- `--refresh-bulk-map` flag on both `validate` and `whitelist-check` subcommands. Bypasses the 7-day on-disk OBS bulk-source-info cache and forces an immediate re-fetch from the OBS API. Useful after an OBS project restructure or when you know the cached map is stale.

### Fixed

- `whitelist-check` verdict line ("No inconsistencies found." / "Found N inconsistent packages") is now the final output line, printed after the "Names with no source mapping" diagnostic block. Previously the verdict was buried mid-output on the new pipeline because the diagnostic block came after it. (`src/bugowner/commands/whitelist.py`)

### Changed

- **Breaking.** Source-name resolution rewritten. The per-package `osc bse` subprocess fan-out and the auto-mutating `~/.cache/bugownership/false_positives.json` cache are removed. They are replaced by:
  - one bulk OBS source-info fetch per cold run (`osc api /source/<project>?view=info&parse=1`), cached at `{cache_dir}/obs_bulk_map.xml` plus a `obs_bulk_map.meta.json` sidecar, with a 7-day TTL and SHA-256 integrity check;
  - a hand-curated overrides file shipped in the wheel at `bugowner/data/false_positives_overrides.json`, edited via PR.

  Resolver pipeline is now `overrides → bulk_map → identity fallthrough → residue`. See `docs/adr/0001-source-name-resolution.md`.

- CLI output for `validate` and `whitelist-check` now distinguishes two sets: `shipped_not_in_submodule` (full residue) and `unresolved_names` (strict subset — names that fell through to identity AND aren't a submodule). A new "Names with no source mapping" block surfaces the smaller set so reviewers can decide whether to add an override.

### Removed

- `~/.cache/bugownership/false_positives.json` runtime cache (no longer read or written). Any leftover file from a previous version is harmless and can be deleted with `rm ~/.cache/bugownership/false_positives.json`.
- `src/bugowner/data/false_positives.seed.json` bundled seed file.
- `false_positives_seed` config key (silently ignored if still present in user configs).
- Internal: `ObsRepository`, `ObsRepositoryImpl`, `FalsePositivesRepository`, `FalsePositivesRepositoryImpl`, `bugowner.utils.seed`.

### Migration

If you maintained custom entries in `~/.cache/bugownership/false_positives.json`, port **only the ones that disagree with the OBS bulk map** into `src/bugowner/data/false_positives_overrides.json` via a PR against this repo. Wholesale-porting the entire cache re-introduces the silent-shadowing failure mode the refactor exists to fix: most of the cache entries simply mirrored what `osc bse` returned, which the bulk map now resolves correctly without an override.

How to find the entries that actually need overriding:

1. Run `bugowner validate -v <ver>` against the new version.
2. Inspect the new **"Names with no source mapping"** block in the output — those are names that fell through to identity-fallthrough but aren't a submodule. They are candidates for an override entry (or for a real submodule fix).
3. For names in your old cache that **are** still flagged, add them. For names in your old cache that **don't** appear in the new output, the bulk map handles them — drop them.

The schema is unchanged (`{"binary_or_subpkg_name": "source_pkg_name" | null}`); `null` still means "treat as not-shipped, do not flag".
