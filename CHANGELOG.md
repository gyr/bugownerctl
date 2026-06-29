# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.5.0] - 2026-06-29

### Changed

- **BREAKING:** Replaced the `validate` command with `check maintainership` and the
  `whitelist-check` command with `check whitelist`. The old top-level commands are removed
  with no aliases.

## [0.4.0] - 2026-06-26

### Fixed

- `query package` and `query maintainer` crashed with "No such file or directory" when invoked,
  because they resolved `_maintainership.json` and `whitelist_maintainership.json` from the
  current working directory instead of the cloned SLFO git repository. Both subcommands now
  resolve files from the SLFO repo path returned by `prepare_slfo_repo`, consistent with
  `validate` and `whitelist-check`.

### Changed

- **BREAKING**: `query package` and `query maintainer` now require `-v/--version`. They clone or
  update the SLFO git repository and can exit `1` on bad version (`ValueError`) or missing
  maintainership file (`FileNotFoundError`). Previously they always exited `0`. Optional
  `-c/--config` flag added (same semantics as `validate`/`whitelist-check`).

## [0.3.0] - 2026-06-26

### Added

- `--version` flag on the top-level `bugownerctl` command. Prints the installed version (derived from the git tag via `hatch-vcs`) and exits.

### Changed

- Version is now derived from git tags via `hatch-vcs`. The static `version =` field has been removed from `pyproject.toml`; tagging a commit is the only step needed to cut a release. Untagged commits get an automatic PEP 440 dev suffix (e.g. `0.2.0.dev3+gabcdef1`).
- **BREAKING**: Python distribution renamed `bugowner` → `bugownerctl`; console script renamed `bugowner` → `bugownerctl`; import path is now `bugownerctl.*`.
- **BREAKING**: env var `BUGOWNER_CONFIG` → `BUGOWNERCTL_CONFIG`.
- **BREAKING**: config search paths `~/.config/bugownership/` & `/etc/bugownership/` → `~/.config/bugownerctl/` & `/etc/bugownerctl/`; default cache dir `~/.cache/bugownership` → `~/.cache/bugownerctl`.

### Migration

- `mv ~/.config/bugownership ~/.config/bugownerctl`; `mv ~/.cache/bugownership ~/.cache/bugownerctl`; replace `BUGOWNER_CONFIG` with `BUGOWNERCTL_CONFIG` in env files; uninstall old `bugowner`, install `bugownerctl`. No compatibility shim is provided.

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
