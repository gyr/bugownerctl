"""Tests for tagged maintainership snapshot parsing and diffing.

Parsing (`parse_tagged_snapshot`) covers the `group:` tagging of group-sourced
names, a user and a like-named group staying distinct, absent `users`/`groups`
keys, null `users`/`groups` parsing exactly as an absent key does, the ignored
top-level `project` key, duplicate names collapsing, two packages keeping their
maintainers separate, and the warning emitted for a package with no
maintainers, whether its lists are empty or null.

Ambiguity warnings cover the three name shapes a maintainer cell cannot
represent — whitespace-bearing, empty, and a user name already starting with
`group:` — their precedence, their once-per-name-per-ref deduplication, and the
ordinary names and ordinary groups that must stay silent.

Untrusted-payload rejection covers every narrowing branch: undecodable bytes,
malformed JSON, an over-long integer literal, a non-object document, a missing
or non-object `packages`, a non-object package entry, a non-list, non-null
`users`/`groups`, and a non-string name (null included) inside those lists.

Diffing (`diff_snapshots`) covers one-sided packages, differing sets, identical
sets emitting nothing, the absent-versus-present-but-unmaintained distinction,
sorting by package name, set semantics over member order, and input immutability.

`MaintainershipDiffRow` is pinned as frozen and as keeping `None` distinct from
`()`. A final class pins the deliberate divergence of this normalization from
`MaintainershipRepositoryImpl.load`.
"""

import dataclasses
import json
import logging
from pathlib import Path

import pytest

from bugownerctl.domain.maintainership_diff import MaintainershipDiffRow
from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugownerctl.services.maintainership_diff_service import (
    diff_snapshots,
    parse_tagged_snapshot,
)

# ---------------------------------------------------------------------------
# parse_tagged_snapshot


