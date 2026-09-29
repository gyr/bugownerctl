"""Tests for MaintainershipRepository."""

import json

import pytest

from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl


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

        repo = MaintainershipRepositoryImpl()
        result = repo.load(json.dumps(data).encode())

        assert result.packages == {
            "apache2": ["user1", "user2"],
            "nginx": ["user3"],
        }

    def test_load_parses_new_format_groups_only(self):
        """Should parse new format with groups only."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "apache2": {"users": [], "groups": ["web-maintainers"]},
                "kernel": {"users": [], "groups": ["kernel-team", "drivers-team"]},
            },
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load(json.dumps(data).encode())

        assert result.packages == {
            "apache2": ["web-maintainers"],
            "kernel": ["kernel-team", "drivers-team"],
        }

    def test_load_parses_new_format_users_and_groups(self):
        """Should parse new format with both users and groups, users first."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "apache2": {"users": ["user1"], "groups": ["web-maintainers"]},
                "kernel": {"users": ["user2", "user3"], "groups": ["kernel-team"]},
            },
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load(json.dumps(data).encode())

        assert result.packages == {
            "apache2": ["user1", "web-maintainers"],
            "kernel": ["user2", "user3", "kernel-team"],
        }

    def test_load_parses_empty_maintainers(self):
        """Should handle packages with no maintainers."""
        data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "orphan": {"users": [], "groups": []},
                "maintained": {"users": ["user1"], "groups": []},
            },
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load(json.dumps(data).encode())

        assert result.packages == {
            "orphan": [],
            "maintained": ["user1"],
        }

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (b'{"packages": {"vim": {"users": null, "groups": ["editors"]}}}', ["editors"]),
            (b'{"packages": {"vim": {"users": ["alice"], "groups": null}}}', ["alice"]),
            (b'{"packages": {"vim": {"users": null, "groups": null}}}', []),
        ],
        ids=["users_null", "groups_null", "both_null"],
    )
    def test_load_null_name_list_normalizes_to_empty(self, content: bytes, expected: list[str]):
        """Should treat a null 'users'/'groups' value as an empty list.

        Real SLFO branches such as slfo-1.2 write JSON null where an empty
        list is meant.
        """
        repo = MaintainershipRepositoryImpl()
        result = repo.load(content)

        assert result.packages == {"vim": expected}

    def test_load_raises_json_decode_error(self):
        """Should raise JSONDecodeError for invalid JSON."""
        repo = MaintainershipRepositoryImpl()
        with pytest.raises(json.JSONDecodeError):
            repo.load(b"{ invalid json }")

    def test_load_raises_key_error_missing_packages(self):
        """Should raise KeyError if 'packages' key is missing."""
        data = {"header": {"document": "obs-maintainers", "version": "1.0"}}

        repo = MaintainershipRepositoryImpl()
        with pytest.raises(KeyError):
            repo.load(json.dumps(data).encode())


class TestMaintainershipRepositoryGetPackages:
    """Tests for MaintainershipRepository.get_packages()."""

    def test_get_packages_returns_all_package_names(self):
        """Should return set of all package names."""
        from bugownerctl.domain.maintainer import MaintainershipData

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
        from bugownerctl.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages(data)

        assert result == set()


class TestMaintainershipRepositoryGetMaintainers:
    """Tests for MaintainershipRepository.get_maintainers()."""

    def test_get_maintainers_returns_list_for_existing_package(self):
        """Should return maintainers list for existing package."""
        from bugownerctl.domain.maintainer import MaintainershipData

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
        from bugownerctl.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={"apache2": ["user1"]})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_maintainers(data, "nonexistent")

        assert result == []

    def test_get_maintainers_returns_empty_list_for_orphan_package(self):
        """Should return empty list for package with no maintainers."""
        from bugownerctl.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={"orphan": []})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_maintainers(data, "orphan")

        assert result == []


class TestMaintainershipRepositoryGetPackagesByMaintainer:
    """Tests for MaintainershipRepository.get_packages_by_maintainer()."""

    def test_get_packages_by_maintainer_returns_user_packages(self):
        """Should return all packages maintained by user."""
        from bugownerctl.domain.maintainer import MaintainershipData

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
        from bugownerctl.domain.maintainer import MaintainershipData

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
        from bugownerctl.domain.maintainer import MaintainershipData

        data = MaintainershipData(packages={"apache2": ["user1"]})

        repo = MaintainershipRepositoryImpl()
        result = repo.get_packages_by_maintainer(data, "nonexistent")

        assert result == []


class TestLoadUsersByPackage:
    """Tests for MaintainershipRepository.load_users_by_package()."""

    def test_load_users_by_package_returns_only_users_key(self):
        """Should return only users values, excluding groups."""
        data = {
            "packages": {
                "apache2": {"users": ["user1", "user2"], "groups": ["web-team"]},
                "nginx": {"users": ["user3"], "groups": ["ops-team"]},
            }
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load_users_by_package(json.dumps(data).encode())

        assert result == {
            "apache2": ["user1", "user2"],
            "nginx": ["user3"],
        }

    def test_load_users_by_package_empty_users_returns_empty_list(self):
        """Should map package with empty users list to empty list."""
        data = {
            "packages": {
                "apache2": {"users": [], "groups": ["web-team"]},
            }
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load_users_by_package(json.dumps(data).encode())

        assert result == {"apache2": []}

    def test_load_users_by_package_missing_users_key_returns_empty_list(self):
        """Should map package with no users key to empty list."""
        data = {
            "packages": {
                "kernel": {"groups": ["kernel-team"]},
            }
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load_users_by_package(json.dumps(data).encode())

        assert result == {"kernel": []}

    @pytest.mark.parametrize(
        "content",
        [b'{"packages": {"vim": {"users": null, "groups": ["editors"]}}}'],
        ids=["users_null"],
    )
    def test_load_users_by_package_null_users_returns_empty_list(self, content: bytes):
        """Should map a package whose users value is JSON null to an empty list.

        Real SLFO branches such as slfo-1.2 write JSON null where an empty
        list is meant.
        """
        repo = MaintainershipRepositoryImpl()
        result = repo.load_users_by_package(content)

        assert result == {"vim": []}

    def test_load_users_by_package_multiple_packages(self):
        """Should return all three packages with correct user lists."""
        data = {
            "packages": {
                "apache2": {"users": ["alice", "bob"], "groups": []},
                "nginx": {"users": ["carol"], "groups": ["web-team"]},
                "kernel": {"users": ["dave", "eve", "frank"], "groups": []},
            }
        }

        repo = MaintainershipRepositoryImpl()
        result = repo.load_users_by_package(json.dumps(data).encode())

        assert result == {
            "apache2": ["alice", "bob"],
            "nginx": ["carol"],
            "kernel": ["dave", "eve", "frank"],
        }

    def test_load_users_by_package_missing_packages_key_raises_key_error(self):
        """Should raise KeyError when JSON has no 'packages' key."""
        data = {"header": {"document": "obs-maintainers", "version": "1.0"}}

        repo = MaintainershipRepositoryImpl()
        with pytest.raises(KeyError):
            repo.load_users_by_package(json.dumps(data).encode())

    def test_load_users_by_package_raises_json_decode_error(self):
        """Should raise JSONDecodeError for invalid JSON."""
        repo = MaintainershipRepositoryImpl()
        with pytest.raises(json.JSONDecodeError):
            repo.load_users_by_package(b"{ invalid json }")
