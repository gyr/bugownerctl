"""Tests for validation_service module - orchestrates validation workflow."""

from pathlib import Path
from unittest.mock import Mock

from bugowner.domain.maintainer import MaintainershipData
from bugowner.services.validation_service import ValidationResult, ValidationService


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
        assert result.unmaintained_submodules == []
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
        assert result.unmaintained_submodules == []
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {}

    def test_validate_all_finds_unmaintained_submodules(self):
        """Should identify submodules not in maintainership file."""
        # Mock repositories
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(
            packages={
                "submod1": ["user2"],
                # submod2 missing - unmaintained
            }
        )

        git_repo = Mock()
        git_repo.list_submodules.return_value = ["submod1", "submod2"]

        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = set()  # No shipped packages

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

        # Should find submod2 as unmaintained
        assert result.orphan_packages == []
        assert result.unmaintained_submodules == ["submod2"]
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
        assert result.unmaintained_submodules == []
        assert result.shipped_not_in_submodule == ["pkg2"]
        assert result.new_false_positives == {}

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
        assert result.unmaintained_submodules == []
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
        # - pkg2 is orphan (empty maintainer list)
        # - submod2 is unmaintained submodule
        # - pkg1, pkg2, pkg3 are all shipped but not in submodules
        assert result.orphan_packages == ["pkg2"]
        assert result.unmaintained_submodules == ["submod2"]
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
        assert result.unmaintained_submodules == []
        assert result.shipped_not_in_submodule == []
        assert result.new_false_positives == {}

        # Should still load all data sources
        maintainership_repo.load.assert_called_once()
        metadata_repo.parse_source_packages.assert_called_once()
        git_repo.list_submodules.assert_called_once()
        false_positives_repo.load.assert_called_once()
