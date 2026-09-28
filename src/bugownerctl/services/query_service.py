"""Query service - query package and maintainer information.

Design Notes:
    - Service layer for querying maintainership data
    - Checks both maintainership file and whitelist
    - Returns structured results for CLI presentation
"""

import json
from dataclasses import dataclass
from enum import Enum

from bugownerctl.repositories.maintainership_repository import MaintainershipRepository


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
        maintainership_content: bytes,
        whitelist_content: bytes | None,
    ) -> PackageMaintainershipResult:
        """Check if package is maintained or whitelisted.

        Checks maintainership file first, then whitelist as fallback.

        Args:
            package_name: Package to check
            maintainership_content: Raw bytes of _maintainership.json
            whitelist_content: Raw bytes of whitelist_maintainership.json, or
                None when there is no whitelist (treated as empty)

        Returns:
            Result indicating if maintained, whitelisted, or neither
        """
        # Load maintainership data
        maintainership_data = self.maintainership_repo.load(maintainership_content)

        # Check if package in maintainership
        if package_name in maintainership_data.packages:
            return PackageMaintainershipResult(
                package_name=package_name,
                status=PackageStatus.MAINTAINED,
                maintainers=maintainership_data.packages[package_name],
            )

        # Load whitelist
        whitelist = set() if whitelist_content is None else self._load_whitelist(whitelist_content)

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
        maintainership_content: bytes,
    ) -> list[str]:
        """Get all packages maintained by a user/group.

        Args:
            maintainer_name: User or group name
            maintainership_content: Raw bytes of _maintainership.json

        Returns:
            Sorted list of package names
        """
        maintainership_data = self.maintainership_repo.load(maintainership_content)

        packages = [
            pkg_name
            for pkg_name, maintainers in maintainership_data.packages.items()
            if maintainer_name in maintainers
        ]

        return sorted(packages)

    def _load_whitelist(self, whitelist_content: bytes) -> set[str]:
        """Parse the whitelist document.

        Args:
            whitelist_content: Raw bytes of the whitelist JSON document

        Returns:
            Set of package names from whitelist

        Raises:
            json.JSONDecodeError: If content is not valid JSON
            ValueError: If the whitelist structure is invalid or too large
        """
        # Check payload size to prevent memory exhaustion
        max_whitelist_size = 10 * 1024 * 1024  # 10 MB
        if len(whitelist_content) > max_whitelist_size:
            raise ValueError(
                f"Whitelist is too large: {len(whitelist_content)} bytes (max {max_whitelist_size})"
            )

        packages = json.loads(whitelist_content)

        # Validate data type
        if not isinstance(packages, list):
            raise ValueError(f"Whitelist must contain a JSON array, got {type(packages).__name__}")

        # Validate all elements are strings
        if not all(isinstance(pkg, str) for pkg in packages):
            raise ValueError("Whitelist must contain only strings")

        return set(packages)
