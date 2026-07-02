"""Hand-curated binary-name → source-name overrides repository.

Loads a small JSON file shipped with the package (and optionally extended by
users) that maps binary or sub-package names to their canonical source-name.
A `null` value explicitly suppresses a binary (e.g. a known false-positive).

This repository is intentionally minimal: pure file I/O plus validation, no
network, no subprocess, no caching. The Phase 4 service consults it BEFORE
the OBS bulk map so curated overrides short-circuit incorrect bulk-map
entries (e.g. kernel-azure cycles).
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable

# Hard ceiling on overrides file size. The shipped file is a few lines; even
# a heavily extended user override is unlikely to reach 1 MiB. Bound the
# worst case so a hostile/corrupted file cannot exhaust memory before parsing.
MAX_OVERRIDES_BYTES = 1024 * 1024  # 1 MiB


@runtime_checkable
class NameOverridesRepository(Protocol):
    """Load a binary→source-name overrides mapping from a JSON file."""

    def load(self, file_path: Path) -> Mapping[str, str | None]:
        """Return the overrides mapping, or {} when the file does not exist.

        Args:
            file_path: Absolute path to the overrides JSON file.

        Returns:
            Mapping of binary name to source name (str) or None.

        Raises:
            ValueError: If `file_path` is not absolute, the file exceeds
                MAX_OVERRIDES_BYTES, the JSON root is not an object, or any
                value is not str or None.
        """
        ...


class NameOverridesRepositoryImpl:
    """Adapter implementation backed by a JSON file on disk."""

    def load(self, file_path: Path) -> Mapping[str, str | None]:
        if not file_path.is_absolute():
            raise ValueError(f"file_path must be absolute, got: {file_path!r}")
        if not file_path.is_file():
            return {}
        size = file_path.stat().st_size
        if size > MAX_OVERRIDES_BYTES:
            raise ValueError(
                f"overrides file exceeds {MAX_OVERRIDES_BYTES} bytes ({size}); "
                "refusing to parse to avoid memory exhaustion"
            )
        raw = json.loads(file_path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"overrides JSON root must be an object (dict), got {type(raw).__name__}"
            )
        result: dict[str, str | None] = {}
        for key, value in raw.items():
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"overrides value for {key!r} must be str or None, got {type(value).__name__}"
                )
            result[key] = value
        return result
