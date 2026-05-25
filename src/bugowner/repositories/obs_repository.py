"""OBS (Open Build Service) repository for querying package information.

This module requires the `osc` (openSUSE Commander) command-line tool to be
installed and available in PATH. Install it with:
    zypper install osc
or
    pip install osc
"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Protocol

logger = logging.getLogger(__name__)


class ObsRepository(Protocol):
    """Interface for OBS (Open Build Service) queries."""

    def get_source_package(self, binary_package: str, project: str) -> str | None:
        """Query OBS to find source package for a binary package.

        Uses `osc -A https://api.suse.de bse {package}` command (old format).
        The command queries all projects, then filters output by project parameter.

        Args:
            binary_package: Name of binary package
            project: OBS project for filtering results (e.g., "SUSE:SLFO:Main").
                Not passed to osc command, only used for output filtering.

        Returns:
            Source package name if found, None otherwise
        """
        ...

    def query_source_packages(self, binary_packages: set[str], project: str) -> dict[str, str]:
        """Query OBS for multiple packages in parallel.

        Args:
            binary_packages: Set of binary package names to query
            project: OBS project (e.g., "SUSE:SLFO:Main")

        Returns:
            Dict mapping binary package → source package (only successful queries)
        """
        ...


class ObsRepositoryImpl:
    """Implementation of OBS repository using osc command-line tool."""

    def get_source_package(self, binary_package: str, project: str) -> str | None:
        """Query OBS to find source package for a binary package.

        Uses `osc -A https://api.suse.de bse {package}` command (old format).
        The command queries all projects, then filters output by project parameter.

        Args:
            binary_package: Name of binary package
            project: OBS project for filtering results (e.g., "SUSE:SLFO:Main").
                Not passed to osc command, only used for output filtering.

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

        # Run osc command matching old code format
        try:
            result = subprocess.run(
                ["osc", "-A", "https://api.suse.de", "bse", binary_package.strip()],
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

        # Parse output - OLD FORMAT: space-separated "SUSE:SLFO:Main apache2:apache2-devel x86_64"
        stdout = result.stdout.strip()
        if not stdout:
            logger.info("No source package found for %s in %s.", binary_package, project)
            return None

        # Filter lines starting with project prefix (e.g., "SUSE:SLFO:Main ")
        project_prefix = f"{project.strip()} "
        filtered_lines = [line for line in stdout.splitlines() if line.startswith(project_prefix)]

        if not filtered_lines:
            logger.info("No source package found for %s in %s.", binary_package, project)
            return None

        # Extract source packages from filtered lines
        source_packages = set()
        for line in filtered_lines:
            parts = line.split()
            if len(parts) >= 2:
                # parts[0] is project, parts[1] is "source:binary" or "source"
                package_field = parts[1]
                # Skip empty package fields
                if package_field:
                    # Split by colon to get source package
                    colon_parts = package_field.split(":")
                    source_packages.add(colon_parts[0])

        if not source_packages:
            logger.info("No source package found for %s in %s.", binary_package, project)
            return None

        # Warn if multiple different source packages found
        if len(source_packages) > 1:
            logger.warning(
                "Found multiple source packages for %s in %s: %s",
                binary_package,
                project,
                source_packages,
            )

        # Return first source package (sorted for deterministic behavior)
        return sorted(source_packages)[0]

    def query_source_packages(self, binary_packages: set[str], project: str) -> dict[str, str]:
        """Query OBS for multiple packages in parallel.

        Args:
            binary_packages: Set of binary package names to query
            project: OBS project (e.g., "SUSE:SLFO:Main")

        Returns:
            Dict mapping binary package → source package (only successful queries)
        """
        results: dict[str, str] = {}

        # Query packages in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_pkg = {
                executor.submit(self.get_source_package, pkg, project): pkg
                for pkg in binary_packages
            }

            for future in as_completed(future_to_pkg):
                pkg = future_to_pkg[future]
                try:
                    source_pkg = future.result()
                    if source_pkg:
                        results[pkg] = source_pkg
                except Exception as exc:
                    logger.error("Package '%s' query failed: %s", pkg, exc)

        return results
