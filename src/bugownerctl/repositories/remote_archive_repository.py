"""Remote archive repository.

Extracts a single file from the tar stream produced by
``git archive --remote=<url> <ref> -- <path>``, entirely in memory.
"""

import io
import tarfile

# The measured payload (`_maintainership.json` on SLFO) is ~307 KB; the cap
# leaves ~50x headroom while bounding what a remote can make this process read.
MAX_TAR_MEMBER_BYTES = 16 * 1024 * 1024


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
