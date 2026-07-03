"""Tests for check command handlers (maintainership and whitelist)."""

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from bugownerctl.commands.check import run_maintainership, run_users, run_whitelist
from bugownerctl.commands.repo_prep import SlfoRepoContext
from bugownerctl.services.user_validation_service import UserValidationResult
from bugownerctl.services.validation_service import ValidationResult
from bugownerctl.services.whitelist_service import WhitelistCheckResult

# ---------------------------------------------------------------------------
# Shared fixtures for maintainership tests
# ---------------------------------------------------------------------------

_MAINT_BASE_CONFIG: dict[str, Any] = {
    "cache_dir": "~/.cache/bugownerctl",
    "slfo_git_url": "https://github.com/test/repo",
    "maintainership_file": "_maintainership.json",
    "products": [{"version": "16.1", "branch": "main"}],
}


def _empty_validation_result() -> ValidationResult:
    """Build a ValidationResult with no findings."""
    return ValidationResult(
        orphan_packages=[],
        maintained_packages_without_submodule=[],
        shipped_not_in_submodule=[],
    )


def _patch_maint_prep(
    monkeypatch: pytest.MonkeyPatch,
    slfo_repo_path: Path = Path("/cache/SLFO"),
    config: dict[str, Any] | None = None,
) -> tuple[Mock, SlfoRepoContext]:
    """Patch prepare_slfo_repo and return (mock_func, fake_slfo_context)."""
    cfg = config if config is not None else _MAINT_BASE_CONFIG
    fake_slfo_context = SlfoRepoContext(
        config=cfg,
        cache_dir=Path.home() / ".cache" / "bugownerctl",
        slfo_repo_path=slfo_repo_path,
        git_repo=Mock(),
    )
    mock_prep = Mock(return_value=fake_slfo_context)
    monkeypatch.setattr("bugownerctl.commands.check.prepare_slfo_repo", mock_prep)
    return mock_prep, fake_slfo_context


