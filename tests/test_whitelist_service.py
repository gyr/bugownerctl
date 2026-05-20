"""Tests for WhitelistService."""

import json
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.bugowner.domain.maintainer import MaintainershipData
from src.bugowner.services.whitelist_service import WhitelistService


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
