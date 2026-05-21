"""Tests for whitelist command handler."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.whitelist import run_update
from bugowner.services.whitelist_service import WhitelistUpdateResult


class TestWhitelistCommand:
    """Tests for whitelist command handler."""

    def test_run_update_creates_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create repository implementation instances."""
        # Mock config loading
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.whitelist.load_config", mock_load_config)

        # Mock repository classes
        mock_maintainership_repo_cls = Mock()
        mock_git_repo_cls = Mock()

        monkeypatch.setattr(
            "bugowner.commands.whitelist.MaintainershipRepositoryImpl",
            mock_maintainership_repo_cls,
        )
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", mock_git_repo_cls)

        # Mock WhitelistService
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=[], removed=[], in_maintainership_not_submodule=[]
        )
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.whitelist.WhitelistService", mock_service_cls)

        # Mock Path operations
        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        run_update(args)

        # Verify repositories were instantiated
        mock_maintainership_repo_cls.assert_called_once()
        mock_git_repo_cls.assert_called_once()

    def test_run_update_creates_whitelist_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create WhitelistService with repository instances."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Create mock repository instances
        mock_maintainership_repo = Mock()
        mock_git_repo = Mock()

        monkeypatch.setattr(
            "bugowner.commands.whitelist.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maintainership_repo),
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )

        # Mock WhitelistService to track instantiation
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=[], removed=[], in_maintainership_not_submodule=[]
        )
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.whitelist.WhitelistService", mock_service_cls)

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        run_update(args)

        # Verify WhitelistService created with both repositories
        mock_service_cls.assert_called_once_with(mock_maintainership_repo, mock_git_repo)

    def test_run_update_calls_update_whitelist_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call WhitelistService.update_whitelist() with correct parameters."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())

        # Mock WhitelistService
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=[], removed=[], in_maintainership_not_submodule=[]
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        run_update(args)

        # Verify update_whitelist called with correct parameters
        mock_service.update_whitelist.assert_called_once()
        call_args = mock_service.update_whitelist.call_args[1]
        assert isinstance(call_args["repo_path"], Path)
        assert isinstance(call_args["maintainership_file"], Path)
        assert isinstance(call_args["whitelist_file"], Path)

    def test_run_update_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful update."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())

        # Mock WhitelistService with results
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=["pkg1"], removed=["pkg2"], in_maintainership_not_submodule=["pkg3"]
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        result = run_update(args)

        assert result == 0

    def test_run_update_prints_added_packages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print added packages to stdout."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())

        # Mock WhitelistService
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=["pkg1", "pkg2"], removed=[], in_maintainership_not_submodule=[]
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        run_update(args)

        captured = capsys.readouterr()
        assert "Added to whitelist" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out

    def test_run_update_prints_removed_packages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print removed packages to stdout."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())

        # Mock WhitelistService
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=[], removed=["pkg1", "pkg2"], in_maintainership_not_submodule=[]
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        run_update(args)

        captured = capsys.readouterr()
        assert "Removed from whitelist" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out

    def test_run_update_prints_invalid_packages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print packages in maintainership but not in submodules."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())

        # Mock WhitelistService
        mock_service = Mock()
        mock_service.update_whitelist.return_value = WhitelistUpdateResult(
            added=[], removed=[], in_maintainership_not_submodule=["pkg1", "pkg2"]
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace()
        run_update(args)

        captured = capsys.readouterr()
        assert "In maintainership but not in submodules" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out
