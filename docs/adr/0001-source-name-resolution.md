# ADR 0001 — Source-name resolution: bulk OBS fetch + committed overrides

**Status:** Accepted (2026-06-08)
**Supersedes:** the per-package `osc bse` fan-out + auto-mutating `false_positives.json` cache.

## Context

`bugowner validate` checks that every binary package shipped in the SLES repository has a corresponding source-package entry in the SLFO submodules. Binary and source names diverge often (`apache2-devel` → `apache2`, `kernel-azure` → `kernel-source-azure`), so the validator needs a binary-name → source-name map.

The previous resolver had two layers:

1. **Per-package `osc bse <name>` subprocess calls**, fanned out across ~10 worker threads. ~2 s per call. Typical run: 200+ unmatched names → ~40+ s of subprocess wall-time, plus OBS load.
2. **`~/.cache/bugownership/false_positives.json`**, a write-back cache populated by the OBS results. On first run it was bootstrapped from a bundled seed file (`false_positives.seed.json`). On every subsequent run, new OBS lookups appended to it.

Both layers had problems that surfaced during a validation-output investigation in June 2026.

### Problems with `osc bse` fan-out

- **Latency.** Observed during development: ~2 s per `osc bse` call, ~10 worker threads (`obs_repository.py:165` in the pre-refactor tree, `e9a7f67~1`), 200+ unmatched names per typical run → ~40 s of subprocess wall-time before the validator could even begin. Numbers are observed-during-development, not formal benchmarks.
- **OBS rate-pressure.** N parallel `osc` invocations each opened a fresh authenticated HTTP session. The bulk endpoint `/source/SUSE:SLFO:Main?view=info&parse=1` returns the equivalent data in **one** request.
- **No cacheability across runs.** Each `osc bse` result was stored in the false-positives cache, but only after the slow round-trip — the first cold run paid the full cost.

### Problems with the auto-mutating cache

- **Silent shadowing.** A stale or wrong cache entry would silently shadow a real bug. If `pkg-foo` was once cached as mapping to `null` (treat as not-shipped), no later validation run would ever flag `pkg-foo` again, even after it became a real shipping package.
- **No review path.** Cache entries were written without human review. Nothing in the commit history reflected what the resolver knew.
- **Confusing UX.** Users saw runs print "Discovered N new binary→source mappings" with no way to inspect, audit, or revert what had just been added.
- **Concurrency hazards.** Two `bugowner validate` invocations in parallel could race on the cache file (mitigated by atomic temp+rename, but the underlying read-modify-write loop was still wrong).

## Decision

**Replace both layers with:**

1. **One bulk OBS fetch per cache-miss run** (`osc api /source/<project>?view=info&parse=1`), parsed into a binary → source mapping. The XML body is cached at `{cache_dir}/obs_bulk_map.xml` with a sidecar `obs_bulk_map.meta.json` containing `{project, fetched_at, sha256}`. Filenames are constant — switching projects triggers a re-fetch via the meta `project` cross-check, not a per-project filename. Cache hits: re-parse the local XML, no network. Three independent gates (project match, ≤7-day TTL, SHA-256 integrity over the XML body) must all pass; any failure degrades to a fresh fetch.
2. **A hand-curated overrides file** shipped in the wheel at `bugowner/data/false_positives_overrides.json`. Schema unchanged from the legacy cache (`{"binary": "source" | null}`). Read-only at runtime, edited via PR.

The resolver pipeline becomes: **overrides → bulk_map → identity fallthrough → residue**.

## Rationale

### Why bulk fetch over per-package

- **One subprocess vs N.** Cold-run subprocess time goes from ~40 s of fan-out to ~26 s of a single `osc api` call (same source: observed during development, June 2026, against `api.suse.de`). Warm runs are ~0 s — the local XML re-parse is microseconds.
- **OBS-friendly.** One authenticated request instead of N parallel ones.
- **Defensive parsing.** `xml.etree.ElementTree.findall` over relative XPaths tolerates missing `<originpackage>` and other schema drift. Parse failure logs a body snippet at WARN and falls back to "empty bulk map" — loud, not silent.

