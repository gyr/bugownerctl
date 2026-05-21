"""Tests for query command handlers."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.query import run_maintainer, run_package
from bugowner.services.query_service import (
    PackageMaintainershipResult,
    PackageStatus,
)


class TestRunPackage:
    """Tests for run_package command handler."""

    def test_creates_repository_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create MaintainershipRepositoryImpl instance."""
        # Mock config loading
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.query.load_config", mock_load_config)

        # Mock repository class
        mock_maintainership_repo_cls = Mock()
        monkeypatch.setattr(
            "bugowner.commands.query.MaintainershipRepositoryImpl",
            mock_maintainership_repo_cls,
        )

        # Mock QueryService
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.query.QueryService", mock_service_cls)

        # Mock Path.cwd
        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        run_package(args)

        # Verify repository was instantiated
        mock_maintainership_repo_cls.assert_called_once()

    def test_creates_query_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create QueryService with repository instance."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        # Create mock repository instance
        mock_maintainership_repo = Mock()
        monkeypatch.setattr(
            "bugowner.commands.query.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maintainership_repo),
        )

        # Mock QueryService to track instantiation
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.query.QueryService", mock_service_cls)

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        run_package(args)

        # Verify QueryService created with repository
        mock_service_cls.assert_called_once_with(mock_maintainership_repo)

    def test_calls_check_package_maintainership_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call QueryService.check_package_maintainership() with correct parameters."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        run_package(args)

        # Verify check_package_maintainership called with correct parameters
        mock_service.check_package_maintainership.assert_called_once()
        call_args = mock_service.check_package_maintainership.call_args[0]
        assert call_args[0] == "test-pkg"
        assert isinstance(call_args[1], Path)
        assert isinstance(call_args[2], Path)

    def test_prints_maintained_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print MAINTAINED status with maintainers list."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with MAINTAINED result
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user1@example.com", "user2@example.com"],
        )
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "maintained" in captured.out.lower()
        assert "user1@example.com" in captured.out
        assert "user2@example.com" in captured.out

    def test_prints_whitelisted_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print WHITELISTED status."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with WHITELISTED result
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.WHITELISTED,
            maintainers=[],
        )
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "whitelisted" in captured.out.lower()

    def test_prints_not_found_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print NOT_FOUND status."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with NOT_FOUND result
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.NOT_FOUND,
            maintainers=[],
        )
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "not found" in captured.out.lower()

    def test_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful query."""
        mock_config = {
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
        }
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(package_name="test-pkg")
        result = run_package(args)

        assert result == 0


class TestRunMaintainer:
    """Tests for run_maintainer command handler."""

    def test_creates_repository_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create MaintainershipRepositoryImpl instance."""
        mock_config = {"maintainership_file": "_maintainership.json"}
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.query.load_config", mock_load_config)

        # Mock repository class
        mock_maintainership_repo_cls = Mock()
        monkeypatch.setattr(
            "bugowner.commands.query.MaintainershipRepositoryImpl",
            mock_maintainership_repo_cls,
        )

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.query.QueryService", mock_service_cls)

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(maintainer_name="user@example.com")
        run_maintainer(args)

        # Verify repository was instantiated
        mock_maintainership_repo_cls.assert_called_once()

    def test_creates_query_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create QueryService with repository instance."""
        mock_config = {"maintainership_file": "_maintainership.json"}
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        # Create mock repository instance
        mock_maintainership_repo = Mock()
        monkeypatch.setattr(
            "bugowner.commands.query.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maintainership_repo),
        )

        # Mock QueryService to track instantiation
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.query.QueryService", mock_service_cls)

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(maintainer_name="user@example.com")
        run_maintainer(args)

        # Verify QueryService created with repository
        mock_service_cls.assert_called_once_with(mock_maintainership_repo)

    def test_calls_get_packages_by_maintainer_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call QueryService.get_packages_by_maintainer() with correct parameters."""
        mock_config = {"maintainership_file": "_maintainership.json"}
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(maintainer_name="user@example.com")
        run_maintainer(args)

        # Verify get_packages_by_maintainer called with correct parameters
        mock_service.get_packages_by_maintainer.assert_called_once()
        call_args = mock_service.get_packages_by_maintainer.call_args[0]
        assert call_args[0] == "user@example.com"
        assert isinstance(call_args[1], Path)

    def test_prints_packages_list(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print packages list."""
        mock_config = {"maintainership_file": "_maintainership.json"}
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2", "pkg3"]
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(maintainer_name="user@example.com")
        run_maintainer(args)

        captured = capsys.readouterr()
        assert "user@example.com" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out
        assert "pkg3" in captured.out

    def test_prints_no_packages_found_when_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print 'No packages found' when maintainer has no packages."""
        mock_config = {"maintainership_file": "_maintainership.json"}
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with empty result
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = []
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(maintainer_name="user@example.com")
        run_maintainer(args)

        captured = capsys.readouterr()
        assert "No packages found" in captured.out or "no packages" in captured.out.lower()

    def test_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful query."""
        mock_config = {"maintainership_file": "_maintainership.json"}
        monkeypatch.setattr("bugowner.commands.query.load_config", Mock(return_value=mock_config))

        monkeypatch.setattr("bugowner.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr("bugowner.commands.query.QueryService", Mock(return_value=mock_service))

        monkeypatch.setattr("bugowner.commands.query.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(maintainer_name="user@example.com")
        result = run_maintainer(args)

        assert result == 0
