"""Query service - query package and maintainer information.

Design Notes:
    - Service layer for querying maintainership data
    - Checks both maintainership file and whitelist
    - Returns structured results for CLI presentation
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from bugowner.repositories.maintainership_repository import MaintainershipRepository


class PackageStatus(Enum):
    """Status of package maintainership."""

    MAINTAINED = "maintained"
    WHITELISTED = "whitelisted"
    NOT_FOUND = "not_found"


@dataclass
class PackageMaintainershipResult:
    """Result of package maintainership check."""

    package_name: str
    status: PackageStatus
    maintainers: list[str]


class QueryService:
    """Service for querying package and maintainer information."""

    def __init__(self, maintainership_repo: MaintainershipRepository) -> None:
        self.maintainership_repo = maintainership_repo

    def check_package_maintainership(
        self,
        package_name: str,
        maintainership_file: Path,
        whitelist_file: Path,
    ) -> PackageMaintainershipResult:
        """Check if package is maintained or whitelisted.

        Checks maintainership file first, then whitelist as fallback.

        Args:
            package_name: Package to check
            maintainership_file: Path to _maintainership.json
            whitelist_file: Path to whitelist_maintainership.json

        Returns:
            Result indicating if maintained, whitelisted, or neither
        """
        # Load maintainership data
        maintainership_data = self.maintainership_repo.load(maintainership_file)

        # Check if package in maintainership
        if package_name in maintainership_data.packages:
            return PackageMaintainershipResult(
                package_name=package_name,
                status=PackageStatus.MAINTAINED,
                maintainers=maintainership_data.packages[package_name],
            )

        # Load whitelist
        whitelist = self._load_whitelist(whitelist_file)

        # Check if package in whitelist
        if package_name in whitelist:
            return PackageMaintainershipResult(
                package_name=package_name,
                status=PackageStatus.WHITELISTED,
                maintainers=[],
            )

        # Package not found
        return PackageMaintainershipResult(
            package_name=package_name,
            status=PackageStatus.NOT_FOUND,
            maintainers=[],
        )

    def get_packages_by_maintainer(
        self,
        maintainer_name: str,
        maintainership_file: Path,
    ) -> list[str]:
        """Get all packages maintained by a user/group.

        Args:
            maintainer_name: User or group name
            maintainership_file: Path to _maintainership.json

        Returns:
            Sorted list of package names
        """
        maintainership_data = self.maintainership_repo.load(maintainership_file)

        packages = [
            pkg_name
            for pkg_name, maintainers in maintainership_data.packages.items()
            if maintainer_name in maintainers
        ]

        return sorted(packages)

    def _load_whitelist(self, whitelist_file: Path) -> set[str]:
        """Load whitelist file.

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
        max_whitelist_size = 10 * 1024 * 1024  # 10 MB
        file_size = whitelist_file.stat().st_size
        if file_size > max_whitelist_size:
            raise ValueError(
                f"Whitelist file {whitelist_file} is too large: "
                f"{file_size} bytes (max {max_whitelist_size})"
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
