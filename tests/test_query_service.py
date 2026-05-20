"""Tests for QueryService."""

from pathlib import Path
from unittest.mock import Mock

from src.bugowner.domain.maintainer import MaintainershipData
from src.bugowner.services.query_service import (
    PackageStatus,
    QueryService,
)


class TestQueryService:
    """Tests for QueryService."""

    def test_init_stores_dependencies(self) -> None:
        """Should store repository dependencies."""
        maintainership_repo = Mock()

        service = QueryService(maintainership_repo)

        assert service.maintainership_repo is maintainership_repo

    def test_check_package_returns_maintained_when_in_maintainership(self, tmp_path: Path) -> None:
        """Should return MAINTAINED status when package in maintainership file."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(
            packages={"pkg1": ["user1@example.com", "user2@example.com"]}
        )
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"

        result = service.check_package_maintainership("pkg1", maintainership_file, whitelist_file)

        assert result.package_name == "pkg1"
        assert result.status == PackageStatus.MAINTAINED
        assert result.maintainers == ["user1@example.com", "user2@example.com"]

    def test_check_package_returns_whitelisted_when_only_in_whitelist(self, tmp_path: Path) -> None:
        """Should return WHITELISTED status when package only in whitelist."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg2"]')

        result = service.check_package_maintainership("pkg2", maintainership_file, whitelist_file)

        assert result.package_name == "pkg2"
        assert result.status == PackageStatus.WHITELISTED
        assert result.maintainers == []

    def test_check_package_returns_not_found_when_missing(self, tmp_path: Path) -> None:
        """Should return NOT_FOUND when package not in maintainership or whitelist."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg2"]')

        result = service.check_package_maintainership("pkg3", maintainership_file, whitelist_file)

        assert result.package_name == "pkg3"
        assert result.status == PackageStatus.NOT_FOUND
        assert result.maintainers == []

    def test_check_package_handles_missing_whitelist_file(self, tmp_path: Path) -> None:
        """Should handle missing whitelist file gracefully."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": ["user@example.com"]})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "nonexistent.json"

        result = service.check_package_maintainership("pkg1", maintainership_file, whitelist_file)

        assert result.status == PackageStatus.MAINTAINED

    def test_get_packages_by_maintainer_returns_all_packages(self, tmp_path: Path) -> None:
        """Should return all packages maintained by specific maintainer."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(
            packages={
                "pkg1": ["user1@example.com", "user2@example.com"],
                "pkg2": ["user1@example.com"],
                "pkg3": ["user2@example.com"],
            }
        )
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"

        result = service.get_packages_by_maintainer("user1@example.com", maintainership_file)

        assert result == ["pkg1", "pkg2"]

    def test_get_packages_by_maintainer_returns_empty_when_not_found(self, tmp_path: Path) -> None:
        """Should return empty list when maintainer not found."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(
            packages={
                "pkg1": ["user1@example.com"],
            }
        )
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"

        result = service.get_packages_by_maintainer("unknown@example.com", maintainership_file)

        assert result == []

    def test_get_packages_by_maintainer_returns_sorted_list(self, tmp_path: Path) -> None:
        """Should return packages in sorted order."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(
            packages={
                "zulu": ["user@example.com"],
                "alpha": ["user@example.com"],
                "mike": ["user@example.com"],
            }
        )
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"

        result = service.get_packages_by_maintainer("user@example.com", maintainership_file)

        assert result == ["alpha", "mike", "zulu"]

    def test_check_package_raises_error_for_invalid_json_type(self, tmp_path: Path) -> None:
        """Should raise ValueError when whitelist JSON is not an array."""
        import pytest  # noqa: I001

        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('{"malformed": "data"}')

        with pytest.raises(ValueError, match="must contain a JSON array"):
            service.check_package_maintainership("pkg2", maintainership_file, whitelist_file)

    def test_check_package_raises_error_for_non_string_elements(self, tmp_path: Path) -> None:
        """Should raise ValueError when whitelist array contains non-strings."""
        import pytest  # noqa: I001

        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg2", 123, "pkg3"]')

        with pytest.raises(ValueError, match="must contain only strings"):
            service.check_package_maintainership("pkg2", maintainership_file, whitelist_file)

    def test_check_package_raises_error_for_large_whitelist(self, tmp_path: Path) -> None:
        """Should raise ValueError when whitelist file exceeds size limit."""
        import json  # noqa: I001
        import pytest  # noqa: I001

        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_file = tmp_path / "maintainership.json"
        whitelist_file = tmp_path / "whitelist.json"

        # Create file larger than 10MB
        large_data = ["pkg"] * (3 * 1024 * 1024)  # ~12 MB
        whitelist_file.write_text(json.dumps(large_data))

        with pytest.raises(ValueError, match="is too large"):
            service.check_package_maintainership("pkg2", maintainership_file, whitelist_file)
