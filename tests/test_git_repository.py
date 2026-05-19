"""Tests for GitRepository."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from src.bugowner.domain.ref_type import RefType
from src.bugowner.repositories.git_repository import GitRepositoryImpl


class TestListSubmodules:
    """Tests for GitRepository.list_submodules()."""

    def test_list_submodules_returns_sorted_list(self) -> None:
        """Should return sorted list of submodule names."""
        mock_output = """
 abc123 submodule-c (heads/main)
 def456 submodule-a (v1.0.0)
 ghi789 submodule-b (tags/v2.0)
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

            repo = GitRepositoryImpl()
            result = repo.list_submodules(Path("/test/repo"))

            assert result == ["submodule-a", "submodule-b", "submodule-c"]
            mock_run.assert_called_once_with(
                ["git", "submodule", "status"],
                capture_output=True,
                text=True,
                check=False,
                cwd="/test/repo",
            )

    def test_list_submodules_handles_empty_output(self) -> None:
        """Should return empty list when no submodules exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            repo = GitRepositoryImpl()
            result = repo.list_submodules(Path("/test/repo"))

            assert result == []

    def test_list_submodules_raises_on_git_error(self) -> None:
        """Should raise RuntimeError when git command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="fatal: not a git repository",
            )

            repo = GitRepositoryImpl()

            with pytest.raises(RuntimeError, match="Git command failed"):
                repo.list_submodules(Path("/test/repo"))

    def test_list_submodules_raises_on_git_not_found(self) -> None:
        """Should raise RuntimeError when git command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            repo = GitRepositoryImpl()

            with pytest.raises(RuntimeError, match="git.*not found"):
                repo.list_submodules(Path("/test/repo"))


class TestCloneOrUpdate:
    """Tests for GitRepository.clone_or_update()."""

    def test_accepts_valid_ssh_urls(self) -> None:
        """Should accept valid SSH URL formats."""
        repo = GitRepositoryImpl()

        valid_ssh_urls = [
            "git@github.com:user/repo.git",
            "git@src.suse.de:products/SLFO.git",
            "user@host.com:path/to/repo.git",
            "git@gitlab.com:group/subgroup/repo.git",
        ]

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            for ssh_url in valid_ssh_urls:
                # Should not raise ValueError
                result = repo.clone_or_update(ssh_url, "main", Path("/cache"), RefType.BRANCH)
                assert isinstance(result, Path)

    def test_rejects_ssh_url_with_port_syntax(self) -> None:
        """Should reject SSH URLs with port between host and path."""
        repo = GitRepositoryImpl()

        # SCP-style SSH URLs (user@host:path) don't support port syntax
        # Port between host and path is invalid: user@host:PORT:path
        # Valid SSH with port requires ssh:// scheme: ssh://user@host:port/path
        invalid_ssh_urls_with_port = [
            "git@github.com:22:user/repo.git",
            "git@gitlab.com:443:group/repo.git",
            "user@host.com:8080:path/repo.git",
        ]

        # No mocks needed - validation should fail before filesystem/subprocess
        for invalid_url in invalid_ssh_urls_with_port:
            with pytest.raises(ValueError, match="Invalid repository URL format"):
                repo.clone_or_update(invalid_url, "main", Path("/cache"), RefType.BRANCH)

    def test_rejects_invalid_url_format(self) -> None:
        """Should raise ValueError for invalid URL formats."""
        repo = GitRepositoryImpl()

        invalid_urls = [
            "not-a-url",
            "https://github.com/repo",  # Missing .git
            "ftp://example.com/repo.git",  # Not HTTP/HTTPS
            "https://example.com/repo.git; rm -rf /",  # Command injection attempt
            "git@github.com",  # SSH missing path
            "git@:repo.git",  # SSH missing host
            "@github.com:repo.git",  # SSH missing user
            "user@host:",  # SSH missing path
        ]

        for invalid_url in invalid_urls:
            with pytest.raises(ValueError, match="Invalid repository URL format"):
                repo.clone_or_update(invalid_url, "main", Path("/cache"), RefType.BRANCH)

    def test_rejects_invalid_git_ref(self) -> None:
        """Should raise ValueError for invalid git reference format."""
        repo = GitRepositoryImpl()

        invalid_refs = [
            "main; rm -rf /",  # Command injection attempt
            "ref with spaces",
            "ref\nwith\nnewlines",
        ]

        for invalid_ref in invalid_refs:
            with pytest.raises(ValueError, match="Invalid git reference format"):
                repo.clone_or_update(
                    "https://github.com/test/repo.git",
                    invalid_ref,
                    Path("/cache"),
                    RefType.BRANCH,
                )

    def test_blocks_git_option_injection(self) -> None:
        """Should block git refs starting with - (option injection)."""
        repo = GitRepositoryImpl()

        dangerous_refs = [
            "--help",
            "--version",
            "-c core.sshCommand=evil",
        ]

        for dangerous_ref in dangerous_refs:
            with pytest.raises(ValueError, match="cannot start with '-'"):
                repo.clone_or_update(
                    "https://github.com/test/repo.git",
                    dangerous_ref,
                    Path("/cache"),
                    RefType.BRANCH,
                )

    def test_blocks_path_traversal_in_ref(self) -> None:
        """Should block path traversal patterns in git refs."""
        repo = GitRepositoryImpl()

        traversal_refs = [
            "../../../etc/passwd",
            "../../.ssh/id_rsa",
            "main/../evil",
        ]

        for traversal_ref in traversal_refs:
            with pytest.raises(ValueError, match="Path traversal not allowed"):
                repo.clone_or_update(
                    "https://github.com/test/repo.git",
                    traversal_ref,
                    Path("/cache"),
                    RefType.BRANCH,
                )

    def test_blocks_ssrf_to_localhost(self) -> None:
        """Should block SSRF attempts to localhost."""
        repo = GitRepositoryImpl()

        localhost_urls = [
            "https://127.0.0.1/repo.git",
            "https://localhost/repo.git",
            "https://0.0.0.0/repo.git",
        ]

        for url in localhost_urls:
            with pytest.raises(ValueError, match="internal network or metadata service"):
                repo.clone_or_update(url, "main", Path("/cache"), RefType.BRANCH)

    def test_blocks_ssrf_to_metadata_service(self) -> None:
        """Should block SSRF to cloud metadata services."""
        repo = GitRepositoryImpl()

        metadata_urls = [
            "https://169.254.169.254/latest/meta-data.git",
            "https://metadata.google.internal/computeMetadata/v1.git",
        ]

        for url in metadata_urls:
            with pytest.raises(ValueError, match="internal network or metadata service"):
                repo.clone_or_update(url, "main", Path("/cache"), RefType.BRANCH)

    def test_blocks_ssrf_to_private_networks(self) -> None:
        """Should block SSRF to private IP ranges."""
        repo = GitRepositoryImpl()

        private_ips = [
            "https://10.0.0.1/repo.git",  # Private class A
            "https://172.16.0.1/repo.git",  # Private class B
            "https://192.168.1.1/repo.git",  # Private class C
        ]

        for url in private_ips:
            with pytest.raises(ValueError, match="internal network or metadata service"):
                repo.clone_or_update(url, "main", Path("/cache"), RefType.BRANCH)

    def test_creates_cache_dir_if_missing(self) -> None:
        """Should create cache directory if it doesn't exist."""
        repo_url = "https://github.com/test/repo.git"
        cache_dir = Path("/nonexistent/cache")

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.resolve", return_value=Path("/cache/repo")),
        ):
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            repo = GitRepositoryImpl()
            repo.clone_or_update(repo_url, "main", cache_dir, RefType.BRANCH)

            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_verifies_git_repo_before_update(self) -> None:
        """Should raise RuntimeError if path exists but isn't a git repository."""
        repo_url = "https://github.com/test/repo.git"
        cache_dir = Path("/cache")
        repo_path = Path("/cache/repo")

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: repo_path),
        ):

            def exists_side_effect(self):
                # repo_path exists but .git doesn't
                if str(self) == str(repo_path):
                    return True
                if str(self) == str(repo_path / ".git"):
                    return False
                return False

            with patch.object(Path, "exists", exists_side_effect):
                repo = GitRepositoryImpl()

                with pytest.raises(RuntimeError, match="not a git repository"):
                    repo.clone_or_update(repo_url, "main", cache_dir, RefType.BRANCH)

    def test_clone_new_repository_with_branch(self) -> None:
        """Should clone repository when it doesn't exist."""
        repo_url = "https://github.com/test/repo.git"
        git_ref = "main"
        cache_dir = Path("/cache")
        ref_type = RefType.BRANCH
        expected_path = Path("/cache/repo")

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: expected_path),
        ):
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            repo = GitRepositoryImpl()
            result = repo.clone_or_update(repo_url, git_ref, cache_dir, ref_type)

            assert result == expected_path
            # Should call git clone and git checkout
            assert mock_run.call_count == 2
            clone_call = call(
                ["git", "clone", "--no-remote-submodules", repo_url, str(expected_path)],
                cwd=None,
                check=True,
                capture_output=True,
                text=True,
            )
            checkout_call = call(
                ["git", "checkout", git_ref],
                cwd=str(expected_path),
                check=True,
                capture_output=True,
                text=True,
            )
            mock_run.assert_has_calls([clone_call, checkout_call])

    def test_update_existing_repository_branch(self) -> None:
        """Should fetch and reset when updating existing branch."""
        repo_url = "https://github.com/test/repo.git"
        git_ref = "main"
        cache_dir = Path("/cache")
        ref_type = RefType.BRANCH
        expected_path = Path("/cache/repo")

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: expected_path),
        ):

            def exists_side_effect(self):
                # cache_dir exists, repo_path exists, .git exists
                return True

            with patch.object(Path, "exists", exists_side_effect):
                # Mock git rev-parse output (current branch)
                mock_run.side_effect = [
                    Mock(returncode=0, stdout="", stderr=""),  # git fetch
                    Mock(returncode=0, stdout="main\n", stderr=""),  # git rev-parse
                    Mock(returncode=0, stdout="", stderr=""),  # git reset
                ]

                repo = GitRepositoryImpl()
                result = repo.clone_or_update(repo_url, git_ref, cache_dir, ref_type)

                assert result == expected_path
                # Should call git fetch, rev-parse, and reset
                assert mock_run.call_count == 3
                mock_run.assert_any_call(
                    ["git", "fetch", "--prune", "origin"],
                    cwd=str(expected_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )

    def test_update_existing_repository_tag(self) -> None:
        """Should only checkout when ref is a tag."""
        repo_url = "https://github.com/test/repo.git"
        git_ref = "v1.0.0"
        cache_dir = Path("/cache")
        ref_type = RefType.TAG
        expected_path = Path("/cache/repo")

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: expected_path),
        ):

            def exists_side_effect(self):
                return True

            with patch.object(Path, "exists", exists_side_effect):
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

                repo = GitRepositoryImpl()
                result = repo.clone_or_update(repo_url, git_ref, cache_dir, ref_type)

                assert result == expected_path
                # Should only call git checkout (not fetch/reset)
                mock_run.assert_called_once_with(
                    ["git", "checkout", git_ref],
                    cwd=str(expected_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )

    def test_update_existing_repository_commit(self) -> None:
        """Should only checkout when ref is a commit hash."""
        repo_url = "https://github.com/test/repo.git"
        git_ref = "abc123def456"
        cache_dir = Path("/cache")
        ref_type = RefType.COMMIT
        expected_path = Path("/cache/repo")

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: expected_path),
        ):

            def exists_side_effect(self):
                return True

            with patch.object(Path, "exists", exists_side_effect):
                mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

                repo = GitRepositoryImpl()
                result = repo.clone_or_update(repo_url, git_ref, cache_dir, ref_type)

                assert result == expected_path
                # Should only call git checkout
                mock_run.assert_called_once()

    def test_clone_raises_on_git_error(self) -> None:
        """Should raise RuntimeError when clone fails."""
        repo_url = "https://github.com/test/repo.git"
        git_ref = "main"
        cache_dir = Path("/cache")
        ref_type = RefType.BRANCH

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: Path("/cache/repo")),
        ):
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git clone", stderr="fatal: repository not found"
            )

            repo = GitRepositoryImpl()

            with pytest.raises(RuntimeError, match="Git command failed"):
                repo.clone_or_update(repo_url, git_ref, cache_dir, ref_type)

    def test_switch_branch_when_on_different_branch(self) -> None:
        """Should switch branches when current branch differs from target."""
        repo_url = "https://github.com/test/repo.git"
        git_ref = "develop"
        cache_dir = Path("/cache")
        ref_type = RefType.BRANCH
        expected_path = Path("/cache/repo")

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.resolve", side_effect=lambda: expected_path),
        ):

            def exists_side_effect(self):
                return True

            with patch.object(Path, "exists", exists_side_effect):
                # Mock: fetch succeeds, current branch is "main", checkout succeeds, reset succeeds
                mock_run.side_effect = [
                    Mock(returncode=0, stdout="", stderr=""),  # git fetch
                    Mock(returncode=0, stdout="main\n", stderr=""),  # git rev-parse
                    Mock(returncode=0, stdout="", stderr=""),  # git checkout develop
                    Mock(returncode=0, stdout="", stderr=""),  # git reset
                ]

                repo = GitRepositoryImpl()
                result = repo.clone_or_update(repo_url, git_ref, cache_dir, ref_type)

                assert result == expected_path
                # Should call fetch, rev-parse, checkout, and reset
                assert mock_run.call_count == 4
                mock_run.assert_any_call(
                    ["git", "checkout", git_ref],
                    cwd=str(expected_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )
