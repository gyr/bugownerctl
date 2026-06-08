"""Tests for validation_service module - orchestrates validation workflow."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from bugowner.domain.bulk_map import BulkMap
from bugowner.domain.maintainer import MaintainershipData
from bugowner.services.validation_service import ValidationResult, ValidationService


def _make_bulk_map(mapping: dict[str, str], project: str = "SUSE:SLFO:Main") -> BulkMap:
    """Build a BulkMap value object for tests."""
    return BulkMap(
        mapping=mapping,
        project=project,
        fetched_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )


def _make_service(
    *,
    maintainership_repo: object = None,
    git_repo: object = None,
    metadata_repo: object = None,
    bulk_map_repo: object | None = None,
    overrides_repo: object | None = None,
) -> ValidationService:
    """Build a ValidationService with sensible mock defaults for tests.

    Tests that don't care about the repos beyond their existence can omit
    them; this helper provides Mock() instances so the required ctor args
    are satisfied.
    """
    if bulk_map_repo is None:
        bulk_map_repo = Mock()
    if overrides_repo is None:
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}
    return ValidationService(
        maintainership_repo,  # type: ignore[arg-type]
        git_repo,  # type: ignore[arg-type]
        metadata_repo,  # type: ignore[arg-type]
        bulk_map_repo=bulk_map_repo,  # type: ignore[arg-type]
        overrides_repo=overrides_repo,  # type: ignore[arg-type]
    )


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_initialization(self):
        """Should initialize with all required fields."""
        result = ValidationResult(
            orphan_packages=["pkg1", "pkg2"],
            maintained_packages_without_submodule=["pkg4"],
            shipped_not_in_submodule=["pkg3"],
            unresolved_names=["pkg3"],
        )

        assert result.orphan_packages == ["pkg1", "pkg2"]
        assert result.maintained_packages_without_submodule == ["pkg4"]
        assert result.shipped_not_in_submodule == ["pkg3"]
        assert result.unresolved_names == ["pkg3"]

    def test_validation_result_with_empty_lists(self):
        """Should handle empty lists."""
        result = ValidationResult(
            orphan_packages=[],
            maintained_packages_without_submodule=[],
            shipped_not_in_submodule=[],
        )

        assert result.orphan_packages == []
        assert result.maintained_packages_without_submodule == []
        assert result.shipped_not_in_submodule == []
        # unresolved_names defaults to []
        assert result.unresolved_names == []


class TestFindOrphanPackages:
    """Test ValidationService.find_orphan_packages method."""

    def test_finds_packages_without_maintainers(self):
        """Should identify shipped packages missing from maintainership data."""
        service = _make_service()
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
        service = _make_service()
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
        service = _make_service()
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
        service = _make_service()
        shipped: set[str] = set()
        maintainership = MaintainershipData(packages={"pkg1": ["user1"]})

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == []

    def test_all_orphans_returns_sorted(self):
        """Should return sorted list when all packages are orphans."""
        service = _make_service()
        shipped = {"zebra", "apple", "middle"}
        maintainership = MaintainershipData(packages={})

        result = service.find_orphan_packages(shipped, maintainership)

        assert result == ["apple", "middle", "zebra"]


class TestFindMaintainedPackagesWithoutSubmodule:
    """Test ValidationService.find_maintained_packages_without_submodule method."""

    def test_finds_packages_in_maintainership_not_in_submodules(self):
        """Should identify packages in maintainership but not in git submodules."""
        service = _make_service()
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
        service = _make_service()
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
        service = _make_service()
        maintainership = MaintainershipData(
            packages={
                "zebra": ["user1"],
                "apple": ["user2"],
                "middle": ["user3"],
            }
        )
        submodules: list[str] = []

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == ["apple", "middle", "zebra"]

    def test_empty_maintainership(self):
        """Should return empty list when maintainership is empty."""
        service = _make_service()
        maintainership = MaintainershipData(packages={})
        submodules = ["mod1", "mod2"]

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == []

    def test_empty_submodules_returns_all_maintained(self):
        """Should return all maintained packages when no submodules exist."""
        service = _make_service()
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
                "pkg3": ["user3"],
            }
        )
        submodules: list[str] = []

        result = service.find_maintained_packages_without_submodule(maintainership, submodules)

        assert result == ["pkg1", "pkg2", "pkg3"]


class TestFindShippedWithoutSubmodule:
    """Test ValidationService.find_shipped_without_submodule (bulk-map pipeline).

    The new pipeline consults overrides FIRST then the bulk map for each
    shipped name; unmapped names fall through as their own source.
    """

    def test_resolves_shipped_via_bulk_map(self):
        """Should resolve binary names to source names via the bulk map."""
        service = _make_service()

        shipped = {"apache2-devel"}
        submodules = ["apache2"]
        overrides_file = Path("/tmp/overrides.json")
        cache_dir = Path("/tmp/cache")
        bulk_map = _make_bulk_map({"apache2-devel": "apache2", "apache2": "apache2"})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            overrides_file,
            cache_dir,
            bulk_map=bulk_map,
        )

        assert valid == {"apache2"}
        assert residue == []
        assert unresolved == []

    def test_override_takes_priority_over_bulk_map(self):
        """Should prefer overrides over bulk_map when both have an entry."""
        overrides_repo = Mock()
        # Override says kernel-azure → kernel-source-azure
        overrides_repo.load.return_value = {"kernel-azure": "kernel-source-azure"}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"kernel-azure"}
        submodules = ["kernel-source-azure"]
        # Bulk_map says kernel-azure → kernel-azure-base (different from override).
        bulk_map = _make_bulk_map({"kernel-azure": "kernel-azure-base"})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # Override wins: resolved to kernel-source-azure, which IS a submodule.
        assert valid == {"kernel-source-azure"}
        assert residue == []
        assert unresolved == []

    def test_override_null_drops_name_from_residue(self):
        """Should drop names explicitly mapped to None in overrides."""
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"SLES-release": None}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"SLES-release"}
        submodules: list[str] = []
        bulk_map = _make_bulk_map({})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # SLES-release explicitly suppressed: NOT in valid, NOT in residue, NOT unresolved.
        assert valid == set()
        assert residue == []
        assert unresolved == []

    def test_unmapped_name_falls_through_to_residue(self):
        """Should treat unmapped names as their own source and report residue."""
        service = _make_service()

        shipped = {"orphan-pkg"}
        submodules: list[str] = []
        bulk_map = _make_bulk_map({})  # no entry for orphan-pkg

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # Passthrough: orphan-pkg → orphan-pkg, not in submodules → residue.
        # Identity fallthrough + not a submodule → unresolved.
        assert valid == set()
        assert residue == ["orphan-pkg"]
        assert unresolved == ["orphan-pkg"]

    def test_no_subprocess_invoked_when_bulk_map_preloaded(self):
        """Should NOT call bulk_map_repo.load_bulk_map when bulk_map passed in.

        Performance contract: when validate_all has already loaded the bulk
        map once, find_shipped_without_submodule must reuse it rather than
        triggering a second (potentially network-bound) load.
        """
        bulk_map_repo = Mock()
        bulk_map_repo.load_bulk_map.side_effect = AssertionError("must not be called")

        service = _make_service(bulk_map_repo=bulk_map_repo)

        bulk_map = _make_bulk_map({"pkg1": "pkg1"})

        # Must not raise.
        valid, residue, unresolved = service.find_shipped_without_submodule(
            {"pkg1"},
            ["pkg1"],
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == {"pkg1"}
        bulk_map_repo.load_bulk_map.assert_not_called()

    def test_empty_shipped_packages(self):
        """Should return empty sets when no shipped packages."""
        service = _make_service()

        shipped: set[str] = set()
        submodules = ["pkg1", "pkg2"]
        bulk_map = _make_bulk_map({})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == set()
        assert residue == []
        assert unresolved == []

    def test_override_target_not_in_submodules_lands_in_residue(self):
        """Override target must land in residue when not a submodule.

        When overrides[shipped] maps to a value that is NOT a submodule,
        the override's resolved value lands in residue. The bulk_map's
        competing answer for the same shipped name MUST be ignored
        entirely (no silent leak into valid via the bulk_map branch).
        """
        overrides_repo = Mock()
        # Override says X → Y.
        overrides_repo.load.return_value = {"X": "Y"}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"X"}
        # Submodules contain Z (bulk_map's answer), NOT Y (override's answer).
        submodules = ["Z"]
        # Bulk_map says X → Z, but override must win and bulk_map answer
        # must NOT leak through.
        bulk_map = _make_bulk_map({"X": "Z"})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # Override wins: resolved to Y. Y is not a submodule → residue.
        # Z (bulk_map's answer) must NOT be in valid.
        # Y came from overrides branch (not identity) → NOT unresolved.
        assert valid == set()
        assert residue == ["Y"]
        assert unresolved == []

    def test_overrides_keyed_on_shipped_name_not_resolved_value(self):
        """Overrides must be consulted on the shipped name, not the resolved value.

        If bulk_map resolves shipped name N to value X, and overrides has
        an entry for X (NOT for N), the override on X must NOT apply.
        Only direct overrides on shipped names take effect.
        """
        overrides_repo = Mock()
        # Override is keyed on X (the resolved value), NOT on N (the shipped name).
        overrides_repo.load.return_value = {"X": None}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"N"}
        submodules: list[str] = []
        # Bulk_map resolves N → X. The override on X is irrelevant because
        # lookup is overrides["N"], not overrides["X"].
        bulk_map = _make_bulk_map({"N": "X"})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        # X falls through bulk_map and lands in residue (override on X ignored).
        # N resolved via bulk_map branch → NOT unresolved.
        assert valid == set()
        assert residue == ["X"]
        assert unresolved == []

    def test_loads_overrides_and_bulk_map_when_not_preloaded(self):
        """Should call repos to load overrides/bulk_map if caller did not pass them in."""
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        bulk_map_repo = Mock()
        bulk_map_repo.load_bulk_map.return_value = _make_bulk_map({"pkg1": "pkg1"})

        service = _make_service(bulk_map_repo=bulk_map_repo, overrides_repo=overrides_repo)

        overrides_file = Path("/tmp/overrides.json")
        cache_dir = Path("/tmp/cache")

        valid, residue, unresolved = service.find_shipped_without_submodule(
            {"pkg1"},
            ["pkg1"],
            overrides_file,
            cache_dir,
        )

        assert valid == {"pkg1"}
        assert residue == []
        assert unresolved == []
        overrides_repo.load.assert_called_once_with(overrides_file)
        bulk_map_repo.load_bulk_map.assert_called_once_with("SUSE:SLFO:Main", cache_dir)

    def test_unresolved_names_subset_of_residue_only_identity_fallthrough(self):
        """unresolved should contain only names that fell through to identity AND aren't submodules.

        Scenario:
          - M is in overrides → resolved to "M-src" (a submodule). NOT residue.
          - B is in bulk_map → resolved to "B-src" (a submodule). NOT residue.
          - I has no override, no bulk_map entry → identity fallthrough.
            I is NOT in submodules → goes to residue AND unresolved.
        """
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"M": "M-src"}
        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"M", "B", "I"}
        submodules = ["M-src", "B-src"]
        bulk_map = _make_bulk_map({"B": "B-src"})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == {"M-src", "B-src"}
        assert residue == ["I"]
        assert unresolved == ["I"]

    def test_unresolved_excludes_overridden_residue(self):
        """Override target landing in residue must NOT be classified as unresolved.

        Resolution went through the overrides branch, so the name had a
        mapping decision; the target just happens not to be a submodule.
        """
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"O": "O-bogus"}
        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"O"}
        submodules: list[str] = []
        bulk_map = _make_bulk_map({})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == set()
        assert residue == ["O-bogus"]
        assert unresolved == []

    def test_unresolved_excludes_bulk_map_residue(self):
        """Bulk_map target landing in residue must NOT be classified as unresolved.

        Resolution went through the bulk_map branch, so the name had a
        mapping decision; the target just happens not to be a submodule.
        """
        service = _make_service()

        shipped = {"K"}
        submodules: list[str] = []
        bulk_map = _make_bulk_map({"K": "K-bogus"})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == set()
        assert residue == ["K-bogus"]
        assert unresolved == []

    def test_unresolved_excludes_identity_in_submodules(self):
        """Identity fallthrough that IS a submodule lands in valid, not residue or unresolved."""
        service = _make_service()

        shipped = {"S"}
        submodules = ["S"]
        bulk_map = _make_bulk_map({})

        valid, residue, unresolved = service.find_shipped_without_submodule(
            shipped,
            submodules,
            Path("/tmp/overrides.json"),
            Path("/tmp/cache"),
            bulk_map=bulk_map,
        )

        assert valid == {"S"}
        assert residue == []
        assert unresolved == []


class TestValidateAll:
    """Test ValidationService.validate_all method."""

    def _make_validate_all_service(
        self,
        *,
        maintainership_packages: dict[str, list[str]],
        submodules: list[str],
        shipped: set[str],
        bulk_map_mapping: dict[str, str],
        overrides: dict[str, str | None] | None = None,
    ) -> tuple[ValidationService, Mock, Mock, Mock, Mock, Mock]:
        """Wire a service with all five mocked dependencies for validate_all."""
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(packages=maintainership_packages)
        git_repo = Mock()
        git_repo.list_submodules.return_value = submodules
        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = shipped

        bulk_map_repo = Mock()
        bulk_map_repo.load_bulk_map.return_value = _make_bulk_map(bulk_map_mapping)
        overrides_repo = Mock()
        overrides_repo.load.return_value = overrides if overrides is not None else {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            git_repo=git_repo,
            metadata_repo=metadata_repo,
            bulk_map_repo=bulk_map_repo,
            overrides_repo=overrides_repo,
        )
        return service, maintainership_repo, git_repo, metadata_repo, bulk_map_repo, overrides_repo

    def test_validate_all_happy_path_no_issues(self):
        """Should orchestrate all validations when no issues found."""
        service, m_repo, g_repo, md_repo, _, _ = self._make_validate_all_service(
            maintainership_packages={"pkg1": ["user1"], "pkg2": ["user2"]},
            submodules=["pkg1", "pkg2"],
            shipped={"pkg1", "pkg2"},
            bulk_map_mapping={"pkg1": "pkg1", "pkg2": "pkg2"},
        )

        maintainership_file = Path("/tmp/maintainership.json")
        repo_metadata_file = Path("/tmp/primary.xml.gz")
        overrides_file = Path("/tmp/overrides.json")
        cache_dir = Path("/tmp/cache")
        git_dir = Path("/tmp/repo")

        result = service.validate_all(
            maintainership_file=maintainership_file,
            repo_metadata_file=repo_metadata_file,
            overrides_file=overrides_file,
            cache_dir=cache_dir,
            git_dir=git_dir,
        )

        m_repo.load.assert_called_once_with(maintainership_file)
        md_repo.parse_source_packages.assert_called_once_with(repo_metadata_file)
        g_repo.list_submodules.assert_called_once_with(git_dir)

        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == []
        assert result.unresolved_names == []

    def test_validate_all_finds_orphan_packages(self):
        """Should identify shipped packages without maintainers."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["user1"],
                # pkg2 in submodules but missing maintainer → orphan
                "pkg2": [],  # Empty list also counts as orphan
            },
            submodules=["pkg1", "pkg2"],
            shipped={"pkg1", "pkg2"},
            bulk_map_mapping={"pkg1": "pkg1", "pkg2": "pkg2"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        assert result.orphan_packages == ["pkg2"]
        assert result.shipped_not_in_submodule == []

    def test_validate_all_finds_shipped_not_in_submodule(self):
        """Should identify shipped packages not in submodules."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={"pkg1": ["user1"], "pkg2": ["user2"]},
            submodules=["pkg1"],
            shipped={"pkg1", "pkg2"},
            bulk_map_mapping={"pkg1": "pkg1"},  # pkg2 unmapped → passthrough → residue
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == ["pkg2"]
        assert result.unresolved_names == ["pkg2"]

    def test_validate_all_uses_valid_packages_for_orphan_check(self):
        """Orphan check must use valid_packages, not raw shipped_packages.

        pkg3 is shipped but neither in submodules nor mapped by overrides/
        bulk_map, so it must NOT appear in orphan_packages even though it
        lacks a maintainer. Only pkg2 (valid via submodule, no maintainer)
        is an orphan.
        """
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["user1"],
                # pkg2 missing (orphan, but in submodules)
                # pkg3 missing AND not valid → must NOT be flagged orphan
            },
            submodules=["pkg1", "pkg2"],
            shipped={"pkg1", "pkg2", "pkg3"},
            # bulk_map only knows pkg1/pkg2 → passthrough; pkg3 unmapped → residue
            bulk_map_mapping={"pkg1": "pkg1", "pkg2": "pkg2"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        assert result.orphan_packages == ["pkg2"]
        assert result.shipped_not_in_submodule == ["pkg3"]
        assert result.unresolved_names == ["pkg3"]

    def test_validate_all_with_multiple_issues(self):
        """Should find all types of issues in single run."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["user1"],
                "pkg2": [],  # orphan if valid
                "pkg3": ["user3"],  # has maintainer but not in submodules
                "submod1": ["user2"],
                # submod2 missing - unmaintained submodule
            },
            submodules=["submod1", "submod2"],
            shipped={"pkg1", "pkg2", "pkg3"},
            bulk_map_mapping={},  # nothing mapped → all passthrough → all residue
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        # No shipped packages are valid (none in submodules) → no orphans checked
        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == ["pkg1", "pkg2", "pkg3"]

    def test_validate_all_with_empty_inputs(self):
        """Should handle completely empty inputs gracefully."""
        service, m_repo, _, md_repo, _, _ = self._make_validate_all_service(
            maintainership_packages={},
            submodules=[],
            shipped=set(),
            bulk_map_mapping={},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        assert result.orphan_packages == []
        assert result.shipped_not_in_submodule == []

        m_repo.load.assert_called_once()
        md_repo.parse_source_packages.assert_called_once()

    def test_validate_all_includes_maintained_packages_without_submodule(self):
        """Should include maintained_packages_without_submodule in ValidationResult."""
        service, _, g_repo, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["alice@example.com"],
                "pkg2": ["bob@example.com"],
                "pkg3": ["charlie@example.com"],
            },
            submodules=["pkg1"],
            shipped={"pkg1", "pkg2", "pkg3"},
            bulk_map_mapping={"pkg1": "pkg1"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        assert result.maintained_packages_without_submodule == ["pkg2", "pkg3"]
        g_repo.list_submodules.assert_called_once()

    def test_validate_all_loads_bulk_map_exactly_once(self):
        """validate_all should fetch bulk_map a single time per invocation."""
        service, _, _, _, bulk_map_repo, _ = self._make_validate_all_service(
            maintainership_packages={"pkg1": ["user1"]},
            submodules=["pkg1"],
            shipped={"pkg1"},
            bulk_map_mapping={"pkg1": "pkg1"},
        )

        service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        assert bulk_map_repo.load_bulk_map.call_count == 1

    def test_validate_all_populates_unresolved_names_from_residue(self):
        """validate_all should set ValidationResult.unresolved_names to the
        sorted residue from the pipeline."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={},
            submodules=["pkg1"],
            shipped={"pkg1", "orphan-z", "orphan-a"},
            bulk_map_mapping={"pkg1": "pkg1"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            cache_dir=Path("/tmp/cache"),
            git_dir=Path("/tmp/repo"),
        )

        # Residue is sorted: orphan-a, orphan-z
        assert result.unresolved_names == ["orphan-a", "orphan-z"]
        assert result.shipped_not_in_submodule == ["orphan-a", "orphan-z"]
