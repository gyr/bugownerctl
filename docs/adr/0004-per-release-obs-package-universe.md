# ADR 0004 — Per-release OBS project as the package universe, fetched every run

**Status:** Accepted (2026-09-29)
**Partially supersedes:** [ADR 0001](0001-source-name-resolution.md) — its on-disk cache of the OBS source info, and the SLFO git submodules as the set shipped names are checked against. The overrides file and the resolver pipeline order stand.
**Scope:** `check maintainership` and `check whitelist`.

## Context

`check maintainership` and `check whitelist` turn shipped binary names (from the product's `primary.xml.gz`) into source package names via `osc api /source/<project>?view=info&parse=1`, then compare them with a package universe. Until this change that universe was the set of **git submodules** of a local SLFO clone. Investigation on 2026-09-28 found three problems:

- **Wrong project for most releases.** The OBS project was hardcoded to `SUSE:SLFO:Main` in the validation and whitelist services, and the check command never passed another one. 16.0 and 16.1 were resolved against the development project rather than the one that builds their branch.
- **Submodules were a stand-in.** Each SLFO branch is built by its own OBS project (`slfo-1.2` → `SUSE:SLFO:1.2`, `slfo-1.3` → `SUSE:SLFO:1.3`, `slfo-main` → `SUSE:SLFO:Main`). Measured on `slfo-main`: every package of `SUSE:SLFO:Main` is a submodule of `origin/slfo-main`, so the OBS project carries the same package list plus multibuild information. Submodules were used only because the bulk source-info endpoint was not known when the check was written.
- **The cache could not be validated.** ADR 0001 cached the source-info reply for 7 days. The OBS API spec (v2.10.50) documents no project-level change marker or ETag, so a cache hit could be stale for up to a week with no cheap way to tell.

## Decision

1. **Each product names its OBS project.** A per-product `obs_project` config key; `check maintainership` and `check whitelist` fail with a `ConfigError` (exit 64) when it is missing. No default: a wrong default is how the original bug hid.
2. **The OBS project's package set is the universe.** It is the `package` attribute of every `<sourceinfo>` in the reply, except names containing `:`. Those are multibuild flavors (`pkg:flavor`); measured on `SUSE:SLFO:Main`, a `:` in the name coincides exactly with an `<originpackage>` child (0 exceptions in 4257 entries). The set and the binary → source mapping come from one parse of one reply.
3. **No cache.** The source info is fetched on every run and parsed in memory. The `--refresh-bulk-map` flag, the `{cache_dir}/obs_bulk_map.*` files and their TTL, SHA-256 and permission handling are removed.
4. **Off-happy-path replies stop the run** with two distinct errors (exit 1), so the operator can tell them apart: a root other than `<sourceinfolist>` ("is not a package list", with the OBS `<summary>` when present), and a `<sourceinfolist>` with no entries ("lists no packages; check 'obs_project' in your config").
5. **A `<sourceinfo>` carrying `<error>` stays in the set.** The package exists in the project even if its build configuration is broken; a warning names the package and the error text.
6. **Names are whitespace-stripped** wherever the parser reads them (`package`, `<originpackage>`, `<subpacks>`), in both the set and the mapping, so `" bash "` never differs from `"bash"`.
7. **`check maintainership` prints three totals** — shipped source packages, packages in the OBS project, maintained packages — ahead of its findings.

Findings are renamed to match: `maintained_packages_not_in_obs` and `shipped_not_in_obs`, printed as "… not in OBS project `<X>`".

## Rationale

- **Source of truth.** The OBS project is what actually builds the release. Submodules were a proxy for it, and a proxy tied to a single clone and branch.
- **Per release, not per repository.** Resolving against the project that builds the product's branch is what makes the result correct for 16.0 and 16.1.
- **Correct over fast.** Without a change marker, the only safe cache is none. One `osc api` call per run is the price; it was already paid on every cache miss.
- **Distinct errors, then counts.** An auth error page or a misspelled project would otherwise yield an empty set and a report full of false findings. The two guards catch the common cases; beyond that, the three totals make an odd reply visible to the operator instead of adding guards for hypothetical malformed replies.

## Consequences

### Positive

- 16.0 and 16.1 are checked against their own package universe.
- `check maintainership` and `check whitelist` no longer need the SLFO submodule list, which removes their last reason to clone (see [ADR 0005](0005-remote-archive-file-access.md)).
- No cache state to go stale, corrupt or clean up.

### Negative

- **Breaking config and output.** Every product used with `check` needs `obs_project`; scripts matching the old "submodule" output lines must be updated. Exit-code values are unchanged, but gate contents change for 16.0, 16.1 and `--strict`.
- **OBS access on every run.** No offline mode; each run pays the full source-info fetch.
- **The operator keeps the branch ↔ project pairing right.** Nothing checks that `obs_project` builds the configured `branch`; a mismatch shows up only in the totals and findings.

## Alternatives considered

- **Keep the submodules as the universe.** Rejected: on `slfo-main` every OBS package is already a submodule, so the submodules add nothing but the need for a clone, and they carry no flavor information.
- **Derive the project from the branch name.** Rejected: the mapping is a naming convention, not a contract; an explicit key fails loudly instead of guessing.
- **Keep the cache with a shorter TTL.** Rejected: without a change marker, any TTL still serves stale data within its window.
- **Keep `SUSE:SLFO:Main` as a default.** Rejected: a silent default caused the bug this ADR fixes.

## References

- `src/bugownerctl/repositories/obs_source_info_repository.py` — fetch, guards, package set and mapping.
- `src/bugownerctl/domain/obs_source_info.py` — `ObsSourceInfo`.
- `src/bugownerctl/services/validation_service.py` (`validate_all`, `resolve_shipped_packages`, `find_maintained_packages_not_in_obs`) — comparison against the package set.
- `src/bugownerctl/commands/product_context.py` (`_resolve_obs_project`) — config validation.
- `CHANGELOG.md` — user-facing breaking notes.
