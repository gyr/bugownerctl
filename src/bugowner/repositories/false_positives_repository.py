"""Repository for managing false positives cache (binary→source package mappings)."""

import json
import os
from pathlib import Path
from typing import Protocol


class FalsePositivesRepository(Protocol):
    """Interface for false positives cache management.

    False positives are binary packages in the repo that map to different
    source package names (or to null to ignore them). This is a persistent
    cache to avoid slow OBS queries on every run.

    Example mappings:
        "apache2-devel": "apache2"     # Binary maps to source
        "SLES-release": null           # Ignore this package

    Typical usage (read-modify-write pattern):
        >>> repo = FalsePositivesRepositoryImpl()
        >>> cache = repo.load(Path("false_positives.json"))
        >>> packages = {"apache2-devel", "kernel"}
        >>> remapped = repo.apply_remapping(packages, cache)
        >>> new_discoveries = {"mysql-client": "mysql"}
        >>> updated = repo.merge_mappings(cache, new_discoveries)
        >>> repo.save(Path("false_positives.json"), updated)

    Note: This implementation is NOT thread-safe or process-safe.
    Concurrent access to the cache file may result in lost updates.
    For production use with parallel processing, consider:
    - File locking (fcntl on Linux)
    - Atomic writes with temp file + rename
    - Database-backed cache instead of JSON file
    """

    def load(self, file_path: Path) -> dict[str, str | None]:
        """Load cached binary→source mappings.

        Args:
            file_path: Path to false_positives.json (must be absolute)

        Returns:
            Dictionary mapping binary package names to source names (or None)
            Returns empty dict if file doesn't exist

        Raises:
            json.JSONDecodeError: If invalid JSON format
            ValueError: If file_path is not absolute or file too large
        """
        ...

    def save(self, file_path: Path, mappings: dict[str, str | None]) -> None:
        """Save updated cache to file.

        Saves as sorted JSON for consistent diffs.

        Args:
            file_path: Path to false_positives.json (must be absolute, not symlink)
            mappings: Complete mapping dictionary (old + new)

        Raises:
            OSError: If file cannot be written (permissions, disk full, etc.)
            ValueError: If file_path is symlink, not absolute, or invalid data
            TypeError: If mappings contains invalid types
        """
        ...

    def apply_remapping(
        self,
        packages: set[str],
        mappings: dict[str, str | None],
    ) -> set[str]:
        """Apply binary→source remapping to package set.

        For each package:
        - If in mappings and maps to None: skip (filter out)
        - If in mappings and maps to string: replace with source name
        - If not in mappings: keep original name

        Args:
            packages: Set of package names (potentially binary names)
            mappings: Binary→source mapping dictionary

        Returns:
            Remapped set of package names (source names)
        """
        ...

    def merge_mappings(
        self,
        existing: dict[str, str | None],
        new_discoveries: dict[str, str],
    ) -> dict[str, str | None]:
        """Merge existing cache with new OBS discoveries.

        Args:
            existing: Current cache contents
            new_discoveries: New binary→source mappings from OBS

        Returns:
            Merged dictionary (existing + new_discoveries)
        """
        ...


class FalsePositivesRepositoryImpl:
    """Implementation of FalsePositivesRepository for managing binary→source mappings."""

    def load(self, file_path: Path) -> dict[str, str | None]:
        """Load cached binary→source mappings.

        Args:
            file_path: Path to false_positives.json (must be absolute)

        Returns:
            Dictionary mapping binary package names to source names (or None)
            Returns empty dict if file doesn't exist

        Raises:
            json.JSONDecodeError: If invalid JSON format
            ValueError: If file_path is not absolute or file too large
        """
        # Validate path is absolute
        if not file_path.is_absolute():
            raise ValueError(f"File path must be absolute: {file_path}")

        # Resolve path (follows symlinks, removes .. components)
        # Safe to follow symlinks when reading (read-only operation)
        resolved = file_path.resolve()

        # Use try/except instead of exists() to avoid TOCTOU race
        try:
            # Check file size before loading (prevent DoS)
            max_file_size = 10 * 1024 * 1024  # 10 MB
            file_size = resolved.stat().st_size
            if file_size > max_file_size:
                raise ValueError(f"Cache file too large: {file_size} bytes (max {max_file_size})")

            with open(resolved, encoding="utf-8") as f:
                data: dict[str, str | None] = json.load(f)
                return data
        except FileNotFoundError:
            return {}

    def save(self, file_path: Path, mappings: dict[str, str | None]) -> None:
        """Save updated cache to file.

        Saves as sorted JSON for consistent diffs.

        Args:
            file_path: Path to false_positives.json (must be absolute, not symlink)
            mappings: Complete mapping dictionary (old + new)

        Raises:
            OSError: If file cannot be written (permissions, disk full, etc.)
            ValueError: If file_path is symlink, not absolute, or invalid data
            TypeError: If mappings contains invalid types
        """
        # Validate path is absolute
        if not file_path.is_absolute():
            raise ValueError(f"File path must be absolute: {file_path}")

        # Check if target is symlink BEFORE resolving (prevent symlink attack)
        # Reject writes to symlinks to prevent overwriting arbitrary files
        if file_path.is_symlink():
            raise ValueError(f"Refusing to write to symlink: {file_path}")

        # Resolve path
        resolved = file_path.resolve()

        # Validate input schema
        if not isinstance(mappings, dict):
            raise TypeError("mappings must be a dict")

        max_string_length = 1000
        for key, value in mappings.items():
            if not isinstance(key, str):
                raise TypeError(f"All keys must be strings, got {type(key)}")
            if value is not None and not isinstance(value, str):
                raise TypeError(f"All values must be str or None, got {type(value)}")

            # Prevent DoS via extremely long strings
            if len(key) > max_string_length:
                raise ValueError(f"Key too long: {len(key)} chars (max {max_string_length})")
            if value and len(value) > max_string_length:
                raise ValueError(f"Value too long: {len(value)} chars (max {max_string_length})")

        # Atomic write: write to temp file, then rename
        # Use prefix to preserve original extension (e.g., .false_positives.json.tmp)
        temp_path = resolved.with_name(f".{resolved.name}.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(mappings, f, sort_keys=True, indent=2)
                f.write("\n")

            # Set restrictive permissions (owner read/write only)
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(resolved)
        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise

    def apply_remapping(
        self,
        packages: set[str],
        mappings: dict[str, str | None],
    ) -> set[str]:
        """Apply binary→source remapping to package set.

        For each package:
        - If in mappings and maps to None: skip (filter out)
        - If in mappings and maps to string: replace with source name
        - If not in mappings: keep original name

        Args:
            packages: Set of package names (potentially binary names)
            mappings: Binary→source mapping dictionary

        Returns:
            Remapped set of package names (source names)
        """
        remapped = set()

        for package in packages:
            # Get mapped value, defaulting to package itself if not in mappings
            source = mappings.get(package, package)
            # Only add if not None (None means filter out)
            if source is not None:
                remapped.add(source)

        return remapped

    def merge_mappings(
        self,
        existing: dict[str, str | None],
        new_discoveries: dict[str, str],
    ) -> dict[str, str | None]:
        """Merge existing cache with new OBS discoveries.

        Args:
            existing: Current cache contents
            new_discoveries: New binary→source mappings from OBS

        Returns:
            Merged dictionary (existing + new_discoveries)
        """
        # Start with existing, then update with new discoveries
        merged = existing.copy()
        merged.update(new_discoveries)
        return merged
