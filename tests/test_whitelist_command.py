"""Tests for whitelist-check command handler."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.whitelist import run
from bugowner.domain.ref_type import RefType
from bugowner.services.whitelist_service import WhitelistCheckResult


class TestWhitelistCheckCommand:
    """Tests for whitelist-check command handler."""

    def test_run_creates_all_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create all repository implementation instances."""
        # Mock config loading
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.whitelist.load_config", mock_load_config)

        # Mock repository classes
        mock_git_repo_cls = Mock()
        mock_metadata_repo_cls = Mock()
        mock_obs_repo_cls = Mock()
        mock_fp_repo_cls = Mock()
        mock_maint_repo_cls = Mock()

        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", mock_git_repo_cls)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl", mock_metadata_repo_cls
        )
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", mock_obs_repo_cls)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.FalsePositivesRepositoryImpl", mock_fp_repo_cls
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.MaintainershipRepositoryImpl", mock_maint_repo_cls
        )

        # Mock services
        mock_validation_service = Mock()
        mock_validation_service_cls = Mock(return_value=mock_validation_service)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.ValidationService", mock_validation_service_cls
        )

        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        mock_whitelist_service_cls = Mock(return_value=mock_whitelist_service)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", mock_whitelist_service_cls
        )

        # Mock repository operations
        mock_git_repo = mock_git_repo_cls.return_value
        mock_metadata_repo = mock_metadata_repo_cls.return_value
        mock_git_repo.clone_or_update.return_value = Path("/cache/slfo")
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        mock_metadata_repo.parse_source_packages.return_value = {"pkg1"}
        mock_git_repo.list_submodules.return_value = ["pkg1"]

        # Mock Path operations
        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        # Verify all repositories were instantiated
        mock_git_repo_cls.assert_called_once()
        mock_metadata_repo_cls.assert_called_once()
        mock_obs_repo_cls.assert_called_once()
        mock_fp_repo_cls.assert_called_once()
        mock_maint_repo_cls.assert_called_once()

    def test_run_creates_validation_service_with_repository_dependencies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create ValidationService with all repository dependencies."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Create mock repository instances
        mock_maint_repo = Mock()
        mock_git_repo = Mock()
        mock_metadata_repo = Mock()
        mock_obs_repo = Mock()
        mock_fp_repo = Mock()

        monkeypatch.setattr(
            "bugowner.commands.whitelist.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maint_repo),
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.ObsRepositoryImpl", Mock(return_value=mock_obs_repo)
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.FalsePositivesRepositoryImpl",
            Mock(return_value=mock_fp_repo),
        )

        # Mock ValidationService to track instantiation
        mock_validation_service = Mock()
        mock_validation_service_cls = Mock(return_value=mock_validation_service)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.ValidationService", mock_validation_service_cls
        )

        # Mock WhitelistService
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        mock_git_repo.clone_or_update.return_value = Path("/cache/slfo")
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        mock_metadata_repo.parse_source_packages.return_value = {"pkg1"}
        mock_git_repo.list_submodules.return_value = ["pkg1"]

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        # Verify ValidationService created with all repositories
        mock_validation_service_cls.assert_called_once_with(
            mock_maint_repo, mock_git_repo, mock_metadata_repo, mock_obs_repo, mock_fp_repo
        )

    def test_run_creates_whitelist_service_with_validation_dependency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create WhitelistService with ValidationService dependency."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        mock_validation_service = Mock()
        mock_validation_service_cls = Mock(return_value=mock_validation_service)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.ValidationService", mock_validation_service_cls
        )

        # Mock WhitelistService to track instantiation
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        mock_whitelist_service_cls = Mock(return_value=mock_whitelist_service)
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService", mock_whitelist_service_cls
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        # Verify WhitelistService created with ValidationService
        mock_whitelist_service_cls.assert_called_once_with(mock_validation_service)

    def test_run_calls_check_whitelist_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call WhitelistService.check_whitelist() with correct parameters."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock git and metadata operations
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/slfo")
        mock_git_repo.list_submodules.return_value = ["pkg1", "pkg2"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )

        mock_metadata_repo = Mock()
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        mock_metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2", "pkg3"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        # Verify check_whitelist called with correct parameters
        mock_whitelist_service.check_whitelist.assert_called_once()
        call_args = mock_whitelist_service.check_whitelist.call_args[1]
        # whitelist_file should come from cloned SLFO repo (like validate command)
        assert call_args["whitelist_file"] == Path("/cache/slfo/whitelist_maintainership.json")
        assert call_args["shipped_packages"] == {"pkg1", "pkg2", "pkg3"}
        assert call_args["submodules"] == ["pkg1", "pkg2"]
        # false_positives_file should come from current directory (persistent cache)
        assert call_args["false_positives_file"] == Path("/test/false_positives.json")

    def test_run_returns_zero_when_no_inconsistencies_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 0 exit code when no inconsistencies found."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService with NO inconsistencies
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[],  # No issues
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        result = run(args)

        assert result == 0

    def test_run_returns_one_when_inconsistencies_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 1 exit code when inconsistencies found."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService with inconsistencies
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=["pkg1", "pkg2"],  # Found issues
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        result = run(args)

        assert result == 1

    def test_run_prints_inconsistent_packages_with_info_prefix(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print inconsistent packages with INFO prefix."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService with inconsistencies
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=["apache2", "kernel-source"],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        captured = capsys.readouterr()
        assert "INFO: Found 2 packages that are BOTH shipped AND whitelisted" in captured.out
        assert "INFO: Inconsistent packages" in captured.out
        assert "INFO: - apache2" in captured.out
        assert "INFO: - kernel-source" in captured.out

    def test_run_prints_success_message_when_no_issues(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print success message with INFO prefix when no issues."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService with NO issues
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[],
            new_false_positives={},
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        captured = capsys.readouterr()
        assert "INFO: No inconsistencies found" in captured.out
        # Ensure no emoji used
        assert "✅" not in captured.out

    def test_run_raises_error_when_version_not_found_in_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError when version not in config."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="99.9", config=None)  # Version not in config

        with pytest.raises(ValueError, match="Version 99.9 not found in config"):
            run(args)

    def test_run_raises_error_when_product_config_has_no_branch_or_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError when product config has neither branch nor commit."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1"}],  # Missing branch and commit
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", config=None)

        with pytest.raises(ValueError, match="has neither branch nor commit"):
            run(args)

    def test_run_raises_error_when_git_ref_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise ValueError when git ref is empty."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": ""}],  # Empty branch
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", config=None)

        with pytest.raises(ValueError, match="Empty git ref for version 16.1"):
            run(args)

    def test_run_raises_error_when_slfo_git_url_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError when slfo_git_url not in config."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            # Missing slfo_git_url
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", config=None)

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            run(args)

    def test_run_supports_commit_ref_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should support commit ref type (not just branch)."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "commit": "abc123def"}],  # Commit instead of branch
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock git and metadata operations
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/slfo")
        mock_git_repo.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )

        mock_metadata_repo = Mock()
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        mock_metadata_repo.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        args = argparse.Namespace(version="16.1", config=None)
        result = run(args)

        # Verify clone_or_update called with COMMIT ref type
        assert mock_git_repo.clone_or_update.called
        call_kwargs = mock_git_repo.clone_or_update.call_args[1]
        assert call_kwargs["git_ref"] == "abc123def"
        assert call_kwargs["ref_type"] == RefType.COMMIT
        assert result == 0

    def test_run_passes_config_path_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should pass args.config to load_config() when provided."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.whitelist.load_config", mock_load_config)

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        # Test with explicit config path
        config_path = Path("/custom/config.yaml")
        args = argparse.Namespace(version="16.1", config=config_path)
        run(args)

        # Verify load_config was called with explicit config path
        mock_load_config.assert_called_once_with(config_path)

    def test_run_passes_none_to_load_config_when_no_config_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass None to load_config() when args.config is None (triggers search)."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "false_positives_file": "false_positives.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.whitelist.load_config", mock_load_config)

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.ObsRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.FalsePositivesRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", Mock())

        # Mock ValidationService
        monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", Mock())

        # Mock WhitelistService
        mock_whitelist_service = Mock()
        mock_whitelist_service.check_whitelist.return_value = WhitelistCheckResult(
            inconsistent_packages=[], new_false_positives={}
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.WhitelistService",
            Mock(return_value=mock_whitelist_service),
        )

        # Mock repository operations
        git_repo_instance = Mock()
        git_repo_instance.clone_or_update.return_value = Path("/cache/slfo")
        git_repo_instance.list_submodules.return_value = ["pkg1"]
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=git_repo_instance)
        )

        metadata_repo_instance = Mock()
        metadata_repo_instance.download_primary_metadata.return_value = Path(
            "/cache/primary.xml.gz"
        )
        metadata_repo_instance.parse_source_packages.return_value = {"pkg1"}
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=metadata_repo_instance),
        )

        monkeypatch.setattr("bugowner.commands.whitelist.Path.cwd", lambda: Path("/test"))

        # Test without config (should default to None)
        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        # Verify load_config was called with None (triggers search)
        mock_load_config.assert_called_once_with(None)
