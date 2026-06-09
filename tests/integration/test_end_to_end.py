"""Integration tests for end-to-end CLI workflows.

Tests complete workflows from CLI entry through to results,
using real fixtures and minimal mocking.
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from bugowner.cli import main
from bugowner.domain.bulk_map import BulkMap


class TestValidateWorkflow:
    """Integration tests for 'bugowner validate' workflow."""

    def test_validate_workflow_with_valid_data(self, tmp_path, monkeypatch):
        """Should complete full validation workflow with valid maintainership data.

        Workflow:
        1. Load maintainership data
        2. List git submodules
        3. Download and parse repo metadata
        4. Resolve binary→source via bulk-map + overrides pipeline
        5. Report validation results
        """
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup test data files
        maintainership_data = {
            "packages": {
                "test-package": {"users": ["user1"], "groups": ["team1"]},
                "another-package": {"users": ["user2"], "groups": []},
            }
        }
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))

        # Create minimal config file with new format
        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        # Mock external calls
        with (
            patch(
                "bugowner.repositories.git_repository.GitRepositoryImpl.clone_or_update"
            ) as mock_clone,
            patch(
                "bugowner.repositories.git_repository.GitRepositoryImpl.list_submodules"
            ) as mock_git,
            patch(
                "bugowner.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.download_primary_metadata"
            ) as mock_download,
            patch(
                "bugowner.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.parse_source_packages"
            ) as mock_parse,
            patch(
                "bugowner.repositories.obs_bulk_source_info_repository.ObsBulkSourceInfoRepositoryImpl.load_bulk_map"
            ) as mock_bulk_map,
            patch("sys.argv", ["bugowner", "validate", "-v", "16.1"]),
        ):
            mock_clone.return_value = tmp_path  # Return test dir as cloned repo
            mock_git.return_value = ["test-package", "another-package"]
            mock_download.return_value = tmp_path / "primary.xml.gz"
            mock_parse.return_value = {"test-package", "another-package"}
            mock_bulk_map.return_value = BulkMap(
                mapping={},
                project="test-project",
                fetched_at=datetime.now(timezone.utc),
            )

            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Validate should succeed with valid data"
            mock_git.assert_called_once()

    def test_validate_workflow_finds_orphan_packages(self, tmp_path, monkeypatch):
        """Should detect packages in repo without maintainers."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup: package in repo but not in maintainership
        maintainership_data = {
            "packages": {"maintained-package": {"users": ["user1"], "groups": []}}
        }
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "products": [{"version": "16.1", "branch": "main"}],
        }
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with (
            patch(
                "bugowner.repositories.git_repository.GitRepositoryImpl.clone_or_update"
            ) as mock_clone,
            patch(
                "bugowner.repositories.git_repository.GitRepositoryImpl.list_submodules"
            ) as mock_git,
            patch(
                "bugowner.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.download_primary_metadata"
            ) as mock_download,
            patch(
                "bugowner.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.parse_source_packages"
            ) as mock_parse,
            patch(
                "bugowner.repositories.obs_bulk_source_info_repository.ObsBulkSourceInfoRepositoryImpl.load_bulk_map"
            ) as mock_bulk_map,
            patch("sys.argv", ["bugowner", "validate", "-v", "16.1"]),
        ):
            mock_clone.return_value = tmp_path  # Return test dir as cloned repo
            mock_git.return_value = ["maintained-package"]
            mock_download.return_value = tmp_path / "primary.xml.gz"
            mock_parse.return_value = {"maintained-package", "orphan-package"}
            mock_bulk_map.return_value = BulkMap(
                mapping={},
                project="test-project",
                fetched_at=datetime.now(timezone.utc),
            )

            # Execute
            exit_code = main()

            # Verify - should report issues found
            assert exit_code == 1, "Should return 1 when orphan packages found"


class TestQueryPackageWorkflow:
    """Integration tests for 'bugowner query package' workflow."""

    def test_query_package_finds_maintained_package(self, tmp_path, monkeypatch):
        """Should find and display package maintainers."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup
        maintainership_data = {
            "packages": {"test-package": {"users": ["user1", "user2"], "groups": ["team1"]}}
        }
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))
        (tmp_path / "whitelist_maintainership.json").write_text(json.dumps([]))

        config_data = {}
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with patch("sys.argv", ["bugowner", "query", "package", "test-package"]):
            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Should succeed when package found"

    def test_query_package_finds_whitelisted_package(self, tmp_path, monkeypatch):
        """Should indicate when package is whitelisted (no maintainer)."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup
        maintainership_data = {"packages": {}}
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))
        (tmp_path / "whitelist_maintainership.json").write_text(json.dumps(["whitelisted-package"]))

        config_data = {}
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with patch("sys.argv", ["bugowner", "query", "package", "whitelisted-package"]):
            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Should succeed when package whitelisted"

    def test_query_package_not_found(self, tmp_path, monkeypatch):
        """Should report when package not found in maintainership or whitelist."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup
        maintainership_data = {"packages": {}}
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))
        (tmp_path / "whitelist_maintainership.json").write_text(json.dumps([]))

        config_data = {}
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with patch("sys.argv", ["bugowner", "query", "package", "unknown-package"]):
            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Query always returns 0, but prints 'Not found'"


class TestQueryMaintainerWorkflow:
    """Integration tests for 'bugowner query maintainer' workflow."""

    def test_query_maintainer_lists_all_packages(self, tmp_path, monkeypatch):
        """Should list all packages maintained by user or group."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup
        maintainership_data = {
            "packages": {
                "package1": {"users": ["user1", "user2"], "groups": []},
                "package2": {"users": ["user1"], "groups": ["team1"]},
                "package3": {"users": ["user3"], "groups": []},
                "package4": {"users": [], "groups": ["team1"]},
            }
        }
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))

        config_data = {}
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with patch("sys.argv", ["bugowner", "query", "maintainer", "user1"]):
            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Should succeed when maintainer found"

    def test_query_maintainer_finds_group_packages(self, tmp_path, monkeypatch):
        """Should find packages maintained by a group."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup
        maintainership_data = {
            "packages": {
                "package1": {"users": ["user1"], "groups": ["team1"]},
                "package2": {"users": [], "groups": ["team1"]},
                "package3": {"users": ["user1"], "groups": []},
            }
        }
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))

        config_data = {}
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with patch("sys.argv", ["bugowner", "query", "maintainer", "team1"]):
            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Should succeed when group found"

    def test_query_maintainer_not_found(self, tmp_path, monkeypatch):
        """Should report when maintainer has no packages."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup
        maintainership_data = {"packages": {"package1": {"users": ["user1"], "groups": []}}}
        (tmp_path / "_maintainership.json").write_text(json.dumps(maintainership_data))

        config_data = {}
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with patch("sys.argv", ["bugowner", "query", "maintainer", "unknown-user"]):
            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Should succeed but show empty list"
