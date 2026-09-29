"""Whitelist service - manages maintainership whitelist file.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for updating whitelist based on the OBS package set vs maintained packages
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
    # Names that fell through the source_info/overrides pipeline to identity
    # AND are not in the OBS package set. Mirrors ValidationResult.unresolved_names.
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

    def load_whitelist(self, content: bytes) -> set[str]:
        """Parse the whitelist document.

        Args:
            content: Raw bytes of the whitelist JSON document

        Returns:
            Set of package names from whitelist

        Raises:
            json.JSONDecodeError: If content is not valid JSON
            ValueError: If the whitelist structure is invalid or too large
        """
        # Check payload size to prevent memory exhaustion
        if len(content) > self.MAX_WHITELIST_SIZE:
            raise ValueError(
                f"Whitelist is too large: {len(content)} bytes (max {self.MAX_WHITELIST_SIZE})"
            )

        packages = json.loads(content)

        # Validate data type
        if not isinstance(packages, list):
            raise ValueError(f"Whitelist must contain a JSON array, got {type(packages).__name__}")

        # Validate all elements are strings
        if not all(isinstance(pkg, str) for pkg in packages):
            raise ValueError("Whitelist must contain only strings")

        return set(packages)

    def check_whitelist(
        self,
        whitelist_content: bytes,
        shipped_packages: set[str],
        overrides_file: Path,
        obs_project: str,
    ) -> WhitelistCheckResult:
        """Check whitelist for inconsistencies with shipped packages.

        Validates that whitelisted packages are NOT shipped. Reports packages
        that are BOTH whitelisted AND validated as shipped (inconsistency).

        Args:
            whitelist_content: Raw bytes of the whitelist JSON document
            shipped_packages: Set of shipped package names from metadata
            overrides_file: Path to hand-curated binary→source overrides JSON
            obs_project: OBS project to query for package resolution

        Returns:
            WhitelistCheckResult with inconsistent packages

        Raises:
            ValueError: If the whitelist is invalid
        """
        # Load whitelist
        whitelist = self.load_whitelist(whitelist_content)

        # Pre-load source_info here (mirrors the pattern validate_all uses) and
        # pass it to resolve_shipped_packages.
        source_info = self.validation_service.source_info_repo.load_source_info(obs_project)

        # Get validated shipped packages using validation pipeline.
        # Residue is dropped — the whitelist consistency check only cares
        # about valid packages — but unresolved_names is surfaced so the
        # command layer can warn operators about names with no source
        # mapping (same UX as the validate command).
        valid_packages, _, unresolved_names = self.validation_service.resolve_shipped_packages(
            shipped_packages,
            overrides_file,
            obs_project,
            source_info=source_info,
        )

        # Find intersection: packages BOTH shipped AND whitelisted (inconsistency)
        inconsistent_packages = valid_packages & whitelist

        return WhitelistCheckResult(
            inconsistent_packages=sorted(inconsistent_packages),
            unresolved_names=unresolved_names,
        )