### Why committed overrides over auto-cache

- **Diff-reviewable.** Every entry in the overrides file is a line in `git log -p`. No more "where did this entry come from?".
- **No silent shadowing.** Stale overrides surface in code review; stale caches don't.
- **Schema-compatible migration.** Same JSON shape as the legacy cache — `kernel-azure: kernel-source-azure` survives the cut without a transform.
- **Wheel-resident, not config.** Overrides ship with the code that depends on them. There is no "first-run bootstrap" step, no `bugowner init` for overrides, and no on-disk file to deploy.

### Why `osc api` subprocess over direct `requests`

- **Auth.** OBS at `api.suse.de` requires either a logged-in `osc` session or an SSH-signed token. The `osc` CLI already handles both. Re-implementing signature handling in Python (via `requests` + `ssh-agent` bridging) duplicates non-trivial security-sensitive code.
- **Operator parity.** When the resolver mis-behaves, the operator can reproduce the fetch byte-for-byte with `osc api /source/SUSE:SLFO:Main?view=info&parse=1`. Direct `requests` calls would diverge from that and complicate debugging.
- **Subprocess cost is amortized.** One `osc` invocation per cold run is fine; the cost that mattered was N invocations, not one.

## Consequences

### Positive

- Cold run drops ~40 s of subprocess time. Warm run: ~0 s, no network.
- All resolver state is either fetched fresh (bulk map, with cache + TTL + integrity) or version-controlled (overrides). No more "what's in my home cache?" mystery.
- The CLI output now distinguishes "shipped but resolved to a non-submodule name" (full residue) from "shipped and could not be resolved at all" (`unresolved_names`, strict subset). Reviewers can act on the smaller set first.

### Negative

- **Breaking change for any user with custom `false_positives.json`.** That file is no longer read or written. Custom mappings must be ported into `false_positives_overrides.json` via PR. The `~/.cache/bugownership/false_positives.json` file on disk is unaffected but irrelevant; users can `rm` it.
- **Slower first-time UX for new override needs.** Previously, the resolver would auto-discover a mapping on first sight. Now a PR is required. This is the intended tradeoff — the silent shadowing was the bigger problem.
- **Overrides are coupled to the bugowner release cycle.** A new override needs a new wheel — and for downstream consumers installing via a VCS-pinned URL (`pip install git+...@tag`), the same constraint applies at the commit/tag level: their dependency-bump cycle gates the override. Acceptable because (a) the overrides set churns rarely (one entry at cut-over) and (b) the alternative — a per-user file — would re-introduce silent shadowing.

## Alternatives considered

- **Per-user committed overrides file under `~/.config/bugownership/`.** Rejected: reintroduces "what's in my home dir?" opacity, no diff trail.
- **Overrides committed inside the SLFO repo.** Initially planned and reversed during Phase 3: the SLFO repo is a Git submodule managed by a different team, and gating overrides on their review path would slow iteration. Shipping in the bugowner wheel keeps overrides with the resolver code that interprets them.
- **Keep the cache, add invalidation TTL only.** Rejected: TTL fixes staleness on the time axis but not on the correctness axis. A wrong entry within its TTL still shadows.
- **Rename overrides file to `.example.json`.** Rejected: the file ships with real entries (`kernel-azure`), not as a template to copy. The `.example` suffix would mis-signal intent.

## References

- `src/bugownerctl/repositories/obs_bulk_source_info_repository.py` — bulk fetch + cache implementation.
- `src/bugownerctl/repositories/name_overrides_repository.py` — overrides loader.
- `src/bugownerctl/services/validation_service.py` (`find_shipped_without_submodule`) — pipeline assembly point.
- `CHANGELOG.md` — user-facing migration notes.
- Git history `e9a7f67~6..e9a7f67` — the six rollout commits (domain → bulk repo → overrides repo → parallel-path pipeline → service cut-over → legacy deletion).
