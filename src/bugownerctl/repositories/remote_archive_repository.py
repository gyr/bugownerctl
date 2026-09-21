"""Remote archive repository.

Fetches a single file from a remote git repository with
``git archive --remote=<url> <ref> -- <path>`` and extracts it from the
resulting tar stream entirely in memory: nothing is cloned and nothing is
written to disk.
"""

import io
import os
import re
import shutil
import subprocess
import tarfile
from typing import Protocol

from bugownerctl.exceptions import MissingBinaryError, NetworkTimeoutError

# The measured payload (`_maintainership.json` on SLFO) is ~307 KB; the cap
# leaves ~50x headroom while bounding what a remote can make this process read.
MAX_TAR_MEMBER_BYTES = 16 * 1024 * 1024

# Cap on the whole tar stream. This does NOT bound what
# subprocess.run(capture_output=True) buffers: by the time we can measure
# proc.stdout, the pipe has already been drained into memory in full. What it
# bounds is what `tarfile` is asked to parse, which is the amplification stage:
# tar's block size is a fixed 512 bytes and an empty member costs one header
# block, so a 32 MiB tar can carry 65,536 members and getmembers() materialises
# a TarInfo object for every one of them.
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024

# Transports this feature can legitimately need. Pinning GIT_ALLOW_PROTOCOL is
# the only lever that actually holds: it overrides the operator's gitconfig, an
# inherited GIT_ALLOW_PROTOCOL, and an inherited GIT_CONFIG_COUNT alike, whereas
# `-c protocol.ext.allow=never` loses to the environment variable. It is also
# the only defence against `url.<x>.insteadOf`, which rewrites a benign-looking
# https:// URL into ext:: *inside* git, after any Python-side check on repo_url
# has already passed. Without this, an attacker who can plant a config file in
# the working directory (see utils/config.py's CWD-first search order) gets
# command execution on a host whose gitconfig re-enables the ext transport.
_ALLOWED_GIT_PROTOCOLS = "ssh:https:http:git:file"

_DEFAULT_TIMEOUT = 60  # seconds


def _validate_ref(ref: str) -> None:
    """Reject refs that git could misread as an option, a path escape or a shell token.

    This deliberately duplicates the ref rules in ``GitRepositoryImpl`` rather
    than importing them: the two call sites have independent lifecycles, and a
    handful of lines is cheaper than coupling this module to a clone-based
    repository it otherwise has nothing to do with. The copies are no longer
    identical: this one uses ``re.fullmatch``, where ``git_repository.py``'s
    ``re.match(...$)`` still accepts a trailing newline.

    Args:
        ref: Branch or tag name to validate.

    Raises:
        ValueError: If the ref is empty or whitespace-only, starts with ``-``,
            contains ``..``, or holds characters outside ``[\\w./-]``.
    """
    if not ref.strip():
        raise ValueError(f"Git reference must not be empty: {ref!r}")
    if ref.startswith("-"):
        raise ValueError(f"Git reference cannot start with '-': {ref}")
    if ".." in ref:
        raise ValueError(f"Path traversal not allowed in git reference: {ref}")
    # fullmatch, not match: `$` also matches just before a terminal newline, so
    # `re.match(r"^[\w./-]+$", "main\n")` succeeds and the allowlist leaks.
    if not re.fullmatch(r"[\w\./-]+", ref):
        raise ValueError(f"Invalid git reference format: {ref}")


def _extract_single_regular_file(tar_bytes: bytes, expected_path: str) -> bytes:
    """Return the content of the one regular file in an in-memory tar archive.

    The archive is never written to disk and ``extractall`` is never called:
    exactly one member is expected, and it must be a regular file whose name
    matches ``expected_path``.

    Args:
        tar_bytes: Raw tar archive bytes, as produced by ``git archive``.
        expected_path: Archive member name the tar is required to contain.

    Returns:
        The member's content as bytes.

    Raises:
        RuntimeError: If the archive is unreadable, does not hold exactly one
            member, or that member is not a regular file, is named something
            other than ``expected_path``, declares more than
            ``MAX_TAR_MEMBER_BYTES`` bytes, or yields no content stream.
    """
    try:
        # mode="r:" (not "r") is load-bearing: "r" transparently inflates
        # gzip/bz2/xz, which would expand the payload before any guard below
        # runs and make MAX_TAR_MEMBER_BYTES unenforceable. `git archive`
        # emits uncompressed tar, so a compressed stream is always wrong here.
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
            members = tar.getmembers()
            if len(members) != 1:
                raise RuntimeError(
                    f"git archive output for {expected_path!r} contains "
                    f"{len(members)} members, expected exactly 1"
                )
            member = members[0]
            if not member.isreg():
                raise RuntimeError(
                    f"git archive member {member.name!r} is not a regular file "
                    f"(tar type {member.type!r})"
                )
            if member.name != expected_path:
                raise RuntimeError(
                    f"git archive member is {member.name!r}, expected {expected_path!r}"
                )
            if member.size > MAX_TAR_MEMBER_BYTES:
                raise RuntimeError(
                    f"git archive member {member.name!r} declares {member.size} bytes, "
                    f"which exceeds the {MAX_TAR_MEMBER_BYTES} byte cap"
                )
            stream = tar.extractfile(member)
            if stream is None:
                raise RuntimeError(
                    f"git archive member {member.name!r} has no readable content stream"
                )
            with stream:
                return stream.read()
    except tarfile.TarError as exc:
        raise RuntimeError(
            f"git archive output for {expected_path!r} is not a readable tar archive: {exc}"
        ) from exc


