"""Validation service - orchestrates validation workflow.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for finding orphans, mismatches, etc.
    - Resolves shipped binary names to canonical source names via the
      OBS bulk source-info map, with hand-curated overrides taking
      priority over the bulk map.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bugownerctl.domain.bulk_map import BulkMap
from bugownerctl.domain.maintainer import MaintainershipData
from bugownerctl.repositories.git_repository import GitRepository
from bugownerctl.repositories.maintainership_repository import MaintainershipRepository
from bugownerctl.repositories.name_overrides_repository import NameOverridesRepository
from bugownerctl.repositories.obs_bulk_source_info_repository import (
    ObsBulkSourceInfoRepository,
)
from bugownerctl.repositories.repo_metadata_repository import RepoMetadataRepository

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Results from validation workflow."""

    orphan_packages: list[str]
    maintained_packages_without_submodule: list[str]
    shipped_not_in_submodule: list[str]
    unresolved_names: list[str] = field(default_factory=list)


class ValidationService:
    """Service for validating maintainership data."""

    def __init__(
        self,
        maintainership_repo: MaintainershipRepository,
        git_repo: GitRepository,
        metadata_repo: RepoMetadataRepository,
        *,
        bulk_map_repo: ObsBulkSourceInfoRepository,
        overrides_repo: NameOverridesRepository,
    ) -> None:
        self.maintainership_repo = maintainership_repo
        self.git_repo = git_repo
        self.metadata_repo = metadata_repo
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
        overrides_file: Path,
        cache_dir: Path,
        obs_project: str = "SUSE:SLFO:Main",
        *,
        bulk_map: BulkMap | None = None,
        overrides: Mapping[str, str | None] | None = None,
    ) -> tuple[set[str], list[str], list[str]]:
        """Find shipped packages not in submodules using the bulk-map pipeline.

        Resolution order per shipped name N:
            1. N in overrides: value None drops N entirely; str value wins.
            2. N in bulk_map: use bulk_map[N].
            3. Else: passthrough (N is its own source name = identity).

        Callers that need cache refresh must pre-load the bulk_map themselves
        (with force_refresh=True on bulk_map_repo.load_bulk_map) before
        passing it here.  validate_all and check_whitelist both do this.

        Args:
            shipped_packages: Set of package names from repo metadata
            submodules: List of git submodule names
            overrides_file: Path to hand-curated overrides JSON
            cache_dir: Cache directory for bulk-map XML
            obs_project: OBS project to query
            bulk_map: Preloaded BulkMap value object (avoids re-fetching when
                validate_all already loaded it)
            overrides: Preloaded overrides mapping

        Returns:
            Tuple of (valid_packages, shipped_not_in_submodule, unresolved_names)
            - valid_packages: Resolved names that ARE submodules.
            - shipped_not_in_submodule: Sorted residue — resolved names that
              are NOT submodules (regardless of which branch resolved them).
            - unresolved_names: STRICT SUBSET of residue. Names that hit
              the identity fallthrough branch (no override, no bulk_map
              entry) AND are not submodules. Semantically: "shipped names
              we have no clue what they are."
        """
        # Caller may pre-load (validate_all does); otherwise hit the repos.
        if overrides is None:
            overrides = self.overrides_repo.load(overrides_file)
        if bulk_map is None:
            bulk_map = self.bulk_map_repo.load_bulk_map(obs_project, cache_dir)

        submodules_set = set(submodules)
        resolved_names: set[str] = set()
        unresolved_set: set[str] = set()
        for name in shipped_packages:
            if name in overrides:
                value = overrides[name]
                if value is None:
                    continue  # explicitly suppressed
                resolved_names.add(value)
            elif name in bulk_map.mapping:
                resolved_names.add(bulk_map.mapping[name])
            else:
                # Identity fallthrough: no mapping at all.
                resolved_names.add(name)
                if name not in submodules_set:
                    unresolved_set.add(name)

        valid = {r for r in resolved_names if r in submodules_set}
        residue = sorted(r for r in resolved_names if r not in submodules_set)
        unresolved = sorted(unresolved_set)
        return (valid, residue, unresolved)

    def validate_all(
        self,
        maintainership_file: Path,
        repo_metadata_file: Path,
        overrides_file: Path,
        cache_dir: Path,
        git_dir: Path,
        obs_project: str = "SUSE:SLFO:Main",
        *,
        force_refresh: bool = False,
    ) -> ValidationResult:
        """Orchestrate all validation checks.

        Args:
            maintainership_file: Path to _maintainership.json
            repo_metadata_file: Path to primary.xml.gz (downloaded metadata)
            overrides_file: Path to hand-curated overrides JSON
            cache_dir: Cache dir for the OBS bulk-map XML
            git_dir: Path to git repository
            obs_project: OBS project to query
            force_refresh: If True, bypass cache and re-fetch from OBS.

        Returns:
            ValidationResult with all validation findings.
        """
        # Load all data
        maintainership_data = self.maintainership_repo.load(maintainership_file)
        shipped_packages = self.metadata_repo.parse_source_packages(repo_metadata_file)
        submodules = self.git_repo.list_submodules(git_dir)

        maintained_packages_without_submodule = self.find_maintained_packages_without_submodule(
            maintainership_data, submodules
        )

        # Pre-load bulk_map and overrides exactly once here so
        # find_shipped_without_submodule reuses them.
        overrides = self.overrides_repo.load(overrides_file)
        bulk_map = self.bulk_map_repo.load_bulk_map(
            obs_project, cache_dir, force_refresh=force_refresh
        )
        (
            valid_packages,
            shipped_not_in_submodule,
            unresolved_names,
        ) = self.find_shipped_without_submodule(
            shipped_packages,
            submodules,
            overrides_file,
            cache_dir,
            obs_project=obs_project,
            bulk_map=bulk_map,
            overrides=overrides,
        )

        # Check orphans only for valid packages (in submodules or resolved)
        orphan_packages = self.find_orphan_packages(valid_packages, maintainership_data)

        return ValidationResult(
            orphan_packages=orphan_packages,
            maintained_packages_without_submodule=maintained_packages_without_submodule,
            shipped_not_in_submodule=shipped_not_in_submodule,
            unresolved_names=unresolved_names,
        )
