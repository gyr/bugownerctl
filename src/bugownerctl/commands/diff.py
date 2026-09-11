"""Diff command handlers.

Compares `_maintainership.json` between two SLFO git refs and writes the
differing packages as CSV.
"""

import argparse
import contextlib
import csv
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from bugownerctl.exceptions import ConfigError
from bugownerctl.exit_codes import ExitCode
from bugownerctl.repositories.remote_archive_repository import (
    RemoteArchiveRepository,
    RemoteArchiveRepositoryImpl,
)
from bugownerctl.services.maintainership_diff_service import diff_snapshots, parse_tagged_snapshot
from bugownerctl.utils.config import load_config

logger = logging.getLogger(__name__)


def _render_cell(maintainers: tuple[str, ...] | None) -> str:
    """Render one side of a diff row as a CSV cell.

    Args:
        maintainers: Sorted maintainer names, or None when the package is absent
            at that ref.

    Returns:
        The names joined by a single space. Both an absent package and a present
        but unmaintained one render as the empty string.
    """
    if maintainers is None:
        return ""
    return " ".join(maintainers)


@contextlib.contextmanager
def _open_output(path: Path | None) -> Iterator[TextIO]:
    """Yield the CSV destination, closing it only when this function opened it.

    Args:
        path: Destination file, or None to write to stdout.

    Yields:
        A writable text stream. stdout is yielded as-is and never closed, since
        the process still needs it after the command returns.

    Note:
        The two branches do not agree on encoding. A file is always written as
        UTF-8; stdout keeps whatever codec the locale gave it, so a non-ASCII
        package name raises UnicodeEncodeError under LC_ALL=C where `-o` would
        have succeeded. Reconfiguring stdout is deliberately not done here: it
        would mutate process-global state that the logging handlers on stderr
        also observe, to fix a case no name in the current data can reach.
    """
    if path is None:
        yield sys.stdout
        return
    # newline="" is the csv module's documented contract for the file it writes
    # to. On POSIX it is not observable -- write-side translation maps \n to
    # os.linesep, which is already \n -- but it is what stops the platform from
    # reintroducing \r wherever os.linesep differs.
    with path.open("w", newline="", encoding="utf-8") as handle:
        yield handle


def run_maintainership(
    args: argparse.Namespace, archive_repo: RemoteArchiveRepository | None = None
) -> int:
    """Execute diff maintainership subcommand.

    Args:
        args: Parsed command-line arguments with ref_a, ref_b, config, output.
        archive_repo: Injection seam for tests; a RemoteArchiveRepositoryImpl is
            constructed when omitted, since argparse calls the handler with the
            namespace alone.

    Returns:
        Exit code (0 = success).

    Raises:
        ConfigError: If the config file cannot be found.
        ValueError: If slfo_git_url is absent from config.
    """
    try:
        config = load_config(args.config) or {}
    except FileNotFoundError as exc:
        raise ConfigError(str(exc)) from exc

    slfo_git_url = config.get("slfo_git_url")
    if not slfo_git_url:
        raise ValueError("slfo_git_url not found in config")

    maintainership_file = config.get("maintainership_file", "_maintainership.json")

    # Constructed only once the config is known good, so that a bad config
    # cannot reach a repository constructor that may one day do real work.
    repo = archive_repo if archive_repo is not None else RemoteArchiveRepositoryImpl()

    logger.info("diffing %s between %r and %r", maintainership_file, args.ref_a, args.ref_b)
    snapshot_a = parse_tagged_snapshot(
        repo.fetch_file(slfo_git_url, args.ref_a, maintainership_file), args.ref_a
    )
    snapshot_b = parse_tagged_snapshot(
        repo.fetch_file(slfo_git_url, args.ref_b, maintainership_file), args.ref_b
    )

    rows = diff_snapshots(snapshot_a, snapshot_b)

    with _open_output(args.output) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["package", args.ref_a, args.ref_b])
        for row in rows:
            writer.writerow(
                [
                    row.package,
                    _render_cell(row.maintainers_a),
                    _render_cell(row.maintainers_b),
                ]
            )

    return ExitCode.OK
