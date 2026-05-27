"""File I/O utilities for JSON handling.

Design Notes:
    - Simple wrappers, NOT security-hardened
    - For security-critical use (validation, size limits, atomic writes),
      use FalsePositivesRepository or similar hardened implementations
    - Accepts str | Path for backward compatibility with legacy code
"""

import json
from pathlib import Path
from typing import Any


def load_json(file_path: str | Path) -> Any:
    """Load JSON file with error handling.

    Args:
        file_path: Path to JSON file (str or Path)

    Returns:
        Parsed JSON data (dict, list, str, int, float, bool, or None)

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If invalid JSON
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    with open(path, encoding="utf-8") as f:
        data: Any = json.load(f)
        return data


def save_json(file_path: str | Path, data: Any, sorted_keys: bool = True) -> None:
    """Save data to JSON file.

    Args:
        file_path: Path to JSON file (str or Path)
        data: Data to save (must be JSON-serializable)
        sorted_keys: Sort dictionary keys alphabetically (default: True)

    Raises:
        OSError: If file cannot be written
        TypeError: If data is not JSON-serializable
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, sort_keys=sorted_keys)
        f.write("\n")


def validate_file_within_directory(base_dir: Path, filename: str, file_description: str) -> Path:
    """Validate that filename stays within base directory.

    Uses Path.resolve() + relative_to() pattern to prevent path traversal
    attacks via malicious config file values.

    Args:
        base_dir: Base directory that file must be within
        filename: Filename from config (may include subdirectories)
        file_description: Description for error messages

    Returns:
        Resolved absolute path to file

    Raises:
        ValueError: If file path escapes base directory
    """
    file_path = (base_dir / filename).resolve()
    try:
        file_path.relative_to(base_dir.resolve())
    except ValueError as e:
        raise ValueError(
            f"{file_description} escapes base directory: "
            f"'{filename}' resolves to {file_path} "
            f"(outside {base_dir})"
        ) from e
    return file_path
