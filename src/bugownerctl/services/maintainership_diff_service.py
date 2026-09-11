"""Parsing and diffing of maintainership snapshots taken at git refs."""

import json
import logging

from ..domain.maintainership_diff import MaintainershipDiffRow

logger = logging.getLogger(__name__)


def _ambiguity_reason(name: str, from_users: bool) -> str | None:
    """Classify how a raw maintainer name would render ambiguously in a CSV cell.

    There are three classes. Two are rendering defects: `commands/diff.py` joins
    a maintainer set into one cell with a space, so a name holding whitespace
    splits into what looks like several names, and an empty name contributes an
    invisible token. The third is data loss: the `group:` tag applied here is
    not a reserved prefix, so a user literally named `group:x` tags to the same
    string as a group named `x` and the two collapse into one set member.

    The name is the raw one, as read from the document, never the tagged one. An
    empty group name tags to the non-empty `group:`, so testing the tagged
    string for emptiness would miss it. The `group:` test is confined to
    users-sourced names by `from_users`: a group's own tag starts with `group:`
    by construction, so a rule that saw only the tagged name would have to match
    every group in the document.

    Whitespace is tested per character rather than as `" " in name`, so a tab, a
    newline or a no-break space is caught too.

    Args:
        name: Raw maintainer name, before the `group:` prefix is applied.
        from_users: True when the name came from the `users` list.

    Returns:
        A reason phrase for the warning, or None when the name is unambiguous.

        At most one reason is returned. The order is not arbitrary: emptiness is
        disjoint from the other two and comes first only for readability, but
        the `group:` collapse deliberately outranks whitespace. A collapse is
        the only class that loses information from the returned snapshot — two
        distinct maintainers become one member and no later stage can recover
        them — whereas whitespace merely makes a cell hard to read. Whitespace
        also stays visible to the operator in the `!r`-quoted name carried by
        the collapse message, so reporting the collapse costs nothing, while
        reporting the whitespace would hide the collapse entirely.
    """
    if not name:
        return "it comes from an empty name, so it identifies no maintainer"
    if from_users and name.startswith("group:"):
        return "a user name starting with 'group:' renders identically to a group"
    if any(character.isspace() for character in name):
        return "it holds whitespace, and maintainer cells join names with a space"
    return None


