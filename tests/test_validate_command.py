"""Tests for validate command handler."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.validate import run
from bugowner.services.validation_service import ValidationResult


class TestValidateCommand:
    """Tests for validate command handler."""

    def test_run_creates_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create all repository implementation instances."""
        # Mock config loading with correct format (slfo_git_url + products)
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.validate.load_config", mock_load_config)

        # Mock repository classes to track instantiation
        mock_maintainership_repo_cls = Mock()
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        mock_git_repo_cls = Mock(return_value=mock_git_repo)
        mock_metadata_repo_cls = Mock()
        mock_obs_repo_cls = Mock()
        mock_false_positives_repo_cls = Mock()

        monkeypatch.setattr(
            "bugowner.commands.validate.MaintainershipRepositoryImpl",
            mock_maintainership_repo_cls,
        )
        monkeypatch.setattr("bugowner.commands.validate.GitRepositoryImpl", mock_git_repo_cls)
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl", mock_metadata_repo_cls
        )
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", mock_obs_repo_cls)
        monkeypatch.setattr(
            "bugowner.commands.validate.FalsePositivesRepositoryImpl",
            mock_false_positives_repo_cls,
        )

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.validate.ValidationService", mock_service_cls)

        # Mock Path operations
        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # Verify all repositories were instantiated
        mock_maintainership_repo_cls.assert_called_once()
        mock_git_repo_cls.assert_called_once()
        mock_metadata_repo_cls.assert_called_once()
        mock_obs_repo_cls.assert_called_once()
        mock_false_positives_repo_cls.assert_called_once()

    def test_run_creates_validation_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create ValidationService with repository instances."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Create mock repository instances
        mock_maintainership_repo = Mock()
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        mock_metadata_repo = Mock()
        mock_obs_repo = Mock()
        mock_false_positives_repo = Mock()

        monkeypatch.setattr(
            "bugowner.commands.validate.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maintainership_repo),
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ObsRepositoryImpl", Mock(return_value=mock_obs_repo)
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.FalsePositivesRepositoryImpl",
            Mock(return_value=mock_false_positives_repo),
        )

        # Mock ValidationService to track instantiation
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        mock_service_cls = Mock(return_value=mock_service)
        monkeypatch.setattr("bugowner.commands.validate.ValidationService", mock_service_cls)

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # Verify ValidationService was created with all repositories
        mock_service_cls.assert_called_once_with(
            mock_maintainership_repo,
            mock_git_repo,
            mock_metadata_repo,
            mock_obs_repo,
            mock_false_positives_repo,
        )

    def test_run_calls_validate_all_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call ValidationService.validate_all() with correct parameters."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock metadata repository to track download_primary_metadata call
        mock_metadata_repo = Mock()
        mock_metadata_repo.download_primary_metadata.return_value = Path(
            "/test/cache/primary.xml.gz"
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # Verify download_primary_metadata called with version
        mock_metadata_repo.download_primary_metadata.assert_called_once()
        download_call_args = mock_metadata_repo.download_primary_metadata.call_args[0]
        assert download_call_args[0] == "16.1"

        # Verify validate_all called with correct parameters
        mock_service.validate_all.assert_called_once()
        call_args = mock_service.validate_all.call_args[1]
        assert isinstance(call_args["maintainership_file"], Path)
        assert isinstance(call_args["repo_metadata_file"], Path)
        assert isinstance(call_args["false_positives_file"], Path)
        assert isinstance(call_args["git_dir"], Path)

    def test_run_returns_zero_when_no_issues_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return 0 exit code when validation finds no issues."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService with clean results
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

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
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService with orphan packages
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=["orphan-pkg1", "orphan-pkg2"],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

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
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=["pkg1", "pkg2"],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

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
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService with all 4 result sets
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=["orphan1", "orphan2"],
            maintained_packages_without_submodule=["maintained1", "maintained2"],
            shipped_not_in_submodule=["shipped1"],
            new_false_positives={"binary1": "source1"},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

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

        assert "INFO: Discovered 1 new binary→source mappings." in output

        # Verify no emoji in output
        assert "✅" not in output
        assert "❌" not in output

    def test_output_format_shows_empty_state_messages(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print INFO messages for empty result sets."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService with empty results
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        captured = capsys.readouterr()
        output = captured.out

        # Verify INFO messages for empty states
        assert (
            "INFO: No maintained packages without an equivalent git submodule were found." in output
        )
        assert "INFO: No orphan packages found." in output

        # Verify no emoji
        assert "✅" not in output
        assert "❌" not in output

    def test_run_passes_config_path_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should pass args.config to load_config() when provided."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.validate.load_config", mock_load_config)

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

        # Test with explicit config path
        config_path = Path("/custom/config.yaml")
        args = argparse.Namespace(version="16.1", debug=False, config=config_path)
        run(args)

        # Verify load_config was called with explicit config path
        mock_load_config.assert_called_once_with(config_path)

    def test_run_passes_none_to_load_config_when_no_config_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass None to load_config() when args.config is None (triggers search)."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "https://github.com/test/repo",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.validate.load_config", mock_load_config)

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        monkeypatch.setattr("bugowner.commands.validate.Path.cwd", lambda: Path("/test"))

        # Test without config (should default to None)
        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # Verify load_config was called with None (triggers search)
        mock_load_config.assert_called_once_with(None)
