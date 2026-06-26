"""Whitelist service - manages maintainership whitelist file.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for updating whitelist based on submodules vs maintained packages
    - Extracted from create_whitelist_maintainership.py
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bugownerctl.services.validation_service import ValidationService


@dataclass
class WhitelistCheckResult:
    """Results from whitelist check operation."""

    inconsistent_packages: list[str]  # Packages BOTH shipped AND whitelisted (sorted)
    # Names that fell through the bulk_map/overrides pipeline to identity
    # AND are not submodules. Mirrors ValidationResult.unresolved_names.
    unresolved_names: list[str] = field(default_factory=list)


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
        overrides_file: Path,
        cache_dir: Path,
        obs_project: str = "SUSE:SLFO:Main",
        *,
        force_refresh: bool = False,
    ) -> WhitelistCheckResult:
        """Check whitelist for inconsistencies with shipped packages.

        Validates that whitelisted packages are NOT shipped. Reports packages
        that are BOTH whitelisted AND validated as shipped (inconsistency).

        Args:
            whitelist_file: Path to whitelist JSON file
            shipped_packages: Set of shipped package names from metadata
            submodules: List of git submodule names
            overrides_file: Path to hand-curated binary→source overrides JSON
            cache_dir: Cache directory for the OBS bulk-map XML
            obs_project: OBS project to query for package resolution
            force_refresh: If True, bypass cache and re-fetch OBS bulk map.

        Returns:
            WhitelistCheckResult with inconsistent packages

        Raises:
            FileNotFoundError: If whitelist file doesn't exist
            ValueError: If whitelist file is invalid
        """
        # Validate whitelist file exists
        if not whitelist_file.exists():
            raise FileNotFoundError(f"Whitelist file {whitelist_file} does not exist")

        # Load whitelist
        whitelist = self.load_whitelist(whitelist_file)

        # Pre-load bulk_map here (mirrors the pattern validate_all uses) so
        # that force_refresh is honoured at this orchestration layer rather
        # than being buried in find_shipped_without_submodule.
        bulk_map = self.validation_service.bulk_map_repo.load_bulk_map(
            obs_project, cache_dir, force_refresh=force_refresh
        )

        # Get validated shipped packages using validation pipeline.
        # Residue is dropped — the whitelist consistency check only cares
        # about valid packages — but unresolved_names is surfaced so the
        # command layer can warn operators about names with no source
        # mapping (same UX as the validate command).
        valid_packages, _, unresolved_names = (
            self.validation_service.find_shipped_without_submodule(
                shipped_packages,
                submodules,
                overrides_file,
                cache_dir,
                obs_project,
                bulk_map=bulk_map,
            )
        )

        # Find intersection: packages BOTH shipped AND whitelisted (inconsistency)
        inconsistent_packages = valid_packages & whitelist

        return WhitelistCheckResult(
            inconsistent_packages=sorted(inconsistent_packages),
            unresolved_names=unresolved_names,
        )