def parse_tagged_snapshot(payload: bytes, ref: str) -> dict[str, frozenset[str]]:
    """Parse a `_maintainership.json` payload into tagged maintainer sets.

    The maintainer set of a package is its `users` entries plus its `groups`
    entries, each group name prefixed with `group:` so that a user and a group
    sharing a name stay distinguishable. A missing `users` or `groups` key, or
    one whose value is JSON null, contributes nothing. The top-level `project`
    key is ignored.

    The payload comes from a remote git ref and is untrusted, so every value
    read from the parsed document is narrowed before use.

    A name that `commands/diff.py` cannot render unambiguously into a maintainer
    cell — see `_ambiguity_reason` for the three classes — is warned about once
    per tagged name per call, naming the package it was first seen in. This is a
    diagnostic only: no name is dropped or rewritten, and the returned mapping is
    the same with the warnings as without them.

    Note: this normalization deliberately differs from
    `MaintainershipRepositoryImpl.load` in
    `src/bugownerctl/repositories/maintainership_repository.py`, which takes a
    `Path`, opens the file itself, and returns untagged `list[str]` maintainers
    (`users + groups` concatenated). The duplication is correct: no single
    signature serves both callers. This function must take `bytes` because the
    document never touches the filesystem, and it must tag by source list
    because a diff has to tell a user from a like-named group. Changing
    `load()` to match would break the `check` and `query` commands, which
    depend on its current contract.

    Args:
        payload: Raw bytes of a `_maintainership.json` document.
        ref: Git ref the payload was read from. Used only to name the source in
            warnings.

    Returns:
        Mapping of package name to the frozenset of its tagged maintainers.

    Raises:
        RuntimeError: If the payload is not decodable UTF-8, is not valid JSON,
            is missing the 'packages' key, or holds a value whose type does not
            match the expected document shape.
    """
    # Clause order is load-bearing: UnicodeDecodeError and JSONDecodeError are
    # both ValueError subclasses, so the specific arms must precede the general
    # one. The bare ValueError arm exists because json.loads does not raise only
    # those two -- CPython's sys.int_max_str_digits limit (4300 by default since
    # 3.11) surfaces from integer-literal conversion inside the scanner as a
    # plain ValueError. Letting it escape would mean exit 64, which cli.py:258
    # reserves for operator input, for what is really a bad remote payload.
    try:
        document: object = json.loads(payload)
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Maintainership payload is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Maintainership payload is not valid JSON: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Maintainership payload holds an unparseable value: {exc}") from exc

    if not isinstance(document, dict):
        raise RuntimeError(
            f"Maintainership document must be a JSON object, got {type(document).__name__}"
        )

    if "packages" not in document:
        raise RuntimeError("Maintainership document is missing the 'packages' key")

    packages: object = document["packages"]
    if not isinstance(packages, dict):
        raise RuntimeError(f"'packages' must be a JSON object, got {type(packages).__name__}")

    snapshot: dict[str, frozenset[str]] = {}
    # Keyed by the tagged name, the string that actually reaches a CSV cell, and
    # local to this call so that each of a diff's two refs reports independently.
    # One maintainer owns hundreds of packages, so warning per occurrence would
    # bury the finding under its own repetitions. Only names that actually warned
    # are recorded: an unambiguous name must not reserve a key and mute a later
    # ambiguous one that tags to the same string. Two distinct root causes can
    # still share one key -- a user named 'group:' and a group named '' both key
    # on 'group:' -- so only the first is reported, but the offending string
    # reaches the operator either way.
    warned_names: set[str] = set()
    for package, entry in packages.items():
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Package {package!r} must map to a JSON object, got {type(entry).__name__}"
            )

        maintainers: set[str] = set()
        for key, prefix in (("users", ""), ("groups", "group:")):
            from_users = key == "users"
            # Real SLFO branches such as slfo-1.2 write JSON null where an empty
            # list is meant, so null and an absent key normalize alike. `is None`,
            # not truthiness: a falsy "" / 0 / {} is still the wrong shape and must
            # raise.
            names: object = entry.get(key)
            if names is None:
                names = []
            if not isinstance(names, list):
                raise RuntimeError(
                    f"'{key}' of package {package!r} must be a list, got {type(names).__name__}"
                )
            for name in names:
                if not isinstance(name, str):
                    raise RuntimeError(
                        f"'{key}' of package {package!r} must hold strings, "
                        f"got {type(name).__name__}"
                    )
                tagged = f"{prefix}{name}"
                if tagged not in warned_names:
                    reason = _ambiguity_reason(name, from_users=from_users)
                    if reason is not None:
                        warned_names.add(tagged)
                        # !r on all three for the reason given below: the name is
                        # remote-controlled just as the package name is.
                        logger.warning(
                            f"Maintainer name {tagged!r} at ref {ref!r} renders ambiguously: "
                            f"{reason} (first seen in package {package!r})"
                        )
                maintainers.add(tagged)

        # !r on both, not quotes: repr escapes embedded newlines and terminal
        # control sequences that would otherwise forge a log record here or
        # clear the operator's screen from stderr via the messages above. For an
        # ordinary name it renders identically. It is load-bearing for the
        # package name, which is remote-controlled; the ref reaches us from argv
        # through _validate_ref's allowlist and so needs only delimiting today.
        # Applied to both regardless, so the guarantee survives a new caller.
        if not maintainers:
            logger.warning(f"Package {package!r} has no maintainers at ref {ref!r}")
        snapshot[package] = frozenset(maintainers)

    return snapshot


def diff_snapshots(
    snapshot_a: dict[str, frozenset[str]], snapshot_b: dict[str, frozenset[str]]
) -> list[MaintainershipDiffRow]:
    """Compare two parsed snapshots package by package.

    A package yields a row when it is present in exactly one snapshot, or when
    it is present in both and its two maintainer sets differ. Comparison is
    set-based, so member ordering in the source documents never produces a row.

    Args:
        snapshot_a: Snapshot of the first ref, from `parse_tagged_snapshot`.
        snapshot_b: Snapshot of the second ref, from `parse_tagged_snapshot`.

    Returns:
        Rows for the differing packages, sorted by package name. `maintainers_a`
        and `maintainers_b` are sorted tuples, or None where the package is
        absent from that snapshot.
    """
    rows: list[MaintainershipDiffRow] = []
    for package in sorted(snapshot_a.keys() | snapshot_b.keys()):
        maintainers_a = snapshot_a.get(package)
        maintainers_b = snapshot_b.get(package)
        if maintainers_a == maintainers_b:
            continue
        rows.append(
            MaintainershipDiffRow(
                package=package,
                maintainers_a=None if maintainers_a is None else tuple(sorted(maintainers_a)),
                maintainers_b=None if maintainers_b is None else tuple(sorted(maintainers_b)),
            )
        )
    return rows
