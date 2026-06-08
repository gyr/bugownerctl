"""Validation service - orchestrates validation workflow.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for finding orphans, mismatches, etc.
    - Extracted from validate_maintainership.py
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bugowner.domain.bulk_map import BulkMap
from bugowner.domain.maintainer import MaintainershipData
from bugowner.repositories.false_positives_repository import (
    FalsePositivesRepository,
)
from bugowner.repositories.git_repository import GitRepository
from bugowner.repositories.maintainership_repository import MaintainershipRepository
from bugowner.repositories.name_overrides_repository import NameOverridesRepository
from bugowner.repositories.obs_bulk_source_info_repository import (
    ObsBulkSourceInfoRepository,
)
from bugowner.repositories.obs_repository import ObsRepository
from bugowner.repositories.repo_metadata_repository import RepoMetadataRepository

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Results from validation workflow."""

    orphan_packages: list[str]
    maintained_packages_without_submodule: list[str]
    shipped_not_in_submodule: list[str]
    new_false_positives: dict[str, str]
    unresolved_names: list[str] = field(default_factory=list)


class ValidationService:
    """Service for validating maintainership data."""

    def __init__(
        self,
        maintainership_repo: MaintainershipRepository,
        git_repo: GitRepository,
        metadata_repo: RepoMetadataRepository,
        obs_repo: ObsRepository,
        false_positives_repo: FalsePositivesRepository,
        *,
        bulk_map_repo: ObsBulkSourceInfoRepository | None = None,
        overrides_repo: NameOverridesRepository | None = None,
    ) -> None:
        self.maintainership_repo = maintainership_repo
        self.git_repo = git_repo
        self.metadata_repo = metadata_repo
        self.obs_repo = obs_repo
        self.false_positives_repo = false_positives_repo
        self.bulk_map_repo = bulk_map_repo
        self.overrides_repo = overrides_repo

    def find_orphan_packages(
        self, shipped_packages: set[str], maintainership_data: MaintainershipData
    ) -> list[str]:
        """Find shipped packages without maintainers.

        Args:
            shipped_packages: Set of shipped package names
            maintainership_data: Maintainership data

        Returns:
            Sorted list of orphan packages
        """
        return sorted(
            [pkg for pkg in shipped_packages if not maintainership_data.packages.get(pkg)]
        )

    def find_maintained_packages_without_submodule(
        self, maintainership_data: MaintainershipData, submodules: list[str]
    ) -> list[str]:
        """Find packages in maintainership file but not in git submodules.

        Args:
            maintainership_data: Maintainership data
            submodules: List of git submodule names

        Returns:
            Sorted list of packages in maintainership without submodules
        """
        packages_in_maintainership = set(maintainership_data.packages.keys())
        submodule_set = set(submodules)
        return sorted(packages_in_maintainership - submodule_set)

    def find_shipped_without_submodule(
        self,
        shipped_packages: set[str],
        submodules: list[str],
        false_positives_file: Path,
        obs_project: str = "SUSE:SLFO:Main",
        cache: dict[str, str | None] | None = None,
        *,
        overrides_file: Path | None = None,
        cache_dir: Path | None = None,
        bulk_map: BulkMap | None = None,
        overrides: Mapping[str, str | None] | None = None,
    ) -> tuple[set[str], list[str], dict[str, str]]:
        """Find shipped packages not in submodules.

        Dispatches to the new bulk-map + overrides pipeline when its
        dependencies are present, otherwise uses the legacy OBS per-package
        fallback. The legacy branch is preserved verbatim for backward
        compatibility during Phase 4a.

        Args:
            shipped_packages: Set of package names from repo metadata
            submodules: List of git submodule names
            false_positives_file: Path to false-positives cache (legacy only)
            obs_project: OBS project to query
            cache: Optional pre-loaded false-positives cache (legacy only)
            overrides_file: Path to hand-curated overrides JSON (new pipeline)
            cache_dir: Cache directory for bulk-map XML (new pipeline)
            bulk_map: Preloaded BulkMap value object (new pipeline,
                avoids re-fetching when validate_all already loaded it)
            overrides: Preloaded overrides mapping (new pipeline)

        Returns:
            Tuple of (valid_packages, shipped_not_in_submodule, new_false_positives)
            - valid_packages: Packages found in submodules or resolved
            - shipped_not_in_submodule: Packages not resolvable to a submodule
            - new_false_positives: Legacy pipeline discoveries; always {}
              under the new pipeline
        """
        if self._has_new_pipeline_deps(overrides_file, cache_dir):
            return self._find_shipped_new_pipeline(
                shipped_packages,
                submodules,
                overrides_file,  # type: ignore[arg-type]
                cache_dir,  # type: ignore[arg-type]
                obs_project,
                bulk_map=bulk_map,
                overrides=overrides,
            )
        return self._find_shipped_legacy_pipeline(
            shipped_packages,
            submodules,
            false_positives_file,
            obs_project,
            cache,
        )

    def _has_new_pipeline_deps(self, overrides_file: Path | None, cache_dir: Path | None) -> bool:
        """Return True iff every dependency for the new pipeline is supplied."""
        return (
            self.bulk_map_repo is not None
            and self.overrides_repo is not None
            and overrides_file is not None
            and cache_dir is not None
        )

    def _find_shipped_legacy_pipeline(
        self,
        shipped_packages: set[str],
        submodules: list[str],
        false_positives_file: Path,
        obs_project: str,
        cache: dict[str, str | None] | None,
    ) -> tuple[set[str], list[str], dict[str, str]]:
        """Legacy implementation: false-positives cache + OBS per-package fallback."""
        # Load cache if not provided
        if cache is None:
            cache = self.false_positives_repo.load(false_positives_file)

        # Apply remapping (binary → source), filter out None values
        remapped_packages: set[str] = set()
        for pkg in shipped_packages:
            remapped = cache.get(pkg, pkg)
            if remapped is not None:
                remapped_packages.add(remapped)

        # Find packages in submodules
        submodules_set = set(submodules)
        valid_packages = remapped_packages & submodules_set

        # Find unknowns (not in submodules after remapping)
        unknowns = remapped_packages - submodules_set

        # Query OBS for unknowns if any
        new_false_positives: dict[str, str] = {}
        shipped_not_in_submodule: list[str] = []

        if unknowns:
            logger.info(f"Found {len(unknowns)} unknown packages. Querying OBS in parallel...")
            new_false_positives = self.obs_repo.query_source_packages(unknowns, obs_project)

            # Check if OBS-resolved packages are in submodules
            for source_pkg in new_false_positives.values():
                if source_pkg in submodules_set:
                    valid_packages.add(source_pkg)

            # Packages where OBS query failed (not found)
            shipped_not_in_submodule = sorted(unknowns - set(new_false_positives.keys()))

            # Merge and save cache if there are new discoveries
            if new_false_positives:
                logger.info(f"Found {len(new_false_positives)} false-positives packages.")
                cache.update(new_false_positives)
                self.false_positives_repo.save(false_positives_file, cache)
            else:
                logger.info("No false-positives packages found.")

        return (valid_packages, shipped_not_in_submodule, new_false_positives)

    def _find_shipped_new_pipeline(
        self,
        shipped_packages: set[str],
        submodules: list[str],
        overrides_file: Path,
        cache_dir: Path,
        obs_project: str,
        *,
        bulk_map: BulkMap | None = None,
        overrides: Mapping[str, str | None] | None = None,
    ) -> tuple[set[str], list[str], dict[str, str]]:
        """New pipeline: hand-curated overrides + OBS bulk source-info map.

        Resolution order per shipped name N:
            1. N in overrides: value None drops N entirely; str value wins.
            2. N in bulk_map: use bulk_map[N].
            3. Else: passthrough (N is its own source name).
        """
        # Caller may pre-load (validate_all does); otherwise hit the repos.
        # mypy: both repos are non-None here because _has_new_pipeline_deps
        # required them; cast via assert for type narrowing.
        assert self.overrides_repo is not None
        assert self.bulk_map_repo is not None
        if overrides is None:
            overrides = self.overrides_repo.load(overrides_file)
        if bulk_map is None:
            bulk_map = self.bulk_map_repo.load_bulk_map(obs_project, cache_dir)

        resolved_names: set[str] = set()
        for name in shipped_packages:
            if name in overrides:
                value = overrides[name]
                if value is None:
                    continue  # explicitly suppressed
                resolved_names.add(value)
            elif name in bulk_map.mapping:
                resolved_names.add(bulk_map.mapping[name])
            else:
                resolved_names.add(name)

        submodules_set = set(submodules)
        valid = {r for r in resolved_names if r in submodules_set}
        residue = sorted(r for r in resolved_names if r not in submodules_set)
        return (valid, residue, {})

    def validate_all(
        self,
        maintainership_file: Path,
        repo_metadata_file: Path,
        false_positives_file: Path,
        git_dir: Path,
        *,
        overrides_file: Path | None = None,
        cache_dir: Path | None = None,
        obs_project: str = "SUSE:SLFO:Main",
    ) -> ValidationResult:
        """Orchestrate all validation checks.

        Args:
            maintainership_file: Path to _maintainership.json
            repo_metadata_file: Path to primary.xml.gz (downloaded metadata)
            false_positives_file: Path to false positives cache (legacy only)
            git_dir: Path to git repository
            overrides_file: Path to hand-curated overrides JSON (new pipeline)
            cache_dir: Cache dir for the OBS bulk-map XML (new pipeline)
            obs_project: OBS project to query

        Returns:
            ValidationResult with all validation findings. Under the new
            pipeline, `new_false_positives` is always {} and
            `unresolved_names` carries the residue; under the legacy
            pipeline, `unresolved_names` stays [].
        """
        # Load all data shared between both pipelines
        maintainership_data = self.maintainership_repo.load(maintainership_file)
        shipped_packages = self.metadata_repo.parse_source_packages(repo_metadata_file)
        submodules = self.git_repo.list_submodules(git_dir)

        maintained_packages_without_submodule = self.find_maintained_packages_without_submodule(
            maintainership_data, submodules
        )

        # Branch on new-pipeline readiness. Pre-load bulk_map and overrides
        # exactly once here so find_shipped_without_submodule reuses them.
        if self._has_new_pipeline_deps(overrides_file, cache_dir):
            assert self.overrides_repo is not None
            assert self.bulk_map_repo is not None
            assert overrides_file is not None
            assert cache_dir is not None
            overrides = self.overrides_repo.load(overrides_file)
            bulk_map = self.bulk_map_repo.load_bulk_map(obs_project, cache_dir)
            (
                valid_packages,
                shipped_not_in_submodule,
                new_false_positives,
            ) = self.find_shipped_without_submodule(
                shipped_packages,
                submodules,
                false_positives_file,
                obs_project=obs_project,
                overrides_file=overrides_file,
                cache_dir=cache_dir,
                bulk_map=bulk_map,
                overrides=overrides,
            )
            unresolved_names = list(shipped_not_in_submodule)
        else:
            cache = self.false_positives_repo.load(false_positives_file)
            (
                valid_packages,
                shipped_not_in_submodule,
                new_false_positives,
            ) = self.find_shipped_without_submodule(
                shipped_packages, submodules, false_positives_file, cache=cache
            )
            unresolved_names = []

        # Check orphans only for valid packages (in submodules or resolved)
        orphan_packages = self.find_orphan_packages(valid_packages, maintainership_data)

        return ValidationResult(
            orphan_packages=orphan_packages,
            maintained_packages_without_submodule=maintained_packages_without_submodule,
            shipped_not_in_submodule=shipped_not_in_submodule,
            new_false_positives=new_false_positives,
            unresolved_names=unresolved_names,
        )