def _patch_maint_other_repos(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    """Patch the 4 repos check.py constructs for maintainership. Returns a dict of mock classes."""
    mock_maint_cls = Mock()
    mock_meta_cls = Mock()
    mock_bulk_cls = Mock()
    mock_over_cls = Mock()

    monkeypatch.setattr("bugownerctl.commands.check.MaintainershipRepositoryImpl", mock_maint_cls)
    monkeypatch.setattr("bugownerctl.commands.check.RepoMetadataRepositoryImpl", mock_meta_cls)
    monkeypatch.setattr("bugownerctl.commands.check.ObsBulkSourceInfoRepositoryImpl", mock_bulk_cls)
    monkeypatch.setattr("bugownerctl.commands.check.NameOverridesRepositoryImpl", mock_over_cls)

    return {
        "maintainership": mock_maint_cls,
        "metadata": mock_meta_cls,
        "bulk_map": mock_bulk_cls,
        "overrides": mock_over_cls,
    }


def _patch_validation_service(
    monkeypatch: pytest.MonkeyPatch, result: ValidationResult | None = None
) -> tuple[Mock, Mock]:
    """Patch ValidationService and return (cls_mock, instance_mock)."""
    instance = Mock()
    instance.validate_all.return_value = (
        result if result is not None else _empty_validation_result()
    )
    cls = Mock(return_value=instance)
    monkeypatch.setattr("bugownerctl.commands.check.ValidationService", cls)
    return cls, instance


# ---------------------------------------------------------------------------
# Shared fixtures for whitelist tests
# ---------------------------------------------------------------------------

_WHITELIST_BASE_CONFIG: dict[str, Any] = {
    "cache_dir": "~/.cache/bugownerctl",
    "slfo_git_url": "https://github.com/test/repo",
    "whitelist_file": "whitelist_maintainership.json",
    "products": [{"version": "16.1", "branch": "main"}],
}


def _empty_whitelist_result() -> WhitelistCheckResult:
    """Build a WhitelistCheckResult with no inconsistencies."""
    return WhitelistCheckResult(inconsistent_packages=[])


def _patch_whitelist_prep(
    monkeypatch: pytest.MonkeyPatch,
    slfo_repo_path: Path = Path("/cache/SLFO"),
    config: dict[str, Any] | None = None,
) -> tuple[Mock, SlfoRepoContext]:
    """Patch prepare_slfo_repo and return (mock_func, fake_slfo_context)."""
    cfg = config if config is not None else _WHITELIST_BASE_CONFIG
    fake_slfo_context = SlfoRepoContext(
        config=cfg,
        cache_dir=Path.home() / ".cache" / "bugownerctl",
        slfo_repo_path=slfo_repo_path,
        git_repo=Mock(),
    )
    mock_prep = Mock(return_value=fake_slfo_context)
    monkeypatch.setattr("bugownerctl.commands.check.prepare_slfo_repo", mock_prep)
    return mock_prep, fake_slfo_context


def _patch_whitelist_other_repos(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    """Patch the 4 repos check.py constructs for whitelist.

    Returns a dict of mock classes. Note: whitelist path does NOT construct
    GitRepositoryImpl directly after the refactor — git_repo comes from slfo_context.
    """
    mock_maint_cls = Mock()
    mock_meta_cls = Mock()
    mock_meta_cls.return_value.download_primary_metadata.return_value = Path(
        "/cache/primary.xml.gz"
    )
    mock_meta_cls.return_value.parse_source_packages.return_value = {"pkg1"}
    mock_bulk_cls = Mock()
    mock_over_cls = Mock()

    monkeypatch.setattr("bugownerctl.commands.check.MaintainershipRepositoryImpl", mock_maint_cls)
    monkeypatch.setattr("bugownerctl.commands.check.RepoMetadataRepositoryImpl", mock_meta_cls)
    monkeypatch.setattr("bugownerctl.commands.check.ObsBulkSourceInfoRepositoryImpl", mock_bulk_cls)
    monkeypatch.setattr("bugownerctl.commands.check.NameOverridesRepositoryImpl", mock_over_cls)

    return {
        "maintainership": mock_maint_cls,
        "metadata": mock_meta_cls,
        "bulk_map": mock_bulk_cls,
        "overrides": mock_over_cls,
    }


def _patch_services(
    monkeypatch: pytest.MonkeyPatch, result: WhitelistCheckResult | None = None
) -> dict[str, Mock]:
    """Patch ValidationService and WhitelistService. Returns the mocks."""
    mock_validation_service = Mock()
    mock_validation_cls = Mock(return_value=mock_validation_service)
    monkeypatch.setattr("bugownerctl.commands.check.ValidationService", mock_validation_cls)

    mock_whitelist_service = Mock()
    mock_whitelist_service.check_whitelist.return_value = (
        result if result is not None else _empty_whitelist_result()
    )
    mock_whitelist_cls = Mock(return_value=mock_whitelist_service)
    monkeypatch.setattr("bugownerctl.commands.check.WhitelistService", mock_whitelist_cls)

    return {
        "validation_cls": mock_validation_cls,
        "validation_service": mock_validation_service,
        "whitelist_cls": mock_whitelist_cls,
        "whitelist_service": mock_whitelist_service,
    }


# ---------------------------------------------------------------------------
# Tests for run_maintainership (formerly validate command)
# ---------------------------------------------------------------------------


class TestCheckMaintainershipCommand:
    """Tests for check maintainership command handler."""

    def test_run_creates_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create all repository implementation instances."""
        mock_prep, _ = _patch_maint_prep(monkeypatch)
        repos = _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        repos["maintainership"].assert_called_once()
        repos["metadata"].assert_called_once()
        repos["bulk_map"].assert_called_once()
        repos["overrides"].assert_called_once()

    def test_run_creates_validation_service_with_new_repos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create ValidationService with new bulk_map+overrides repos."""
        mock_prep, fake_slfo_context = _patch_maint_prep(monkeypatch)

        mock_maint_inst = Mock()
        mock_meta_inst = Mock()
        mock_bulk_inst = Mock()
        mock_over_inst = Mock()

        monkeypatch.setattr(
            "bugownerctl.commands.check.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maint_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_meta_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.ObsBulkSourceInfoRepositoryImpl",
            Mock(return_value=mock_bulk_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.NameOverridesRepositoryImpl",
            Mock(return_value=mock_over_inst),
        )

        cls_mock, _ = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        cls_mock.assert_called_once_with(
            mock_maint_inst,
            fake_slfo_context.git_repo,
            mock_meta_inst,
            bulk_map_repo=mock_bulk_inst,
            overrides_repo=mock_over_inst,
        )

    def test_run_calls_validate_all_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call ValidationService.validate_all() with correct parameters."""
        mock_prep, fake_slfo_context = _patch_maint_prep(monkeypatch)
        repos = _patch_maint_other_repos(monkeypatch)
        repos["metadata"].return_value.download_primary_metadata.return_value = Path(
            "/test/cache/primary.xml.gz"
        )

        _, instance = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        # Verify download_primary_metadata called with version
        repos["metadata"].return_value.download_primary_metadata.assert_called_once()
        download_call_args = repos["metadata"].return_value.download_primary_metadata.call_args[0]
        assert download_call_args[0] == "16.1"

        # Verify validate_all called with correct parameters
        instance.validate_all.assert_called_once()
        call_args = instance.validate_all.call_args[1]
        assert isinstance(call_args["maintainership_file"], Path)
        assert isinstance(call_args["repo_metadata_file"], Path)
        assert isinstance(call_args["git_dir"], Path)
        # cache_dir must come from config (expanded), NOT from CWD
        expected_cache_dir = Path("~/.cache/bugownerctl").expanduser()
        assert call_args["cache_dir"] == expected_cache_dir
        # overrides_file must resolve via importlib.resources (lives under
        # the installed package's data dir); just confirm it's a Path and
        # points at the shipped basename.
        assert isinstance(call_args["overrides_file"], Path)
        assert call_args["overrides_file"].name == "false_positives_overrides.json"

    def test_run_returns_zero_when_no_issues_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code when validation finds no issues."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        result = run_maintainership(args)

        assert result == 0

    def test_run_returns_two_when_orphan_packages_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 2 exit code when orphan packages found."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=["orphan-pkg1", "orphan-pkg2"],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=[],
            ),
        )

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        result = run_maintainership(args)

        assert result == 2

    def test_run_returns_zero_for_shipped_not_in_submodule_without_strict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shipped_not_in_submodule alone does NOT gate without --strict."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=[],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=["pkg1"],
            ),
        )
        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        result = run_maintainership(args)
        assert result == 0

    def test_run_returns_two_for_shipped_not_in_submodule_with_strict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shipped_not_in_submodule gates when --strict is set."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=[],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=["pkg1"],
            ),
        )
        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=True
        )
        result = run_maintainership(args)
        assert result == 2

    def test_run_prints_orphan_packages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print orphan packages to stdout."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=["pkg1", "pkg2"],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=[],
            ),
        )

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        captured = capsys.readouterr()
        assert "Orphan packages" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out

    def test_output_format_matches_old_script_with_info_prefix_and_set_labels(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print output with INFO prefix and SET labels matching old script format."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=["orphan1", "orphan2"],
                maintained_packages_without_submodule=["maintained1", "maintained2"],
                shipped_not_in_submodule=["shipped1"],
            ),
        )

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        captured = capsys.readouterr()
        output = captured.out

        # Verify INFO prefix on all output lines
        assert "INFO: Found 2 maintained packages without an equivalent git submodule." in output
        assert "INFO: Maintained packages without an equivalent git submodule:" in output
        assert "INFO: - maintained1" in output
        assert "INFO: - maintained2" in output

        assert "INFO: Found 1 shipped packages not found in git submodule." in output
        assert "INFO: Shipped packages not found in git submodule:" in output
        assert "INFO: - shipped1" in output

        assert "INFO: Found 2 orphan packages." in output
        assert "INFO: Orphan packages:" in output
        assert "INFO: - orphan1" in output
        assert "INFO: - orphan2" in output

        # Verify no emoji in output
        assert "[OK]" not in output  # placeholder for check mark
        # Original assertions used emoji characters; keep ASCII-only here.

    def test_output_format_shows_empty_state_messages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print INFO messages for empty result sets."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        captured = capsys.readouterr()
        output = captured.out

        assert (
            "INFO: No maintained packages without an equivalent git submodule were found." in output
        )
        assert "INFO: No orphan packages found." in output

    def test_validate_prints_unresolved_names_section(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print the unresolved-names section when unresolved_names is non-empty."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=[],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=["mystery-pkg"],
                unresolved_names=["mystery-pkg"],
            ),
        )

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" in captured.out
        assert "mystery-pkg" in captured.out

    def test_validate_omits_unresolved_section_when_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should NOT print the unresolved-names section when unresolved_names is empty."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(monkeypatch)  # default: empty result, unresolved=[]

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" not in captured.out

    def test_run_forwards_version_and_config_to_prepare_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should forward args.version and args.config to prepare_slfo_repo."""
        mock_prep, _ = _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        config_path = Path("/custom/config.yaml")
        args = argparse.Namespace(
            version="16.1", debug=False, config=config_path, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        mock_prep.assert_called_once_with("16.1", config_path)

    def test_run_passes_force_refresh_false_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass force_refresh=False to validate_all when --refresh-bulk-map not set."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _, instance = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        call_kwargs = instance.validate_all.call_args[1]
        assert call_kwargs.get("force_refresh") is False

    def test_run_passes_force_refresh_true_when_flag_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass force_refresh=True to validate_all when --refresh-bulk-map is set."""
        _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _, instance = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=True, strict=False
        )
        run_maintainership(args)

        call_kwargs = instance.validate_all.call_args[1]
        assert call_kwargs.get("force_refresh") is True

    def test_run_forwards_none_config_to_prepare_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass None to prepare_slfo_repo() when args.config is None."""
        mock_prep, _ = _patch_maint_prep(monkeypatch)
        _patch_maint_other_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        mock_prep.assert_called_once_with("16.1", None)

    def test_run_uses_maintainership_file_from_cloned_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use _maintainership.json from cloned SLFO repo, not cwd."""
        slfo_repo_path = Path("/cache/bugownerctl/SLFO")
        mock_prep, fake_slfo_context = _patch_maint_prep(monkeypatch, slfo_repo_path=slfo_repo_path)
        _patch_maint_other_repos(monkeypatch)
        _, instance = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", debug=False, config=None, refresh_bulk_map=False, strict=False
        )
        run_maintainership(args)

        instance.validate_all.assert_called_once()
        call_kwargs = instance.validate_all.call_args[1]
        expected_maintainership = slfo_repo_path / "_maintainership.json"
        assert call_kwargs["maintainership_file"] == expected_maintainership
        assert call_kwargs["git_dir"] == slfo_repo_path


# ---------------------------------------------------------------------------
# Tests for run_whitelist (formerly whitelist-check command)
# ---------------------------------------------------------------------------


class TestCheckWhitelistCommand:
    """Tests for check whitelist command handler."""

    def test_run_creates_all_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create all repository implementation instances (no git_cls after refactor)."""
        _patch_whitelist_prep(monkeypatch)
        repos = _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        repos["maintainership"].assert_called_once()
        repos["metadata"].assert_called_once()
        repos["bulk_map"].assert_called_once()
        repos["overrides"].assert_called_once()

    def test_run_creates_validation_service_with_new_repos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create ValidationService receiving fake_slfo_context.git_repo."""
        mock_prep, fake_slfo_context = _patch_whitelist_prep(monkeypatch)

        mock_maint_inst = Mock()
        mock_meta_inst = Mock()
        mock_meta_inst.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        mock_meta_inst.parse_source_packages.return_value = {"pkg1"}
        mock_bulk_inst = Mock()
        mock_over_inst = Mock()

        monkeypatch.setattr(
            "bugownerctl.commands.check.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maint_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_meta_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.ObsBulkSourceInfoRepositoryImpl",
            Mock(return_value=mock_bulk_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.NameOverridesRepositoryImpl",
            Mock(return_value=mock_over_inst),
        )

        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        # ValidationService called with slfo_context.git_repo (not a fresh GitRepositoryImpl).
        services["validation_cls"].assert_called_once_with(
            mock_maint_inst,
            fake_slfo_context.git_repo,
            mock_meta_inst,
            bulk_map_repo=mock_bulk_inst,
            overrides_repo=mock_over_inst,
        )

    def test_run_creates_whitelist_service_with_validation_dependency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create WhitelistService with ValidationService dependency."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        services["whitelist_cls"].assert_called_once_with(services["validation_service"])

    def test_run_calls_check_whitelist_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call WhitelistService.check_whitelist() with correct parameters."""
        slfo_repo_path = Path("/cache/SLFO")
        mock_prep, fake_slfo_context = _patch_whitelist_prep(
            monkeypatch, slfo_repo_path=slfo_repo_path
        )

        repos = _patch_whitelist_other_repos(monkeypatch)
        repos["metadata"].return_value.parse_source_packages.return_value = {
            "pkg1",
            "pkg2",
            "pkg3",
        }
        fake_slfo_context.git_repo.list_submodules.return_value = ["pkg1", "pkg2"]

        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        services["whitelist_service"].check_whitelist.assert_called_once()
        call_args = services["whitelist_service"].check_whitelist.call_args[1]
        # whitelist_file must come from slfo_repo_path
        assert call_args["whitelist_file"] == slfo_repo_path / "whitelist_maintainership.json"
        assert call_args["shipped_packages"] == {"pkg1", "pkg2", "pkg3"}
        assert call_args["submodules"] == ["pkg1", "pkg2"]
        # cache_dir must come from fake_slfo_context
        assert call_args["cache_dir"] == fake_slfo_context.cache_dir
        # overrides_file must resolve via importlib.resources to the shipped JSON
        assert isinstance(call_args["overrides_file"], Path)
        assert call_args["overrides_file"].name == "false_positives_overrides.json"

    def test_run_returns_zero_when_no_inconsistencies_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 0 exit code when no inconsistencies found."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        result = run_whitelist(args)

        assert result == 0

    def test_run_returns_two_when_inconsistencies_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 2 exit code when inconsistencies found."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(inconsistent_packages=["pkg1", "pkg2"]),
        )

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        result = run_whitelist(args)

        assert result == 2

    def test_run_returns_zero_for_unresolved_names_without_strict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """unresolved_names alone does NOT gate without --strict."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(inconsistent_packages=[], unresolved_names=["mystery"]),
        )
        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        result = run_whitelist(args)
        assert result == 0

    def test_run_returns_two_for_unresolved_names_with_strict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """unresolved_names gates when --strict is set."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(inconsistent_packages=[], unresolved_names=["mystery"]),
        )
        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=True)
        result = run_whitelist(args)
        assert result == 2

    def test_run_prints_inconsistent_packages_with_info_prefix(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print inconsistent packages with INFO prefix."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(inconsistent_packages=["apache2", "kernel-source"]),
        )

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        captured = capsys.readouterr()
        assert "INFO: Found 2 packages that are BOTH shipped AND whitelisted" in captured.out
        assert "INFO: Inconsistent packages" in captured.out
        assert "INFO: - apache2" in captured.out
        assert "INFO: - kernel-source" in captured.out

    def test_run_prints_success_message_when_no_issues(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print success message with INFO prefix when no issues."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        captured = capsys.readouterr()
        assert "INFO: No inconsistencies found" in captured.out

    def test_whitelist_prints_unresolved_names_section(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print the unresolved-names section when unresolved_names is non-empty."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(
                inconsistent_packages=[],
                unresolved_names=["mystery-pkg"],
            ),
        )

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" in captured.out
        assert "mystery-pkg" in captured.out

    def test_verdict_printed_after_unresolved_section_when_no_inconsistencies(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Verdict line must be printed LAST, after the unresolved-names diagnostic."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(
                inconsistent_packages=[],
                unresolved_names=["mystery-pkg"],
            ),
        )

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        captured = capsys.readouterr()
        unresolved_idx = captured.out.index("Names with no source mapping")
        verdict_idx = captured.out.index("No inconsistencies found")
        assert unresolved_idx < verdict_idx, (
            f"Verdict must come AFTER unresolved-names section, got:\n{captured.out}"
        )

    def test_verdict_printed_after_unresolved_section_when_inconsistencies_present(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Inconsistency verdict block must come LAST, after the unresolved-names diagnostic."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(
                inconsistent_packages=["apache2"],
                unresolved_names=["mystery-pkg"],
            ),
        )

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        captured = capsys.readouterr()
        unresolved_idx = captured.out.index("Names with no source mapping")
        verdict_idx = captured.out.index("BOTH shipped AND whitelisted")
        assert unresolved_idx < verdict_idx, (
            f"Verdict must come AFTER unresolved-names section, got:\n{captured.out}"
        )

    def test_whitelist_omits_unresolved_section_when_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should NOT print the unresolved-names section when unresolved_names is empty."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)  # default: empty result, unresolved=[]

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" not in captured.out

    def test_run_forwards_version_and_config_to_prepare_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should forward args.version and args.config to prepare_slfo_repo."""
        mock_prep, _ = _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)

        config_path = Path("/custom/config.yaml")
        args = argparse.Namespace(
            version="16.1", config=config_path, refresh_bulk_map=False, strict=False
        )
        run_whitelist(args)

        mock_prep.assert_called_once_with("16.1", config_path)

    def test_run_forwards_none_config_to_prepare_slfo_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass None to prepare_slfo_repo() when args.config is None."""
        mock_prep, _ = _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        mock_prep.assert_called_once_with("16.1", None)

    def test_run_passes_force_refresh_false_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass force_refresh=False to check_whitelist when --refresh-bulk-map not set."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        call_kwargs = services["whitelist_service"].check_whitelist.call_args[1]
        assert call_kwargs.get("force_refresh") is False

    def test_run_passes_force_refresh_true_when_flag_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass force_refresh=True to check_whitelist when --refresh-bulk-map is set."""
        _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=True, strict=False)
        run_whitelist(args)

        call_kwargs = services["whitelist_service"].check_whitelist.call_args[1]
        assert call_kwargs.get("force_refresh") is True

    def test_run_calls_list_submodules_on_ctx_git_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call list_submodules on slfo_context.git_repo, not a fresh GitRepositoryImpl."""
        mock_prep, fake_slfo_context = _patch_whitelist_prep(monkeypatch)
        _patch_whitelist_other_repos(monkeypatch)
        _patch_services(monkeypatch)
        fake_slfo_context.git_repo.list_submodules.return_value = ["submodule1"]

        args = argparse.Namespace(version="16.1", config=None, refresh_bulk_map=False, strict=False)
        run_whitelist(args)

        fake_slfo_context.git_repo.list_submodules.assert_called_once_with(
            fake_slfo_context.slfo_repo_path
        )


