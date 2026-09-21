"""Tests for the `diff maintainership` command handler."""

import argparse
import json
import logging
import sys
from pathlib import Path

import pytest
import yaml

from bugownerctl.commands.diff import run_maintainership
from bugownerctl.exceptions import ConfigError

SLFO_GIT_URL = "https://example.invalid/slfo.git"


class FakeArchiveRepository:
    """In-memory stand-in for `RemoteArchiveRepository`.

    Maps a git ref to the bytes `fetch_file` should return for it, or to an
    exception instance it should raise instead. Every call is recorded so tests
    can assert on the requested file name.
    """

    def __init__(self, outcomes: dict[str, bytes | Exception]) -> None:
        self._outcomes = outcomes
        self.calls: list[tuple[str, str, str]] = []

    def fetch_file(self, repo_url: str, ref: str, file_path: str) -> bytes:
        self.calls.append((repo_url, ref, file_path))
        outcome = self._outcomes[ref]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def write_config(tmp_path: Path, **overrides: object) -> Path:
    """Write a real YAML config file under tmp_path and return its path."""
    config: dict[str, object] = {"slfo_git_url": SLFO_GIT_URL}
    config.update(overrides)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def snapshot_bytes(packages: dict[str, dict[str, list[str]]]) -> bytes:
    """Serialise a `_maintainership.json` document to bytes."""
    return json.dumps({"packages": packages}).encode("utf-8")


def make_args(
    config: Path, ref_a: str = "v1", ref_b: str = "v2", output: Path | None = None
) -> argparse.Namespace:
    """Build the argparse namespace the handler consumes."""
    return argparse.Namespace(config=config, ref_a=ref_a, ref_b=ref_b, output=output)


