"""Configuration file loading utilities.

Design Notes:
    - Exceptions bubble up without logging (industry best practice)
    - Logging at utility level creates duplicate logs and couples code
    - Callers handle exceptions at appropriate boundary
    - Accepts str | Path for backward compatibility with legacy code
"""

import os
from pathlib import Path
from typing import Any

import yaml


def find_config_file(explicit_path: Path | None = None) -> Path:
    """Find config file using standard search hierarchy.

    Precedence (highest to lowest):
    1. Explicit path (CLI --config argument)
    2. BUGOWNERCTL_CONFIG environment variable
    3. ./validate_maintainership.yaml (project-local)
    4. ~/.config/bugownerctl/config.yaml (XDG user config)
    5. /etc/bugownerctl/config.yaml (system-wide)

    Args:
        explicit_path: Optional explicit config path from CLI argument

    Returns:
        Path to config file (guaranteed to exist)

    Raises:
        FileNotFoundError: If config not found in any location
    """
    # 1. Explicit path (highest priority)
    if explicit_path is not None:
        resolved = explicit_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Config file specified via --config not found: {resolved}")
        return resolved

    # 2. BUGOWNERCTL_CONFIG environment variable
    env_config = os.getenv("BUGOWNERCTL_CONFIG")
    if env_config:
        env_path = Path(env_config).expanduser().resolve()
        if not env_path.exists():
            raise FileNotFoundError(f"Config file from BUGOWNERCTL_CONFIG not found: {env_path}")
        return env_path

    # Track searched locations for error message
    searched_locations = []

    # 3. Project-local config (CWD)
    project_config = Path.cwd() / "validate_maintainership.yaml"
    searched_locations.append(f"Project directory: {project_config}")
    if project_config.exists():
        return project_config.resolve()

    # 4. User XDG config
    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        user_config = Path(xdg_config_home) / "bugownerctl" / "config.yaml"
    else:
        user_config = Path.home() / ".config" / "bugownerctl" / "config.yaml"
    searched_locations.append(f"User config (XDG): {user_config}")
    if user_config.exists():
        return user_config.resolve()

    # 5. System config
    system_config = Path("/etc/bugownerctl/config.yaml")
    searched_locations.append(f"System config: {system_config}")
    if system_config.exists():
        return system_config.resolve()

    # Not found anywhere - provide helpful error
    error_msg = (
        "Config file not found in any location.\n\n"
        "Searched locations:\n  " + "\n  ".join(searched_locations) + "\n\n"
        "Solutions:\n"
        "  1. Create config in project directory: ./validate_maintainership.yaml\n"
        "  2. Create user config: ~/.config/bugownerctl/config.yaml\n"
        "  3. Use --config flag to specify path\n"
        "  4. Set BUGOWNERCTL_CONFIG environment variable"
    )
    raise FileNotFoundError(error_msg)


def load_config(
    config_file: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load YAML configuration file.

    If config_file is None, searches standard locations via find_config_file().
    If config_file is provided, loads that file directly (no search).

    Args:
        config_file: Optional explicit path to YAML config (str, Path, or None)
                    If None, searches standard locations

    Returns:
        Configuration dictionary, or None if file is empty

    Raises:
        FileNotFoundError: If config file not found
        yaml.YAMLError: If invalid YAML
    """
    # If no config file specified, search for it
    if config_file is None:
        config_path = find_config_file()
    else:
        # Explicit path provided - use it directly (backward compatibility)
        config_path = Path(config_file) if isinstance(config_file, str) else config_file

    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] | None = yaml.safe_load(f)
        return config
