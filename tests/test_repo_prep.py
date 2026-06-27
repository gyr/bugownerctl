"""Tests for prepare_slfo_repo helper (repo_prep module)."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from bugownerctl.commands.repo_prep import prepare_slfo_repo
from bugownerctl.domain.ref_type import RefType

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

BASE_CONFIG: dict[str, Any] = {
    "cache_dir": "~/.cache/bugownerctl",
    "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
    "products": [
        {"version": "16.1", "branch": "slfo-main"},
        {"version": "16.0", "commit": "9d679ed"},
    ],
}


def _make_mock_git_cls(return_path: Path = Path("/cache/SLFO")) -> tuple[Mock, Mock]:
    """Build a (mock_cls, mock_instance) pair for GitRepositoryImpl."""
    mock_instance = Mock()
    mock_instance.clone_or_update.return_value = return_path
    mock_cls = Mock(return_value=mock_instance)
    return mock_cls, mock_instance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPrepareSlfoRepoRefTypes:
    """Tests that verify correct RefType and git_ref forwarded to clone_or_update."""

    def test_branch_ref_uses_branch_ref_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product with branch key → clone_or_update receives RefType.BRANCH and the branch name."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_repo_path == Path("/cache/SLFO")
        mock_git_instance.clone_or_update.assert_called_once_with(
            repo_url="gitea@src.suse.de:products/SLFO.git",
            git_ref="slfo-main",
            cache_dir=Path.home() / ".cache" / "bugownerctl",
            ref_type=RefType.BRANCH,
        )

    def test_commit_ref_uses_commit_ref_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product with commit key → clone_or_update receives RefType.COMMIT and the commit hash."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        prepare_slfo_repo(version="16.0", config_file=None)

        mock_git_instance.clone_or_update.assert_called_once_with(
            repo_url="gitea@src.suse.de:products/SLFO.git",
            git_ref="9d679ed",
            cache_dir=Path.home() / ".cache" / "bugownerctl",
            ref_type=RefType.COMMIT,
        )


class TestPrepareSlfoRepoCacheDir:
    """Tests that verify cache_dir tilde expansion and forwarding."""

    def test_cache_dir_tilde_is_expanded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache_dir with leading tilde is expanded to absolute home-based path."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        expected_cache_dir = Path.home() / ".cache" / "bugownerctl"
        assert ctx.cache_dir == expected_cache_dir
        call_kwargs = mock_git_instance.clone_or_update.call_args.kwargs
        assert call_kwargs["cache_dir"] == expected_cache_dir


class TestPrepareSlfoRepoContextFields:
    """Tests that verify the returned SlfoRepoContext fields."""

    def test_ctx_git_repo_is_same_instance_as_constructed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ctx.git_repo is the exact instance returned by GitRepositoryImpl(), not a new one."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.git_repo is mock_git_instance

    def test_ctx_slfo_repo_path_equals_clone_return(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ctx.slfo_repo_path equals the path returned by clone_or_update."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls(return_path=Path("/cache/SLFO"))
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_repo_path == Path("/cache/SLFO")

    def test_ctx_config_equals_loaded_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ctx.config is the exact dict object returned by load_config (identity check)."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.config is loaded_config


class TestPrepareSlfoRepoErrors:
    """Tests that verify ValueError is raised for invalid inputs."""

    def test_raises_version_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Requesting a version absent from products list raises ValueError."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="Version 99.9 not found in config"):
            prepare_slfo_repo(version="99.9", config_file=None)

    def test_raises_neither_branch_nor_commit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product config missing both branch and commit keys raises ValueError."""
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [
                {"version": "16.1"},  # neither branch nor commit
            ],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="has neither branch nor commit"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize("empty_ref", ["", None])
    def test_raises_empty_git_ref(
        self, empty_ref: str | None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string or None git ref raises ValueError."""
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [
                {"version": "16.1", "branch": empty_ref},
            ],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="Empty git ref for version 16.1"):
            prepare_slfo_repo(version="16.1", config_file=None)

    def test_raises_missing_slfo_git_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config without slfo_git_url raises ValueError."""
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            # slfo_git_url is absent
            "products": [
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            prepare_slfo_repo(version="16.1", config_file=None)


class TestPrepareSlfoRepoConfigFile:
    """Tests for config_file forwarding and cache_dir default."""

    def test_config_file_forwarded_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit config_file path is passed verbatim to load_config."""
        mock_load = Mock(return_value=dict(BASE_CONFIG))
        monkeypatch.setattr("bugownerctl.commands.repo_prep.load_config", mock_load)
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        prepare_slfo_repo(version="16.1", config_file=Path("/explicit/config.yaml"))

        mock_load.assert_called_once_with(Path("/explicit/config.yaml"))

    def test_cache_dir_defaults_when_key_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config without cache_dir key falls back to ~/.cache/bugownerctl."""
        loaded_config: dict[str, Any] = {
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [{"version": "16.1", "branch": "slfo-main"}],
            # cache_dir key intentionally absent
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.cache_dir == Path.home() / ".cache" / "bugownerctl"
