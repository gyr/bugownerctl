"""Configuration file loading utilities.

Design Notes:
    - Exceptions bubble up without logging (industry best practice)
    - Logging at utility level creates duplicate logs and couples code
    - Callers handle exceptions at appropriate boundary
    - Accepts str | Path for backward compatibility with legacy code
"""

from pathlib import Path
from typing import Any

import yaml


def load_config(
    config_file: str | Path = Path("validate_maintainership.yaml"),
) -> dict[str, Any] | None:
    """Load YAML configuration file.

    Args:
        config_file: Path to YAML config (str or Path, default: validate_maintainership.yaml)

    Returns:
        Configuration dictionary, or None if file is empty

    Raises:
        FileNotFoundError: If config file not found
        yaml.YAMLError: If invalid YAML
    """
    config_path = Path(config_file) if isinstance(config_file, str) else config_file
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] | None = yaml.safe_load(f)
        return config
