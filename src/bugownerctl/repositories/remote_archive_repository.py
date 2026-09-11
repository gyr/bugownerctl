"""Remote archive repository.

Extracts a single file from the tar stream produced by
``git archive --remote=<url> <ref> -- <path>``, entirely in memory, and
validates the git ref before it can reach that command line.
"""

import io
import re
import tarfile

# The measured payload (`_maintainership.json` on SLFO) is ~307 KB; the cap
# leaves ~50x headroom while bounding what a remote can make this process read.
MAX_TAR_MEMBER_BYTES = 16 * 1024 * 1024


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
