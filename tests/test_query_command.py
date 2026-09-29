"""Tests for query command handlers."""

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, call

import pytest

from bugownerctl.commands.product_context import ProductContext
from bugownerctl.commands.query import run_maintainer, run_package
from bugownerctl.repositories.remote_archive_repository import FileNotFoundAtRefError
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


# Stand-in payloads for the files served by the archive fetch.
_MAINT_CONTENT = b'{"packages": {}}'
_WHITELIST_CONTENT = b'["whitelisted-pkg"]'


def _fetch_by_name(files: dict[str, bytes]) -> Callable[[str, str, str], bytes]:
    """Build a fetch_file side effect serving `files` by name.

    Any other name raises FileNotFoundAtRefError, as the real fetch does for a
    file absent at the ref.
    """

    def fetch_file(repo_url: str, ref: str, file_path: str) -> bytes:
        if file_path in files:
            return files[file_path]
        raise FileNotFoundAtRefError(f"File {file_path!r} does not exist at ref {ref!r}")

    return fetch_file


def _stub_archive_fetch(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Replace the default RemoteArchiveRepositoryImpl with one serving the default files.

    Handlers called without an injected archive_repo construct the default
    implementation; this keeps them off the network. Returns the class mock.
    """
    archive_cls = Mock()
    archive_cls.return_value.fetch_file.side_effect = _fetch_by_name(
        {
            "_maintainership.json": _MAINT_CONTENT,
            "whitelist_maintainership.json": _WHITELIST_CONTENT,
        }
    )
    monkeypatch.setattr("bugownerctl.commands.query.RemoteArchiveRepositoryImpl", archive_cls)
    return archive_cls


def _patch_product_context(
    monkeypatch: pytest.MonkeyPatch,
    config: dict[str, Any] | None = None,
) -> tuple[Mock, ProductContext]:
    """Patch resolve_product_context and return (mock_func, fake_product_context)."""
    cfg = config if config is not None else _BASE_CONFIG
    fake_product_context = ProductContext(
        config=cfg,
        cache_dir=Path.home() / ".cache" / "bugownerctl",
        slfo_git_url=cfg["slfo_git_url"],
        ref="main",
    )
    mock_resolve = Mock(return_value=fake_product_context)
    monkeypatch.setattr("bugownerctl.commands.query.resolve_product_context", mock_resolve)
    _stub_archive_fetch(monkeypatch)
    return mock_resolve, fake_product_context


def _patch_package_service(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Patch MaintainershipRepositoryImpl and QueryService; return the service instance."""
    monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())
    mock_service = Mock()
    mock_service.check_package_maintainership.return_value = PackageMaintainershipResult(
        package_name="test-pkg",
        status=PackageStatus.NOT_FOUND,
        maintainers=[],
    )
    monkeypatch.setattr("bugownerctl.commands.query.QueryService", Mock(return_value=mock_service))
    return mock_service


