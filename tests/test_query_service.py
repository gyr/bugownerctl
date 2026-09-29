"""Tests for QueryService."""

from unittest.mock import Mock

from bugownerctl.domain.maintainer import MaintainershipData
from bugownerctl.services.query_service import (
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

    def test_check_package_returns_maintained_when_in_maintainership(self) -> None:
        """Should return MAINTAINED status when package in maintainership file."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(
            packages={"pkg1": ["user1@example.com", "user2@example.com"]}
        )
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"

        result = service.check_package_maintainership("pkg1", maintainership_content, b"[]")

        assert result.package_name == "pkg1"
        assert result.status == PackageStatus.MAINTAINED
        assert result.maintainers == ["user1@example.com", "user2@example.com"]

    def test_check_package_returns_whitelisted_when_only_in_whitelist(self) -> None:
        """Should return WHITELISTED status when package only in whitelist."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"
        whitelist_content = b'["pkg2"]'

        result = service.check_package_maintainership(
            "pkg2", maintainership_content, whitelist_content
        )

        assert result.package_name == "pkg2"
        assert result.status == PackageStatus.WHITELISTED
        assert result.maintainers == []

    def test_check_package_returns_not_found_when_missing(self) -> None:
        """Should return NOT_FOUND when package not in maintainership or whitelist."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"
        whitelist_content = b'["pkg2"]'

        result = service.check_package_maintainership(
            "pkg3", maintainership_content, whitelist_content
        )

        assert result.package_name == "pkg3"
        assert result.status == PackageStatus.NOT_FOUND
        assert result.maintainers == []

    def test_check_package_treats_none_whitelist_as_empty(self) -> None:
        """Should return NOT_FOUND when there is no whitelist (None) and no maintainer."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": ["user@example.com"]})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"

        result = service.check_package_maintainership("pkg2", maintainership_content, None)

        assert result.status == PackageStatus.NOT_FOUND

    def test_get_packages_by_maintainer_returns_all_packages(self) -> None:
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

        maintainership_content = b"{}"

        result = service.get_packages_by_maintainer("user1@example.com", maintainership_content)

        assert result == ["pkg1", "pkg2"]

    def test_get_packages_by_maintainer_returns_empty_when_not_found(self) -> None:
        """Should return empty list when maintainer not found."""
        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(
            packages={
                "pkg1": ["user1@example.com"],
            }
        )
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"

        result = service.get_packages_by_maintainer("unknown@example.com", maintainership_content)

        assert result == []

    def test_get_packages_by_maintainer_returns_sorted_list(self) -> None:
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

        maintainership_content = b"{}"

        result = service.get_packages_by_maintainer("user@example.com", maintainership_content)

        assert result == ["alpha", "mike", "zulu"]

    def test_check_package_raises_error_for_invalid_json_type(self) -> None:
        """Should raise ValueError when whitelist JSON is not an array."""
        import pytest  # noqa: I001

        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"
        whitelist_content = b'{"malformed": "data"}'

        with pytest.raises(ValueError, match="must contain a JSON array"):
            service.check_package_maintainership("pkg2", maintainership_content, whitelist_content)

    def test_check_package_raises_error_for_non_string_elements(self) -> None:
        """Should raise ValueError when whitelist array contains non-strings."""
        import pytest  # noqa: I001

        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"
        whitelist_content = b'["pkg2", 123, "pkg3"]'

        with pytest.raises(ValueError, match="must contain only strings"):
            service.check_package_maintainership("pkg2", maintainership_content, whitelist_content)

    def test_check_package_rejects_oversized_whitelist_payload(self) -> None:
        """Should raise ValueError when the whitelist payload exceeds the 10 MB limit."""
        import pytest  # noqa: I001

        maintainership_repo = Mock()
        maintainership_data = MaintainershipData(packages={"pkg1": []})
        maintainership_repo.load.return_value = maintainership_data

        service = QueryService(maintainership_repo)

        maintainership_content = b"{}"
        max_size = 10 * 1024 * 1024
        # Valid JSON array one byte over the limit, so only the size check can reject it.
        oversized = b"[" + b" " * (max_size - 1) + b"]"

        with pytest.raises(
            ValueError,
            match=rf"^Whitelist is too large: {len(oversized)} bytes \(max {max_size}\)$",
        ):
            service.check_package_maintainership("pkg2", maintainership_content, oversized)
