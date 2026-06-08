"""Tests for validation_service module - orchestrates validation workflow."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from bugowner.domain.bulk_map import BulkMap
from bugowner.domain.maintainer import MaintainershipData
from bugowner.services.validation_service import ValidationResult, ValidationService


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_initialization(self):
        """Should initialize with all required fields."""
        result = ValidationResult(
            orphan_packages=["pkg1", "pkg2"],
            maintained_packages_without_submodule=["pkg4"],
            shipped_not_in_submodule=["pkg3"],
            new_false_positives={"bin1": "src1"},
        )

        assert result.orphan_packages == ["pkg1", "pkg2"]
        assert result.maintained_packages_without_submodule == ["pkg4"]
        assert result.shipped_not_in_submodule == ["pkg3"]
        assert result.new_false_positives == {"bin1": "src1"}

    def test_validation_result_with_empty_lists(self):
        """Should handle empty lists and dicts."""
        result = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
            new_false_positives={},
        )

        assert result.orphan_packages == []
        assert result.maintained_packages_without_submodule == []
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


class TestFindMaintainedPackagesWithoutSubmodule:
    """Test ValidationService.find_maintained_packages_without_submodule method."""

    def test_finds_packages_in_maintainership_not_in_submodules(self):
        """Should identify packages in maintainership but not in git submodules."""
        service = ValidationService(None, None, None, None, None)
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
                "pkg3": ["user3"],
            }
        )
        submodules = ["pkg2", "pkg4"]  # pkg1 and pkg3 missing

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == ["pkg1", "pkg3"]

    def test_all_packages_have_submodules(self):
        """Should return empty list when all maintained packages have submodules."""
        service = ValidationService(None, None, None, None, None)
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
            }
        )
        submodules = ["pkg1", "pkg2", "pkg3"]

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == []

    def test_all_packages_lack_submodules_returns_sorted(self):
        """Should return sorted list when all packages lack submodules."""
        service = ValidationService(None, None, None, None, None)
        maintainership = MaintainershipData(
            packages={
                "zebra": ["user1"],
                "apple": ["user2"],
                "middle": ["user3"],
            }
        )
        submodules = []

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == ["apple", "middle", "zebra"]

    def test_empty_maintainership(self):
        """Should return empty list when maintainership is empty."""
        service = ValidationService(None, None, None, None, None)
        maintainership = MaintainershipData(packages={})
        submodules = ["mod1", "mod2"]

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == []

    def test_empty_submodules_returns_all_maintained(self):
        """Should return all maintained packages when no submodules exist."""
        service = ValidationService(None, None, None, None, None)
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
                "pkg3": ["user3"],
            }
        )
        submodules = []

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == ["pkg1", "pkg2", "pkg3"]


class TestFindShippedWithoutSubmodule:
    """Test ValidationService.find_shipped_without_submodule method."""

    def test_returns_three_tuple_with_shipped_not_in_submodule(self):
        """Should return 3-tuple including shipped_not_in_submodule list."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()
        # OBS finds pkg2 → "pkg2-src", but NOT pkg3 (returns empty dict means not found)
        obs_repo.query_source_packages.return_value = {"pkg2": "pkg2-src"}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"pkg1", "pkg2", "pkg3"}
        submodules = ["pkg1", "pkg2-src"]
        fp_file = Path("/tmp/fp.json")

        # Expecting 3-tuple return
        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

        # pkg1 in submodules directly
        # pkg2 mapped to pkg2-src via OBS, pkg2-src in submodules
        assert valid == {"pkg1", "pkg2-src"}

        # pkg3 NOT found in OBS (not in new_fps), so should be in shipped_not_in_submodule
        assert not_in_sub == ["pkg3"]

        # Only pkg2 discovered via OBS
        assert new_fps == {"pkg2": "pkg2-src"}

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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

        # All shipped packages found in submodules
        assert valid == {"pkg1", "pkg2"}
        assert not_in_sub == []  # No packages missing
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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

        # Binary package remapped to source package found in submodules
        assert valid == {"source-pkg"}
        assert not_in_sub == []  # Resolved via cache
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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

        # Unknown package resolved via OBS to source package in submodules
        assert valid == {"source-pkg"}
        assert not_in_sub == []  # Found via OBS
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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

        # Only known package is valid, unknown not resolved
        assert valid == {"known-pkg"}
        assert not_in_sub == ["unknown-pkg"]  # OBS didn't find it
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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

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

        valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
            shipped, submodules, fp_file
        )

        # skip-pkg filtered out (null in cache), valid-pkg found
        assert valid == {"valid-pkg"}
        assert new_fps == {}

        # Should load cache
        false_positives_repo.load.assert_called_once_with(fp_file)

        # Should NOT query OBS (skip-pkg filtered, valid-pkg in submodules)
        obs_repo.query_source_packages.assert_not_called()

        # Should NOT save cache
        false_positives_repo.save.assert_not_called()

    def test_logs_obs_query_activity_when_unknowns_found(self, caplog):
        """Should log OBS query activity when unknown packages found."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()
        # OBS finds pkg2 → pkg2-src
        obs_repo.query_source_packages.return_value = {"pkg2": "pkg2-src"}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"pkg1", "pkg2", "pkg3"}
        submodules = ["pkg1"]  # pkg2, pkg3 unknown
        fp_file = Path("/tmp/fp.json")

        # Capture logs
        with caplog.at_level(logging.INFO):
            valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
                shipped, submodules, fp_file
            )

        # Should log before OBS queries
        assert "Found 2 unknown packages. Querying OBS in parallel..." in caplog.text

        # Should log when false positives discovered
        assert "Found 1 false-positives packages" in caplog.text

    def test_logs_no_false_positives_when_obs_returns_empty(self, caplog):
        """Should log 'No false-positives' when OBS returns nothing."""
        # Mock repositories
        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {}  # OBS finds nothing

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        shipped = {"pkg1", "pkg2"}
        submodules = []  # All unknown
        fp_file = Path("/tmp/fp.json")

        # Capture logs
        with caplog.at_level(logging.INFO):
            valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
                shipped, submodules, fp_file
            )

        # Should log before OBS queries
        assert "Found 2 unknown packages. Querying OBS in parallel..." in caplog.text

        # Should log when no false positives found
        assert "No false-positives packages found" in caplog.text

    def test_no_obs_logging_when_all_packages_in_submodules(self, caplog):
        """Should NOT log OBS activity when all packages in submodules."""
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

        shipped = {"pkg1", "pkg2"}
        submodules = ["pkg1", "pkg2"]  # All in submodules
        fp_file = Path("/tmp/fp.json")

        # Capture logs
        with caplog.at_level(logging.INFO):
            valid, not_in_sub, new_fps = service.find_shipped_without_submodule(
                shipped, submodules, fp_file
            )

        # Should NOT log OBS activity (no unknowns)
        assert "Querying OBS" not in caplog.text
        assert "false-positives" not in caplog.text


class TestValidateAll:
    """Test ValidationService.validate_all method."""

    def test_validate_all_happy_path_no_issues(self):
        """Should orchestrate all validations when no issues found."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1", "pkg2"]

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2"}

        obs_repo = Mock()

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        maintainership_file = Path("/tmp/maintainership.json")
        repo_metadata_file = Path("/tmp/primary.xml.gz")
        false_positives_file = Path("/tmp/fp.json")
        git_dir = Path("/tmp/repo")

        result = service.validate_all(
            maintainership_file,
            repo_metadata_file,
            false_positives_file,
            git_dir,
        )

        # Should load all data
        maintainership_repo.load.assert_called_once_with(maintainership_file)
        metadata_repo.parse_source_packages.assert_called_once_with(repo_metadata_file)
        git_repo.list_submodules.assert_called_once_with(git_dir)

        # All packages have maintainers, all submodules maintained, all shipped in submodules
        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {}

    def test_validate_all_finds_orphan_packages(self):
        """Should identify shipped packages without maintainers."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                # pkg2 missing - orphan (but IS in submodules, so not shipped_not_in_submodule)
                "pkg2": [],  # Empty list also counts as orphan
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1", "pkg2"]

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2"}

        obs_repo = Mock()

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # Should find pkg2 as orphan (empty maintainer list)
        assert result.orphan_packages == ["pkg2"]
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {}

    def test_validate_all_finds_shipped_not_in_submodule(self):
        """Should identify shipped packages not in submodules."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1"]

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2"}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {}  # Not found in OBS

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # Should find pkg2 not in submodules
        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == ["pkg2"]
        assert result.new_false_positives == {}

    def test_validate_all_uses_valid_packages_for_orphan_check(self):
        """Should check orphans only for valid packages, not all shipped packages.

        Bug: validate_all currently passes shipped_packages to find_orphan_packages,
        but should pass valid_packages (packages in submodules or OBS-resolved).

        Scenario:
        - shipped_packages = {pkg1, pkg2, pkg3}
        - pkg3 NOT in submodules
        - OBS query returns None for pkg3 (not found)
        - Therefore pkg3 NOT in valid_packages
        - Therefore pkg3 should NOT appear in orphan_packages
        """
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["user1"],  # Has maintainer
                # pkg2 missing - orphan (but in submodules, so valid)
                # pkg3 missing - but NOT valid (not in submodules, OBS returns None)
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1", "pkg2"]  # pkg3 NOT in submodules

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2", "pkg3"}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {}  # OBS returns None for pkg3

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # BUG EXPOSED: Current code incorrectly includes pkg3 in orphan check
        # pkg3 should NOT be checked because it's not valid (not in submodules, OBS failed)
        # Only pkg2 should be in orphan_packages (valid but no maintainer)
        assert result.orphan_packages == ["pkg2"]  # Will FAIL with current code
        assert result.shipped_not_in_submodule == ["pkg3"]

    def test_validate_all_with_new_false_positives_discovered(self):
        """Should return new binary→source mappings discovered from OBS queries."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "src-pkg": ["user1"],
                "bin-pkg": ["user1"],  # Binary package also in maintainership
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["src-pkg"]

        metadata_repo = Mock()
        # Metadata shows bin-pkg as shipped (even though unusual)
        metadata_repo.parse_source_packages.return_value = {"bin-pkg"}

        obs_repo = Mock()
        # OBS maps bin-pkg → src-pkg
        obs_repo.query_source_packages.return_value = {"bin-pkg": "src-pkg"}

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}
        false_positives_repo.save = Mock()  # Mock save method

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # Should return new mapping, bin-pkg maps to src-pkg which IS in submodules
        # So no shipped_not_in_submodule issue
        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {"bin-pkg": "src-pkg"}

        # Should load cache only once (optimization from code review)
        false_positives_repo.load.assert_called_once_with(Path("/tmp/fp.json"))

    def test_validate_all_with_multiple_issues(self):
        """Should find all types of issues in single run."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": [],  # Empty list - orphan
                "pkg3": ["user3"],  # Has maintainer but not in submodules
                "submod1": ["user2"],
                # submod2 missing - unmaintained submodule
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["submod1", "submod2"]

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2", "pkg3"}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {}  # pkg2, pkg3 not found in OBS

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # Should find all types of issues:
        # - NO orphans (pkg2 has empty maintainer list BUT not valid - not in submodules)
        # - submod2 is unmaintained submodule
        # - pkg1, pkg2, pkg3 are all shipped but not in submodules (none are valid)
        assert result.orphan_packages == []  # None valid, so none checked for orphans
        assert result.shipped_not_in_submodule == ["pkg1", "pkg2", "pkg3"]
        assert result.new_false_positives == {}

    def test_validate_all_with_empty_inputs(self):
        """Should handle completely empty inputs gracefully."""
        # Mock repositories - all return empty data
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(packages={})

        git_repo = Mock()
        git_repo.list_submodules.return_value = []

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = set()

        obs_repo = Mock()

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # All results should be empty
        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {}

        # Should still load all data sources
        maintainership_repo.load.assert_called_once()
        metadata_repo.parse_source_packages.assert_called_once()

    def test_validate_all_includes_maintained_packages_without_submodule(self):
        """Should include maintained_packages_without_submodule in ValidationResult."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["alice@example.com"],
                "pkg2": ["bob@example.com"],
                "pkg3": ["charlie@example.com"],
            }
        )

        git_repo = Mock()
        # Only pkg1 has submodule
        git_repo.list_submodules.return_value = ["pkg1"]

        metadata_repo = Mock()
        # All packages shipped
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2", "pkg3"}

        obs_repo = Mock()
        obs_repo.query_source_packages.return_value = {}

        false_positives_repo = Mock()
        false_positives_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=obs_repo,
            false_positives_repo=false_positives_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        # pkg2, pkg3 in maintainership but not in submodules
        assert result.maintained_packages_without_submodule == ["pkg2", "pkg3"]
        git_repo.list_submodules.assert_called_once()
        false_positives_repo.load.assert_called_once()


def _make_bulk_map(mapping: dict[str, str], project: str = "SUSE:SLFO:Main") -> BulkMap:
    """Build a BulkMap value object for tests."""
    return BulkMap(
        mapping=mapping,
        project=project,
        fetched_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )


class TestFindShippedNewPipeline:
    """Test ValidationService.find_shipped_without_submodule new pipeline.

    The new pipeline (bulk_map + overrides) is gated on bulk_map_repo and
    overrides_repo being supplied to the constructor and on overrides_file +
    cache_dir being supplied to the method. When all four are present, the
    legacy obs_repo + false_positives_repo path is bypassed entirely.
    """

    def test_resolves_shipped_via_bulk_map(self):
        """Should resolve binary names to source names via the bulk map."""
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        shipped = {"apache2-devel"}
        submodules = ["apache2"]
        fp_file = Path("/tmp/fp.json")
        overrides_file = Path("/tmp/overrides.json")
        cache_dir = Path("/tmp/cache")
        bulk_map = _make_bulk_map({"apache2-devel": "apache2", "apache2": "apache2"})

        valid, residue, new_fps = service.find_shipped_without_submodule(
            shipped,
            submodules,
            fp_file,
            overrides_file=overrides_file,
            cache_dir=cache_dir,
            bulk_map=bulk_map,
        )

        assert valid == {"apache2"}
        assert residue == []
        assert new_fps == {}

    def test_override_takes_priority_over_bulk_map(self):
        """Should prefer overrides over bulk_map when both have an entry."""
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        # Override says kernel-azure → kernel-source-azure
        overrides_repo.load.return_value = {"kernel-azure": "kernel-source-azure"}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        shipped = {"kernel-azure"}
        submodules = ["kernel-source-azure"]
        # Bulk_map says kernel-azure → kernel-azure-base (different from override).
        bulk_map = _make_bulk_map({"kernel-azure": "kernel-azure-base"})

        valid, residue, new_fps = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # Override wins: resolved to kernel-source-azure, which IS a submodule.
        assert valid == {"kernel-source-azure"}
        assert residue == []
        assert new_fps == {}

    def test_override_null_drops_name_from_residue(self):
        """Should drop names explicitly mapped to None in overrides."""
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"SLES-release": None}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        shipped = {"SLES-release"}
        submodules: list[str] = []  # empty
        bulk_map = _make_bulk_map({})

        valid, residue, new_fps = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # SLES-release explicitly suppressed: NOT in valid, NOT in residue.
        assert valid == set()
        assert residue == []
        assert "SLES-release" not in residue
        assert new_fps == {}

    def test_unmapped_name_falls_through_to_residue(self):
        """Should treat unmapped names as their own source and report residue."""
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        shipped = {"orphan-pkg"}
        submodules: list[str] = []  # no submodules
        bulk_map = _make_bulk_map({})  # no entry for orphan-pkg

        valid, residue, new_fps = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # Passthrough: orphan-pkg → orphan-pkg, not in submodules → residue.
        assert valid == set()
        assert residue == ["orphan-pkg"]
        assert new_fps == {}

    def test_no_subprocess_invoked_when_bulk_map_preloaded(self):
        """Should NOT call bulk_map_repo.load_bulk_map when bulk_map passed in.

        Performance contract: when validate_all has already loaded the bulk
        map once, find_shipped_without_submodule must reuse it rather than
        triggering a second (potentially network-bound) load.
        """
        bulk_map_repo = Mock()
        bulk_map_repo.load_bulk_map.side_effect = AssertionError("must not be called")
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        bulk_map = _make_bulk_map({"pkg1": "pkg1"})

        # Must not raise.
        valid, residue, new_fps = service.find_shipped_without_submodule(
            {"pkg1"},
            ["pkg1"],
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == {"pkg1"}
        bulk_map_repo.load_bulk_map.assert_not_called()

    def test_validate_all_loads_bulk_map_exactly_once(self):
        """validate_all should fetch bulk_map a single time per invocation."""
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(packages={"pkg1": ["user1"]})
        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1"]
        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1"}

        bulk_map_repo = Mock()
        bulk_map_repo.load_bulk_map.return_value = _make_bulk_map({"pkg1": "pkg1"})
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
        )

        assert bulk_map_repo.load_bulk_map.call_count == 1

    def test_new_pipeline_returns_empty_new_false_positives_dict(self):
        """New pipeline always returns {} as 3rd tuple element (shim contract).

        4b removes new_false_positives entirely. Until then, the shim must
        keep returning {} to preserve the legacy 3-tuple shape.
        """
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        bulk_map = _make_bulk_map({"pkg1": "pkg1"})
        result = service.find_shipped_without_submodule(
            {"pkg1"},
            ["pkg1"],
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert result[2] == {}

    def test_validate_all_populates_unresolved_names_from_new_pipeline(self):
        """validate_all should set ValidationResult.unresolved_names to the
        sorted residue under the new pipeline; legacy path leaves it []."""
        # --- New pipeline branch ---
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(packages={})
        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1"]
        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "orphan-z", "orphan-a"}

        bulk_map_repo = Mock()
        bulk_map_repo.load_bulk_map.return_value = _make_bulk_map({"pkg1": "pkg1"})
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service_new = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        result_new = service_new.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
        )

        # Residue is sorted: orphan-a, orphan-z
        assert result_new.unresolved_names == ["orphan-a", "orphan-z"]
        assert result_new.shipped_not_in_submodule == ["orphan-a", "orphan-z"]

        # --- Legacy branch (no new deps): unresolved_names stays [] ---
        legacy_fp_repo = Mock()
        legacy_fp_repo.load.return_value = {}
        legacy_obs_repo = Mock()
        legacy_obs_repo.query_source_packages.return_value = {}

        service_legacy = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=legacy_obs_repo,
            false_positives_repo=legacy_fp_repo,
        )

        result_legacy = service_legacy.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
        )

        assert result_legacy.unresolved_names == []

    def test_validate_all_uses_valid_packages_for_orphan_check(self):
        """Orphan check must use valid_packages, not raw shipped_packages.

        New-pipeline mirror of the legacy invariant: pkg3 is shipped but
        neither in submodules nor mapped by overrides/bulk_map, so it must
        NOT appear in orphan_packages even though it lacks a maintainer.
        Only pkg2 (valid via submodule, no maintainer) is an orphan.
        """
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                # pkg2 missing (orphan, but in submodules)
                # pkg3 missing AND not valid → must NOT be flagged orphan
            }
        )
        git_repo = Mock()
        git_repo.list_submodules.return_value = ["pkg1", "pkg2"]
        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = {"pkg1", "pkg2", "pkg3"}

        bulk_map_repo = Mock()
        # bulk_map only knows pkg1/pkg2 → passthrough; pkg3 unmapped → residue
        bulk_map_repo.load_bulk_map.return_value = _make_bulk_map({"pkg1": "pkg1", "pkg2": "pkg2"})
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        result = service.validate_all(
            Path("/tmp/maintainership.json"),
            Path("/tmp/primary.xml.gz"),
            Path("/tmp/fp.json"),
            Path("/tmp/repo"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
        )

        assert result.orphan_packages == ["pkg2"]
        assert result.shipped_not_in_submodule == ["pkg3"]
        assert result.unresolved_names == ["pkg3"]

    def test_override_target_not_in_submodules_lands_in_residue(self):
        """Override target must land in residue when not a submodule.

        When overrides[shipped] maps to a value that is NOT a submodule,
        the override's resolved value lands in residue. The bulk_map's
        competing answer for the same shipped name MUST be ignored
        entirely (no silent leak into valid via the bulk_map branch).
        """
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        # Override says X → Y.
        overrides_repo.load.return_value = {"X": "Y"}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        shipped = {"X"}
        # Submodules contain Z (bulk_map's answer), NOT Y (override's answer).
        submodules = ["Z"]
        # Bulk_map says X → Z, but override must win and bulk_map answer
        # must NOT leak through.
        bulk_map = _make_bulk_map({"X": "Z"})

        valid, residue, new_fps = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # Override wins: resolved to Y. Y is not a submodule → residue.
        # Z (bulk_map's answer) must NOT be in valid.
        assert valid == set()
        assert residue == ["Y"]
        assert new_fps == {}

    def test_overrides_keyed_on_shipped_name_not_resolved_value(self):
        """Overrides must be consulted on the shipped name, not the resolved value.

        If bulk_map resolves shipped name N to value X, and overrides has
        an entry for X (NOT for N), the override on X must NOT apply.
        Only direct overrides on shipped names take effect.
        """
        bulk_map_repo = Mock()
        overrides_repo = Mock()
        # Override is keyed on X (the resolved value), NOT on N (the shipped name).
        overrides_repo.load.return_value = {"X": None}

        service = ValidationService(
            maintainership_repo=None,
            git_repo=None,
            metadata_repo=None,
            obs_repo=Mock(),
            false_positives_repo=Mock(),
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )

        shipped = {"N"}
        submodules: list[str] = []
        # Bulk_map resolves N → X. The override on X is irrelevant because
        # lookup is overrides["N"], not overrides["X"].
        bulk_map = _make_bulk_map({"N": "X"})

        valid, residue, new_fps = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/fp.json"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # X falls through bulk_map and lands in residue (override on X ignored).
        assert valid == set()
        assert residue == ["X"]
        assert new_fps == {}
