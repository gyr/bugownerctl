"""MaintainershipRepository for loading and querying maintainership data."""

import json
from typing import Protocol

from ..domain.maintainer import MaintainershipData


def _names_or_empty(entry: dict[str, list[str] | None], key: str) -> list[str]:
    """Return the name list stored under ``key``, or an empty list.

    Args:
        entry: One package object from the "packages" mapping
        key: Name-list key to read, "users" or "groups"

    Returns:
        The stored name list, or an empty list if the key is absent or null.
    """
    # Real SLFO branches such as slfo-1.2 write JSON null where an empty list
    # is meant, so null and an absent key normalize alike.
    value = entry.get(key)
    if value is None:
        return []
    return value


class MaintainershipRepository(Protocol):
    """Interface for maintainership data access."""

    def load(self, content: bytes) -> MaintainershipData:
        """Parse maintainership JSON content.

        Expects new format with "packages" key containing package objects.
        Returns normalized format: {"package": ["maintainer1", "maintainer2"]}

        Args:
            content: Raw bytes of a _maintainership.json document

        Returns:
            MaintainershipData with normalized package->maintainers mapping

        Raises:
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required 'packages' key
        """
        ...

    def get_packages(self, data: MaintainershipData) -> set[str]:
        """Extract all package names from maintainership data.

        Args:
            data: MaintainershipData instance

        Returns:
            Set of package names
        """
        ...

    def get_maintainers(self, data: MaintainershipData, package: str) -> list[str]:
        """Get maintainers for a specific package.

        Args:
            data: MaintainershipData instance
            package: Package name

        Returns:
            List of maintainers, empty list if package not found
        """
        ...

    def get_packages_by_maintainer(self, data: MaintainershipData, maintainer: str) -> list[str]:
        """Get all packages maintained by a user/group.

        Args:
            data: MaintainershipData instance
            maintainer: User or group name

        Returns:
            List of package names maintained by the maintainer
        """
        ...

    def load_users_by_package(self, content: bytes) -> dict[str, list[str]]:
        """Parse users per package from maintainership JSON content.

        Returns only the "users" list per package, excluding groups.

        Args:
            content: Raw bytes of a _maintainership.json document

        Returns:
            Mapping of package name to list of user login strings.

        Raises:
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required 'packages' key
        """
        ...


class MaintainershipRepositoryImpl:
    """Repository for maintainership data access."""

    def load(self, content: bytes) -> MaintainershipData:
        """Parse maintainership JSON content.

        Expects new format with "packages" key containing package objects.
        Returns normalized format: {"package": ["maintainer1", "maintainer2"]}

        Args:
            content: Raw bytes of a _maintainership.json document

        Returns:
            MaintainershipData with normalized package->maintainers mapping

        Raises:
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required 'packages' key
        """
        data = json.loads(content)

        packages_raw = data["packages"]
        packages_normalized = {}

        for package_name, maintainers in packages_raw.items():
            users = _names_or_empty(maintainers, "users")
            groups = _names_or_empty(maintainers, "groups")
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

    def load_users_by_package(self, content: bytes) -> dict[str, list[str]]:
        """Parse users per package from maintainership JSON content.

        Returns only the "users" list per package, excluding groups.

        Args:
            content: Raw bytes of a _maintainership.json document

        Returns:
            Mapping of package name to list of user login strings.

        Raises:
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required 'packages' key
        """
        data = json.loads(content)
        return {pkg: _names_or_empty(pkg_obj, "users") for pkg, pkg_obj in data["packages"].items()}
