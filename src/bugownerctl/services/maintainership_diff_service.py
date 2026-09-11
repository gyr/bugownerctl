"""Parsing and diffing of maintainership snapshots taken at git refs."""

import json
import logging

from ..domain.maintainership_diff import MaintainershipDiffRow

logger = logging.getLogger(__name__)


def parse_tagged_snapshot(payload: bytes) -> dict[str, frozenset[str]]:
    """Parse a `_maintainership.json` payload into tagged maintainer sets.

    The maintainer set of a package is its `users` entries plus its `groups`
    entries, each group name prefixed with `group:` so that a user and a group
    sharing a name stay distinguishable. A missing `users` or `groups` key, or
    one whose value is JSON null, contributes nothing. The top-level `project`
    key is ignored.

    The payload comes from a remote git ref and is untrusted, so every value
    read from the parsed document is narrowed before use.

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
    for package, entry in packages.items():
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Package {package!r} must map to a JSON object, got {type(entry).__name__}"
            )

        maintainers: set[str] = set()
        for key, prefix in (("users", ""), ("groups", "group:")):
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
                maintainers.add(f"{prefix}{name}")

        # !r, not quotes: the package name is remote-controlled, and repr escapes
        # embedded newlines and terminal control sequences that would otherwise
        # forge a log record here or clear the operator's screen from stderr via
        # the messages above. For an ordinary name repr renders identically.
        if not maintainers:
            logger.warning(f"Package {package!r} has no maintainers in this snapshot")
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
