"""Init command handler.

Creates initial configuration file from bundled example.
"""

import argparse
import shutil
from importlib.resources import files
from pathlib import Path


def run(args: argparse.Namespace) -> int:
    """Create initial config file from bundled example.

    Args:
        args: Parsed arguments
            - location: 'user' | 'local' | 'system'
            - force: Overwrite existing config

    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Determine target location based on args.location
    if args.location == "user":
        config_home = Path.home() / ".config" / "bugownership"
        target_path = config_home / "config.yaml"
    elif args.location == "local":
        target_path = Path.cwd() / "validate_maintainership.yaml"
    elif args.location == "system":
        target_path = Path("/etc/bugownership/config.yaml")
    else:
        print(f"Error: Invalid location '{args.location}'")
        return 1

    # Resolve path for security (prevents traversal)
    target_path = target_path.resolve()

    # Check if config already exists
    if target_path.exists() and not args.force:
        print(f"Error: Config file already exists: {target_path}")
        print("Use --force to overwrite")
        return 1

    if target_path.exists() and args.force:
        print(f"Overwriting existing config: {target_path}")

    # Get bundled example file
    try:
        example_traversable = files("bugowner").joinpath("data/config.example.yaml")
        # Convert Traversable to Path for proper type checking and file operations
        example_path = Path(str(example_traversable))
        if not example_path.exists():
            print("Error: Bundled config example not found")
            return 1
    except Exception as e:
        print(f"Error: Failed to locate bundled example: {e}")
        return 1

    # Create parent directory if needed
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"Error: Permission denied creating directory: {target_path.parent}")
        print(f"  {e}")
        return 1

    # Copy example to target
    try:
        shutil.copy2(example_path, target_path)
    except PermissionError as e:
        print(f"Error: Permission denied writing config: {target_path}")
        print(f"  {e}")
        return 1
    except Exception as e:
        print(f"Error: Failed to copy config: {e}")
        return 1

    # Print success message
    print(f"✓ Created {'user' if args.location == 'user' else args.location} config")
    print(f"  Location: {target_path}")
    print()
    print("Next steps:")
    print(f"  1. Edit config: {target_path}")
    print("  2. Update slfo_git_url and products")
    print("  3. Run: bugowner validate -v 16.1")

    return 0
