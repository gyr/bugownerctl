"""Tests for WhitelistService."""

import json
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.domain.maintainer import MaintainershipData
from bugowner.services.whitelist_service import WhitelistCheckResult, WhitelistService


class TestWhitelistService:
    """Tests for WhitelistService."""

    def test_init_stores_dependencies(self) -> None:
        """Should store repository dependencies."""
        maintainership_repo = Mock()
        git_repo = Mock()

        service = WhitelistService(maintainership_repo, git_repo)

        assert service.maintainership_repo is maintainership_repo
        assert service.git_repo is git_repo

    def test_load_whitelist_returns_empty_set_when_file_not_exists(self, tmp_path: Path) -> None:
        """Should return empty set when whitelist file doesn't exist."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "nonexistent.json"

        result = service.load_whitelist(whitelist_file)

        assert result == set()

    def test_load_whitelist_returns_set_from_json_array(self, tmp_path: Path) -> None:
        """Should load whitelist from JSON array file."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1", "pkg2", "pkg3"]')

        result = service.load_whitelist(whitelist_file)

        assert result == {"pkg1", "pkg2", "pkg3"}

    def test_save_whitelist_writes_sorted_json_array(self, tmp_path: Path) -> None:
        """Should save packages as sorted JSON array."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "whitelist.json"
        packages = ["pkg3", "pkg1", "pkg2"]

        service.save_whitelist(whitelist_file, packages)

        content = json.loads(whitelist_file.read_text())
        assert content == ["pkg1", "pkg2", "pkg3"]

    def test_update_whitelist_calculates_added_packages(self, tmp_path: Path) -> None:
        """Should calculate packages to add (submodules - maintained)."""
        # Setup mocks
        maintainership_repo = Mock()
        git_repo = Mock()

        # Submodules: a, b, c
        git_repo.list_submodules.return_value = ["a", "b", "c"]

        # Maintained: a, b (missing c)
        maintainership_data = MaintainershipData(packages={"a": [], "b": []})
        maintainership_repo.load.return_value = maintainership_data

        service = WhitelistService(maintainership_repo, git_repo)

        repo_path = tmp_path / "repo"
        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"

        result = service.update_whitelist(repo_path, maintainership_file, whitelist_file)

        # Should add c (in submodules but not in maintained)
        assert sorted(result.added) == ["c"]

    def test_update_whitelist_calculates_removed_packages(self, tmp_path: Path) -> None:
        """Should calculate packages to remove (old_whitelist - new_added)."""
        maintainership_repo = Mock()
        git_repo = Mock()

        # Submodules: a, b, c
        git_repo.list_submodules.return_value = ["a", "b", "c"]

        # Maintained: a, b (missing c)
        maintainership_data = MaintainershipData(packages={"a": [], "b": []})
        maintainership_repo.load.return_value = maintainership_data

        service = WhitelistService(maintainership_repo, git_repo)

        repo_path = tmp_path / "repo"
        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"

        # Old whitelist: c, d (d no longer needed)
        whitelist_file.write_text('["c", "d"]')

        result = service.update_whitelist(repo_path, maintainership_file, whitelist_file)

        # Should remove d (was in old whitelist but not in new added)
        assert sorted(result.removed) == ["d"]

    def test_update_whitelist_calculates_invalid_packages(self, tmp_path: Path) -> None:
        """Should calculate invalid packages (maintained - submodules)."""
        maintainership_repo = Mock()
        git_repo = Mock()

        # Submodules: a, b
        git_repo.list_submodules.return_value = ["a", "b"]

        # Maintained: a, b, c (c not in submodules)
        maintainership_data = MaintainershipData(packages={"a": [], "b": [], "c": []})
        maintainership_repo.load.return_value = maintainership_data

        service = WhitelistService(maintainership_repo, git_repo)

        repo_path = tmp_path / "repo"
        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"

        result = service.update_whitelist(repo_path, maintainership_file, whitelist_file)

        # Should report c (in maintained but not in submodules)
        assert sorted(result.in_maintainership_not_submodule) == ["c"]

    def test_update_whitelist_saves_added_packages_to_file(self, tmp_path: Path) -> None:
        """Should save added packages to whitelist file."""
        maintainership_repo = Mock()
        git_repo = Mock()

        # Submodules: a, b, c
        git_repo.list_submodules.return_value = ["a", "b", "c"]

        # Maintained: a (missing b, c)
        maintainership_data = MaintainershipData(packages={"a": []})
        maintainership_repo.load.return_value = maintainership_data

        service = WhitelistService(maintainership_repo, git_repo)

        repo_path = tmp_path / "repo"
        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"

        service.update_whitelist(repo_path, maintainership_file, whitelist_file)

        # Verify file saved with sorted added packages
        content = json.loads(whitelist_file.read_text())
        assert content == ["b", "c"]

    def test_load_whitelist_raises_error_for_invalid_json_type(self, tmp_path: Path) -> None:
        """Should raise ValueError when JSON is not an array."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('{"malformed": "data"}')

        with pytest.raises(ValueError, match="must contain a JSON array"):
            service.load_whitelist(whitelist_file)

    def test_load_whitelist_raises_error_for_non_string_elements(self, tmp_path: Path) -> None:
        """Should raise ValueError when array contains non-strings."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1", 123, "pkg2"]')

        with pytest.raises(ValueError, match="must contain only strings"):
            service.load_whitelist(whitelist_file)

    def test_load_whitelist_raises_error_for_large_file(self, tmp_path: Path) -> None:
        """Should raise ValueError when file exceeds size limit."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "whitelist.json"

        # Create file larger than MAX_WHITELIST_SIZE
        large_data = ["pkg"] * (service.MAX_WHITELIST_SIZE // 4 + 1)
        whitelist_file.write_text(json.dumps(large_data))

        with pytest.raises(ValueError, match="is too large"):
            service.load_whitelist(whitelist_file)

    def test_save_whitelist_sets_restrictive_permissions(self, tmp_path: Path) -> None:
        """Should set file permissions to 0o600 (owner read/write only)."""
        service = WhitelistService(Mock(), Mock())
        whitelist_file = tmp_path / "whitelist.json"
        packages = ["pkg1", "pkg2"]

        service.save_whitelist(whitelist_file, packages)

        # Check file permissions
        file_stat = whitelist_file.stat()
        permissions = stat.filemode(file_stat.st_mode)
        # Should be -rw------- (owner read/write only)
        assert permissions == "-rw-------"


class TestCheckWhitelist:
    """Tests for WhitelistService.check_whitelist() method."""

    def test_check_whitelist_finds_no_inconsistencies_when_none_exist(self, tmp_path: Path) -> None:
        """Should return empty list when validated packages don't overlap with whitelist."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist file with different packages
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg3", "pkg4"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2", "pkg5"},
            submodules=["pkg1", "pkg2"],
            false_positives_file=false_positives_file,
        )

        # Verify
        assert isinstance(result, WhitelistCheckResult)
        assert result.inconsistent_packages == []
        assert result.new_false_positives == {}

    def test_check_whitelist_finds_inconsistencies_when_packages_shipped_and_whitelisted(
        self, tmp_path: Path
    ) -> None:
        """Should find packages that are BOTH shipped AND whitelisted."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2", "pkg3"},  # valid_packages (validated shipped)
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist with pkg1 and pkg2 (overlap with validated shipped)
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1", "pkg2", "pkg4"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2", "pkg3", "pkg5"},
            submodules=["pkg1", "pkg2", "pkg3"],
            false_positives_file=false_positives_file,
        )

        # Verify - pkg1 and pkg2 are in BOTH validated shipped and whitelist
        assert result.inconsistent_packages == ["pkg1", "pkg2"]
        assert result.new_false_positives == {}

    def test_check_whitelist_handles_empty_whitelist(self, tmp_path: Path) -> None:
        """Should return no inconsistencies when whitelist is empty."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create empty whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text("[]")

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2"},
            submodules=["pkg1", "pkg2"],
            false_positives_file=false_positives_file,
        )

        # Verify
        assert result.inconsistent_packages == []
        assert result.new_false_positives == {}

    def test_check_whitelist_returns_new_false_positives_from_validation_pipeline(
        self, tmp_path: Path
    ) -> None:
        """Should return new false positives discovered during validation."""
        # Setup mock validation service with new false positives
        mock_validation_service = Mock()
        new_fps = {"apache2-devel": "apache2", "kernel-default": "kernel-source"}
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"apache2", "kernel-source"},  # valid_packages
            [],  # shipped_not_in_submodule
            new_fps,  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"apache2-devel", "kernel-default"},
            submodules=["apache2", "kernel-source"],
            false_positives_file=false_positives_file,
        )

        # Verify new false positives are returned
        assert result.new_false_positives == new_fps

    def test_check_whitelist_raises_error_when_whitelist_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when whitelist file doesn't exist."""
        mock_validation_service = Mock()
        service = WhitelistService(mock_validation_service)

        whitelist_file = tmp_path / "nonexistent.json"
        false_positives_file = tmp_path / "false_positives.json"

        # Execute and verify
        with pytest.raises(FileNotFoundError, match="Whitelist file .* does not exist"):
            service.check_whitelist(
                whitelist_file=whitelist_file,
                shipped_packages={"pkg1"},
                submodules=["pkg1"],
                false_positives_file=false_positives_file,
            )

    def test_check_whitelist_calls_validation_service_with_correct_parameters(
        self, tmp_path: Path
    ) -> None:
        """Should call validation service with correct parameters."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1"},  # valid_packages
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1"]')

        false_positives_file = tmp_path / "false_positives.json"
        shipped_packages = {"pkg1", "pkg2"}
        submodules = ["pkg1"]
        obs_project = "TEST:PROJECT"

        # Execute
        service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages=shipped_packages,
            submodules=submodules,
            false_positives_file=false_positives_file,
            obs_project=obs_project,
        )

        # Verify validation service was called with correct parameters
        mock_validation_service.find_shipped_without_submodule.assert_called_once_with(
            shipped_packages, submodules, false_positives_file, obs_project
        )

    def test_check_whitelist_returns_sorted_inconsistent_packages(self, tmp_path: Path) -> None:
        """Should return inconsistent packages in sorted order."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"zebra", "apple", "banana"},  # valid_packages (unsorted)
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist with same packages (unsorted)
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["banana", "zebra", "apple"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"zebra", "apple", "banana"},
            submodules=["zebra", "apple", "banana"],
            false_positives_file=false_positives_file,
        )

        # Verify sorted output
        assert result.inconsistent_packages == ["apple", "banana", "zebra"]
