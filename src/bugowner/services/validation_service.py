"""Validation service - orchestrates validation workflow.

Design Notes:
    - Service layer coordinates between repositories
    - Business logic for finding orphans, mismatches, etc.
    - Extracted from validate_maintainership.py
"""

from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Results from validation workflow."""

    orphan_packages: list[str]
    unmaintained_submodules: list[str]
    shipped_not_in_submodule: list[str]
    new_false_positives: dict[str, str]
