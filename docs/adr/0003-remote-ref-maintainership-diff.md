# ADR 0003 — Maintainership diff across git refs: in-memory `git archive --remote`

**Status:** Accepted (2026-09-11)
**Scope:** the `bugownerctl diff maintainership` subcommand only. No existing command changes behaviour.

## Context

Release engineering needs to answer "how did package maintainership change between two SLFO refs?" — typically `slfo-main` versus a released branch such as `slfo-1.3`. The answer is read by humans and pasted into spreadsheets, so the output is CSV.

`_maintainership.json` lives in the SLFO git repository at `gitea@src.suse.de:products/SLFO.git`. Every existing bugownerctl subcommand that reads it goes through `prepare_slfo_repo` (`commands/repo_prep.py:37,88`), which resolves a *product version* from config and clones or updates a working copy under `{cache_dir}`. That path is a poor fit here for two independent reasons:

- **It is keyed on product version, not on ref.** `prepare_slfo_repo` requires a `version` that maps to a `products:` entry. A diff addresses two arbitrary refs, most of which have no product entry at all.
- **It needs a checkout on disk.** Two refs means either two clones, or one clone checked out twice in sequence — and a clone of SLFO is far larger than the single 40 KB file we actually want.

A stale local clone is not a theoretical hazard: during design, a clone that had not been fetched reported **7** differing packages where the live remote reports **8**.

## Decision

**Fetch the file directly from the remote with `git archive --remote`, in memory, per ref. No clone, no temp file, no checkout.**

```
git archive --remote=<slfo_git_url> <ref> -- <maintainership_file>
```

The tar that comes back (~307 KB) is read with stdlib `tarfile` over an `io.BytesIO`, exactly one regular member is extracted, and that member is parsed with stdlib `json`. Measured **~1.0 s per ref**; peak memory is two ~300 KB tars plus two parsed dicts of 2977 entries — a few MB.

Supporting decisions, each settled by measurement rather than preference:

- **`REF_A`/`REF_B` are branch or tag names.** Commit SHAs are not supported.
- **A new `RemoteArchiveRepository` module**, not a method on the existing `GitRepositoryImpl`.
- **The snapshot parser is a second, deliberately divergent normalization**, not a reuse of `MaintainershipRepositoryImpl.load`.
- **SSH is the intended transport.** The Gitea HTTP API is not used. `GIT_ALLOW_PROTOCOL` permits `ssh:https:http:git:file`, so a differently-configured `slfo_git_url` still works; nothing here enforces SSH beyond the default remote being an SSH URL.
- **No `-r/--release`.** The subcommand takes a config-only parent parser.

## Rationale

### Why SHAs cannot be supported

`git archive --remote` **fails** for a short SHA and for a full SHA: the process exits 1 with no stdout and `remote: fatal: no such ref: <sha>` on stderr. Only `slfo-1.3`, `refs/heads/slfo-1.3` and `HEAD` succeed. This is the upload-archive protocol's behaviour, not a client limitation, so it cannot be worked around short of cloning — which is the thing this design exists to avoid. The peeled form `slfo-1.3^{}` never reaches the server at all: `^` and `{}` fall outside the ref allowlist and `_validate_ref` (`remote_archive_repository.py:71`) rejects it locally.

The command performs **no client-side SHA regex check** — the allowlist above rejects only characters that are not valid in a ref at all, never a well-formed ref on the grounds that it looks like a SHA. A repository may legitimately hold a branch named `abcdef1`, and rejecting it locally would be wrong where the server would have answered. Instead the server's rejection is caught and the hint is appended to the error message (`remote_archive_repository.py:214-219`), which the CLI maps to exit 64.

### Why a separate repository module rather than `GitRepositoryImpl.fetch_archive()`

`GitRepositoryImpl._run_git_command` (`git_repository.py:133-139`) hardcodes `text=True`, and `git archive` output is a binary tar. Reuse would require one of:

- Threading a `text: bool` parameter through `_run_git_command` — changing a signature on the `clone_or_update` path that all five existing subcommands execute and that `tests/test_git_repository.py` pins.
- Adding a *second* private runner to the same class, giving one class two subprocess idioms and two irreconcilable error policies: `check=True` → `RuntimeError` on any non-zero, versus this feature's mapping in which rc=1 means four different things.

The second is also a Liskov problem. `GitRepository`'s contract says git failures surface as `RuntimeError`, while `fetch_file` must surface ref-not-found as a `ValueError` so the CLI maps it to exit 64. A separate module modifies **zero** existing production files.

### Why the normalization diverges from `MaintainershipRepositoryImpl.load`

`load` (`maintainership_repository.py:89,115`) takes a `Path`, opens the file itself, and returns untagged `list[str]` maintainers formed by concatenating `users + groups`. `parse_tagged_snapshot` takes `bytes` — the document never touches the filesystem — and tags group-sourced names with a `group:` prefix, because a diff must be able to tell a user from a like-named group.

No single signature serves both callers. Changing `load()` to match would break `check` and `query`, which depend on its current contract. The duplication is therefore deliberate: `parse_tagged_snapshot` carries a cross-reference comment naming `load` and explaining why it does not reuse it, and the divergence is pinned by a test. The reference is one-directional — `maintainership_repository.py` is not edited, because this feature modifies no existing production file but `cli.py`.

