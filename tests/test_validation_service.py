"""Tests for validation_service module - orchestrates validation workflow."""

from src.bugowner.domain.maintainer import MaintainershipData
from src.bugowner.services.validation_service import ValidationResult, ValidationService


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_initialization(self):
        """Should initialize with all required fields."""
        result = ValidationResult(
            orphan_packages=["pkg1", "pkg2"],
            unmaintained_submodules=["mod1"],
            shipped_not_in_submodule=["pkg3"],
            new_false_positives={"bin1": "src1"},
        )

        assert result.orphan_packages == ["pkg1", "pkg2"]
        assert result.unmaintained_submodules == ["mod1"]
        assert result.shipped_not_in_submodule == ["pkg3"]
        assert result.new_false_positives == {"bin1": "src1"}

    def test_validation_result_with_empty_lists(self):
        """Should handle empty lists and dicts."""
        result = ValidationResult(
            orphan_packages=[],
            unmaintained_submodules=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )

        assert result.orphan_packages == []
        assert result.unmaintained_submodules == []
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {}


class TestFindOrphanPackages:
    """Test ValidationService.find_orphan_packages method."""

    def test_finds_packages_without_maintainers(self):
        """Should identify shipped packages missing from maintainership data."""
        service = ValidationService(None, None, None, None, None)
        shipped = {"pkg1", "pkg2", "pkg3"}
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
                # pkg3 missing - should be orphan
            }
        )

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == ["pkg3"]

    def test_empty_maintainer_list_is_orphan(self):
        """Should treat packages with empty maintainer lists as orphans."""
        service = ValidationService(None, None, None, None, None)
        shipped = {"pkg1", "pkg2"}
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": [],  # empty list - orphan
            }
        )

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == ["pkg2"]

    def test_no_orphans_when_all_maintained(self):
        """Should return empty list when all shipped packages have maintainers."""
        service = ValidationService(None, None, None, None, None)
        shipped = {"pkg1", "pkg2"}
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
            }
        )

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == []

    def test_empty_shipped_packages(self):
        """Should return empty list when no packages shipped."""
        service = ValidationService(None, None, None, None, None)
        shipped = set()
        maintainership = MaintainershipData(packages={"pkg1": ["user1"]})

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == []

    def test_all_orphans_returns_sorted(self):
        """Should return sorted list when all packages are orphans."""
        service = ValidationService(None, None, None, None, None)
        shipped = {"zebra", "apple", "middle"}
        maintainership = MaintainershipData(packages={})

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == ["apple", "middle", "zebra"]
