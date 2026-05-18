"""MaintainershipRepository for loading and querying maintainership data."""

import json
from pathlib import Path

from ..domain.maintainer import MaintainershipData


class MaintainershipRepositoryImpl:
    """Repository for maintainership data access."""

    def load(self, file_path: Path) -> MaintainershipData:
        """Load and parse maintainership JSON file.

        Expects new format with "packages" key containing package objects.
        Returns normalized format: {"package": ["maintainer1", "maintainer2"]}

        Args:
            file_path: Path to _maintainership.json

        Returns:
            MaintainershipData with normalized package->maintainers mapping

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required 'packages' key
        """
        with open(file_path) as f:
            data = json.load(f)

        packages_raw = data["packages"]
        packages_normalized = {}

        for package_name, maintainers in packages_raw.items():
            users = maintainers.get("users", [])
            groups = maintainers.get("groups", [])
            packages_normalized[package_name] = users + groups

        return MaintainershipData(packages=packages_normalized)

    def get_packages(self, data: MaintainershipData) -> set[str]:
        """Extract all package names from maintainership data.

        Args:
            data: MaintainershipData instance

        Returns:
            Set of package names
        """
        return set(data.packages.keys())

    def get_maintainers(self, data: MaintainershipData, package: str) -> list[str]:
        """Get maintainers for a specific package.

        Args:
            data: MaintainershipData instance
            package: Package name

        Returns:
            List of maintainers, empty list if package not found
        """
        return data.packages.get(package, [])

    def get_packages_by_maintainer(self, data: MaintainershipData, maintainer: str) -> list[str]:
        """Get all packages maintained by a user/group.

        Args:
            data: MaintainershipData instance
            maintainer: User or group name

        Returns:
            List of package names maintained by the maintainer
        """
        result = []
        for package_name, maintainers in data.packages.items():
            if maintainer in maintainers:
                result.append(package_name)
        return result