class TestParseTaggedSnapshot:
    """Tests for parse_tagged_snapshot()."""

    def test_groups_are_prefixed(self) -> None:
        """Should tag every group-sourced name with 'group:' and leave users untagged."""
        payload = (
            b'{"project": "SLFO:1.3",'
            b' "packages": {"vim": {"users": ["alice"], "groups": ["editors"]}}}'
        )

        assert parse_tagged_snapshot(payload, "slfo-test") == {
            "vim": frozenset({"alice", "group:editors"})
        }

    def test_user_and_group_of_the_same_name_do_not_collide(self) -> None:
        """Should keep a user and a like-named group as two distinct maintainers."""
        payload = b'{"packages": {"vim": {"users": ["editors"], "groups": ["editors"]}}}'

        assert parse_tagged_snapshot(payload, "slfo-test") == {
            "vim": frozenset({"editors", "group:editors"})
        }

    def test_each_package_keeps_its_own_maintainers(self) -> None:
        """Should not leak maintainers from one package into the next.

        Every other parse test uses a single package, so a maintainer set
        hoisted out of the per-package loop would pass all of them at 100%
        line coverage. Two packages are the smallest input that catches it.
        """
        payload = b'{"packages": {"vim": {"users": ["alice"]}, "emacs": {"groups": ["editors"]}}}'

        assert parse_tagged_snapshot(payload, "slfo-test") == {
            "vim": frozenset({"alice"}),
            "emacs": frozenset({"group:editors"}),
        }

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            (b'{"packages": {"vim": {"users": ["alice"]}}}', frozenset({"alice"})),
            (b'{"packages": {"vim": {"groups": ["editors"]}}}', frozenset({"group:editors"})),
            (b'{"packages": {"vim": {}}}', frozenset()),
            (
                b'{"packages": {"vim": {"users": null, "groups": ["editors"]}}}',
                frozenset({"group:editors"}),
            ),
            (
                b'{"packages": {"vim": {"users": ["alice"], "groups": null}}}',
                frozenset({"alice"}),
            ),
            (b'{"packages": {"vim": {"users": null, "groups": null}}}', frozenset()),
        ],
        ids=[
            "groups_key_absent",
            "users_key_absent",
            "both_keys_absent",
            "users_null",
            "groups_null",
            "both_null",
        ],
    )
    def test_absent_or_null_name_list_contributes_nothing(
        self, payload: bytes, expected: frozenset[str]
    ) -> None:
        """Should treat a missing or null 'users'/'groups' key as an empty list.

        Real SLFO branches write null where an empty list is meant. Measured on
        slfo-1.2 on 2026-09-11: 1538 packages carry "users": null and 1344 carry
        "groups": null, which made the diff command unusable against that ref.
        """
        assert parse_tagged_snapshot(payload, "slfo-test") == {"vim": expected}

    def test_both_name_lists_null_is_logged_as_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn naming the package when both name lists are null, as for empty lists.

        Null is normalized to the empty list, so it reaches the same
        no-maintainers warning as `{"users": [], "groups": []}`; there is no
        separate null warning.
        """
        payload = b'{"packages": {"abseil-cpp": {"users": null, "groups": null}}}'

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {"abseil-cpp": frozenset()}
        # The whole record list, not a substring: a substring assertion still
        # passes when a second, null-specific warning is emitted alongside the
        # shared one, which is exactly what this test exists to forbid.
        assert [record.getMessage() for record in caplog.records] == [
            "Package 'abseil-cpp' has no maintainers at ref 'slfo-1.3'"
        ]

    def test_top_level_project_key_is_ignored(self) -> None:
        """Should ignore the top-level 'project' key rather than surfacing it as a package."""
        payload = b'{"project": "SLFO:1.3", "packages": {"vim": {"users": ["alice"]}}}'

        assert parse_tagged_snapshot(payload, "slfo-test") == {"vim": frozenset({"alice"})}

    def test_empty_packages_object_yields_empty_snapshot(self) -> None:
        """Should return an empty snapshot for a document holding no packages."""
        assert parse_tagged_snapshot(b'{"project": "SLFO:1.3", "packages": {}}', "slfo-test") == {}

    def test_duplicate_names_collapse_into_one_member(self) -> None:
        """Should collapse a repeated name into a single set member."""
        payload = b'{"packages": {"vim": {"users": ["alice", "alice"], "groups": ["e", "e"]}}}'

        assert parse_tagged_snapshot(payload, "slfo-test") == {
            "vim": frozenset({"alice", "group:e"})
        }

    def test_empty_maintainer_set_is_logged_as_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn naming the package when it parses to an empty maintainer set."""
        payload = b'{"packages": {"vim": {"users": [], "groups": []}}}'

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.2")

        assert result == {"vim": frozenset()}
        assert [record.getMessage() for record in caplog.records] == [
            "Package 'vim' has no maintainers at ref 'slfo-1.2'"
        ]

    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            ("slfo-1.2", "Package 'abseil-cpp' has no maintainers at ref 'slfo-1.2'"),
            ("slfo-1.3", "Package 'abseil-cpp' has no maintainers at ref 'slfo-1.3'"),
        ],
        ids=["first_ref", "second_ref"],
    )
    def test_the_no_maintainers_warning_names_the_ref(
        self, ref: str, expected: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should name the ref the payload was read from in the no-maintainers warning.

        One diff run parses two refs, so a warning saying only "this snapshot"
        leaves the operator unable to tell which ref the unmaintained package
        came from. Two refs are pinned because one would pass just as well
        against a ref hardcoded into the message.
        """
        payload = b'{"packages": {"abseil-cpp": {"users": [], "groups": []}}}'

        with caplog.at_level(logging.WARNING):
            parse_tagged_snapshot(payload, ref)

        assert [record.getMessage() for record in caplog.records] == [expected]


# ---------------------------------------------------------------------------
# parse_tagged_snapshot — names that render ambiguously in a maintainer cell


def _document(packages: dict[str, dict[str, list[str]]]) -> bytes:
    """Encode a maintainership document carrying the given package entries.

    Built rather than written as a byte literal because these tests carry names
    holding tabs, newlines and a no-break space, which a literal would have to
    escape twice and would make unreadable.

    Args:
        packages: Mapping of package name to its raw 'users'/'groups' lists.

    Returns:
        The UTF-8 encoded JSON document.
    """
    return json.dumps({"project": "SLFO:1.3", "packages": packages}).encode()


class TestParseTaggedSnapshotAmbiguousNames:
    """Tests for the warnings on maintainer names that a CSV cell cannot represent.

    `commands/diff.py` renders a maintainer set into one cell by joining the
    names with a space, so a name holding whitespace, an empty name and a user
    name already starting with 'group:' all produce a cell the reader cannot
    decode back. None of them is an error: the parse still succeeds and the
    snapshot is unchanged, the operator is only told the cell is untrustworthy.
    """

    @pytest.mark.parametrize(
        "name",
        ["ali ce", "ali\tce", "ali\nce", "ali\u00a0ce"],
        ids=["space", "tab", "newline", "no_break_space"],
    )
    def test_whitespace_in_a_user_name_is_warned(
        self, name: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn for any whitespace in a name, not just a literal space.

        The cell joins names with a space, but a tab or a newline breaks the CSV
        reader just as badly, and a no-break space is invisible to the operator
        reading the cell. The tab, newline and no-break space cases fail against
        a check written as `" " in name`.
        """
        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(_document({"vim": {"users": [name]}}), "slfo-1.3")

        assert result == {"vim": frozenset({name})}
        assert [record.getMessage() for record in caplog.records] == [
            f"Maintainer name {name!r} at ref 'slfo-1.3' renders ambiguously: it holds "
            f"whitespace, and maintainer cells join names with a space "
            f"(first seen in package 'vim')"
        ]

    def test_an_empty_user_name_is_warned(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should warn for an empty user name, which contributes an invisible cell token."""
        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(_document({"vim": {"users": ["", "alice"]}}), "slfo-1.3")

        assert result == {"vim": frozenset({"", "alice"})}
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name '' at ref 'slfo-1.3' renders ambiguously: it comes from an "
            "empty name, so it identifies no maintainer (first seen in package 'vim')"
        ]

    def test_an_empty_group_name_is_warned(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should warn for an empty group name, whose tagged form 'group:' is not empty.

        This is what forbids testing emptiness against the tagged string: after
        prefixing, an empty group name is the six-character 'group:' and an
        emptiness check applied there would let it through silently.
        """
        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(_document({"vim": {"groups": [""]}}), "slfo-1.3")

        assert result == {"vim": frozenset({"group:"})}
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name 'group:' at ref 'slfo-1.3' renders ambiguously: it comes from an "
            "empty name, so it identifies no maintainer (first seen in package 'vim')"
        ]

    def test_a_user_named_like_a_tagged_group_is_warned_and_collapses_into_it(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn once when a user 'group:x' and a real group 'x' tag to the same string.

        This is the concrete harm: the two are byte-identical after tagging, so
        they collapse into one set member and neither the diff nor the CSV
        reader can tell the user from the group. The single record also pins
        that the group does not warn a second time under the same tagged name.
        """
        payload = _document({"vim": {"users": ["group:x"], "groups": ["x"]}})

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {"vim": frozenset({"group:x"})}
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name 'group:x' at ref 'slfo-1.3' renders ambiguously: a user name "
            "starting with 'group:' renders identically to a group "
            "(first seen in package 'vim')"
        ]

    def test_an_unambiguous_name_does_not_reserve_its_key_against_a_later_ambiguous_one(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should key the seen-set on names that warned, never on every name encountered.

        A group 'x' and a user 'group:x' tag to the same string, but only the
        user is ambiguous. If the seen-set recorded every tagged name rather
        than only the warned ones, the harmless group in the first package would
        occupy the 'group:x' slot and silence the real finding in the second.

        Verified by mutation: hoisting `warned_names.add(tagged)` out of the
        `if reason is not None:` block passes every other test in this file and
        fails only this one.
        """
        payload = _document({"a-first": {"groups": ["x"]}, "b-second": {"users": ["group:x"]}})

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {"a-first": frozenset({"group:x"}), "b-second": frozenset({"group:x"})}
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name 'group:x' at ref 'slfo-1.3' renders ambiguously: a user name "
            "starting with 'group:' renders identically to a group "
            "(first seen in package 'b-second')"
        ]

    def test_a_group_literally_named_with_the_prefix_is_not_warned(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should keep the 'group:' reason to users-sourced names, even for a group named 'group:x'.

        Such a group tags to 'group:group:x' and collides only with a *user*
        named 'group:group:x' — which the users-sourced rule already reports, so
        the collision is covered from the side that can act on it. Verified by
        mutation: dropping the `from_users` guard makes this the only failing
        test.
        """
        payload = _document({"vim": {"groups": ["group:x"]}})

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {"vim": frozenset({"group:group:x"})}
        assert [record.getMessage() for record in caplog.records] == []

    @pytest.mark.parametrize(
        ("entry", "reason"),
        [
            (
                {"users": ["group:a b"]},
                "a user name starting with 'group:' renders identically to a group",
            ),
            (
                {"groups": ["a b"]},
                "it holds whitespace, and maintainer cells join names with a space",
            ),
        ],
        ids=["user_source_reports_the_collapse", "group_source_reports_the_whitespace"],
    )
    def test_the_collapse_reason_wins_over_whitespace(
        self, entry: dict[str, list[str]], reason: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should report the 'group:' collapse, not the whitespace, for a doubly ambiguous name.

        Both cases tag to the same 'group:a b'. From the users list the name is
        ambiguous twice over, and the collapse is the reason that must win: it
        is the only class that loses data, silently merging two distinct
        maintainers into one set member, whereas whitespace only makes the cell
        unreadable — and the whitespace is visible anyway in the !r-quoted name
        this very message carries. From the groups list the collapse rule does
        not apply, so the same tagged name is reported for its whitespace; that
        case is what stops the reasons being swapped wholesale rather than
        reordered.
        """
        with caplog.at_level(logging.WARNING):
            parse_tagged_snapshot(_document({"vim": entry}), "slfo-1.3")

        assert [record.getMessage() for record in caplog.records] == [
            f"Maintainer name 'group:a b' at ref 'slfo-1.3' renders ambiguously: {reason} "
            f"(first seen in package 'vim')"
        ]

    def test_a_repeated_ambiguous_name_warns_once_naming_the_first_package(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn once per name per ref, naming the package it was first seen in.

        A single maintainer typically owns hundreds of packages, so warning per
        occurrence would emit hundreds of identical lines for one bad name.
        """
        payload = _document(
            {
                "vim": {"users": ["ali ce"]},
                "emacs": {"users": ["ali ce"]},
                "nano": {"users": ["ali ce"]},
            }
        )

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {
            "vim": frozenset({"ali ce"}),
            "emacs": frozenset({"ali ce"}),
            "nano": frozenset({"ali ce"}),
        }
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name 'ali ce' at ref 'slfo-1.3' renders ambiguously: it holds "
            "whitespace, and maintainer cells join names with a space "
            "(first seen in package 'vim')"
        ]

    def test_dedup_does_not_carry_across_calls(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should warn once per ref, so the same bad name at both refs of a diff is reported twice.

        One call parses one ref. State kept across calls — a module-level or
        default-argument seen-set — would silence the second ref entirely.
        """
        payload = _document({"vim": {"users": ["ali ce"]}})

        with caplog.at_level(logging.WARNING):
            parse_tagged_snapshot(payload, "slfo-1.2")
            parse_tagged_snapshot(payload, "slfo-1.3")

        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name 'ali ce' at ref 'slfo-1.2' renders ambiguously: it holds "
            "whitespace, and maintainer cells join names with a space "
            "(first seen in package 'vim')",
            "Maintainer name 'ali ce' at ref 'slfo-1.3' renders ambiguously: it holds "
            "whitespace, and maintainer cells join names with a space "
            "(first seen in package 'vim')",
        ]

    @pytest.mark.parametrize("ref", ["slfo-1.2", "slfo-1.3"], ids=["first_ref", "second_ref"])
    def test_the_ambiguity_warning_names_the_ref(
        self, ref: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should name the ref the payload was read from, as the no-maintainers warning does.

        Two refs are pinned because one would pass just as well against a ref
        hardcoded into the message.
        """
        with caplog.at_level(logging.WARNING):
            parse_tagged_snapshot(_document({"vim": {"users": ["ali ce"]}}), ref)

        assert [record.getMessage() for record in caplog.records] == [
            f"Maintainer name 'ali ce' at ref {ref!r} renders ambiguously: it holds "
            f"whitespace, and maintainer cells join names with a space "
            f"(first seen in package 'vim')"
        ]

    def test_ordinary_names_are_never_warned_about(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should stay silent for a document whose names are all unambiguous.

        Ordinary groups are the load-bearing part: every group's tagged name
        starts with 'group:' by construction, so a rule reading the tagged name
        instead of the raw one would warn about all of them. 'group-editors' and
        'grouper' are here because they are the near misses -- a prefix test
        written against 'group' rather than 'group:' warns about both.
        """
        payload = _document(
            {
                "vim": {"users": ["alice", "bob"], "groups": ["editors"]},
                "emacs": {"users": ["carol"], "groups": ["group-editors", "grouper"]},
            }
        )

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {
            "vim": frozenset({"alice", "bob", "group:editors"}),
            "emacs": frozenset({"carol", "group:group-editors", "group:grouper"}),
        }
        assert [record.getMessage() for record in caplog.records] == []

    def test_a_sole_empty_maintainer_is_ambiguous_not_unmaintained(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should warn about the empty name only, not about the package having no maintainers.

        The set holds one member, the empty string, so the package is not
        unmaintained even though its cell renders as blank exactly like an
        unmaintained one. Emitting both warnings would tell the operator two
        contradictory things about the same package.
        """
        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(_document({"vim": {"users": [""]}}), "slfo-1.3")

        assert result == {"vim": frozenset({""})}
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name '' at ref 'slfo-1.3' renders ambiguously: it comes from an "
            "empty name, so it identifies no maintainer (first seen in package 'vim')"
        ]

    def test_the_snapshot_is_unchanged_by_every_ambiguity_class_at_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should return exactly the sets it returned before the warnings existed.

        The warnings are diagnostics: no name is dropped, renamed or escaped on
        the way into the snapshot, and the ambiguous members survive verbatim so
        the diff still compares them.
        """
        payload = _document({"vim": {"users": ["", "a b", "group:x"], "groups": ["x", ""]}})

        with caplog.at_level(logging.WARNING):
            result = parse_tagged_snapshot(payload, "slfo-1.3")

        assert result == {"vim": frozenset({"", "a b", "group:x", "group:"})}
        assert [record.getMessage() for record in caplog.records] == [
            "Maintainer name '' at ref 'slfo-1.3' renders ambiguously: it comes from an "
            "empty name, so it identifies no maintainer (first seen in package 'vim')",
            "Maintainer name 'a b' at ref 'slfo-1.3' renders ambiguously: it holds "
            "whitespace, and maintainer cells join names with a space "
            "(first seen in package 'vim')",
            "Maintainer name 'group:x' at ref 'slfo-1.3' renders ambiguously: a user name "
            "starting with 'group:' renders identically to a group "
            "(first seen in package 'vim')",
            "Maintainer name 'group:' at ref 'slfo-1.3' renders ambiguously: it comes from an "
            "empty name, so it identifies no maintainer (first seen in package 'vim')",
        ]


# ---------------------------------------------------------------------------
# parse_tagged_snapshot — untrusted payload rejection


class TestParseTaggedSnapshotRejections:
    """Tests for every value-narrowing rejection in parse_tagged_snapshot()."""

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            (b"{not json at all", "not valid JSON"),
            (b"", "not valid JSON"),
            (b'{"packages": {"\xff": {}}}', "not valid UTF-8"),
        ],
        ids=["malformed_json", "empty_payload", "undecodable_bytes"],
    )
    def test_undecodable_payload_raises_runtime_error(self, payload: bytes, message: str) -> None:
        """Should raise RuntimeError when the payload is not decodable JSON."""
        with pytest.raises(RuntimeError, match=message):
            parse_tagged_snapshot(payload, "slfo-test")

    @pytest.mark.parametrize(
        ("payload", "type_name"),
        [
            (b"[]", "list"),
            (b'"packages"', "str"),
            (b"42", "int"),
            (b"null", "NoneType"),
        ],
        ids=["list", "string", "number", "null"],
    )
    def test_non_object_document_raises_runtime_error(self, payload: bytes, type_name: str) -> None:
        """Should raise RuntimeError naming the type when the document is not an object."""
        with pytest.raises(RuntimeError, match=f"must be a JSON object, got {type_name}"):
            parse_tagged_snapshot(payload, "slfo-test")

    def test_oversized_integer_literal_raises_runtime_error(self) -> None:
        """Should raise RuntimeError, not ValueError, for an over-long integer literal.

        CPython caps integer string conversion at sys.int_max_str_digits (4300
        by default since 3.11) and the JSON scanner surfaces that as a bare
        ValueError, which is neither JSONDecodeError nor UnicodeDecodeError. If
        it escaped, cli.py would map it to exit 64 — operator input — for what
        is a defect in the remote payload.
        """
        payload = b'{"packages": {"vim": {"users": [' + b"1" * 5000 + b"]}}}"

        with pytest.raises(RuntimeError, match="holds an unparseable value"):
            parse_tagged_snapshot(payload, "slfo-test")

    def test_missing_packages_key_raises_runtime_error(self) -> None:
        """Should raise RuntimeError naming 'packages' when the key is absent."""
        with pytest.raises(RuntimeError, match="missing the 'packages' key"):
            parse_tagged_snapshot(b'{"project": "SLFO:1.3"}', "slfo-test")

    @pytest.mark.parametrize(
        ("payload", "type_name"),
        [
            (b'{"packages": []}', "list"),
            (b'{"packages": null}', "NoneType"),
            (b'{"packages": "vim"}', "str"),
        ],
        ids=["list", "null", "string"],
    )
    def test_non_object_packages_raises_runtime_error(self, payload: bytes, type_name: str) -> None:
        """Should raise RuntimeError naming the type when 'packages' is not an object."""
        with pytest.raises(
            RuntimeError, match=f"'packages' must be a JSON object, got {type_name}"
        ):
            parse_tagged_snapshot(payload, "slfo-test")

    @pytest.mark.parametrize(
        ("payload", "type_name"),
        [
            (b'{"packages": {"vim": []}}', "list"),
            (b'{"packages": {"vim": null}}', "NoneType"),
            (b'{"packages": {"vim": ["alice"]}}', "list"),
        ],
        ids=["list", "null", "list_of_names"],
    )
    def test_non_object_package_entry_raises_runtime_error(
        self, payload: bytes, type_name: str
    ) -> None:
        """Should raise RuntimeError naming the package when its entry is not an object."""
        with pytest.raises(RuntimeError, match=f"Package 'vim'.*JSON object, got {type_name}"):
            parse_tagged_snapshot(payload, "slfo-test")

    @pytest.mark.parametrize(
        ("payload", "key", "type_name"),
        [
            (b'{"packages": {"vim": {"users": "alice"}}}', "users", "str"),
            # Falsy but not null: pins that the normalization tests `is None`
            # rather than truthiness, so these keep raising rather than being
            # silently read as an empty list.
            (b'{"packages": {"vim": {"users": ""}}}', "users", "str"),
            (b'{"packages": {"vim": {"groups": false}}}', "groups", "bool"),
            (b'{"packages": {"vim": {"groups": "editors"}}}', "groups", "str"),
            (b'{"packages": {"vim": {"groups": {}}}}', "groups", "dict"),
        ],
        ids=[
            "users_string",
            "users_empty_string",
            "groups_false",
            "groups_string",
            "groups_object",
        ],
    )
    def test_non_list_name_container_raises_runtime_error(
        self, payload: bytes, key: str, type_name: str
    ) -> None:
        """Should raise RuntimeError naming key and package when 'users'/'groups' is not a list."""
        with pytest.raises(
            RuntimeError, match=f"'{key}' of package 'vim' must be a list, got {type_name}"
        ):
            parse_tagged_snapshot(payload, "slfo-test")

    @pytest.mark.parametrize(
        ("payload", "key", "type_name"),
        [
            (b'{"packages": {"vim": {"users": ["alice", 7]}}}', "users", "int"),
            (b'{"packages": {"vim": {"users": [null]}}}', "users", "NoneType"),
            (b'{"packages": {"vim": {"groups": [{"name": "editors"}]}}}', "groups", "dict"),
            (b'{"packages": {"vim": {"groups": [["editors"]]}}}', "groups", "list"),
        ],
        ids=["users_number", "users_null", "groups_object", "groups_list"],
    )
    def test_non_string_name_raises_runtime_error(
        self, payload: bytes, key: str, type_name: str
    ) -> None:
        """Should raise RuntimeError naming key and package when a name is not a string."""
        with pytest.raises(
            RuntimeError, match=f"'{key}' of package 'vim' must hold strings, got {type_name}"
        ):
            parse_tagged_snapshot(payload, "slfo-test")


# ---------------------------------------------------------------------------
# MaintainershipDiffRow


class TestMaintainershipDiffRow:
    """Tests for the MaintainershipDiffRow value object."""

    def test_absent_is_distinct_from_present_but_empty(self) -> None:
        """Should keep None (package absent at that ref) distinct from () (present, unowned).

        The whole point of the diff is to tell "this package was dropped" from
        "this package lost its last maintainer"; collapsing None into () would
        erase that difference.
        """
        absent = MaintainershipDiffRow(package="vim", maintainers_a=("alice",), maintainers_b=None)
        unowned = MaintainershipDiffRow(package="vim", maintainers_a=("alice",), maintainers_b=())

        assert absent != unowned

    def test_is_frozen(self) -> None:
        """Should reject attribute assignment, being a frozen value object."""
        row = MaintainershipDiffRow(package="vim", maintainers_a=None, maintainers_b=("alice",))

        with pytest.raises(dataclasses.FrozenInstanceError):
            row.package = "emacs"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# diff_snapshots


class TestDiffSnapshots:
    """Tests for diff_snapshots()."""

    def test_package_only_in_a_yields_none_for_b(self) -> None:
        """Should emit a row with maintainers_b None when the package is absent from b."""
        result = diff_snapshots({"vim": frozenset({"alice"})}, {})

        assert result == [
            MaintainershipDiffRow(package="vim", maintainers_a=("alice",), maintainers_b=None)
        ]

    def test_package_only_in_b_yields_none_for_a(self) -> None:
        """Should emit a row with maintainers_a None when the package is absent from a."""
        result = diff_snapshots({}, {"vim": frozenset({"alice"})})

        assert result == [
            MaintainershipDiffRow(package="vim", maintainers_a=None, maintainers_b=("alice",))
        ]

    def test_differing_maintainers_yield_both_sides_sorted(self) -> None:
        """Should emit a row carrying both sides as tuples sorted by name."""
        result = diff_snapshots(
            {"vim": frozenset({"bob", "alice"})},
            {"vim": frozenset({"carol", "alice", "group:editors"})},
        )

        assert result == [
            MaintainershipDiffRow(
                package="vim",
                maintainers_a=("alice", "bob"),
                maintainers_b=("alice", "carol", "group:editors"),
            )
        ]

    def test_identical_maintainers_yield_no_row(self) -> None:
        """Should emit nothing for a package whose maintainer set is unchanged."""
        snapshot = {"vim": frozenset({"alice", "group:editors"})}

        assert diff_snapshots(snapshot, dict(snapshot)) == []

    def test_empty_snapshots_yield_no_rows(self) -> None:
        """Should return an empty list when both snapshots are empty."""
        assert diff_snapshots({}, {}) == []

    def test_absent_package_differs_from_present_but_unmaintained(self) -> None:
        """Should emit a row distinguishing an absent package from a present, unowned one."""
        result = diff_snapshots({"vim": frozenset()}, {})

        assert result == [
            MaintainershipDiffRow(package="vim", maintainers_a=(), maintainers_b=None)
        ]

    def test_package_unmaintained_on_both_sides_yields_no_row(self) -> None:
        """Should emit nothing when a package is present and unmaintained at both refs."""
        assert diff_snapshots({"vim": frozenset()}, {"vim": frozenset()}) == []

    def test_rows_are_sorted_by_package_name(self) -> None:
        """Should return rows ordered by package name, whatever the input insertion order."""
        a = {"zsh": frozenset({"alice"}), "emacs": frozenset({"bob"})}
        b = {"vim": frozenset({"carol"}), "emacs": frozenset({"dave"})}

        assert [row.package for row in diff_snapshots(a, b)] == ["emacs", "vim", "zsh"]

    def test_member_order_in_the_source_json_never_produces_a_row(self) -> None:
        """Should compare as sets, so reordering names in the source JSON changes nothing."""
        a = parse_tagged_snapshot(
            b'{"packages": {"vim": {"users": ["alice", "bob"], "groups": ["x", "y"]}}}', "slfo-test"
        )
        b = parse_tagged_snapshot(
            b'{"packages": {"vim": {"users": ["bob", "alice"], "groups": ["y", "x"]}}}', "slfo-test"
        )

        assert diff_snapshots(a, b) == []

    def test_inputs_are_not_mutated(self) -> None:
        """Should leave both snapshot mappings untouched."""
        a = {"vim": frozenset({"alice"})}
        b = {"emacs": frozenset({"bob"})}

        diff_snapshots(a, b)

        assert a == {"vim": frozenset({"alice"})}
        assert b == {"emacs": frozenset({"bob"})}


# ---------------------------------------------------------------------------
# Deliberate divergence from MaintainershipRepositoryImpl.load


class TestNormalizationDivergence:
    """Tests pinning the deliberate divergence from MaintainershipRepositoryImpl.load()."""

    DOCUMENT = (
        b'{"project": "SLFO:1.3", "packages": {"vim": {"users": ["alice"], "groups": ["editors"]}}}'
    )

    def test_load_returns_untagged_names_while_the_parser_tags_groups(self, tmp_path: Path) -> None:
        """Should tag group-sourced names, unlike load(), which concatenates users and groups.

        This duplication is intentional and must stay: a diff has to tell the
        user 'editors' from the group 'editors', whereas check/query rely on
        load()'s untagged list. See the cross-reference comment in
        maintainership_diff_service.parse_tagged_snapshot.
        """
        file_path = tmp_path / "_maintainership.json"
        file_path.write_bytes(self.DOCUMENT)

        loaded = MaintainershipRepositoryImpl().load(file_path)

        assert loaded.packages["vim"] == ["alice", "editors"]
        tagged = parse_tagged_snapshot(self.DOCUMENT, "slfo-test")

        assert tagged["vim"] == frozenset({"alice", "group:editors"})
