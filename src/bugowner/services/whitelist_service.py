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

if TYPE_CHECKING:
    from bugowner.services.validation_service import ValidationService


@dataclass
class WhitelistCheckResult:
    """Results from whitelist check operation."""

    inconsistent_packages: list[str]  # Packages BOTH shipped AND whitelisted (sorted)
    new_false_positives: dict[str, str]  # New binary→source mappings from validation


class WhitelistService:
    """Service for managing maintainership whitelist."""

    MAX_WHITELIST_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(self, validation_service: "ValidationService") -> None:
        """Initialize whitelist service with validation service dependency.

        Args:
            validation_service: Service for validating shipped packages
        """
        self.validation_service = validation_service

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
