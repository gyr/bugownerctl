"""Validation service - orchestrates validation workflow.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for finding orphans, mismatches, etc.
    - Extracted from validate_maintainership.py
"""

from dataclasses import dataclass

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
