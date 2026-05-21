"""Tests for MaintainershipRepository."""

import json
import tempfile
from pathlib import Path

import pytest

from bugowner.repositories.maintainership_repository import MaintainershipRepositoryImpl


class TestMaintainershipRepositoryLoad:
    """Tests for MaintainershipRepository.load()."""

    def test_load_parses_new_format_users_only(self):
        """Should parse new format with users only."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "apache2": {"users": ["user1", "user2"], "groups": []},
                "nginx": {"users": ["user3"], "groups": []},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)

        try:
            repo = MaintainershipRepositoryImpl()
            result = repo.load(tmp_path)

            assert result.packages == {
                "apache2": ["user1", "user2"],
                "nginx": ["user3"],
            }
        finally:
            tmp_path.unlink()

    def test_load_parses_new_format_groups_only(self):
        """Should parse new format with groups only."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "apache2": {"users": [], "groups": ["web-maintainers"]},
                "kernel": {"users": [], "groups": ["kernel-team", "drivers-team"]},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)

        try:
            repo = MaintainershipRepositoryImpl()
            result = repo.load(tmp_path)

            assert result.packages == {
                "apache2": ["web-maintainers"],
                "kernel": ["kernel-team", "drivers-team"],
            }
        finally:
            tmp_path.unlink()

    def test_load_parses_new_format_users_and_groups(self):
        """Should parse new format with both users and groups, users first."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "apache2": {"users": ["user1"], "groups": ["web-maintainers"]},
                "kernel": {"users": ["user2", "user3"], "groups": ["kernel-team"]},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)

        try:
            repo = MaintainershipRepositoryImpl()
            result = repo.load(tmp_path)

            assert result.packages == {
                "apache2": ["user1", "web-maintainers"],
                "kernel": ["user2", "user3", "kernel-team"],
            }
        finally:
            tmp_path.unlink()

    def test_load_parses_empty_maintainers(self):
        """Should handle packages with no maintainers."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "orphan": {"users": [], "groups": []},
                "maintained": {"users": ["user1"], "groups": []},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)

        try:
            repo = MaintainershipRepositoryImpl()
            result = repo.load(tmp_path)

            assert result.packages == {
                "orphan": [],
                "maintained": ["user1"],
            }
        finally:
            tmp_path.unlink()

    def test_load_raises_file_not_found(self):
        """Should raise FileNotFoundError for non-existent file."""
        repo = MaintainershipRepositoryImpl()
        with pytest.raises(FileNotFoundError):
            repo.load(Path("/nonexistent/path/file.json"))

    def test_load_raises_json_decode_error(self):
        """Should raise JSONDecodeError for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp.write("{ invalid json }")
            tmp_path = Path(tmp.name)

        try:
            repo = MaintainershipRepositoryImpl()
            with pytest.raises(json.JSONDecodeError):
                repo.load(tmp_path)
        finally:
            tmp_path.unlink()

    def test_load_raises_key_error_missing_packages(self):
        """Should raise KeyError if 'packages' key is missing."""
        data = {"header": {"document": "obs-maintainers", "version": "1.0"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(data, tmp)
            tmp_path = Path(tmp.name)

        try:
            repo = MaintainershipRepositoryImpl()
            with pytest.raises(KeyError):
                repo.load(tmp_path)
        finally:
            tmp_path.unlink()


class TestMaintainershipRepositoryGetPackages:
    """Tests for MaintainershipRepository.get_packages()."""

    def test_get_packages_returns_all_package_names(self):
        """Should return set of all package names."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(
            packages={
                "apache2": ["user1"],
                "nginx": ["user2"],
                "kernel": ["user3"],
            }
        )

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages(data)

        assert result == {"apache2", "nginx", "kernel"}

    def test_get_packages_returns_empty_set_for_empty_data(self):
        """Should return empty set for empty packages."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages(data)

        assert result == set()


class TestMaintainershipRepositoryGetMaintainers:
    """Tests for MaintainershipRepository.get_maintainers()."""

    def test_get_maintainers_returns_list_for_existing_package(self):
        """Should return maintainers list for existing package."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(
            packages={
                "apache2": ["user1", "web-maintainers"],
                "nginx": ["user2"],
            }
        )

        repo = MaintainershipRepositoryImpl()
        result = repo.get_maintainers(data, "apache2")

        assert result == ["user1", "web-maintainers"]

    def test_get_maintainers_returns_empty_list_for_nonexistent_package(self):
        """Should return empty list for non-existent package."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={"apache2": ["user1"]})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_maintainers(data, "nonexistent")

        assert result == []

    def test_get_maintainers_returns_empty_list_for_orphan_package(self):
        """Should return empty list for package with no maintainers."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={"orphan": []})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_maintainers(data, "orphan")

        assert result == []


class TestMaintainershipRepositoryGetPackagesByMaintainer:
    """Tests for MaintainershipRepository.get_packages_by_maintainer()."""

    def test_get_packages_by_maintainer_returns_user_packages(self):
        """Should return all packages maintained by user."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(
            packages={
                "apache2": ["user1", "user2"],
                "nginx": ["user1", "web-maintainers"],
                "kernel": ["user2"],
                "orphan": [],
            }
        )

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages_by_maintainer(data, "user1")

        assert sorted(result) == ["apache2", "nginx"]

    def test_get_packages_by_maintainer_returns_group_packages(self):
        """Should return all packages maintained by group."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(
            packages={
                "apache2": ["user1", "web-maintainers"],
                "nginx": ["web-maintainers"],
                "kernel": ["user2", "kernel-team"],
            }
        )

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages_by_maintainer(data, "web-maintainers")

        assert sorted(result) == ["apache2", "nginx"]

    def test_get_packages_by_maintainer_returns_empty_for_nonexistent(self):
        """Should return empty list for non-existent maintainer."""
        from bugowner.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={"apache2": ["user1"]})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages_by_maintainer(data, "nonexistent")

        assert result == []
