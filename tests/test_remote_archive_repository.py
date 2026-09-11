"""Tests for the remote archive repository.

Tar extraction (`_extract_single_regular_file`) covers:
  - Happy path: one regular member matching the expected path.
  - Member-count violations (zero members, more than one member).
  - Non-regular member types (directory, symlink, hardlink, device, fifo).
  - Member name mismatch.
  - Member size over the cap, rejected from the header.
  - Compressed archives, which git archive never emits.
  - Unreadable archives and a missing extraction stream.

Ref validation (`_validate_ref`) covers accepted refs plus each rejection
branch: empty, leading '-', '..' traversal, and out-of-allowlist characters.
"""

import gzip
import io
import re
import tarfile

import pytest

from bugownerctl.repositories import remote_archive_repository
from bugownerctl.repositories.remote_archive_repository import (
    _extract_single_regular_file,
    _validate_ref,
)

# ---------------------------------------------------------------------------
# Helpers


def _make_tar(members: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    """Build an in-memory tar from (TarInfo, payload) pairs."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for info, payload in members:
            tar.addfile(info, io.BytesIO(payload) if payload is not None else None)
    return buffer.getvalue()


def _regular(name: str, payload: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name=name)
    info.type = tarfile.REGTYPE
    info.size = len(payload)
    return info, payload


# ---------------------------------------------------------------------------
# _extract_single_regular_file


class TestExtractSingleRegularFile:
    """Tests for _extract_single_regular_file()."""

    def test_returns_member_bytes(self) -> None:
        """Should return the bytes of the single regular member matching the path."""
        payload = b'{"packages": {}}'
        tar_bytes = _make_tar([_regular("_maintainership.json", payload)])

        assert _extract_single_regular_file(tar_bytes, "_maintainership.json") == payload

    def test_zero_members_raises_runtime_error(self) -> None:
        """Should raise RuntimeError naming the expected path when the tar is empty."""
        tar_bytes = _make_tar([])

        with pytest.raises(RuntimeError, match="contains 0 members"):
            _extract_single_regular_file(tar_bytes, "_maintainership.json")

    def test_multiple_members_raises_runtime_error(self) -> None:
        """Should raise RuntimeError reporting the member count when the tar has 2 members."""
        tar_bytes = _make_tar(
            [_regular("_maintainership.json", b"{}"), _regular("other.json", b"{}")]
        )

        with pytest.raises(RuntimeError, match="contains 2 members"):
            _extract_single_regular_file(tar_bytes, "_maintainership.json")

    @pytest.mark.parametrize(
        ("member_type", "linkname"),
        [
            (tarfile.DIRTYPE, ""),
            (tarfile.SYMTYPE, "/etc/passwd"),
            (tarfile.LNKTYPE, "_maintainership.json"),
            (tarfile.CHRTYPE, ""),
            (tarfile.FIFOTYPE, ""),
        ],
        ids=["directory", "symlink", "hardlink", "device", "fifo"],
    )
    def test_non_regular_member_raises_runtime_error(
        self, member_type: bytes, linkname: str
    ) -> None:
        """Should raise RuntimeError naming the member when it is not a regular file."""
        info = tarfile.TarInfo(name="_maintainership.json")
        info.type = member_type
        info.linkname = linkname
        tar_bytes = _make_tar([(info, None)])

        with pytest.raises(RuntimeError, match="'_maintainership.json' is not a regular file"):
            _extract_single_regular_file(tar_bytes, "_maintainership.json")

    def test_member_name_mismatch_raises_runtime_error(self) -> None:
        """Should raise RuntimeError naming both the found and the expected path."""
        tar_bytes = _make_tar([_regular("../../etc/passwd", b"root:x:0:0")])

        with pytest.raises(RuntimeError, match=r"'\.\./\.\./etc/passwd'.*'_maintainership\.json'"):
            _extract_single_regular_file(tar_bytes, "_maintainership.json")

    def test_oversized_member_raises_runtime_error_from_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should reject an over-cap member from its header, without reading its content."""
        monkeypatch.setattr(remote_archive_repository, "MAX_TAR_MEMBER_BYTES", 4)
        monkeypatch.setattr(
            tarfile.TarFile,
            "extractfile",
            lambda *args, **kwargs: pytest.fail("member content was read despite the size cap"),
        )
        tar_bytes = _make_tar([_regular("_maintainership.json", b"0123456789")])

        with pytest.raises(RuntimeError, match="10 bytes.*exceeds the 4 byte cap"):
            _extract_single_regular_file(tar_bytes, "_maintainership.json")

    def test_compressed_archive_raises_runtime_error(self) -> None:
        """Should reject a gzip-compressed tar: git archive emits uncompressed tar only.

        Accepting compression would let a small payload inflate before the
        member guards run, making MAX_TAR_MEMBER_BYTES unenforceable.
        """
        compressed = gzip.compress(_make_tar([_regular("_maintainership.json", b"{}")]))

        with pytest.raises(RuntimeError, match="is not a readable tar archive"):
            _extract_single_regular_file(compressed, "_maintainership.json")

    def test_unreadable_archive_raises_runtime_error(self) -> None:
        """Should wrap a tarfile.TarError in RuntimeError naming the expected path."""
        with pytest.raises(RuntimeError, match="is not a readable tar archive"):
            _extract_single_regular_file(b"not a tar at all", "_maintainership.json")

    def test_missing_extraction_stream_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise RuntimeError when extractfile() yields no stream for a regular member."""
        monkeypatch.setattr(tarfile.TarFile, "extractfile", lambda *args, **kwargs: None)
        tar_bytes = _make_tar([_regular("_maintainership.json", b"{}")])

        with pytest.raises(RuntimeError, match="'_maintainership.json' has no readable content"):
            _extract_single_regular_file(tar_bytes, "_maintainership.json")


# ---------------------------------------------------------------------------
# _validate_ref


class TestValidateRef:
    """Tests for _validate_ref()."""

    @pytest.mark.parametrize("ref", ["slfo-1.3", "refs/heads/slfo-main"], ids=["tag", "full_ref"])
    def test_accepts_valid_ref(self, ref: str) -> None:
        """Should accept a plain tag name and a fully qualified ref path."""
        _validate_ref(ref)

    @pytest.mark.parametrize("ref", ["", "   ", "\t\n"], ids=["empty", "spaces", "whitespace"])
    def test_rejects_empty_ref(self, ref: str) -> None:
        """Should raise ValueError for an empty or whitespace-only ref."""
        with pytest.raises(ValueError, match="must not be empty"):
            _validate_ref(ref)

    @pytest.mark.parametrize(
        "ref", ["--upload-pack=touch /tmp/pwned", "-o"], ids=["upload_pack", "short_option"]
    )
    def test_rejects_ref_starting_with_dash(self, ref: str) -> None:
        """Should raise ValueError naming the ref when it could be read as a git option."""
        with pytest.raises(ValueError, match=rf"cannot start with '-': {re.escape(ref)}"):
            _validate_ref(ref)

    @pytest.mark.parametrize(
        "ref", ["../../etc/passwd", "refs/heads/..", "a..b"], ids=["traversal", "trailing", "range"]
    )
    def test_rejects_ref_containing_double_dot(self, ref: str) -> None:
        """Should raise ValueError naming the ref when it contains a '..' path traversal."""
        with pytest.raises(ValueError, match=rf"Path traversal.*{re.escape(ref)}"):
            _validate_ref(ref)

    @pytest.mark.parametrize(
        "ref",
        [
            "slfo;rm -rf /",
            "slfo 1.3",
            "$(id)",
            "slfo\nmain",
            "main\n",
            "refs/heads/main~1",
            "sl'fo",
        ],
        ids=[
            "semicolon",
            "space",
            "substitution",
            "interior_newline",
            "trailing_newline",
            "tilde",
            "quote",
        ],
    )
    def test_rejects_ref_with_characters_outside_the_allowlist(self, ref: str) -> None:
        """Should raise ValueError naming the ref when it holds characters outside [\\w./-]."""
        with pytest.raises(ValueError, match="Invalid git reference format"):
            _validate_ref(ref)