class RemoteArchiveRepository(Protocol):
    """Fetch a single file from a remote git repository without cloning it."""

    def fetch_file(self, repo_url: str, ref: str, file_path: str) -> bytes:
        """Return the content of ``file_path`` at ``ref`` in ``repo_url``.

        Args:
            repo_url: Git remote URL, as accepted by ``git archive --remote``.
            ref: Branch or tag name to read the file from.
            file_path: Name of a file in the repository root. It must not
                contain ``/``: ``git archive`` emits a directory member for
                every path component, and this extraction accepts exactly one
                member. Note that git treats this as a pathspec, so a value
                containing glob metacharacters can match several files and will
                be rejected for the same reason.

        Returns:
            The file's content as bytes.

        Raises:
            ValueError: If ``ref`` or ``file_path`` is malformed, if the remote
                does not serve ``ref``, or if ``file_path`` does not exist at
                ``ref``. All four are operator input, so they share exit 64.
            MissingBinaryError: If ``git`` is not in PATH.
            NetworkTimeoutError: If the ``git archive`` subprocess exceeds the
                timeout.
            RuntimeError: If ``git archive`` exits non-zero for any other
                reason, or its output is not a single-file tar archive.
        """
        ...


class RemoteArchiveRepositoryImpl:
    """Adapter backed by ``git archive --remote``."""

    def fetch_file(self, repo_url: str, ref: str, file_path: str) -> bytes:
        _validate_ref(ref)
        if "/" in file_path:
            raise ValueError(
                f"file_path must name a file in the repository root, got {file_path!r}: "
                "git archive emits a directory member for every path component, "
                "and this extraction accepts exactly one member."
            )

        git_bin = shutil.which("git")
        if git_bin is None:
            raise MissingBinaryError("git")
        # stdin=DEVNULL plus GIT_TERMINAL_PROMPT=0 make an unauthenticated
        # remote fail fast instead of blocking on a credential prompt. We do
        # NOT force `ssh -o BatchMode=yes`: BatchMode also refuses passphrase
        # prompts, which breaks passphrase-protected keys that are not already
        # loaded into an ssh-agent — a working setup we must not penalise.
        try:
            proc = subprocess.run(
                [git_bin, "archive", f"--remote={repo_url}", ref, "--", file_path],
                capture_output=True,
                check=False,
                timeout=_DEFAULT_TIMEOUT,
                stdin=subprocess.DEVNULL,
                env={
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_ALLOW_PROTOCOL": _ALLOWED_GIT_PROTOCOLS,
                },
            )
        except FileNotFoundError as exc:
            raise MissingBinaryError("git") from exc
        except subprocess.TimeoutExpired as exc:
            raise NetworkTimeoutError(
                f"git archive --remote={repo_url!r} {ref!r}", _DEFAULT_TIMEOUT
            ) from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
            # These two strings come from the *server*, and git's messages are
            # gettext-translated, so matching them is best-effort: a non-English
            # server falls through to the generic branch below and the operator
            # still sees the raw stderr. Forcing LC_ALL=C would not help, since
            # the locale that matters is the remote's, not ours.
            if "remote: fatal: no such ref:" in stderr:
                raise ValueError(
                    f"Remote {repo_url} does not serve ref {ref!r}. Check the spelling; "
                    "note also that git archive --remote serves only branch and tag "
                    "names, never a commit SHA."
                )
            if "did not match any files" in stderr:
                raise ValueError(f"File {file_path!r} does not exist at ref {ref!r} in {repo_url}")
            raise RuntimeError(
                f"git archive --remote={repo_url} {ref} failed (exit {proc.returncode}):\n{stderr}"
            )

        if len(proc.stdout) > MAX_ARCHIVE_BYTES:
            raise RuntimeError(
                f"git archive output for {file_path!r} is {len(proc.stdout)} bytes, "
                f"which exceeds the {MAX_ARCHIVE_BYTES} byte cap"
            )

        return _extract_single_regular_file(proc.stdout, file_path)
