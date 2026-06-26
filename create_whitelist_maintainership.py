import json
import subprocess
import sys
from typing import Set

MAINTAINERSHIP_FILE = "_maintainership.json"
WHITELIST_FILE = "whitelist_maintainership.json"

def get_git_submodules() -> Set[str]:
    """
    Retrieves a set of submodule names (paths) from the git repository.
    Uses 'git submodule status' and parses the output.
    """
    submodules = set()
    try:
        # Run 'git submodule status' command
        # The output format is: <sha1> <path> (<branch>)
        # We need the <path>, which is the second element.
        result = subprocess.run(
            ['git', 'submodule', 'status'],
            capture_output=True,
            text=True,
            check=True,
            cwd='.' # Run command from the current directory
        )
        
        # Process each line of the output
        for line in result.stdout.strip().split('\n'):
            if line:
                # Split the line by whitespace
                parts = line.split()
                if len(parts) >= 2:
                    # The submodule path is the second element (index 1)
                    submodule_path = parts[1].strip()
                    submodules.add(submodule_path)
        
    except subprocess.CalledProcessError as e:
        # This handles errors if the git command itself fails (e.g., not a git repo)
        print(f" Error running git command: {e}", file=sys.stderr)
        print(" Ensure you are in the root of a git repository.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(" Error: 'git' command not found. Ensure git is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)

    return submodules


def get_maintained_packages() -> Set[str]:
    """
    Reads the list of packages from the _maintainership.json file.
    Returns a set of package names (keys).
    """
    maintained_packages = set()
    try:
        with open(MAINTAINERSHIP_FILE, 'r') as f:
            data = json.load(f)
        
        # The keys of the dictionary are the package names
        maintained_packages = set(data.keys())
        
    except FileNotFoundError:
        print(f" Error: Maintainership file '{MAINTAINERSHIP_FILE}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f" Error: Invalid JSON format in '{MAINTAINERSHIP_FILE}'.", file=sys.stderr)
        sys.exit(1)
        
    return maintained_packages

def check_submodules_listed(submodules: Set[str], maintained: Set[str]) -> bool:
    """
    Compares the set of actual submodules with the set of maintained packages.
    Returns True if all submodules are listed, False otherwise.
    """
    missing_in_json = submodules - maintained
    invalid_in_json = maintained - submodules
    
    all_listed = True
    
    if missing_in_json:
        print(" The following packages from git submodules are **MISSING** from the maintainership file and will be whitelisted:")
        for package in sorted(list(missing_in_json)):
            print(f"- {package}")
        all_listed = False
        missing_in_json_list = sorted(list(missing_in_json))
        with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(missing_in_json_list, f, indent=4, sort_keys=True)
        print(f"Saved misssing packages to {WHITELIST_FILE}")
        
    print("---")
    
    if invalid_in_json:
        print(" The following packages in the maintainership file are **NOT** active git submodules:")
        for entry in sorted(list(invalid_in_json)):
            print(f"- {entry}")
    else:
        print(" No invalid packages found in the maintainership file.")

    print("---")
        
    if all_listed:
        print(" SUCCESS: All active packages from git submodules are listed in the maintainership file.")
        return True
    else:
        print(" FAILURE: Not all active packages from git submodules are listed in the maintainership file.")
        return False

def main():
    """Main function to run the check."""
    print("Starting git submodule and maintainership check...")
    
    # 1. Get the list of actual submodules
    actual_submodules = get_git_submodules()
    
    # 2. Get the list of maintained submodules
    maintained_submodules = get_maintained_packages()
    
    # 3. Check for discrepancies
    is_valid = check_submodules_listed(actual_submodules, maintained_submodules)
    
    # Set exit code based on the result
    if not is_valid:
        sys.exit(1)
    # else: sys.exit(0) is default behavior if the script runs to completion

if __name__ == "__main__":
    # DEPRECATION WARNING
    print("\n" + "=" * 80, file=sys.stderr)
    print("WARNING: This script is DEPRECATED", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print("", file=sys.stderr)
    print("Please use the new unified CLI instead:", file=sys.stderr)
    print("  Old: python create_whitelist_maintainership.py", file=sys.stderr)
    print("  New: bugownerctl whitelist update", file=sys.stderr)
    print("", file=sys.stderr)
    print("Installation: uv pip install -e .", file=sys.stderr)
    print("Help:         bugownerctl --help", file=sys.stderr)
    print("", file=sys.stderr)
    print("This script will be removed in a future release.", file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)

    main()
