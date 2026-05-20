"""Tests for validation_service module - orchestrates validation workflow."""

from pathlib import Path
from unittest.mock import Mock

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


class TestFindUnmaintainedSubmodules:
    """Test ValidationService.find_unmaintained_submodules method."""

    def test_finds_submodules_not_in_maintainership(self):
        """Should identify submodules missing from maintainership data."""
        service = ValidationService(None, None, None, None, None)
        submodules = ["mod1", "mod2", "mod3"]
        maintainership = MaintainershipData(
            packages={
                "mod1": ["user1"],
                "mod2": ["user2"],
                # mod3 missing - should be unmaintained
            }
        )

        result = service.find_unmaintained_submodules(submodules, maintainership)

        assert result == ["mod3"]

    def test_all_submodules_maintained(self):
        """Should return empty list when all submodules in maintainership."""
        service = ValidationService(None, None, None, None, None)
        submodules = ["mod1", "mod2"]
        maintainership = MaintainershipData(
            packages={
                "mod1": ["user1"],
                "mod2": ["user2"],
            }
        )

        result = service.find_unmaintained_submodules(submodules, maintainership)

        assert result == []

    def test_all_submodules_unmaintained_returns_sorted(self):
        """Should return sorted list when all submodules unmaintained."""
        service = ValidationService(None, None, None, None, None)
        submodules = ["zebra", "apple", "middle"]
        maintainership = MaintainershipData(packages={})

        result = service.find_unmaintained_submodules(submodules, maintainership)

        assert result == ["apple", "middle", "zebra"]

    def test_empty_submodules_list(self):
        """Should return empty list when no submodules provided."""
        service = ValidationService(None, None, None, None, None)
        submodules = []
        maintainership = MaintainershipData(packages={"mod1": ["user1"]})

        result = service.find_unmaintained_submodules(submodules, maintainership)

        assert result == []

    def test_empty_maintainership_all_unmaintained(self):
        """Should return all submodules when maintainership empty."""
        service = ValidationService(None, None, None, None, None)
        submodules = ["mod1", "mod2", "mod3"]
        maintainership = MaintainershipData(packages={})

        result = service.find_unmaintained_submodules(submodules, maintainership)

        assert result == ["mod1", "mod2", "mod3"]


class TestFindShippedWithoutSubmodule:
    """Test ValidationService.find_shipped_without_submodule method."""

    def test_all_packages_in_submodules_no_obs_queries(self):
        """Should return all packages when already in submodules."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}  # Empty cache

        obs_repo = Mock()

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"pkg1", "pkg2"}
        submodules = ["pkg1", "pkg2", "pkg3"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # All shipped packages found in submodules
        assert valid == {"pkg1", "pkg2"}
        assert new_fps == {}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should NOT query OBS (all in submodules)
        obs_repo.query_source_packages.assert_not_called()

        # Should NOT save cache (no updates)
        false_positives_repo.save.assert_not_called()

    def test_binary_package_remapped_via_cache(self):
        """Should remap binary packages to source using cache."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {"binary-pkg": "source-pkg"}

        obs_repo = Mock()

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"binary-pkg"}
        submodules = ["source-pkg"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # Binary package remapped to source package found in submodules
        assert valid == {"source-pkg"}
        assert new_fps == {}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should NOT query OBS (resolved via cache)
        obs_repo.query_source_packages.assert_not_called()

        # Should NOT save cache (no new discoveries)
        false_positives_repo.save.assert_not_called()

    def test_unknown_package_found_in_obs(self):
        """Should query OBS for unknown packages and update cache."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {"unknown-pkg": "source-pkg"}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"unknown-pkg"}
        submodules = ["source-pkg"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # Unknown package resolved via OBS to source package in submodules
        assert valid == {"source-pkg"}
        assert new_fps == {"unknown-pkg": "source-pkg"}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should query OBS for unknown package
        obs_repo.query_source_packages.assert_called_once_with({"unknown-pkg"}, "SUSE:SLFO:Main")

        # Should save updated cache
        false_positives_repo.save.assert_called_once_with(fp_file, {"unknown-pkg": "source-pkg"})

    def test_unknown_package_not_found_in_obs(self):
        """Should handle unknowns not found in OBS without updating cache."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {}  # Not found in OBS

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"unknown-pkg", "known-pkg"}
        submodules = ["known-pkg"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # Only known package is valid, unknown not resolved
        assert valid == {"known-pkg"}
        assert new_fps == {}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should query OBS for unknown package
        obs_repo.query_source_packages.assert_called_once_with({"unknown-pkg"}, "SUSE:SLFO:Main")

        # Should NOT save cache (no new discoveries)
        false_positives_repo.save.assert_not_called()

    def test_empty_shipped_packages(self):
        """Should return empty sets when no shipped packages."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = set()
        submodules = ["pkg1", "pkg2"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # No shipped packages, so nothing valid
        assert valid == set()
        assert new_fps == {}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should NOT query OBS (no packages)
        obs_repo.query_source_packages.assert_not_called()

        # Should NOT save cache
        false_positives_repo.save.assert_not_called()

    def test_partial_obs_results(self):
        """Should handle partial OBS results (some found, some not)."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()
        # Only unknown1 found in OBS, unknown2 not found
        obs_repo.query_source_packages.return_value = {"unknown1": "source1"}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"unknown1", "unknown2"}
        submodules = ["source1"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # Only unknown1 resolved to source1
        assert valid == {"source1"}
        assert new_fps == {"unknown1": "source1"}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should query OBS for both unknowns
        obs_repo.query_source_packages.assert_called_once_with(
            {"unknown1", "unknown2"}, "SUSE:SLFO:Main"
        )

        # Should save cache with partial results
        false_positives_repo.save.assert_called_once_with(fp_file, {"unknown1": "source1"})

    def test_null_cache_values_filtered(self):
        """Should filter out packages with null cache values."""
        # Mock repositories
        false_positives_repo = Mock()
        # Cache has null value (package should be skipped)
        false_positives_repo.load.return_value = {"skip-pkg": None}

        obs_repo = Mock()

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"skip-pkg", "valid-pkg"}
        submodules = ["valid-pkg"]
        fp_file = Path("/tmp/fp.json")

        valid, new_fps = service.find_shipped_without_submodule(shipped, submodules, fp_file)

        # skip-pkg filtered out (null in cache), valid-pkg found
        assert valid == {"valid-pkg"}
        assert new_fps == {}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should NOT query OBS (skip-pkg filtered, valid-pkg in submodules)
        obs_repo.query_source_packages.assert_not_called()

        # Should NOT save cache
        false_positives_repo.save.assert_not_called()
