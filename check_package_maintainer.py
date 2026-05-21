import json
import sys
from typing import Set

MAINTAINERSHIP_FILE = "_maintainership.json"
WHITELIST_FILE = "whitelist_maintainership.json"

def load_maintainership_data(file_path: str) -> Set[str]:
    """
    Loads keys (submodule names) from the _maintainership.json file.
    
    Returns: A set of submodule names (keys).
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Assuming it's a JSON object (dictionary)
            data = json.load(f)
            return set(data.keys())
            
    except FileNotFoundError:
        print(f" Error: Maintainership file '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f" Error: Invalid JSON format in '{file_path}'.", file=sys.stderr)
        # Note: This will catch the duplicate key issue as well.
        sys.exit(1)
    except Exception as e:
        print(f" An unexpected error occurred while loading {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


def load_whitelist_data(file_path: str) -> Set[str]:
    """
    Loads package names from the _maintainership-whitelist.json file.
    
    Returns: A set of package names.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Assuming it's a JSON array (list) of strings
            data = json.load(f)
            
            if not isinstance(data, list):
                print(f" Error: Whitelist file '{file_path}' must contain a JSON array/list.", file=sys.stderr)
                sys.exit(1)
                
            # Convert list of package names to a set for fast lookups
            return set(data)
            
    except FileNotFoundError:
        print(f" Warning: Whitelist file '{file_path}' not found. Continuing without whitelist check.", file=sys.stderr)
        return set() # Return an empty set if the file is missing
    except json.JSONDecodeError:
        print(f" Error: Invalid JSON format in '{file_path}'.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f" An unexpected error occurred while loading {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


def check_package_maintainership(package_name: str, maintained: Set[str], whitelisted: Set[str]) -> bool:
    """
    Checks if a package is maintained or whitelisted.
    
    Returns: True if the package is listed or whitelisted, False otherwise.
    """
    
    # 1. Check the primary maintainership list
    if package_name in maintained:
        print(f" Success: Package '**{package_name}**' found in **{MAINTAINERSHIP_FILE}**.")
        return True

    # 2. Check the whitelist
    if package_name in whitelisted:
        print(f" Allowed: Package '**{package_name}**' is allowed via **{WHITELIST_FILE}**.")
        return True

    # 3. Not found
    print(f" Failure: Package '**{package_name}**' is **not** listed in {MAINTAINERSHIP_FILE} or {WHITELIST_FILE}.")
    return False


def main():
    """Main function to parse arguments and run the check."""
    
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <package_name>", file=sys.stderr)
        sys.exit(1)
        
    package_to_check = sys.argv[1]
    
    print(f"Starting check for package: **{package_to_check}**")
    print("---")
    
    # Load data
    maintained_packages = load_maintainership_data(MAINTAINERSHIP_FILE)
    whitelisted_packages = load_whitelist_data(WHITELIST_FILE)
    
    # Run check
    is_valid = check_package_maintainership(package_to_check, maintained_packages, whitelisted_packages)
    
    # Set exit code for use in CI/shell scripts
    if not is_valid:
        sys.exit(1)
    else:
        sys.exit(0) # Success


if __name__ == "__main__":
    # DEPRECATION WARNING
    print("\n" + "=" * 80, file=sys.stderr)
    print("WARNING: This script is DEPRECATED", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print("", file=sys.stderr)
    print("Please use the new unified CLI instead:", file=sys.stderr)
    print("  Old: python check_package_maintainer.py <package>", file=sys.stderr)
    print("  New: bugowner query package <package>", file=sys.stderr)
    print("", file=sys.stderr)
    print("Installation: uv pip install -e .", file=sys.stderr)
    print("Help:         bugowner --help", file=sys.stderr)
    print("", file=sys.stderr)
    print("This script will be removed in a future release.", file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)

    main()
