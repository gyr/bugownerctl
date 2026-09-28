"""Tests for validation_service module - orchestrates validation workflow."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugownerctl.domain.maintainer import MaintainershipData
from bugownerctl.domain.obs_source_info import ObsSourceInfo
from bugownerctl.services.validation_service import ValidationResult, ValidationService

# Synthetic OBS project name passed to every service call that requires one.
_OBS_PROJECT = "TEST:Project:1.0"


def _make_source_info(
    mapping: dict[str, str],
    project: str = "SUSE:SLFO:Main",
    *,
    packages: frozenset[str] = frozenset(),
) -> ObsSourceInfo:
    """Build an ObsSourceInfo value object for tests."""
    return ObsSourceInfo(
        mapping=mapping,
        project=project,
        fetched_at=datetime(2026, 6, 8, tzinfo=UTC),
        packages=packages,
    )


def _make_service(
    *,
    maintainership_repo: object = None,
    metadata_repo: object = None,
    source_info_repo: object | None = None,
    overrides_repo: object | None = None,
) -> ValidationService:
    """Build a ValidationService with sensible mock defaults for tests.

    Tests that don't care about the repos beyond their existence can omit
    them; this helper provides Mock() instances so the required ctor args
    are satisfied.
    """
    if source_info_repo is None:
        source_info_repo = Mock()
    if overrides_repo is None:
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}
    return ValidationService(
        maintainership_repo,  # type: ignore[arg-type]
        metadata_repo,  # type: ignore[arg-type]
        source_info_repo=source_info_repo,  # type: ignore[arg-type]
        overrides_repo=overrides_repo,  # type: ignore[arg-type]
    )


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_initialization(self):
        """Should initialize with all required fields."""
        result = ValidationResult(
            orphan_packages=["pkg1", "pkg2"],
            maintained_packages_not_in_obs=["pkg4"],
            shipped_not_in_obs=["pkg3"],
            shipped_package_count=0,
            obs_package_count=0,
            maintained_package_count=0,
            unresolved_names=["pkg3"],
        )

        assert result.orphan_packages == ["pkg1", "pkg2"]
        assert result.maintained_packages_not_in_obs == ["pkg4"]
        assert result.shipped_not_in_obs == ["pkg3"]
        assert result.unresolved_names == ["pkg3"]

    def test_validation_result_with_empty_lists(self):
        """Should handle empty lists."""
        result = ValidationResult(
            orphan_packages=[],
            maintained_packages_not_in_obs=[],
            shipped_not_in_obs=[],
            shipped_package_count=0,
            obs_package_count=0,
            maintained_package_count=0,
        )

        assert result.orphan_packages == []
        assert result.maintained_packages_not_in_obs == []
        assert result.shipped_not_in_obs == []
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


class TestFindMaintainedPackagesNotInObs:
    """Test ValidationService.find_maintained_packages_not_in_obs method."""

    def test_finds_packages_in_maintainership_not_in_obs(self):
        """Should identify packages in maintainership but not in the OBS package set."""
        service = _make_service()
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
                "pkg3": ["user3"],
            }
        )
        obs_packages = frozenset({"pkg2", "pkg4"})  # pkg1 and pkg3 missing

        result = service.find_maintained_packages_not_in_obs(maintainership, obs_packages)

        assert result == ["pkg1", "pkg3"]

    def test_all_packages_in_obs(self):
        """Should return empty list when all maintained packages are in the OBS package set."""
        service = _make_service()
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
            }
        )
        obs_packages = frozenset({"pkg1", "pkg2", "pkg3"})

        result = service.find_maintained_packages_not_in_obs(maintainership, obs_packages)

        assert result == []

    def test_no_packages_in_obs_returns_sorted(self):
        """Should return sorted list when no package is in the OBS package set."""
        service = _make_service()
        maintainership = MaintainershipData(
            packages={
                "zebra": ["user1"],
                "apple": ["user2"],
                "middle": ["user3"],
            }
        )
        obs_packages: frozenset[str] = frozenset()

        result = service.find_maintained_packages_not_in_obs(maintainership, obs_packages)

        assert result == ["apple", "middle", "zebra"]

    def test_empty_maintainership(self):
        """Should return empty list when maintainership is empty."""
        service = _make_service()
        maintainership = MaintainershipData(packages={})
        obs_packages = frozenset({"mod1", "mod2"})

        result = service.find_maintained_packages_not_in_obs(maintainership, obs_packages)

        assert result == []

    def test_empty_obs_package_set_returns_all_maintained(self):
        """Should return all maintained packages when the OBS package set is empty."""
        service = _make_service()
        maintainership = MaintainershipData(
            packages={
                "pkg1": ["user1"],
                "pkg2": ["user2"],
                "pkg3": ["user3"],
            }
        )
        obs_packages: frozenset[str] = frozenset()

        result = service.find_maintained_packages_not_in_obs(maintainership, obs_packages)

        assert result == ["pkg1", "pkg2", "pkg3"]


class TestResolveShippedPackages:
    """Test ValidationService.resolve_shipped_packages (source-info pipeline).

    The new pipeline consults overrides FIRST then the OBS source info for each
    shipped name; unmapped names fall through as their own source.
    """

    def test_resolves_shipped_via_source_info(self):
        """Should resolve binary names to source names via the OBS source info."""
        service = _make_service()

        shipped = {"apache2-devel"}
        overrides_file = Path("/tmp/overrides.json")
        source_info = _make_source_info(
            {"apache2-devel": "apache2", "apache2": "apache2"}, packages=frozenset({"apache2"})
        )

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            overrides_file,
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == {"apache2"}
        assert residue == []
        assert unresolved == []

    def test_override_takes_priority_over_source_info(self):
        """Should prefer overrides over source_info when both have an entry."""
        overrides_repo = Mock()
        # Override says kernel-azure → kernel-source-azure
        overrides_repo.load.return_value = {"kernel-azure": "kernel-source-azure"}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"kernel-azure"}
        # OBS source info says kernel-azure → kernel-azure-base (different from override).
        source_info = _make_source_info(
            {"kernel-azure": "kernel-azure-base"}, packages=frozenset({"kernel-source-azure"})
        )

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        # Override wins: resolved to kernel-source-azure, which IS in the OBS package set.
        assert valid == {"kernel-source-azure"}
        assert residue == []
        assert unresolved == []

    def test_override_null_drops_name_from_residue(self):
        """Should drop names explicitly mapped to None in overrides."""
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"SLES-release": None}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"SLES-release"}
        source_info = _make_source_info({})

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        # SLES-release explicitly suppressed: NOT in valid, NOT in residue, NOT unresolved.
        assert valid == set()
        assert residue == []
        assert unresolved == []

    def test_unmapped_name_falls_through_to_residue(self):
        """Should treat unmapped names as their own source and report residue."""
        service = _make_service()

        shipped = {"orphan-pkg"}
        source_info = _make_source_info({})  # no entry for orphan-pkg

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        # Passthrough: orphan-pkg → orphan-pkg, not in the OBS package set → residue.
        # Identity fallthrough + not in the OBS package set → unresolved.
        assert valid == set()
        assert residue == ["orphan-pkg"]
        assert unresolved == ["orphan-pkg"]

    def test_no_subprocess_invoked_when_source_info_preloaded(self):
        """Should NOT call source_info_repo.load_source_info when source_info passed in.

        Performance contract: when validate_all has already loaded the OBS
        source info once, resolve_shipped_packages must reuse it rather than
        triggering a second (potentially network-bound) load.
        """
        source_info_repo = Mock()
        source_info_repo.load_source_info.side_effect = AssertionError("must not be called")

        service = _make_service(source_info_repo=source_info_repo)

        source_info = _make_source_info({"pkg1": "pkg1"}, packages=frozenset({"pkg1"}))

        # Must not raise.
        valid, residue, unresolved = service.resolve_shipped_packages(
            {"pkg1"},
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == {"pkg1"}
        source_info_repo.load_source_info.assert_not_called()

    def test_empty_shipped_packages(self):
        """Should return empty sets when no shipped packages."""
        service = _make_service()

        shipped: set[str] = set()
        source_info = _make_source_info({}, packages=frozenset({"pkg1", "pkg2"}))

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == set()
        assert residue == []
        assert unresolved == []

    def test_override_target_not_in_obs_lands_in_residue(self):
        """Override target must land in residue when not in the OBS package set.

        When overrides[shipped] maps to a value NOT in the OBS package set,
        the override's resolved value lands in residue. The source_info's
        competing answer for the same shipped name MUST be ignored
        entirely (no silent leak into valid via the source_info branch).
        """
        overrides_repo = Mock()
        # Override says X → Y.
        overrides_repo.load.return_value = {"X": "Y"}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"X"}
        # OBS package set contains Z (source_info's answer), NOT Y (override's answer).
        # OBS source info says X → Z, but override must win and source_info answer
        # must NOT leak through.
        source_info = _make_source_info({"X": "Z"}, packages=frozenset({"Z"}))

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        # Override wins: resolved to Y. Y is not in the OBS package set → residue.
        # Z (source_info's answer) must NOT be in valid.
        # Y came from overrides branch (not identity) → NOT unresolved.
        assert valid == set()
        assert residue == ["Y"]
        assert unresolved == []

    def test_overrides_keyed_on_shipped_name_not_resolved_value(self):
        """Overrides must be consulted on the shipped name, not the resolved value.

        If source_info resolves shipped name N to value X, and overrides has
        an entry for X (NOT for N), the override on X must NOT apply.
        Only direct overrides on shipped names take effect.
        """
        overrides_repo = Mock()
        # Override is keyed on X (the resolved value), NOT on N (the shipped name).
        overrides_repo.load.return_value = {"X": None}

        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"N"}
        # OBS source info resolves N → X. The override on X is irrelevant because
        # lookup is overrides["N"], not overrides["X"].
        source_info = _make_source_info({"N": "X"})

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        # X falls through source_info and lands in residue (override on X ignored).
        # N resolved via source_info branch → NOT unresolved.
        assert valid == set()
        assert residue == ["X"]
        assert unresolved == []

    def test_loads_overrides_and_source_info_when_not_preloaded(self):
        """Should call repos to load overrides/source_info if caller did not pass them in."""
        overrides_repo = Mock()
        overrides_repo.load.return_value = {}

        source_info_repo = Mock()
        source_info_repo.load_source_info.return_value = _make_source_info(
            {"pkg1": "pkg1"}, packages=frozenset({"pkg1"})
        )

        service = _make_service(source_info_repo=source_info_repo, overrides_repo=overrides_repo)

        overrides_file = Path("/tmp/overrides.json")

        valid, residue, unresolved = service.resolve_shipped_packages(
            {"pkg1"},
            overrides_file,
            obs_project=_OBS_PROJECT,
        )

        assert valid == {"pkg1"}
        assert residue == []
        assert unresolved == []
        overrides_repo.load.assert_called_once_with(overrides_file)
        source_info_repo.load_source_info.assert_called_once_with(_OBS_PROJECT)

    def test_unresolved_names_subset_of_residue_only_identity_fallthrough(self):
        """unresolved should contain only identity-fallthrough names not in the OBS package set.

        Scenario:
          - M is in overrides → resolved to "M-src" (in the set). NOT residue.
          - B is in source_info → resolved to "B-src" (in the set). NOT residue.
          - I has no override, no source_info entry → identity fallthrough.
            I is NOT in the set → goes to residue AND unresolved.
        """
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"M": "M-src"}
        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"M", "B", "I"}
        source_info = _make_source_info({"B": "B-src"}, packages=frozenset({"M-src", "B-src"}))

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == {"M-src", "B-src"}
        assert residue == ["I"]
        assert unresolved == ["I"]

    def test_unresolved_excludes_overridden_residue(self):
        """Override target landing in residue must NOT be classified as unresolved.

        Resolution went through the overrides branch, so the name had a
        mapping decision; the target just happens not to be in the OBS package set.
        """
        overrides_repo = Mock()
        overrides_repo.load.return_value = {"O": "O-bogus"}
        service = _make_service(overrides_repo=overrides_repo)

        shipped = {"O"}
        source_info = _make_source_info({})

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == set()
        assert residue == ["O-bogus"]
        assert unresolved == []

    def test_unresolved_excludes_source_info_residue(self):
        """OBS source info target landing in residue must NOT be classified as unresolved.

        Resolution went through the source_info branch, so the name had a
        mapping decision; the target just happens not to be in the OBS package set.
        """
        service = _make_service()

        shipped = {"K"}
        source_info = _make_source_info({"K": "K-bogus"})

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == set()
        assert residue == ["K-bogus"]
        assert unresolved == []

    def test_unresolved_excludes_identity_in_obs(self):
        """Identity fallthrough in the OBS package set lands in valid, not residue/unresolved."""
        service = _make_service()

        shipped = {"S"}
        source_info = _make_source_info({}, packages=frozenset({"S"}))

        valid, residue, unresolved = service.resolve_shipped_packages(
            shipped,
            Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
            source_info=source_info,
        )

        assert valid == {"S"}
        assert residue == []
        assert unresolved == []

    def test_resolve_shipped_packages_requires_obs_project(self):
        """Omitting obs_project is a TypeError — there is no silent default project."""
        service = _make_service()

        with pytest.raises(TypeError, match="obs_project"):
            service.resolve_shipped_packages(  # type: ignore[call-arg]  # omission under test
                {"pkg1"},
                Path("/tmp/overrides.json"),
                source_info=_make_source_info({}),
            )


class TestValidateAll:
    """Test ValidationService.validate_all method."""

    def _make_validate_all_service(
        self,
        *,
        maintainership_packages: dict[str, list[str]],
        obs_packages: frozenset[str],
        shipped: set[str],
        source_info_mapping: dict[str, str],
        overrides: dict[str, str | None] | None = None,
    ) -> tuple[ValidationService, Mock, Mock, Mock, Mock]:
        """Wire a service with all four mocked dependencies for validate_all."""
        maintainership_repo = Mock()
        maintainership_repo.load.return_value = MaintainershipData(packages=maintainership_packages)
        metadata_repo = Mock()
        metadata_repo.parse_source_packages.return_value = shipped

        source_info_repo = Mock()
        source_info_repo.load_source_info.return_value = _make_source_info(
            source_info_mapping, packages=obs_packages
        )
        overrides_repo = Mock()
        overrides_repo.load.return_value = overrides if overrides is not None else {}

        service = ValidationService(
            maintainership_repo=maintainership_repo,
            metadata_repo=metadata_repo,
            source_info_repo=source_info_repo,
            overrides_repo=overrides_repo,
        )
        return service, maintainership_repo, metadata_repo, source_info_repo, overrides_repo

    def test_validate_all_happy_path_no_issues(self):
        """Should orchestrate all validations when no issues found."""
        service, m_repo, md_repo, _, _ = self._make_validate_all_service(
            maintainership_packages={"pkg1": ["user1"], "pkg2": ["user2"]},
            obs_packages=frozenset({"pkg1", "pkg2"}),
            shipped={"pkg1", "pkg2"},
            source_info_mapping={"pkg1": "pkg1", "pkg2": "pkg2"},
        )

        maintainership_file = Path("/tmp/maintainership.json")
        repo_metadata_file = Path("/tmp/primary.xml.gz")
        overrides_file = Path("/tmp/overrides.json")

        result = service.validate_all(
            maintainership_file=maintainership_file,
            repo_metadata_file=repo_metadata_file,
            overrides_file=overrides_file,
            obs_project=_OBS_PROJECT,
        )

        m_repo.load.assert_called_once_with(maintainership_file)
        md_repo.parse_source_packages.assert_called_once_with(repo_metadata_file)

        assert result.orphan_packages == []
        assert result.shipped_not_in_obs == []
        assert result.unresolved_names == []

    def test_validate_all_finds_orphan_packages(self):
        """Should identify shipped packages without maintainers."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["user1"],
                # pkg2 in the OBS package set but missing maintainer → orphan
                "pkg2": [],  # Empty list also counts as orphan
            },
            obs_packages=frozenset({"pkg1", "pkg2"}),
            shipped={"pkg1", "pkg2"},
            source_info_mapping={"pkg1": "pkg1", "pkg2": "pkg2"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.orphan_packages == ["pkg2"]
        assert result.shipped_not_in_obs == []

    def test_validate_all_finds_shipped_not_in_obs(self):
        """Should identify shipped packages not in the OBS package set."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={"pkg1": ["user1"], "pkg2": ["user2"]},
            obs_packages=frozenset({"pkg1"}),
            shipped={"pkg1", "pkg2"},
            source_info_mapping={"pkg1": "pkg1"},  # pkg2 unmapped → passthrough → residue
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.orphan_packages == []
        assert result.shipped_not_in_obs == ["pkg2"]
        assert result.unresolved_names == ["pkg2"]

    def test_validate_all_uses_valid_packages_for_orphan_check(self):
        """Orphan check must use valid_packages, not raw shipped_packages.

        pkg3 is shipped but neither in the OBS package set nor mapped by
        overrides/source_info, so it must NOT appear in orphan_packages even
        though it lacks a maintainer. Only pkg2 (valid via the OBS package
        set, no maintainer) is an orphan.
        """
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["user1"],
                # pkg2 missing (orphan, but in the OBS package set)
                # pkg3 missing AND not valid → must NOT be flagged orphan
            },
            obs_packages=frozenset({"pkg1", "pkg2"}),
            shipped={"pkg1", "pkg2", "pkg3"},
            # source_info only knows pkg1/pkg2 → passthrough; pkg3 unmapped → residue
            source_info_mapping={"pkg1": "pkg1", "pkg2": "pkg2"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.orphan_packages == ["pkg2"]
        assert result.shipped_not_in_obs == ["pkg3"]
        assert result.unresolved_names == ["pkg3"]

    def test_validate_all_with_multiple_issues(self):
        """Should find all types of issues in single run."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["user1"],
                "pkg2": [],  # orphan if valid
                "pkg3": ["user3"],  # has maintainer but not in the OBS package set
                "obspkg1": ["user2"],
                # obspkg2 missing - unmaintained OBS package
            },
            obs_packages=frozenset({"obspkg1", "obspkg2"}),
            shipped={"pkg1", "pkg2", "pkg3"},
            source_info_mapping={},  # nothing mapped → all passthrough → all residue
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        # No shipped packages are valid (none in the OBS package set) → no orphans checked
        assert result.orphan_packages == []
        assert result.shipped_not_in_obs == ["pkg1", "pkg2", "pkg3"]

    def test_validate_all_with_empty_inputs(self):
        """Should handle completely empty inputs gracefully."""
        service, m_repo, md_repo, _, _ = self._make_validate_all_service(
            maintainership_packages={},
            obs_packages=frozenset(),
            shipped=set(),
            source_info_mapping={},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.orphan_packages == []
        assert result.shipped_not_in_obs == []

        m_repo.load.assert_called_once()
        md_repo.parse_source_packages.assert_called_once()

    def test_validate_all_includes_maintained_packages_not_in_obs(self):
        """Should include maintained_packages_not_in_obs in ValidationResult."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={
                "pkg1": ["alice@example.com"],
                "pkg2": ["bob@example.com"],
                "pkg3": ["charlie@example.com"],
            },
            obs_packages=frozenset({"pkg1"}),
            shipped={"pkg1", "pkg2", "pkg3"},
            source_info_mapping={"pkg1": "pkg1"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.maintained_packages_not_in_obs == ["pkg2", "pkg3"]

    def test_validate_all_loads_source_info_exactly_once(self):
        """validate_all should fetch source_info a single time per invocation."""
        service, _, _, source_info_repo, _ = self._make_validate_all_service(
            maintainership_packages={"pkg1": ["user1"]},
            obs_packages=frozenset({"pkg1"}),
            shipped={"pkg1"},
            source_info_mapping={"pkg1": "pkg1"},
        )

        service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        source_info_repo.load_source_info.assert_called_once_with(_OBS_PROJECT)

    def test_validate_all_populates_unresolved_names_from_residue(self):
        """validate_all should set ValidationResult.unresolved_names to the
        sorted residue from the pipeline."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={},
            obs_packages=frozenset({"pkg1"}),
            shipped={"pkg1", "orphan-z", "orphan-a"},
            source_info_mapping={"pkg1": "pkg1"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        # Residue is sorted: orphan-a, orphan-z
        assert result.unresolved_names == ["orphan-a", "orphan-z"]
        assert result.shipped_not_in_obs == ["orphan-a", "orphan-z"]

    def test_validate_all_requires_obs_project(self):
        """Omitting obs_project is a TypeError — there is no silent default project."""
        service, _, _, source_info_repo, _ = self._make_validate_all_service(
            maintainership_packages={},
            obs_packages=frozenset(),
            shipped=set(),
            source_info_mapping={},
        )

        with pytest.raises(TypeError, match="obs_project"):
            service.validate_all(  # type: ignore[call-arg]  # omission under test
                maintainership_file=Path("/tmp/maintainership.json"),
                repo_metadata_file=Path("/tmp/primary.xml.gz"),
                overrides_file=Path("/tmp/overrides.json"),
            )

        source_info_repo.load_source_info.assert_not_called()

    def test_validate_all_orphan_check_uses_source_resolved_via_source_info(self):
        """A binary resolved to a source in the OBS package set makes that source valid."""
        service, *_ = self._make_validate_all_service(
            maintainership_packages={"pkg-a": []},
            obs_packages=frozenset({"pkg-a"}),
            shipped={"pkg-a-devel", "stray-bin"},
            source_info_mapping={"pkg-a-devel": "pkg-a", "pkg-a": "pkg-a"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.shipped_not_in_obs == ["stray-bin"]
        assert result.unresolved_names == ["stray-bin"]
        # pkg-a is in the OBS package set → valid → orphan (empty maintainer list).
        assert result.orphan_packages == ["pkg-a"]

    def test_validate_all_returns_package_totals(self):
        """validate_all should report shipped, OBS and maintained package counts.

        Shipped count is taken before name resolution; an entry with an empty
        maintainer list is not counted as maintained.
        """
        service, *_ = self._make_validate_all_service(
            maintainership_packages={"pkg-a": ["user1"], "pkg-b": ["user2"], "pkg-c": []},
            obs_packages=frozenset({"pkg-a", "pkg-b", "pkg-c", "pkg-d"}),
            shipped={"pkg-a", "pkg-a-devel", "stray-bin"},
            source_info_mapping={"pkg-a-devel": "pkg-a", "pkg-a": "pkg-a"},
        )

        result = service.validate_all(
            maintainership_file=Path("/tmp/maintainership.json"),
            repo_metadata_file=Path("/tmp/primary.xml.gz"),
            overrides_file=Path("/tmp/overrides.json"),
            obs_project=_OBS_PROJECT,
        )

        assert result.shipped_package_count == 3
        assert result.obs_package_count == 4
        assert result.maintained_package_count == 2
