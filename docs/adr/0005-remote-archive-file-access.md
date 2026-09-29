# ADR 0005 — SLFO files via `git archive --remote` for every command; no clone

**Status:** Accepted (2026-09-29)
**Amends:** [ADR 0003](0003-remote-ref-maintainership-diff.md) — its transport, until now limited to `diff maintainership`, becomes the only way any command reads SLFO files.
**Scope:** `check maintainership`, `check whitelist`, `check users`, `query package`, `query maintainer`.

## Context

Every `check` and `query` subcommand went through `prepare_slfo_repo`, which cloned or updated the SLFO repository under `{cache_dir}/SLFO` and checked out the product's `branch` or `commit`. The clone served two purposes:

1. the git submodule list, used as the package universe by `check maintainership` and `check whitelist`;
2. two JSON files in the repository root, `maintainership_file` and `whitelist_file`.

[ADR 0004](0004-per-release-obs-package-universe.md) replaced the submodule list with the OBS project's package set, which leaves only the two files. ADR 0003 had already shown that `git archive --remote` fetches one such file in memory in about a second, while a clone costs far more and goes stale between fetches. It had also measured that the upload-archive protocol serves branch and tag names only — never a commit SHA.

## Decision

1. **No clone.** `prepare_slfo_repo` becomes `resolve_product_context` (module `commands/product_context.py`, dataclass `ProductContext`). It only resolves config — `cache_dir`, `slfo_git_url`, `ref`, `base_url`, `obs_project` — and creates nothing on disk. `{cache_dir}` still holds the `primary.xml.gz` cache.
2. **Every command fetches its files with `RemoteArchiveRepositoryImpl.fetch_file`**, the same adapter `diff maintainership` uses, at the product's branch, and the loaders parse `bytes` instead of reading a `Path`.
3. **`branch:` is required; `commit:` pins are rejected** with a `ConfigError` (exit 64) that says why. Tag names pass the same ref validation but are unverified against `src.suse.de`.
4. **File names are repository-root names.** `fetch_file` rejects any `/`, because `git archive` emits a directory member per path component and the extraction accepts exactly one member. This replaces the clone-era `validate_file_within_directory` check, which allowed subdirectories.
5. **A missing file is an operator error (exit 64)**, raised as `FileNotFoundAtRefError` (a `ValueError`) when the server reports `did not match any files`. `query package` catches only that error on the whitelist and treats the whitelist as empty, because `slfo-1.2` has no whitelist file; `check whitelist` fails.
6. **URL checks move into context resolution.** The SSH/HTTP(S) format check and the SSRF check for HTTP(S) URLs, formerly run only inside the clone, now run in `resolve_product_context` with the same rules and messages.

## Rationale

- **One file needs one fetch.** With the submodules gone, a clone downloads the whole SLFO tree to read two small files.
- **Always current.** ADR 0003 measured a stale clone giving a wrong answer; reading the remote on every run removes that failure mode for `check` and `query` too.
- **One transport, one set of guards.** `fetch_file` already carries the protocol allowlist, ref validation, size caps, timeout and single-member extraction; reusing it removes the clone path's separate subprocess and error policy (`GitRepositoryImpl`, `RefType`, `validate_file_within_directory` are deleted).
- **Rejecting `commit:` up front** turns a guaranteed remote failure into a config error that names the fix.

## Consequences

### Positive

- No `{cache_dir}/SLFO` clone to create, update, disk-budget or repair.
- `check`, `query` and `diff` share one code path to SLFO.
- Loaders take `bytes`, so no temp file ever exists.

### Negative

- **Breaking config.** `commit:` pins must become `branch:`; `maintainership_file` / `whitelist_file` values with a subdirectory are rejected.
- **Network and credentials on every run** for `slfo_git_url` — an SSH key for the default `gitea@src.suse.de` remote. No offline mode.
- **A pinned, reproducible snapshot is no longer possible.** A branch moves; a tag is the closest substitute and is unverified on `src.suse.de`.
- **Server error strings are still matched** (`no such ref`, `did not match any files`); a non-English remote falls through to the generic `RuntimeError` (exit 1), as ADR 0003 recorded.
- **Leftover `{cache_dir}/SLFO`** from earlier versions is not removed automatically.

## Alternatives considered

- **Keep the clone for the two files.** Rejected: whole-tree cost and the stale-clone hazard for data that fits in one ~1 s fetch.
- **Gitea raw HTTP API.** Rejected in ADR 0003 (login redirect / 403 on a private repository; would add token handling).
- **Allow subdirectories by accepting directory members in the tar.** Rejected: both files live in the repository root; widening the extraction contract for an unused case is speculative.
- **Resolve `commit:` pins by cloning only when one is present.** Rejected: keeps the whole clone path alive for one config shape.

## References

- `src/bugownerctl/commands/product_context.py` — `resolve_product_context`, URL checks.
- `src/bugownerctl/repositories/remote_archive_repository.py` — `fetch_file`, `FileNotFoundAtRefError`.
- `src/bugownerctl/commands/check.py`, `src/bugownerctl/commands/query.py` — callers.
- [ADR 0003](0003-remote-ref-maintainership-diff.md) — the transport and its measurements.
- `CHANGELOG.md` — user-facing breaking notes.
