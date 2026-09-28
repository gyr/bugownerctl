"""Validation service - orchestrates validation workflow.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for finding orphans, mismatches, etc.
    - Resolves shipped binary names to canonical source names via the
      OBS source info, with hand-curated overrides taking
      priority over the OBS source info.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bugownerctl.domain.maintainer import MaintainershipData
from bugownerctl.domain.obs_source_info import ObsSourceInfo
from bugownerctl.repositories.maintainership_repository import MaintainershipRepository
from bugownerctl.repositories.name_overrides_repository import NameOverridesRepository
from bugownerctl.repositories.obs_source_info_repository import (
    ObsSourceInfoRepository,
)
from bugownerctl.repositories.repo_metadata_repository import RepoMetadataRepository

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Results from validation workflow."""

    orphan_packages: list[str]
    maintained_packages_not_in_obs: list[str]
    shipped_not_in_obs: list[str]
    shipped_package_count: int
    obs_package_count: int
    maintained_package_count: int
    unresolved_names: list[str] = field(default_factory=list)


class ValidationService:
    """Service for validating maintainership data."""

    def __init__(
        self,
        maintainership_repo: MaintainershipRepository,
        metadata_repo: RepoMetadataRepository,
        *,
        source_info_repo: ObsSourceInfoRepository,
        overrides_repo: NameOverridesRepository,
    ) -> None:
        self.maintainership_repo = maintainership_repo
        self.metadata_repo = metadata_repo
        self.source_info_repo = source_info_repo
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

    def find_maintained_packages_not_in_obs(
        self, maintainership_data: MaintainershipData, obs_packages: frozenset[str]
    ) -> list[str]:
        """Find packages in maintainership file but not in the OBS package set.

        Args:
            maintainership_data: Maintainership data
            obs_packages: Source package names of the OBS project

        Returns:
            Sorted list of maintained packages absent from the OBS package set
        """
        return sorted(set(maintainership_data.packages.keys()) - obs_packages)

    def resolve_shipped_packages(
        self,
        shipped_packages: set[str],
        overrides_file: Path,
        obs_project: str,
        *,
        source_info: ObsSourceInfo | None = None,
        overrides: Mapping[str, str | None] | None = None,
    ) -> tuple[set[str], list[str], list[str]]:
        """Resolve shipped names and split them against the OBS package set.

        Resolution order per shipped name N:
            1. N in overrides: value None drops N entirely; str value wins.
            2. N in source_info: use source_info[N].
            3. Else: passthrough (N is its own source name = identity).

        Callers that already loaded the source_info (via
        source_info_repo.load_source_info) pass it here as source_info= to avoid
        re-fetching.  validate_all and check_whitelist both do this.

        Args:
            shipped_packages: Set of package names from repo metadata
            overrides_file: Path to hand-curated overrides JSON
            obs_project: OBS project to query
            source_info: Preloaded ObsSourceInfo value object (avoids re-fetching when
                validate_all already loaded it). Its `packages` set is the
                OBS package set compared against.
            overrides: Preloaded overrides mapping

        Returns:
            Tuple of (valid_packages, shipped_not_in_obs, unresolved_names)
            - valid_packages: Resolved names that ARE in the OBS package set.
            - shipped_not_in_obs: Sorted residue — resolved names that
              are NOT in the OBS package set (regardless of which branch
              resolved them).
            - unresolved_names: STRICT SUBSET of residue. Names that hit
              the identity fallthrough branch (no override, no source_info
              entry) AND are not in the OBS package set. Semantically:
              "shipped names we have no clue what they are."
        """
        # Caller may pre-load (validate_all does); otherwise hit the repos.
        if overrides is None:
            overrides = self.overrides_repo.load(overrides_file)
        if source_info is None:
            source_info = self.source_info_repo.load_source_info(obs_project)

        obs_packages = source_info.packages
        resolved_names: set[str] = set()
        unresolved_set: set[str] = set()
        for name in shipped_packages:
            if name in overrides:
                value = overrides[name]
                if value is None:
                    continue  # explicitly suppressed
                resolved_names.add(value)
            elif name in source_info.mapping:
                resolved_names.add(source_info.mapping[name])
            else:
                # Identity fallthrough: no mapping at all.
                resolved_names.add(name)
                if name not in obs_packages:
                    unresolved_set.add(name)

        valid = {r for r in resolved_names if r in obs_packages}
        residue = sorted(r for r in resolved_names if r not in obs_packages)
        unresolved = sorted(unresolved_set)
        return (valid, residue, unresolved)

    def validate_all(
        self,
        maintainership_file: Path,
        repo_metadata_file: Path,
        overrides_file: Path,
        obs_project: str,
    ) -> ValidationResult:
        """Orchestrate all validation checks.

        Args:
            maintainership_file: Path to _maintainership.json
            repo_metadata_file: Path to primary.xml.gz (downloaded metadata)
            overrides_file: Path to hand-curated overrides JSON
            obs_project: OBS project to query

        Returns:
            ValidationResult with all validation findings.
        """
        # Load all data
        maintainership_data = self.maintainership_repo.load(maintainership_file)
        shipped_packages = self.metadata_repo.parse_source_packages(repo_metadata_file)

        # Pre-load source_info and overrides exactly once here so
        # resolve_shipped_packages reuses them.
        overrides = self.overrides_repo.load(overrides_file)
        source_info = self.source_info_repo.load_source_info(obs_project)

        logger.info("starting validate_all for %d shipped packages", len(shipped_packages))
        maintained_packages_not_in_obs = self.find_maintained_packages_not_in_obs(
            maintainership_data, source_info.packages
        )
        logger.debug(
            "found %d maintained packages not in the OBS package set",
            len(maintained_packages_not_in_obs),
        )
        (
            valid_packages,
            shipped_not_in_obs,
            unresolved_names,
        ) = self.resolve_shipped_packages(
            shipped_packages,
            overrides_file,
            obs_project=obs_project,
            source_info=source_info,
            overrides=overrides,
        )

        # Check orphans only for valid packages (resolved into the OBS package set)
        orphan_packages = self.find_orphan_packages(valid_packages, maintainership_data)

        return ValidationResult(
            orphan_packages=orphan_packages,
            maintained_packages_not_in_obs=maintained_packages_not_in_obs,
            shipped_not_in_obs=shipped_not_in_obs,
            shipped_package_count=len(shipped_packages),
            obs_package_count=len(source_info.packages),
            # Same truthiness as find_orphan_packages: empty maintainer list = unmaintained
            maintained_package_count=sum(
                1 for maintainers in maintainership_data.packages.values() if maintainers
            ),
            unresolved_names=unresolved_names,
        )