class TestRunMaintainership:
    """Tests for run_maintainership."""

    def test_writes_csv_rows_for_differing_packages(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Each package whose maintainers changed becomes one CSV row.

        The first cell deliberately carries three names from both source lists.
        A single-name cell would render identically under any separator, so a
        one-name payload leaves the join character, the `group:` tag and the
        intra-cell alphabetical order all unpinned.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes({"pkg-a": {"users": ["bob", "alice"], "groups": ["team"]}}),
                "v2": snapshot_bytes({"pkg-a": {"users": ["bob"]}}),
            }
        )

        exit_code = run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert exit_code == 0
        assert capsys.readouterr().out == (
            "package,v1,v2,change\npkg-a,alice bob group:team,bob,changed\n"
        )

    def test_header_holds_the_two_refs_exactly_as_typed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The header echoes the operator's ref strings verbatim, unnormalised."""
        repo = FakeArchiveRepository(
            {
                "refs/tags/SLFO-1.1.1": snapshot_bytes({}),
                "main": snapshot_bytes({}),
            }
        )
        args = make_args(write_config(tmp_path), ref_a="refs/tags/SLFO-1.1.1", ref_b="main")

        run_maintainership(args, archive_repo=repo)

        header = capsys.readouterr().out.splitlines()[0]
        assert header == "package,refs/tags/SLFO-1.1.1,main,change"

    def test_package_absent_from_one_ref_renders_empty_cell(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A package missing at a ref gets an empty cell on that side.

        Both directions run at once, so since the change column landed this
        pins that column's direction as well as the cell contents.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes({"gone": {"users": ["alice"]}}),
                "v2": snapshot_bytes({"arrived": {"users": ["bob"]}}),
            }
        )

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert capsys.readouterr().out == (
            "package,v1,v2,change\narrived,,bob,added\ngone,alice,,removed\n"
        )

    def test_package_present_but_unowned_renders_empty_cell(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A package that lost its last maintainer renders an empty cell too.

        Distinct from the absent case above: `diff_snapshots` hands back `()`
        here and `None` there, and both must reach the CSV as "". This is the
        row an operator reads the report to find.

        Since the change column landed it is also the only test stopping that
        column from being derived from an empty second cell: the row must read
        `unmaintained`, not `removed`, because pkg-a is still present at v2 --
        it lost its last maintainer there, it was not dropped from the ref.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes({"pkg-a": {"users": ["alice"]}}),
                "v2": snapshot_bytes({"pkg-a": {"users": []}}),
            }
        )

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert capsys.readouterr().out == "package,v1,v2,change\npkg-a,alice,,unmaintained\n"

    def test_each_snapshot_is_parsed_under_the_ref_it_was_fetched_from(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Every no-maintainers warning names the ref its package actually came from.

        `parse_tagged_snapshot` takes the payload and the ref as two separate
        `str`-typed arguments, so nothing but this test stops the handler
        pairing a payload with the wrong ref: transposing the two calls' refs
        leaves the CSV correct and every other test passing.

        Each ref carries its own unowned package, which is what makes the
        pairing observable. One unowned package at one ref would still let a
        handler that passed `ref_a` to both calls emit the expected warning.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes({"orphan-a": {"users": [], "groups": []}}),
                "v2": snapshot_bytes({"orphan-b": {"users": [], "groups": []}}),
            }
        )

        with caplog.at_level(logging.WARNING):
            run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert [record.getMessage() for record in caplog.records] == [
            "Package 'orphan-a' has no maintainers at ref 'v1'",
            "Package 'orphan-b' has no maintainers at ref 'v2'",
        ]

    def test_change_column_still_names_the_transitions_the_widening_left_alone(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """added, removed and changed keep their meanings after the widening.

        Splitting `adopted` and `unmaintained` out of `changed` narrowed what the
        remaining three words cover, so all three appear in one run here to pin
        each to its own transition rather than only pinning the vocabulary.

        The two orphan rows are what make this test irreplaceable, and they are
        the reason its packages are not simply added and removed ones -- those
        states are already pinned twice over elsewhere in this file. A package
        can arrive already unowned or leave having been unowned, so a row whose
        maintainer cells are empty on *both* sides is reachable in either
        direction, and nothing else here exercises that. Without these two rows
        a classifier that consults the opposite side's maintainers to decide,
        `"added" if row.maintainers_b else "removed"`, passes the whole suite.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes(
                    {"dying-orphan": {"users": []}, "reowned": {"users": ["alice"]}}
                ),
                "v2": snapshot_bytes(
                    {"newborn-orphan": {"users": []}, "reowned": {"users": ["bob"]}}
                ),
            }
        )

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert capsys.readouterr().out == (
            "package,v1,v2,change\n"
            "dying-orphan,,,removed\n"
            "newborn-orphan,,,added\n"
            "reowned,alice,bob,changed\n"
        )

    def test_change_column_separates_an_absent_package_from_an_unowned_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The column resolves the empty cell's two meanings, which is why it exists.

        Both rows here render an identical `,,bob` tail: `absent` was not in v1
        at all, `unowned` was in v1 with no maintainers. Only the fourth column
        tells them apart, so this fails for any implementation that derives the
        word from the rendered cell being empty instead of from `None`.

        It is the mirror of the removed/unmaintained test below, and pins the
        same ordering from the other side: a classifier that tested emptiness
        before `None` would call `absent` adopted, because `not None` is True.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes({"unowned": {"users": [], "groups": []}}),
                "v2": snapshot_bytes({"absent": {"users": ["bob"]}, "unowned": {"users": ["bob"]}}),
            }
        )

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert capsys.readouterr().out == (
            "package,v1,v2,change\nabsent,,bob,added\nunowned,,bob,adopted\n"
        )

    def test_change_column_separates_a_removed_package_from_an_unmaintained_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The column resolves the empty cell's two meanings on the v2 side too.

        Both rows here render an identical `alice,,` tail: `gone` is not in v2 at
        all, `lost-owner` is in v2 with no maintainers. Only the fourth column
        tells them apart.

        This fails for any implementation that tests emptiness before `None`,
        because `not None` is True and `gone` would then classify as
        unmaintained rather than removed.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes(
                    {"gone": {"users": ["alice"]}, "lost-owner": {"users": ["alice"]}}
                ),
                "v2": snapshot_bytes({"lost-owner": {"users": []}}),
            }
        )

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert capsys.readouterr().out == (
            "package,v1,v2,change\ngone,alice,,removed\nlost-owner,alice,,unmaintained\n"
        )

    def test_no_differences_writes_header_only_and_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Identical snapshots produce a header row and nothing else."""
        payload = snapshot_bytes({"pkg-a": {"users": ["alice"], "groups": ["team"]}})
        repo = FakeArchiveRepository({"v1": payload, "v2": payload})

        exit_code = run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert exit_code == 0
        assert capsys.readouterr().out == "package,v1,v2,change\n"

    def test_output_flag_writes_utf8_file_without_carriage_returns(self, tmp_path: Path) -> None:
        """`-o FILE` writes UTF-8 bytes with bare \\n line endings.

        csv.writer emits \\r\\n unless lineterminator is overridden, which is the
        part this assertion actually pins: on POSIX, dropping newline="" from
        the open changes nothing, because write-side translation maps \\n to
        os.linesep and os.linesep is already \\n. newline="" stays because it is
        the documented csv contract and does matter where os.linesep differs.

        The non-ASCII package name makes the explicit encoding="utf-8" on the
        open load-bearing rather than incidentally satisfied by the locale.
        """
        repo = FakeArchiveRepository(
            {
                "v1": snapshot_bytes({"pkg-ä": {"users": ["alice"]}}),
                "v2": snapshot_bytes({"pkg-ä": {"users": ["bob"]}}),
            }
        )
        target = tmp_path / "diff.csv"

        run_maintainership(make_args(write_config(tmp_path), output=target), archive_repo=repo)

        written = target.read_bytes()
        assert b"\r" not in written
        assert written == "package,v1,v2,change\npkg-ä,alice,bob,changed\n".encode()

    def test_stdout_stays_open_after_writing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Writing to stdout must not close it: the process still needs it."""
        repo = FakeArchiveRepository({"v1": snapshot_bytes({}), "v2": snapshot_bytes({})})

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert not sys.stdout.closed
        print("still usable")
        assert "still usable" in capsys.readouterr().out

    def test_maintainership_file_defaults_to_underscore_maintainership_json(
        self, tmp_path: Path
    ) -> None:
        """A config without maintainership_file falls back to the standard name."""
        repo = FakeArchiveRepository({"v1": snapshot_bytes({}), "v2": snapshot_bytes({})})

        run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert repo.calls == [
            (SLFO_GIT_URL, "v1", "_maintainership.json"),
            (SLFO_GIT_URL, "v2", "_maintainership.json"),
        ]

    def test_maintainership_file_from_config_is_fetched(self, tmp_path: Path) -> None:
        """An explicit maintainership_file overrides the default name."""
        repo = FakeArchiveRepository({"v1": snapshot_bytes({}), "v2": snapshot_bytes({})})
        config = write_config(tmp_path, maintainership_file="_owners.json")

        run_maintainership(make_args(config), archive_repo=repo)

        assert [call[2] for call in repo.calls] == ["_owners.json", "_owners.json"]

    def test_missing_slfo_git_url_raises_value_error(self, tmp_path: Path) -> None:
        """A config without slfo_git_url is operator error, reported as ValueError."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump({"maintainership_file": "x.json"}), encoding="utf-8")
        repo = FakeArchiveRepository({})

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            run_maintainership(make_args(config_path), archive_repo=repo)

        assert repo.calls == []

    def test_missing_config_file_raises_config_error(self, tmp_path: Path) -> None:
        """A --config path that does not exist surfaces as ConfigError, not FileNotFoundError."""
        repo = FakeArchiveRepository({})

        with pytest.raises(ConfigError):
            run_maintainership(make_args(tmp_path / "absent.yaml"), archive_repo=repo)

    def test_value_error_from_fetch_file_propagates_unchanged(self, tmp_path: Path) -> None:
        """An unknown ref must reach the CLI handler as the ValueError it was."""
        failure = ValueError("Remote does not serve ref 'typo'")
        repo = FakeArchiveRepository({"v1": failure, "v2": snapshot_bytes({})})

        with pytest.raises(ValueError) as exc_info:
            run_maintainership(make_args(write_config(tmp_path)), archive_repo=repo)

        assert exc_info.value is failure

    def test_existing_output_file_untouched_when_second_fetch_fails(self, tmp_path: Path) -> None:
        """Both refs are fetched before the output is opened, so a late failure clobbers nothing."""
        target = tmp_path / "diff.csv"
        target.write_text("previous run\n", encoding="utf-8")
        repo = FakeArchiveRepository(
            {"v1": snapshot_bytes({}), "v2": ValueError("no such ref: v2")}
        )

        with pytest.raises(ValueError):
            run_maintainership(make_args(write_config(tmp_path), output=target), archive_repo=repo)

        assert target.read_text(encoding="utf-8") == "previous run\n"

    def test_callable_with_namespace_alone(self, tmp_path: Path) -> None:
        """argparse calls `args.func(args)`, so archive_repo must be optional.

        The config here is empty, so the run fails on operator input before any
        remote is contacted: what is under test is that omitting the injection
        seam is a valid call, not a TypeError. An empty file, not "{}", because
        load_config returns None for the former and a dict for the latter --
        only the former exercises the handler's `or {}` guard.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            run_maintainership(make_args(config_path))
