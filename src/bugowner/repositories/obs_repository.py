"""OBS (Open Build Service) repository for querying package information.

This module requires the `osc` (openSUSE Commander) command-line tool to be
installed and available in PATH. Install it with:
    zypper install osc
or
    pip install osc
"""

import logging
import subprocess
from typing import Protocol

logger = logging.getLogger(__name__)


class ObsRepository(Protocol):
    """Interface for OBS (Open Build Service) queries."""

    def get_source_package(self, binary_package: str, project: str) -> str | None:
        """Query OBS to find source package for a binary package.

        Uses `osc bse` command to search for source packages.

        Args:
            binary_package: Name of binary package
            project: OBS project (e.g., "SUSE:SLFO:Main")

        Returns:
            Source package name if found, None otherwise
        """
        ...


class ObsRepositoryImpl:
    """Implementation of OBS repository using osc command-line tool."""

    def get_source_package(self, binary_package: str, project: str) -> str | None:
        """Query OBS to find source package for a binary package.

        Uses `osc bse` command to search for source packages.

        Args:
            binary_package: Name of binary package
            project: OBS project (e.g., "SUSE:SLFO:Main")

        Returns:
            Source package name if found, None otherwise
        """
        # Validate inputs
        if not binary_package or not binary_package.strip():
            return None
        if not project or not project.strip():
            return None

        # Reject inputs starting with dashes (potential flag injection)
        if binary_package.strip().startswith("-") or project.strip().startswith("-"):
            logger.warning(
                "Rejected potential flag injection: package=%s, project=%s",
                binary_package,
                project,
            )
            return None

        # Run osc bse command with timeout
        try:
            result = subprocess.run(
                ["osc", "bse", project.strip(), binary_package.strip()],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "osc command timed out for package=%s, project=%s",
                binary_package,
                project,
            )
            return None

        # Check if command failed
        if result.returncode != 0:
            logger.debug(
                "osc command failed for package=%s, project=%s: %s",
                binary_package,
                project,
                result.stderr,
            )
            return None

        # Parse output - format: "binary | source | arch"
        stdout = result.stdout.strip()
        if not stdout:
            return None

        # Get first line (in case of multiple matches)
        first_line = stdout.split("\n")[0]

        # Parse pipe-separated format
        parts = first_line.split("|")
        if len(parts) < 2:
            return None

        # Extract source package name (second column)
        source_package = parts[1].strip()
        return source_package if source_package else None
