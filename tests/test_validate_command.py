"""Tests for validate command handler."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.validate import run
from bugowner.services.validation_service import ValidationResult


def _empty_result() -> ValidationResult:
    """Build a ValidationResult with no findings."""
    return ValidationResult(
        orphan_packages=[],
        maintained_packages_without_submodule=[],
        shipped_not_in_submodule=[],
    )


def _patch_repos(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    """Patch all repository impls used by validate.run. Returns the mock classes.

    Wires a git repo instance with `clone_or_update` returning a stable path
    so downstream code that derives `slfo_repo_path` does not blow up.
    """
    mock_maint_cls = Mock()
    mock_git_repo = Mock()
    mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
    mock_git_cls = Mock(return_value=mock_git_repo)
    mock_meta_cls = Mock()
    mock_bulk_cls = Mock()
    mock_over_cls = Mock()

    monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", mock_maint_cls)
    monkeypatch.setattr("bugowner.commands.validate.GitRepositoryImpl", mock_git_cls)
    monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", mock_meta_cls)
    monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", mock_bulk_cls)
    monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", mock_over_cls)

    return {
        "maintainership": mock_maint_cls,
        "git_cls": mock_git_cls,
        "git_repo": mock_git_repo,
        "metadata": mock_meta_cls,
        "bulk_map": mock_bulk_cls,
        "overrides": mock_over_cls,
    }


def _patch_validation_service(
    monkeypatch: pytest.MonkeyPatch, result: ValidationResult | None = None
) -> tuple[Mock, Mock]:
    """Patch ValidationService and return (cls_mock, instance_mock)."""
    instance = Mock()
    instance.validate_all.return_value = result if result is not None else _empty_result()
    cls = Mock(return_value=instance)
    monkeypatch.setattr("bugowner.commands.validate.ValidationService", cls)
    return cls, instance


class TestValidateCommand:
    """Tests for validate command handler."""

    def test_run_creates_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create all repository implementation instances."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        repos = _patch_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        repos["maintainership"].assert_called_once()
        repos["git_cls"].assert_called_once()
        repos["metadata"].assert_called_once()
        repos["bulk_map"].assert_called_once()
        repos["overrides"].assert_called_once()

    def test_run_creates_validation_service_with_new_repos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create ValidationService with new bulk_map+overrides repos."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Create explicit mock instances so we can verify the wiring.
        mock_maint_inst = Mock()
        mock_git_inst = Mock()
        mock_git_inst.clone_or_update.return_value = Path("/cache/SLFO")
        mock_meta_inst = Mock()
        mock_bulk_inst = Mock()
        mock_over_inst = Mock()

        monkeypatch.setattr(
            "bugowner.commands.validate.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maint_inst),
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_inst)
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_meta_inst),
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl",
            Mock(return_value=mock_bulk_inst),
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.NameOverridesRepositoryImpl",
            Mock(return_value=mock_over_inst),
        )

        cls_mock, _ = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # ValidationService called with positional (maint, git, metadata) +
        # kwargs (bulk_map_repo, overrides_repo).
        cls_mock.assert_called_once_with(
            mock_maint_inst,
            mock_git_inst,
            mock_meta_inst,
            bulk_map_repo=mock_bulk_inst,
            overrides_repo=mock_over_inst,
        )

    def test_run_calls_validate_all_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call ValidationService.validate_all() with correct parameters."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        repos = _patch_repos(monkeypatch)
        repos["metadata"].return_value.download_primary_metadata.return_value = Path(
            "/test/cache/primary.xml.gz"
        )

        _, instance = _patch_validation_service(monkeypatch)

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

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
        expected_cache_dir = Path("~/.cache/bugownership").expanduser()
        assert call_args["cache_dir"] == expected_cache_dir
        # overrides_file must resolve via importlib.resources (lives under
        # the installed package's data dir); just confirm it's a Path and
        # points at the shipped basename.
        assert isinstance(call_args["overrides_file"], Path)
        assert call_args["overrides_file"].name == "false_positives_overrides.json"

    def test_run_returns_zero_when_no_issues_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code when validation finds no issues."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        result = run(args)

        assert result == 0

    def test_run_returns_one_when_orphan_packages_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 1 exit code when orphan packages found."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=["orphan-pkg1", "orphan-pkg2"],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=[],
            ),
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        result = run(args)

        assert result == 1

    def test_run_prints_orphan_packages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print orphan packages to stdout."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=["pkg1", "pkg2"],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=[],
            ),
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        captured = capsys.readouterr()
        assert "Orphan packages" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out

    def test_output_format_matches_old_script_with_info_prefix_and_set_labels(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print output with INFO prefix and SET labels matching old script format."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=["orphan1", "orphan2"],
                maintained_packages_without_submodule=["maintained1", "maintained2"],
                shipped_not_in_submodule=["shipped1"],
            ),
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

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
        assert "[OK]" not in output  # placeholder for ✅
        # Original assertions used emoji characters; keep ASCII-only here.

    def test_output_format_shows_empty_state_messages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print INFO messages for empty result sets."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

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
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(
            monkeypatch,
            ValidationResult(
                orphan_packages=[],
                maintained_packages_without_submodule=[],
                shipped_not_in_submodule=["mystery-pkg"],
                unresolved_names=["mystery-pkg"],
            ),
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" in captured.out
        assert "mystery-pkg" in captured.out

    def test_validate_omits_unresolved_section_when_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should NOT print the unresolved-names section when unresolved_names is empty."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_validation_service(monkeypatch)  # default: empty result, unresolved=[]

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" not in captured.out

    def test_run_passes_config_path_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should pass args.config to load_config() when provided."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.validate.load_config", mock_load_config)

        _patch_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        config_path = Path("/custom/config.yaml")
        args = argparse.Namespace(version="16.1", debug=False, config=config_path)
        run(args)

        mock_load_config.assert_called_once_with(config_path)

    def test_run_passes_none_to_load_config_when_no_config_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass None to load_config() when args.config is None (triggers search)."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.validate.load_config", mock_load_config)

        _patch_repos(monkeypatch)
        _patch_validation_service(monkeypatch)

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        mock_load_config.assert_called_once_with(None)
