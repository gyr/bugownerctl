"""Validation service - orchestrates validation workflow.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for finding orphans, mismatches, etc.
    - Extracted from validate_maintainership.py
"""

from dataclasses import dataclass
from pathlib import Path

from src.bugowner.domain.maintainer import MaintainershipData
from src.bugowner.repositories.false_positives_repository import (
    FalsePositivesRepository,
)
from src.bugowner.repositories.git_repository import GitRepository
from src.bugowner.repositories.maintainership_repository import (
    MaintainershipRepositoryImpl,
)
from src.bugowner.repositories.obs_repository import ObsRepository
from src.bugowner.repositories.repo_metadata_repository import RepoMetadataRepository


@dataclass
class ValidationResult:
    """Results from validation workflow."""

    orphan_packages: list[str]
    unmaintained_submodules: list[str]
    shipped_not_in_submodule: list[str]
    new_false_positives: dict[str, str]


class ValidationService:
    """Service for validating maintainership data."""

    def __init__(
        self,
        maintainership_repo: MaintainershipRepositoryImpl,
        git_repo: GitRepository,
        metadata_repo: RepoMetadataRepository,
        obs_repo: ObsRepository,
        false_positives_repo: FalsePositivesRepository,
    ) -> None:
        self.maintainership_repo = maintainership_repo
        self.git_repo = git_repo
        self.metadata_repo = metadata_repo
        self.obs_repo = obs_repo
        self.false_positives_repo = false_positives_repo

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

    def find_unmaintained_submodules(
        self, submodules: list[str], maintainership_data: MaintainershipData
    ) -> list[str]:
        """Find submodules not listed in maintainership file.

        Args:
            submodules: List of git submodule names
            maintainership_data: Maintainership data

        Returns:
            Sorted list of unmaintained submodule names
        """
        return sorted([sub for sub in submodules if sub not in maintainership_data.packages])

    def find_shipped_without_submodule(
        self,
        shipped_packages: set[str],
        submodules: list[str],
        false_positives_file: Path,
        obs_project: str = "SUSE:SLFO:Main",
    ) -> tuple[set[str], dict[str, str]]:
        """Find shipped packages not in submodules (with OBS fallback).

        Args:
            shipped_packages: Set of package names from repo metadata
            submodules: List of git submodule names
            false_positives_file: Path to cache file
            obs_project: OBS project to query

        Returns:
            Tuple of (valid_packages, new_false_positives)
        """
        # Load cache
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
        if unknowns:
            new_false_positives = self.obs_repo.query_source_packages(unknowns, obs_project)

            # Check if OBS-resolved packages are in submodules
            for source_pkg in new_false_positives.values():
                if source_pkg in submodules_set:
                    valid_packages.add(source_pkg)

            # Merge and save cache if there are new discoveries
            if new_false_positives:
                cache.update(new_false_positives)
                self.false_positives_repo.save(false_positives_file, cache)

        return (valid_packages, new_false_positives)
