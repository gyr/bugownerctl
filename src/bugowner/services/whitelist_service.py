"""Whitelist service - manages maintainership whitelist file.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for updating whitelist based on submodules vs maintained packages
    - Extracted from create_whitelist_maintainership.py
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from bugowner.repositories.git_repository import GitRepository
from bugowner.repositories.maintainership_repository import MaintainershipRepository

if TYPE_CHECKING:
    from bugowner.services.validation_service import ValidationService


@dataclass
class WhitelistUpdateResult:
    """Results from whitelist update operation."""

    added: list[str]
    removed: list[str]
    in_maintainership_not_submodule: list[str]


@dataclass
class WhitelistCheckResult:
    """Results from whitelist check operation."""

    inconsistent_packages: list[str]  # Packages BOTH shipped AND whitelisted (sorted)
    new_false_positives: dict[str, str]  # New binary→source mappings from validation


class WhitelistService:
    """Service for managing maintainership whitelist."""

    MAX_WHITELIST_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        validation_service: "ValidationService | MaintainershipRepository",
        git_repo: GitRepository | None = None,
    ) -> None:
        # Support both old and new constructor signatures (temporary backward compatibility)
        # Old: WhitelistService(maintainership_repo, git_repo)
        # New: WhitelistService(validation_service)
        # TODO: Remove old signature in Phase 2 of whitelist refactor
        if git_repo is not None:
            # Old signature: first arg is maintainership_repo
            self.maintainership_repo: MaintainershipRepository | None = validation_service  # type: ignore[assignment]
            self.git_repo: GitRepository | None = git_repo
            self.validation_service: "ValidationService | None" = None
        else:
            # New signature: first arg is validation_service
            self.validation_service = validation_service  # type: ignore[assignment]
            self.maintainership_repo = None
            self.git_repo = None

    def load_whitelist(self, whitelist_file: Path) -> set[str]:
        """Load existing whitelist file.

        Returns empty set if file doesn't exist.

        Args:
            whitelist_file: Path to whitelist JSON file

        Returns:
            Set of package names from whitelist

        Raises:
            json.JSONDecodeError: If whitelist file contains invalid JSON
            ValueError: If whitelist file structure is invalid or too large
            OSError: If file cannot be read (permissions, etc.)
        """
        if not whitelist_file.exists():
            return set()

        # Check file size to prevent memory exhaustion
        file_size = whitelist_file.stat().st_size
        if file_size > self.MAX_WHITELIST_SIZE:
            raise ValueError(
                f"Whitelist file {whitelist_file} is too large: "
                f"{file_size} bytes (max {self.MAX_WHITELIST_SIZE})"
            )

        with open(whitelist_file, encoding="utf-8") as f:
            packages = json.load(f)

        # Validate data type
        if not isinstance(packages, list):
            raise ValueError(
                f"Whitelist file {whitelist_file} must contain a JSON array, "
                f"got {type(packages).__name__}"
            )

        # Validate all elements are strings
        if not all(isinstance(pkg, str) for pkg in packages):
            raise ValueError(f"Whitelist file {whitelist_file} must contain only strings")

        return set(packages)

    def save_whitelist(self, whitelist_file: Path, packages: list[str]) -> None:
        """Save whitelist to file (sorted JSON array).

        Args:
            whitelist_file: Path to whitelist JSON file
            packages: List of package names

        Raises:
            OSError: If file cannot be written (permissions, disk space, etc.)
        """
        sorted_packages = sorted(packages)

        with open(whitelist_file, "w", encoding="utf-8") as f:
            json.dump(sorted_packages, f, indent=4)

        # Set restrictive permissions (owner read/write only)
        whitelist_file.chmod(0o600)

    def update_whitelist(
        self,
        repo_path: Path,
        maintainership_file: Path,
        whitelist_file: Path,
    ) -> WhitelistUpdateResult:
        """Update whitelist with missing submodules.

        Compares actual git submodules with packages in maintainership file.
        Updates whitelist to contain submodules missing from maintainership.

        Args:
            repo_path: Path to git repository
            maintainership_file: Path to _maintainership.json
            whitelist_file: Path to whitelist_maintainership.json

        Returns:
            WhitelistUpdateResult with added/removed packages
        """
        # Load current state
        submodules = set(self.git_repo.list_submodules(repo_path))
        maintainership_data = self.maintainership_repo.load(maintainership_file)
        maintained = set(maintainership_data.packages.keys())
        old_whitelist = self.load_whitelist(whitelist_file)

        # Calculate changes
        added = submodules - maintained
        in_maintainership_not_submodule = maintained - submodules
        removed = old_whitelist - added

        # Save new whitelist
        self.save_whitelist(whitelist_file, sorted(added))

        return WhitelistUpdateResult(
            added=sorted(added),
            removed=sorted(removed),
            in_maintainership_not_submodule=sorted(in_maintainership_not_submodule),
        )

    def check_whitelist(
        self,
        whitelist_file: Path,
        shipped_packages: set[str],
        submodules: list[str],
        false_positives_file: Path,
        obs_project: str = "SUSE:SLFO:Main",
    ) -> WhitelistCheckResult:
        """Check whitelist for inconsistencies with shipped packages.

        Validates that whitelisted packages are NOT shipped. Reports packages
        that are BOTH whitelisted AND validated as shipped (inconsistency).

        Args:
            whitelist_file: Path to whitelist JSON file
            shipped_packages: Set of shipped package names from metadata
            submodules: List of git submodule names
            false_positives_file: Path to false positives cache
            obs_project: OBS project to query for package resolution

        Returns:
            WhitelistCheckResult with inconsistent packages and new false positives

        Raises:
            FileNotFoundError: If whitelist file doesn't exist
            ValueError: If whitelist file is invalid
        """
        # Validate whitelist file exists
        if not whitelist_file.exists():
            raise FileNotFoundError(f"Whitelist file {whitelist_file} does not exist")

        # Load whitelist
        whitelist = self.load_whitelist(whitelist_file)

        # Get validated shipped packages using validation pipeline
        (
            valid_packages,
            _,
            new_false_positives,
        ) = self.validation_service.find_shipped_without_submodule(
            shipped_packages, submodules, false_positives_file, obs_project
        )

        # Find intersection: packages BOTH shipped AND whitelisted (inconsistency)
        inconsistent_packages = valid_packages & whitelist

        return WhitelistCheckResult(
            inconsistent_packages=sorted(inconsistent_packages),
            new_false_positives=new_false_positives,
        )
