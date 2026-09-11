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

Fetching (`fetch_file`) covers the happy path, the exact argv and subprocess
keyword arguments, the pinned git environment, a rejected sub-path file_path,
a missing or vanishing git binary, timeouts, each non-zero exit branch, the
whole-archive size cap, and a zero-byte success stream.
"""

import gzip
import io
import re
import shutil
import subprocess
import tarfile
from typing import Any

import pytest

from bugownerctl.exceptions import MissingBinaryError, NetworkTimeoutError
from bugownerctl.repositories import remote_archive_repository
from bugownerctl.repositories.remote_archive_repository import (
    RemoteArchiveRepository,
    RemoteArchiveRepositoryImpl,
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


def _completed(
    *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0
) -> subprocess.CompletedProcess[bytes]:
    """Build a CompletedProcess standing in for a `git archive --remote` run."""
    return subprocess.CompletedProcess(
        args=["git", "archive"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _patch_run(
    monkeypatch: pytest.MonkeyPatch,
    result: subprocess.CompletedProcess[bytes] | Exception,
) -> list[dict[str, Any]]:
    """Patch subprocess.run to return `result` (or raise it), recording every call.

    Returns the list the calls are recorded into; each entry holds the
    positional ``args`` tuple and the keyword arguments of one call.
    """
    calls: list[dict[str, Any]] = []

    def _fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append({"args": args, "kwargs": kwargs})
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return calls


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


# ---------------------------------------------------------------------------
# fetch_file


class TestFetchFile:
    """Tests for RemoteArchiveRepositoryImpl.fetch_file()."""

    def test_returns_file_bytes_from_archive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return the payload bytes of the file carried by the git archive stream."""
        payload = b'{"packages": {"vim": {}}}'
        tar_bytes = _make_tar([_regular("_maintainership.json", payload)])
        _patch_run(monkeypatch, _completed(stdout=tar_bytes))
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

        result = RemoteArchiveRepositoryImpl().fetch_file(
            "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
        )

        assert result == payload

    def test_invokes_git_archive_with_exact_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should invoke git archive with the --remote= form, the -- separator and no text mode."""
        tar_bytes = _make_tar([_regular("_maintainership.json", b"{}")])
        calls = _patch_run(monkeypatch, _completed(stdout=tar_bytes))
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

        RemoteArchiveRepositoryImpl().fetch_file(
            "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
        )

        assert len(calls) == 1
        assert calls[0]["args"][0] == [
            "/usr/bin/git",
            "archive",
            "--remote=https://src.suse.de/pool/vim",
            "slfo-1.3",
            "--",
            "_maintainership.json",
        ]
        assert calls[0]["kwargs"].get("capture_output") is True
        assert calls[0]["kwargs"].get("check") is False
        assert not calls[0]["kwargs"].get("text")
        assert "shell" not in calls[0]["kwargs"]

    def test_passes_devnull_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should pass stdin=DEVNULL so a credential prompt cannot hang the run."""
        tar_bytes = _make_tar([_regular("_maintainership.json", b"{}")])
        calls = _patch_run(monkeypatch, _completed(stdout=tar_bytes))
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

        RemoteArchiveRepositoryImpl().fetch_file(
            "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
        )

        assert calls[0]["kwargs"]["stdin"] is subprocess.DEVNULL

    def test_disables_git_terminal_prompt_without_dropping_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should set GIT_TERMINAL_PROMPT=0 in an env that still inherits os.environ."""
        monkeypatch.setenv("SSH_AUTH_SOCK", "/run/user/1000/keyring/ssh")
        tar_bytes = _make_tar([_regular("_maintainership.json", b"{}")])
        calls = _patch_run(monkeypatch, _completed(stdout=tar_bytes))
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

        RemoteArchiveRepositoryImpl().fetch_file(
            "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
        )

        env = calls[0]["kwargs"]["env"]
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["SSH_AUTH_SOCK"] == "/run/user/1000/keyring/ssh"

    def test_pins_git_allow_protocol_over_any_inherited_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should overwrite an inherited GIT_ALLOW_PROTOCOL, not merge with it.

        GIT_ALLOW_PROTOCOL is the only lever that reliably keeps the `ext`
        transport off: it beats the operator's gitconfig, and it is the only
        defence against a `url.<x>.insteadOf` rule rewriting a benign https://
        URL into `ext::sh -c ...` inside git, where no Python-side check on
        repo_url can see it.
        """
        monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "ext")
        tar_bytes = _make_tar([_regular("_maintainership.json", b"{}")])
        calls = _patch_run(monkeypatch, _completed(stdout=tar_bytes))
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

        RemoteArchiveRepositoryImpl().fetch_file(
            "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
        )

        allowed = calls[0]["kwargs"]["env"]["GIT_ALLOW_PROTOCOL"].split(":")
        assert "ext" not in allowed
        assert "ssh" in allowed
        assert "https" in allowed

    def test_passes_default_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should bound the subprocess with the 60 second default timeout."""
        tar_bytes = _make_tar([_regular("_maintainership.json", b"{}")])
        calls = _patch_run(monkeypatch, _completed(stdout=tar_bytes))
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")

        RemoteArchiveRepositoryImpl().fetch_file(
            "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
        )

        assert calls[0]["kwargs"]["timeout"] == 60

    def test_invalid_ref_is_rejected_before_any_subprocess_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should validate the ref first, so a hostile ref never reaches git."""
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        calls = _patch_run(monkeypatch, _completed())

        with pytest.raises(ValueError, match="cannot start with '-'"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "--upload-pack=id", "_maintainership.json"
            )

        assert calls == []

    def test_file_path_with_a_directory_component_is_rejected_before_any_subprocess_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should reject a file_path holding '/' up front, naming the real cause.

        `git archive` emits a directory member for every path component, so a
        sub-path yields more than one member and would otherwise fail deep in
        the tar layer with a member-count error that points at the wrong thing.
        """
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        calls = _patch_run(monkeypatch, _completed())

        with pytest.raises(ValueError, match="must name a file in the repository root"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "sub/_maintainership.json"
            )

        assert calls == []

    def test_missing_git_in_path_raises_missing_binary_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise MissingBinaryError when git is absent from PATH."""
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        calls = _patch_run(monkeypatch, _completed())

        with pytest.raises(MissingBinaryError, match="git"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

        assert calls == []

    def test_git_vanishing_between_lookup_and_exec_raises_missing_binary_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should translate FileNotFoundError from exec into MissingBinaryError."""
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(monkeypatch, FileNotFoundError("/usr/bin/git"))

        with pytest.raises(MissingBinaryError, match="git"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

    def test_subprocess_timeout_raises_network_timeout_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should translate TimeoutExpired into NetworkTimeoutError labelled with url and ref."""
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(monkeypatch, subprocess.TimeoutExpired(cmd="git archive", timeout=60))

        with pytest.raises(NetworkTimeoutError) as excinfo:
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

        assert excinfo.value.timeout == 60
        assert (
            excinfo.value.label == "git archive --remote='https://src.suse.de/pool/vim' 'slfo-1.3'"
        )

    def test_generic_failure_raises_runtime_error_with_returncode_and_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise RuntimeError carrying the exit code and decoded stderr."""
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(
            monkeypatch,
            _completed(returncode=1, stderr=b"fatal: Could not read from remote repository."),
        )

        with pytest.raises(
            RuntimeError, match=r"(?s)exit 1.*Could not read from remote repository"
        ):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

    def test_failure_with_empty_stderr_still_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should still raise RuntimeError when git exits non-zero saying nothing.

        Both stderr sniffs miss, so the generic branch has to carry the failure
        on the exit code alone rather than falling through to the tar parser.
        """
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(monkeypatch, _completed(returncode=1, stderr=b""))

        with pytest.raises(RuntimeError, match="exit 1"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

    def test_unknown_ref_raises_value_error_hinting_that_shas_are_not_servable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError naming the ref and explaining that SHAs are not servable."""
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(
            monkeypatch,
            _completed(
                returncode=1,
                stderr=b"remote: fatal: no such ref: 1f3c0de\nfatal: sent error to the client",
            ),
        )

        with pytest.raises(ValueError, match=r"(?s)'1f3c0de'.*branch.*tag.*commit SHA"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "1f3c0de", "_maintainership.json"
            )

    def test_absent_file_raises_value_error_naming_path_and_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError naming the file and the ref when the pathspec matches none.

        ValueError, not RuntimeError: an absent file at a valid ref is operator
        input, exactly like an unknown ref, and cli.py maps both to exit 64.
        Exit 1 stays reserved for genuine internal faults.
        """
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(
            monkeypatch,
            _completed(
                returncode=1,
                stderr=b"fatal: pathspec '_maintainership.json' did not match any files",
            ),
        )

        with pytest.raises(ValueError, match=r"'_maintainership\.json'.*'slfo-1\.3'"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

    def test_oversized_archive_raises_runtime_error_before_parsing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should reject an over-cap stream on its length, before handing it to tarfile.

        The payload is deliberately not a valid tar: if the cap were checked
        after parsing, the failure would be the tar layer's "not a readable tar
        archive", not this size message.
        """
        oversized = b"x" * 32
        monkeypatch.setattr(remote_archive_repository, "MAX_ARCHIVE_BYTES", 16)
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(monkeypatch, _completed(stdout=oversized))

        with pytest.raises(RuntimeError, match=r"32 bytes.*16 byte cap"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )

    def test_empty_stdout_raises_runtime_error_from_the_tar_layer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should reject a zero-byte success stream instead of reading it as an empty file.

        Defence in depth: git signals an unservable ref with a non-zero exit,
        not an empty stream, but nothing here should ever turn zero bytes into
        a successful empty result.
        """
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
        _patch_run(monkeypatch, _completed(stdout=b""))

        with pytest.raises(RuntimeError, match="is not a readable tar archive"):
            RemoteArchiveRepositoryImpl().fetch_file(
                "https://src.suse.de/pool/vim", "slfo-1.3", "_maintainership.json"
            )


# ---------------------------------------------------------------------------
# Protocol conformance


class TestProtocol:
    """Tests that the implementation satisfies the RemoteArchiveRepository protocol."""

    def test_impl_satisfies_protocol(self) -> None:
        """Should type-check as a RemoteArchiveRepository."""
        impl: RemoteArchiveRepository = RemoteArchiveRepositoryImpl()

        assert hasattr(impl, "fetch_file")
