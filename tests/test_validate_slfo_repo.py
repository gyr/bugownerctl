"""Tests for validate command SLFO repository handling."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.validate import run
from bugowner.domain.ref_type import RefType
from bugowner.services.validation_service import ValidationResult


class TestValidateSLFORepo:
    """Test validate command clones/checks out SLFO repo correctly."""

    def test_run_clones_slfo_repo_for_branch_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should clone SLFO repo using git URL and branch from config for branch-based version."""
        # Config format: slfo_git_url + products list with version/branch
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.0", "commit": "9d679ed"},
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock GitRepository to track clone_or_update call
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        mock_git_repo_cls = Mock(return_value=mock_git_repo)
        monkeypatch.setattr("bugowner.commands.validate.GitRepositoryImpl", mock_git_repo_cls)

        # Mock other repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_metadata_repo = Mock()
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )
        monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", Mock())

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # Verify clone_or_update called with correct parameters
        mock_git_repo.clone_or_update.assert_called_once_with(
            repo_url="gitea@src.suse.de:products/SLFO.git",
            git_ref="slfo-main",
            cache_dir=Path.home() / ".cache" / "bugownership",
            ref_type=RefType.BRANCH,
        )

    def test_run_clones_slfo_repo_for_commit_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should clone SLFO repo using git URL and commit from config for commit-based version."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.0", "commit": "9d679ed"},
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock GitRepository
        mock_git_repo = Mock()
        mock_git_repo.clone_or_update.return_value = Path("/cache/SLFO")
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )

        # Mock other repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_metadata_repo = Mock()
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )
        monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", Mock())

        # Mock ValidationService
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(version="16.0", debug=False, config=None)
        run(args)

        # Verify clone_or_update called with commit ref
        mock_git_repo.clone_or_update.assert_called_once_with(
            repo_url="gitea@src.suse.de:products/SLFO.git",
            git_ref="9d679ed",
            cache_dir=Path.home() / ".cache" / "bugownership",
            ref_type=RefType.COMMIT,
        )

    def test_run_uses_maintainership_file_from_cloned_repo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use _maintainership.json from cloned SLFO repo, not cwd."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [{"version": "16.1", "branch": "slfo-main"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock GitRepository to return specific path
        mock_git_repo = Mock()
        slfo_repo_path = Path("/cache/bugownership/SLFO")
        mock_git_repo.clone_or_update.return_value = slfo_repo_path
        monkeypatch.setattr(
            "bugowner.commands.validate.GitRepositoryImpl", Mock(return_value=mock_git_repo)
        )

        # Mock other repositories
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        mock_metadata_repo = Mock()
        mock_metadata_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        monkeypatch.setattr(
            "bugowner.commands.validate.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_metadata_repo),
        )
        monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", Mock())

        # Mock ValidationService to track validate_all call
        mock_service = Mock()
        mock_service.validate_all.return_value = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
        )
        monkeypatch.setattr(
            "bugowner.commands.validate.ValidationService", Mock(return_value=mock_service)
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)
        run(args)

        # Verify validate_all called with paths from cloned repo
        mock_service.validate_all.assert_called_once()
        call_kwargs = mock_service.validate_all.call_args[1]

        # maintainership_file should be inside cloned repo
        expected_maintainership = slfo_repo_path / "_maintainership.json"
        assert call_kwargs["maintainership_file"] == expected_maintainership

        # git_dir should be cloned repo path
        assert call_kwargs["git_dir"] == slfo_repo_path

    def test_run_raises_error_if_version_not_in_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError if requested version not found in config."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.0", "commit": "9d679ed"},
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", Mock())

        args = argparse.Namespace(version="99.9", debug=False, config=None)

        with pytest.raises(ValueError, match="Version 99.9 not found in config"):
            run(args)

    def test_run_raises_error_if_product_has_neither_branch_nor_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError if product config has neither branch nor commit."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.1"},  # Missing both branch and commit
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", Mock())

        args = argparse.Namespace(version="16.1", debug=False, config=None)

        with pytest.raises(
            ValueError, match="Product config for version 16.1 has neither branch nor commit"
        ):
            run(args)

    def test_run_raises_error_if_slfo_git_url_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError if slfo_git_url not in config."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            # slfo_git_url missing
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.1", "branch": "main"},
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        # Mock repositories
        monkeypatch.setattr("bugowner.commands.validate.GitRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.MaintainershipRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.RepoMetadataRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.ObsBulkSourceInfoRepositoryImpl", Mock())
        monkeypatch.setattr("bugowner.commands.validate.NameOverridesRepositoryImpl", Mock())

        args = argparse.Namespace(version="16.1", debug=False, config=None)

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            run(args)

    def test_run_raises_error_if_git_ref_is_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError if git ref is empty string."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.1", "branch": ""},  # Empty string
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)

        with pytest.raises(ValueError, match="Empty git ref for version 16.1"):
            run(args)

    def test_run_raises_error_if_git_ref_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise ValueError if git ref is None."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "maintainership_file": "_maintainership.json",
            "false_positives_file": "false_positives.json",
            "products": [
                {"version": "16.1", "commit": None},  # None value
            ],
        }
        monkeypatch.setattr(
            "bugowner.commands.validate.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", debug=False, config=None)

        with pytest.raises(ValueError, match="Empty git ref for version 16.1"):
            run(args)
