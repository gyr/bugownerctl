"""Tests for query command handlers."""

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from bugownerctl.commands.query import run_maintainer, run_package
from bugownerctl.commands.repo_prep import SlfoRepoContext
from bugownerctl.services.query_service import (
    PackageMaintainershipResult,
    PackageStatus,
)

_BASE_CONFIG: dict[str, Any] = {
    "cache_dir": "~/.cache/bugownerctl",
    "slfo_git_url": "https://github.com/test/repo",
    "maintainership_file": "_maintainership.json",
    "whitelist_file": "whitelist_maintainership.json",
    "products": [{"version": "16.1", "branch": "main"}],
}


def _patch_prep(
    monkeypatch: pytest.MonkeyPatch,
    slfo_repo_path: Path = Path("/cache/SLFO"),
    config: dict[str, Any] | None = None,
) -> tuple[Mock, SlfoRepoContext]:
    """Patch prepare_slfo_repo and return (mock_func, fake_slfo_context)."""
    cfg = config if config is not None else _BASE_CONFIG
    fake_slfo_context = SlfoRepoContext(
        config=cfg,
        cache_dir=Path.home() / ".cache" / "bugownerctl",
        slfo_repo_path=slfo_repo_path,
        git_repo=Mock(),
    )
    mock_prep = Mock(return_value=fake_slfo_context)
    monkeypatch.setattr("bugownerctl.commands.query.prepare_slfo_repo", mock_prep)
    return mock_prep, fake_slfo_context


class TestRunPackage:
    """Tests for run_package command handler."""

    def test_creates_repository_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create MaintainershipRepositoryImpl instance."""
        _patch_prep(monkeypatch)

        # Mock repository class
        mock_maintainership_repo_cls = Mock()
        monkeypatch.setattr(
            "bugownerctl.commands.query.MaintainershipRepositoryImpl",
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
        monkeypatch.setattr("bugownerctl.commands.query.QueryService", mock_service_cls)

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        run_package(args)

        # Verify repository was instantiated
        mock_maintainership_repo_cls.assert_called_once()

    def test_creates_query_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create QueryService with repository instance."""
        _patch_prep(monkeypatch)

        # Create mock repository instance
        mock_maintainership_repo = Mock()
        monkeypatch.setattr(
            "bugownerctl.commands.query.MaintainershipRepositoryImpl",
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
        monkeypatch.setattr("bugownerctl.commands.query.QueryService", mock_service_cls)

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        run_package(args)

        # Verify QueryService created with repository
        mock_service_cls.assert_called_once_with(mock_maintainership_repo)

    def test_calls_check_package_maintainership_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call QueryService.check_package_maintainership() with correct parameters."""
        _patch_prep(monkeypatch)

        # Mock repositories
        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
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
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with MAINTAINED result
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user1@example.com", "user2@example.com"],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
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
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with WHITELISTED result
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.WHITELISTED,
            maintainers=[],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "whitelisted" in captured.out.lower()

    def test_prints_not_found_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print NOT_FOUND status."""
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with NOT_FOUND result
        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.NOT_FOUND,
            maintainers=[],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "not found" in captured.out.lower()

    def test_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful query."""
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        result = run_package(args)

        assert result == 0

    def test_run_package_resolves_both_files_under_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should resolve both maintainership and whitelist files under slfo_repo_path."""
        _patch_prep(monkeypatch, slfo_repo_path=Path("/cache/SLFO"))

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        run_package(args)

        call_args = mock_service.check_package_maintainership.call_args[0]
        assert call_args[1] == Path("/cache/SLFO/_maintainership.json")
        assert call_args[2] == Path("/cache/SLFO/whitelist_maintainership.json")

    def test_run_package_forwards_version_and_config_to_prepare_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should forward version and config args to prepare_slfo_repo."""
        mock_prep, _ = _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
            package_name="test-pkg",
            status=PackageStatus.MAINTAINED,
            maintainers=["user@example.com"],
        )
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(package_name="test-pkg", version="16.1", config=None)
        run_package(args)

        mock_prep.assert_called_once_with("16.1", None)


class TestRunMaintainer:
    """Tests for run_maintainer command handler."""

    def test_creates_repository_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create MaintainershipRepositoryImpl instance."""
        _patch_prep(monkeypatch)

        # Mock repository class
        mock_maintainership_repo_cls = Mock()
        monkeypatch.setattr(
            "bugownerctl.commands.query.MaintainershipRepositoryImpl",
            mock_maintainership_repo_cls,
        )

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugownerctl.commands.query.QueryService", mock_service_cls)

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
        run_maintainer(args)

        # Verify repository was instantiated
        mock_maintainership_repo_cls.assert_called_once()

    def test_creates_query_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create QueryService with repository instance."""
        _patch_prep(monkeypatch)

        # Create mock repository instance
        mock_maintainership_repo = Mock()
        monkeypatch.setattr(
            "bugownerctl.commands.query.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maintainership_repo),
        )

        # Mock QueryService to track instantiation
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugownerctl.commands.query.QueryService", mock_service_cls)

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
        run_maintainer(args)

        # Verify QueryService created with repository
        mock_service_cls.assert_called_once_with(mock_maintainership_repo)

    def test_calls_get_packages_by_maintainer_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call QueryService.get_packages_by_maintainer() with correct parameters."""
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
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
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2", "pkg3"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
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
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with empty result
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = []
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
        run_maintainer(args)

        captured = capsys.readouterr()
        assert "No packages found" in captured.out or "no packages" in captured.out.lower()

    def test_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful query."""
        _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
        result = run_maintainer(args)

        assert result == 0

    def test_run_maintainer_resolves_only_maintainership_under_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should resolve maintainership file under slfo_repo_path."""
        _patch_prep(monkeypatch, slfo_repo_path=Path("/cache/SLFO"))

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
        run_maintainer(args)

        call_args = mock_service.get_packages_by_maintainer.call_args[0]
        assert call_args[1] == Path("/cache/SLFO/_maintainership.json")

    def test_run_maintainer_forwards_version_and_config_to_prepare_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should forward version and config args to prepare_slfo_repo."""
        mock_prep, _ = _patch_prep(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", version="16.1", config=None)
        run_maintainer(args)

        mock_prep.assert_called_once_with("16.1", None)
