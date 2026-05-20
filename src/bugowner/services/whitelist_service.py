"""Whitelist service - manages maintainership whitelist file.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for updating whitelist based on submodules vs maintained packages
    - Extracted from create_whitelist_maintainership.py
"""

import json
from dataclasses import dataclass
from pathlib import Path

from src.bugowner.repositories.git_repository import GitRepository
from src.bugowner.repositories.maintainership_repository import MaintainershipRepository


@dataclass
class WhitelistUpdateResult:
    """Results from whitelist update operation."""

    added: list[str]
    removed: list[str]
    in_maintainership_not_submodule: list[str]


class WhitelistService:
    """Service for managing maintainership whitelist."""

    MAX_WHITELIST_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        maintainership_repo: MaintainershipRepository,
        git_repo: GitRepository,
    ) -> None:
        self.maintainership_repo = maintainership_repo
        self.git_repo = git_repo

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