# ---------------------------------------------------------------------------
# Helpers for check users tests
# ---------------------------------------------------------------------------


def _empty_users_result() -> UserValidationResult:
    """Build a UserValidationResult with one confirmed login and no invalid/not_found."""
    return UserValidationResult(confirmed=["user1"], invalid=[], not_found=[])


def _patch_users_service(
    monkeypatch: pytest.MonkeyPatch,
    result: UserValidationResult | None = None,
) -> tuple[Mock, Mock]:
    """Patch MaintainershipRepositoryImpl, ObsPersonRepositoryImpl, UserValidationService.

    Patches the three targets at bugownerctl.commands.check.* and returns
    (service_cls_mock, service_instance_mock).
    """
    monkeypatch.setattr("bugownerctl.commands.check.MaintainershipRepositoryImpl", Mock())
    monkeypatch.setattr("bugownerctl.commands.check.ObsPersonRepositoryImpl", Mock())

    service_instance = Mock()
    service_instance.validate.return_value = result if result is not None else _empty_users_result()
    service_cls = Mock(return_value=service_instance)
    monkeypatch.setattr("bugownerctl.commands.check.UserValidationService", service_cls)

    return service_cls, service_instance


# ---------------------------------------------------------------------------
# Tests for run_users
# ---------------------------------------------------------------------------


