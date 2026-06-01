"""Seed file utilities for bootstrapping the false-positives cache."""

import json
import shutil
from importlib.resources import files
from pathlib import Path
from typing import Any


def get_seed_file_path(config: dict[str, Any] | None = None) -> Path:
    """Locate the false-positives seed file.

    Precedence:
      1. config["false_positives_seed"] override (for CI / custom seeds)
      2. Bundled package data: src/bugowner/data/false_positives.seed.json

    Args:
        config: Optional config dict; None and {} both use the bundled seed.

    Returns:
        Resolved Path to the seed file (guaranteed to exist).

    Raises:
        FileNotFoundError: If neither path resolves to an existing file.
    """
    config = config or {}

    if override := config.get("false_positives_seed"):
        path = Path(override).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"Seed file from config (false_positives_seed) not found: {path}"
            )
        return path

    # Same idiom as src/bugowner/commands/init.py:49
    seed_traversable = files("bugowner").joinpath("data/false_positives.seed.json")
    seed_path = Path(str(seed_traversable))
    if not seed_path.exists():
        raise FileNotFoundError(f"Bundled seed file not found: {seed_path}")
    return seed_path


def bootstrap_cache_from_seed(cache_file: Path, seed_file: Path) -> int:
    """Copy seed → cache iff cache does not yet exist (idempotent).

    Args:
        cache_file: Destination cache path (created if absent).
        seed_file: Source seed path (must exist).

    Returns:
        Number of entries copied (0 if cache already existed).

    Raises:
        FileNotFoundError: If seed does not exist.
        OSError: If cache parent dir cannot be created or copy fails.
    """
    if cache_file.exists() or cache_file.is_symlink():
        return 0
    if not seed_file.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_file}")

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_file, cache_file)

    with open(cache_file, encoding="utf-8") as f:
        return len(json.load(f))