A caveat that belongs on the record: the `group:` prefix reflects **which JSON list a name came from**, not whether the name is genuinely a group. At least one group name sits in the `users` list on `slfo-main`, so it renders untagged there and tagged elsewhere. That is a data bug in SLFO, not in this tool, and the diff faithfully reports it.

### Why not the Gitea raw HTTP API

Measured against `src.suse.de`: the anonymous raw endpoint returns **303** redirecting to the login page, and the API returns **403**. Gitea's raw endpoint on a private repository requires a token or a session cookie. Adopting it would force a credential-management surface that bugownerctl deliberately lacks — the tool authenticates with the operator's existing SSH key and stores no tokens, matching how `check` and `query` already reach SLFO.

### Why comparison is set-based

The maintainer set of a package is `users` merged with `groups`. Comparison is set-based, so reordering inside the source document never produces a row; verified that **0** ordering-only differences exist today. A row is emitted only when the sets differ or the package exists in exactly one ref. The top-level `project` key is not compared.

Cells join names with a single space, sorted alphabetically. All 214 maintainer names in the current data match `[A-Za-z0-9._-]+`, so the space separator is collision-safe. No CSV formula-injection escaping is applied, for the same reason: no current name begins with a character a spreadsheet would treat as a formula.

### Subprocess hardening

`stdin=subprocess.DEVNULL` plus `GIT_TERMINAL_PROMPT=0` make an unauthenticated remote fail fast rather than block on a credential prompt. `ssh -o BatchMode=yes` is deliberately **not** set: BatchMode also refuses passphrase prompts, which would break passphrase-protected keys that are not already loaded into an ssh-agent.

`GIT_ALLOW_PROTOCOL` is pinned, the subprocess carries `timeout=60`, and the archive is capped at 32 MiB before extraction. Extraction reads exactly one regular member and **never calls `extractall`**.

## Consequences

### Positive

- **Always current.** Reading the remote directly removes the stale-clone failure mode that produced a wrong answer (7 rows instead of 8) during design.
- **Cheap.** ~1 s and a few MB per ref, against a clone of the whole SLFO tree.
- **Zero blast radius.** The feature adds `repositories/remote_archive_repository.py`, `services/maintainership_diff_service.py`, `domain/maintainership_diff.py` and `commands/diff.py`. The only existing production file it touches is `cli.py`, and only to register the subparser.
- **No new exception types.** Operator input errors raise `ValueError` → exit 64; malformed remote payloads raise `RuntimeError` → exit 1; the existing `MissingBinaryError` → 127 and `NetworkTimeoutError` → 124 are reused unchanged.

### Negative

- **Network and working credentials for the remote are required on every run** — an SSH key, for the default `gitea@src.suse.de` URL. There is no offline mode and no cache. Acceptable: the command is interactive and infrequent, and caching would reintroduce the staleness this design removes.
- **Commit SHAs cannot be diffed.** Protocol-imposed, documented in `--help` on both ref arguments and in the ref-not-found error.
- **The maintainership document is parsed twice in the codebase**, by two functions with different contracts. Mitigated by a cross-reference comment on the new parser and a divergence test, but the older `load` has no comment pointing back, so a reader arriving there will not learn of the second parser. A candidate for consolidation only if the shared library in [ADR 0002](0002-shared-slfo-ecosystem.md) is built.
- **Server error strings are matched to classify failures.** `remote: fatal: no such ref:` and `did not match any files` are gettext-translated on the remote, so a non-English server falls through to the generic `RuntimeError` branch. The operator still sees the raw stderr; forcing `LC_ALL=C` would not help, because the locale that matters is the remote's.

## Alternatives considered

- **Clone or update a working copy per ref (the `prepare_slfo_repo` path).** Rejected: keyed on product version rather than ref, needs a full checkout for one 40 KB file, and carries the stale-clone hazard measured above.
- **`git archive --remote` into a temp file, then read it.** Rejected: adds a filesystem lifetime and a cleanup path for data that fits comfortably in memory.
- **A `fetch_archive()` method on `GitRepositoryImpl`.** Rejected on the `text=True` incompatibility and the error-policy conflict argued above.
- **Gitea raw HTTP / API.** Rejected on the measured 303/403 and the credential surface it would add.
- **Rejecting SHA-shaped refs client-side.** Rejected: would wrongly reject a real branch named `abcdef1`. The server's own rejection carries the hint instead.
- **A `-r/--release` flag for symmetry with the other data subcommands.** Rejected: there is no product version to resolve. `cli.py`'s shared `context` parser hard-requires `-r`, so `diff maintainership` takes a new `config_only` parent carrying `-c/--config` alone.

## References

- `src/bugownerctl/repositories/remote_archive_repository.py` — transport, ref validation, single-member tar extraction.
- `src/bugownerctl/services/maintainership_diff_service.py` — `parse_tagged_snapshot`, `diff_snapshots`.
- `src/bugownerctl/domain/maintainership_diff.py` — `MaintainershipDiffRow`.
- `src/bugownerctl/commands/diff.py` — handler and CSV rendering.
- `src/bugownerctl/repositories/maintainership_repository.py` (`load`) — the divergent normalization this one deliberately does not reuse.
- [ADR 0002](0002-shared-slfo-ecosystem.md) — the shared-library proposal in which the two parsers might one day converge.
- `README.md` — user-facing documentation of the subcommand.