class TestCheckUsersCommand:
    """Tests for check users command handler."""

    def test_run_returns_zero_when_all_users_confirmed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns 0 when result.invalid and result.not_found are both empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=["gyr"], invalid=[], not_found=[]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        result = run_users(args)

        assert result == 0

    def test_run_returns_one_when_invalid_accounts_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns 1 when result.invalid is non-empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=[], invalid=["baduser"], not_found=[]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        result = run_users(args)

        assert result == 2

    def test_run_returns_one_when_not_found_accounts_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns 1 when result.not_found is non-empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=[], invalid=[], not_found=["ghost"]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        result = run_users(args)

        assert result == 2

    def test_run_prints_confirmed_section_when_non_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Confirmed section (Found N..., Confirmed accounts:, - login) prints when non-empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=["gyr"], invalid=[], not_found=[]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        captured = capsys.readouterr()
        assert "INFO: Found 1 confirmed OBS accounts." in captured.out
        assert "INFO: Confirmed accounts:" in captured.out
        assert "INFO: - gyr" in captured.out

    def test_run_prints_invalid_section_when_non_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Invalid section prints with INFO prefix when result.invalid is non-empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=[], invalid=["locked-user"], not_found=[]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        captured = capsys.readouterr()
        assert "INFO: Found 1 invalid (locked / non-confirmed) accounts." in captured.out
        assert "INFO: Invalid accounts:" in captured.out
        assert "INFO: - locked-user" in captured.out

    def test_run_prints_not_found_section_when_non_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Not-found section prints with INFO prefix when result.not_found is non-empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=[], invalid=[], not_found=["ghost"]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        captured = capsys.readouterr()
        assert "INFO: Found 1 accounts not found in OBS." in captured.out
        assert "INFO: Accounts not found in OBS:" in captured.out
        assert "INFO: - ghost" in captured.out

    def test_run_prints_all_confirmed_summary_when_no_invalid_or_not_found(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Prints 'All N users are confirmed' summary when invalid and not_found are empty."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=["gyr", "other"], invalid=[], not_found=[]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        captured = capsys.readouterr()
        assert "INFO: All 2 users are confirmed OBS accounts." in captured.out

    def test_run_prints_failure_summary_when_any_invalid_or_not_found(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Prints 'X of N users are not confirmed' summary when any invalid or not_found."""
        _patch_maint_prep(monkeypatch)
        _patch_users_service(
            monkeypatch,
            UserValidationResult(confirmed=["ok-user"], invalid=["bad-user"], not_found=["ghost"]),
        )

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        captured = capsys.readouterr()
        # 1 invalid + 1 not_found = 2; total = 1 + 1 + 1 = 3
        assert "INFO: 2 of 3 users are not confirmed OBS accounts." in captured.out

    def test_run_resolves_maintainership_file_from_slfo_repo_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolves maintainership_file via config.get + validate_file_within_directory."""
        slfo_repo_path = Path("/cache/bugownerctl/SLFO")
        _patch_maint_prep(monkeypatch, slfo_repo_path=slfo_repo_path)
        _, service_instance = _patch_users_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        service_instance.validate.assert_called_once()
        positional_args = service_instance.validate.call_args[0]
        expected_file = slfo_repo_path / "_maintainership.json"
        assert positional_args[0] == expected_file

    def test_run_forwards_api_and_batch_size_to_service_validate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forwards args.api and args.batch_size to service.validate() as positional args."""
        _patch_maint_prep(monkeypatch)
        _, service_instance = _patch_users_service(monkeypatch)

        args = argparse.Namespace(
            version="16.1",
            config=None,
            api="https://api.example.com",
            batch_size=25,
        )
        run_users(args)

        service_instance.validate.assert_called_once()
        positional_args = service_instance.validate.call_args[0]
        assert positional_args[1] == "https://api.example.com"
        assert positional_args[2] == 25

    def test_run_wires_user_validation_service_with_correct_repos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """UserValidationService must be constructed with (maintainership_repo, person_repo)."""
        _patch_maint_prep(monkeypatch)

        mock_maint_inst = Mock()
        mock_person_inst = Mock()
        monkeypatch.setattr(
            "bugownerctl.commands.check.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maint_inst),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.check.ObsPersonRepositoryImpl",
            Mock(return_value=mock_person_inst),
        )
        service_instance = Mock()
        service_instance.validate.return_value = _empty_users_result()
        service_cls = Mock(return_value=service_instance)
        monkeypatch.setattr("bugownerctl.commands.check.UserValidationService", service_cls)

        args = argparse.Namespace(
            version="16.1", config=None, api="https://api.suse.de", batch_size=50
        )
        run_users(args)

        service_cls.assert_called_once_with(mock_maint_inst, mock_person_inst)