def _patch_maintainer_service(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Patch MaintainershipRepositoryImpl and QueryService; return the service instance."""
    monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())
    mock_service = Mock()
    mock_service.get_packages_by_maintainer.return_value = ["pkg1"]
    monkeypatch.setattr("bugownerctl.commands.query.QueryService", Mock(return_value=mock_service))
    return mock_service


_CUSTOM_NAMES_CONFIG: dict[str, Any] = {
    **_BASE_CONFIG,
    "maintainership_file": "custom_maint.json",
    "whitelist_file": "custom_whitelist.json",
}


class TestRunPackage:
    """Tests for run_package command handler."""

    def test_creates_repository_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create MaintainershipRepositoryImpl instance."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        # Verify repository was instantiated
        mock_maintainership_repo_cls.assert_called_once()

    def test_creates_query_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create QueryService with repository instance."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        # Verify QueryService created with repository
        mock_service_cls.assert_called_once_with(mock_maintainership_repo)

    def test_calls_check_package_maintainership_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call QueryService.check_package_maintainership() with correct parameters."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        # Verify check_package_maintainership called with correct parameters
        mock_service.check_package_maintainership.assert_called_once()
        call_args = mock_service.check_package_maintainership.call_args[0]
        assert call_args[0] == "test-pkg"
        assert call_args[1] == _MAINT_CONTENT
        assert call_args[2] == _WHITELIST_CONTENT

    def test_prints_maintained_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print MAINTAINED status with maintainers list."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
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
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "whitelisted" in captured.out.lower()

    def test_prints_not_found_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print NOT_FOUND status."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        captured = capsys.readouterr()
        assert "test-pkg" in captured.out
        assert "not found" in captured.out.lower()

    def test_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful query."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        result = run_package(args)

        assert result == 0

    def test_run_package_uses_default_archive_repo_when_none_injected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without archive_repo, a RemoteArchiveRepositoryImpl is built and its bytes used."""
        _patch_product_context(monkeypatch)
        archive_cls = _stub_archive_fetch(monkeypatch)
        mock_service = _patch_package_service(monkeypatch)

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        archive_cls.assert_called_once_with()
        call_args = mock_service.check_package_maintainership.call_args[0]
        assert call_args[1] == _MAINT_CONTENT
        assert call_args[2] == _WHITELIST_CONTENT

    def test_run_package_fetches_maintainership_then_whitelist_via_archive_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both configured files are fetched at the product ref, maintainership first."""
        _patch_product_context(monkeypatch, config=_CUSTOM_NAMES_CONFIG)
        mock_service = _patch_package_service(monkeypatch)
        archive_repo = Mock()
        archive_repo.fetch_file.side_effect = _fetch_by_name(
            {
                "custom_maint.json": b'{"packages": {"fetched": {}}}',
                "custom_whitelist.json": b'["fetched-pkg"]',
            }
        )

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args, archive_repo=archive_repo)

        assert archive_repo.fetch_file.call_args_list == [
            call("https://github.com/test/repo", "main", "custom_maint.json"),
            call("https://github.com/test/repo", "main", "custom_whitelist.json"),
        ]
        call_args = mock_service.check_package_maintainership.call_args[0]
        assert call_args[1] == b'{"packages": {"fetched": {}}}'
        assert call_args[2] == b'["fetched-pkg"]'

    def test_run_package_passes_none_when_whitelist_missing_at_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A whitelist absent at the ref (FileNotFoundAtRefError) is passed on as None."""
        _patch_product_context(monkeypatch, config=_CUSTOM_NAMES_CONFIG)
        mock_service = _patch_package_service(monkeypatch)
        archive_repo = Mock()
        archive_repo.fetch_file.side_effect = _fetch_by_name({"custom_maint.json": _MAINT_CONTENT})

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args, archive_repo=archive_repo)

        call_args = mock_service.check_package_maintainership.call_args[0]
        assert call_args[1] == _MAINT_CONTENT
        assert call_args[2] is None

    def test_run_package_propagates_other_whitelist_fetch_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A plain ValueError on the whitelist fetch is not swallowed as a missing file."""
        _patch_product_context(monkeypatch)
        mock_service = _patch_package_service(monkeypatch)
        archive_repo = Mock()
        archive_repo.fetch_file.side_effect = [
            _MAINT_CONTENT,
            ValueError("Remote does not serve ref 'main'"),
        ]

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        with pytest.raises(ValueError, match="does not serve ref"):
            run_package(args, archive_repo=archive_repo)

        mock_service.check_package_maintainership.assert_not_called()

    def test_run_package_propagates_missing_maintainership_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A maintainership file absent at the ref propagates; the whitelist is never fetched."""
        _patch_product_context(monkeypatch, config=_CUSTOM_NAMES_CONFIG)
        mock_service = _patch_package_service(monkeypatch)
        archive_repo = Mock()
        archive_repo.fetch_file.side_effect = _fetch_by_name(
            {"custom_whitelist.json": _WHITELIST_CONTENT}
        )

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        with pytest.raises(FileNotFoundAtRefError, match="custom_maint.json"):
            run_package(args, archive_repo=archive_repo)

        archive_repo.fetch_file.assert_called_once_with(
            "https://github.com/test/repo", "main", "custom_maint.json"
        )
        mock_service.check_package_maintainership.assert_not_called()

    def test_run_package_forwards_version_and_config_to_resolve_product_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should forward version and config args to resolve_product_context."""
        mock_resolve, _ = _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(package_name="test-pkg", release="16.1", config=None)
        run_package(args)

        mock_resolve.assert_called_once_with("16.1", None)


class TestRunMaintainer:
    """Tests for run_maintainer command handler."""

    def test_creates_repository_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create MaintainershipRepositoryImpl instance."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args)

        # Verify repository was instantiated
        mock_maintainership_repo_cls.assert_called_once()

    def test_creates_query_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create QueryService with repository instance."""
        _patch_product_context(monkeypatch)

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

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args)

        # Verify QueryService created with repository
        mock_service_cls.assert_called_once_with(mock_maintainership_repo)

    def test_calls_get_packages_by_maintainer_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call QueryService.get_packages_by_maintainer() with correct parameters."""
        _patch_product_context(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args)

        # Verify get_packages_by_maintainer called with correct parameters
        mock_service.get_packages_by_maintainer.assert_called_once()
        call_args = mock_service.get_packages_by_maintainer.call_args[0]
        assert call_args[0] == "user@example.com"
        assert call_args[1] == _MAINT_CONTENT

    def test_prints_packages_list(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print packages list."""
        _patch_product_context(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2", "pkg3"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
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
        _patch_product_context(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        # Mock QueryService with empty result
        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = []
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args)

        captured = capsys.readouterr()
        assert "No packages found" in captured.out or "no packages" in captured.out.lower()

    def test_returns_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code after successful query."""
        _patch_product_context(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        result = run_maintainer(args)

        assert result == 0

    def test_run_maintainer_uses_default_archive_repo_when_none_injected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without archive_repo, a RemoteArchiveRepositoryImpl is built and its bytes used."""
        _patch_product_context(monkeypatch)
        archive_cls = _stub_archive_fetch(monkeypatch)
        mock_service = _patch_maintainer_service(monkeypatch)

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args)

        archive_cls.assert_called_once_with()
        call_args = mock_service.get_packages_by_maintainer.call_args[0]
        assert call_args[1] == _MAINT_CONTENT

    def test_run_maintainer_fetches_only_maintainership_via_archive_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the configured maintainership file is fetched at the product ref."""
        _patch_product_context(monkeypatch, config=_CUSTOM_NAMES_CONFIG)
        mock_service = _patch_maintainer_service(monkeypatch)
        archive_repo = Mock()
        archive_repo.fetch_file.return_value = b'{"packages": {"fetched": {}}}'

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args, archive_repo=archive_repo)

        archive_repo.fetch_file.assert_called_once_with(
            "https://github.com/test/repo", "main", "custom_maint.json"
        )
        call_args = mock_service.get_packages_by_maintainer.call_args[0]
        assert call_args[1] == b'{"packages": {"fetched": {}}}'

    def test_run_maintainer_propagates_missing_maintainership_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A maintainership file absent at the ref propagates out of the handler."""
        _patch_product_context(monkeypatch, config=_CUSTOM_NAMES_CONFIG)
        mock_service = _patch_maintainer_service(monkeypatch)
        archive_repo = Mock()
        archive_repo.fetch_file.side_effect = _fetch_by_name({})

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        with pytest.raises(FileNotFoundAtRefError, match="custom_maint.json"):
            run_maintainer(args, archive_repo=archive_repo)

        mock_service.get_packages_by_maintainer.assert_not_called()

    def test_run_maintainer_forwards_version_and_config_to_resolve_product_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should forward version and config args to resolve_product_context."""
        mock_resolve, _ = _patch_product_context(monkeypatch)

        monkeypatch.setattr("bugownerctl.commands.query.MaintainershipRepositoryImpl", Mock())

        mock_service = Mock()
        mock_service.get_packages_by_maintainer.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugownerctl.commands.query.QueryService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(maintainer_name="user@example.com", release="16.1", config=None)
        run_maintainer(args)

        mock_resolve.assert_called_once_with("16.1", None)
