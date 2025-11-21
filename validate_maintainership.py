import zstandard as zstd
from lxml import etree
import yaml
import re
import sys
import json
import subprocess
from typing import List, Set, Dict, Tuple, Optional, Any
import os
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import tempfile
from contextlib import contextmanager

# --- Configuration ---
load_dotenv()


def load_config(config_file_path: str) -> Dict[str, Any]:
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(
            f"Error: Configuration file '{config_file_path}' not found.",
            file=sys.stderr,
        )
        sys.exit(1)
    except yaml.YAMLError as e:
        print(
            f"Error: Invalid YAML format in '{config_file_path}': {e}", file=sys.stderr
        )
        sys.exit(1)


config = load_config("validate_maintainership.yaml")

ZST_FILE_PATHS: List[str] = config["zst_file_paths"]
GIT_REPOSITORIES: Dict[str, Dict[str, str]] = config["git_repositories"]
FALSEPOSITIVES_FILE: str = config["false_positives_file"]
NSMAP: Dict[str, str] = config["nsmap"]
OUTPUT_FILES: Dict[str, str] = config["output_files"]

COMMON_NS_URI: str = NSMAP["common"]


@contextmanager
def clone_repository(repo_url: str, branch: str) -> Optional[str]:
    """
    Clones a Git repository into a temporary directory and provides the path.
    The temporary directory is automatically cleaned up upon exiting the context.
    """
    temp_dir = tempfile.TemporaryDirectory()
    try:
        print(f"--- Cloning {repo_url} (branch: {branch}) into {temp_dir.name} ---")
        subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                branch,
                "--depth",
                "1",
                "--no-remote-submodules",
                repo_url,
                temp_dir.name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        yield temp_dir.name
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repository {repo_url}: {e.stderr}", file=sys.stderr)
        yield None
    finally:
        temp_dir.cleanup()


def get_source_package_from_obs(package: str) -> Optional[str]:
    """
    Get the source package from OBS.
    This function takes a package name, queries OBS to find its source package,
    and returns the source package name.

    :param api_url: OBS instance
    :param project: OBS project
    :param package: binary name
    :return: source package
    """
    project: str = "SUSE:SLFO:Main"
    command: str = f"osc -A https://api.suse.de bse {package}"
    output: subprocess.CompletedProcess = subprocess.run(
        command.split(),
        capture_output=True,
        text=True,
        check=False,
    )
    filtered_output: List[str] = [
        line for line in output.stdout.splitlines() if line.startswith(f"{project} ")
    ]
    if len(filtered_output) == 0:
        print(f"No source package found for {package} in {project}.")
        return None
    packages: List[str] = []
    for line in filtered_output:
        items: List[str] = line.split()
        item: List[str] = items[1].split(":")
        if len(item) > 0:
            packages.append(item[0])
    source_package: Set[str] = set(packages)
    if len(source_package) != 1:
        print(
            "More than 1 source package found for %s in %s: %s",
            package,
            project,
            source_package,
        )
    return str(next(iter(source_package)))


def run_git_submodule(slfo_git_repo_path: str) -> str:
    """
    Execute `git submodule status` in the given directory.
    Returns the command's stdout.
    """
    try:
        result: subprocess.CompletedProcess = subprocess.run(
            ["git", "submodule", "status"],
            capture_output=True,
            text=True,
            check=False,
            cwd=slfo_git_repo_path,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"`git submodule status` failed (exit {result.returncode}). "
                f"Stderr: {result.stderr.strip()}"
            )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f" Error running git command: {e}", file=sys.stderr)
        print(" Ensure you are in the root of a Git repository.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            " Error: 'git' command not found. Ensure Git is installed and in your PATH.",
            file=sys.stderr,
        )
        sys.exit(1)


def parse_git_submodules(git_output: str) -> List[str]:
    """
    This function parses the output of `git submodule status` and extracts the
    submodule names.
    """
    names: List[str] = []
    for line in git_output.splitlines():
        parts: List[str] = line.strip().split()
        if len(parts) >= 2:
            names.append(parts[1])
    return names


def get_packages_from_git_submodules(slfo_git_repo_path: str) -> List[str]:
    """
    Retrieves a sorted list of submodule names from the Git repository.
    """
    print(f"--- Getting submodule names from {slfo_git_repo_path} ---")
    submodule_names: List[str] = []
    try:
        raw: str = run_git_submodule(slfo_git_repo_path)
    except RuntimeError as err:
        print(f"{err}", file=sys.stderr)
        return []

    submodule_names = parse_git_submodules(raw)
    submodule_names.sort()

    return submodule_names


def get_package_name_from_repo_metadata(filename: str) -> Optional[str]:
    """
    Parses the package name from a source rpm filename.
    """
    # 1. Strip extensions first to simplify the pattern matching
    name_no_suffix: str = re.sub(r"\.(src|nosrc)\.rpm$", "", filename)
    name_no_suffix = re.sub(r"\.[a-zA-Z0-9_]+$", "", name_no_suffix)

    # 2. Primary Pattern Explanation (Targets the start of the version):
    # (.*?)  -> Capture group 1 (Package Name). Non-greedy.
    # -      -> Matches the hyphen that separates Name from Version.
    # \d+    -> Captures the start of the version (e.g., 2, 6, 31, 20240927, or 17).
    # [\.+-] -> Requires the number to be immediately followed by a dot, plus sign, or hyphen.

    # We add '+' to the required following characters to handle the '17+359' pattern.
    match: Optional[re.Match[str]] = re.match(r"(.*?)-\d+[.+-].*", name_no_suffix)

    if match:
        # Group 1 is the package name.
        return match.group(1)

    # Fallback: For versions that start with a number but lack a dot or plus/minus (e.g., package-1-release)
    match_fallback: Optional[re.Match[str]] = re.match(
        r"(.*?)-\d+(-.*)?$", name_no_suffix
    )
    if match_fallback:
        return match_fallback.group(1)

    return None


def _parse_zst_file(zst_file: str) -> Set[Tuple[str, str, Optional[str]]]:
    """
    Parses a single .zst file and returns a set of binary data tuples.
    """
    print(f"--- Parsing binary packages from {zst_file} ---")
    binary_data_set: Set[Tuple[str, str, Optional[str]]] = set()
    try:
        dctx = zstd.ZstdDecompressor()
        with open(zst_file, "rb") as compressed_file:
            with dctx.stream_reader(compressed_file) as xml_stream:
                context = etree.iterparse(
                    xml_stream, events=("end",), tag=f"{{{COMMON_NS_URI}}}package"
                )
                for _, element in context:
                    name_element = element.find(f"{{{COMMON_NS_URI}}}name")
                    sourcerpm_element = element.find(
                        "common:format/rpm:sourcerpm", namespaces=NSMAP
                    )

                    if name_element is not None and name_element.text:
                        binary_name: str = name_element.text
                        sourcerpm_filename: str = (
                            sourcerpm_element.text
                            if sourcerpm_element is not None and sourcerpm_element.text
                            else "N/A"
                        )
                        package_name: Optional[str] = (
                            get_package_name_from_repo_metadata(sourcerpm_filename)
                        )
                        binary_data_set.add(
                            (binary_name, sourcerpm_filename, package_name)
                        )
                    element.clear()
    except FileNotFoundError:
        print(f"Error: The file '{zst_file}' was not found.", file=sys.stderr)
    except Exception as e:
        print(f"An error occurred while parsing '{zst_file}': {e}", file=sys.stderr)
    return binary_data_set


def get_binary_data_from_repo_metadata() -> List[Tuple[str, str, Optional[str]]]:
    """
    Parses repository metadata from .zst files in parallel.
    Returns a sorted list of unique tuples: (binary_name, sourcerpm_filename, package_name)
    """
    print("--- Parsing repository metadata ---")
    binary_data_set: Set[Tuple[str, str, Optional[str]]] = set()

    with ProcessPoolExecutor() as executor:
        results = executor.map(_parse_zst_file, ZST_FILE_PATHS)
        for result in results:
            binary_data_set.update(result)

    sorted_binary_data: List[Tuple[str, str, Optional[str]]] = sorted(
        list(binary_data_set)
    )

    output_json_file: str = OUTPUT_FILES["binary_data_from_repo"]
    print(f"--- Saving repository metadata to {output_json_file} ---")
    try:
        binary_data_as_dict_list = [
            {"binary_name": row[0], "source_rpm": row[1], "package_name": row[2]}
            for row in sorted_binary_data
        ]
        with open(output_json_file, "w", encoding="utf-8") as f:
            json.dump(binary_data_as_dict_list, f, indent=4, sort_keys=True)
        print(f"Successfully saved data to {output_json_file}")
    except IOError as e:
        print(f"Error writing to JSON file: {e}", file=sys.stderr)

    return sorted_binary_data


def find_binaries_in_productcompose(data: Any, packages_set: Set[str]) -> None:
    """Recursively search for 'binaries' keys in YAML data."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "packages" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        match = re.match(r"^\s*([^\s#]+)", item)
                        if match:
                            packages_set.add(match.group(1))
            else:
                find_binaries_in_productcompose(value, packages_set)
    elif isinstance(data, list):
        for item in data:
            find_binaries_in_productcompose(item, packages_set)


def get_binaries_from_productcompose(
    productcompose_file: str,
) -> Optional[Set[str]]:
    """
    Parses the productcompose file and returns a unique set of binary names.
    """
    binaries: Set[str] = set()
    print(f"--- Parsing binaries from {productcompose_file} ---")
    try:
        with open(productcompose_file, "r") as f:
            content: str = f.read()

        marker: str = "#  ### AUTOMATICALLY GENERATED, DO NOT EDIT ###"
        content_to_parse: str = content
        if marker in content:
            content_to_parse = content[content.find(marker) :]
        else:
            print(
                f"Warning: Marker '{marker}' not found. Parsing the whole file.",
                file=sys.stderr,
            )

        yaml_docs = yaml.safe_load_all(content_to_parse)
        for doc in yaml_docs:
            if doc:
                find_binaries_in_productcompose(doc, binaries)

    except FileNotFoundError:
        print(f"Error: The file '{productcompose_file}' was not found.", file=sys.stderr)
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML in '{productcompose_file}': {e}", file=sys.stderr)
        return None

    print(f"Found {len(binaries)} unique binaries in the productcompose file.")
    return binaries


def check_binaries_not_shipped(
    binary_data_list: List[Tuple[str, str, Optional[str]]],
    binary_set_from_compose: Set[str],
) -> None:
    """
    This function compares the binaries from the productcompose file with the binaries
    from the repository metadata and writes any not shipped binaries to a file.
    """
    print("--- Checking for binaries not shipped ---")
    binaries_from_repo: Set[str] = {item[0] for item in binary_data_list}
    binaries_not_shipped: List[str] = sorted(
        list(binary_set_from_compose - binaries_from_repo)
    )

    if binaries_not_shipped:
        print(f"Found {len(binaries_not_shipped)} binaries not shipped.")
        with open(OUTPUT_FILES["binaries_not_shipped"], "w", encoding="utf-8") as f:
            json.dump(binaries_not_shipped, f, indent=4, sort_keys=True)
        print(f"Saved binaries not shipped to {OUTPUT_FILES['binaries_not_shipped']}")
    else:
        print("No binaries not shipped found.")


def check_invalid_packages(
    binary_data_list: List[Tuple[str, str, Optional[str]]], submodule_list: List[str]
) -> Optional[Set[str]]:
    """
    Checks for packages that are not in the git submodules and not in the false positives file.
    This function identifies packages that are not part of the git submodules,
    checks them against a list of false positives, and queries OBS for the source package in parallel.
    Invalid packages are written to a file.
    """
    print("--- Checking for invalid packages ---")
    packages_from_repo: Set[str] = {
        item[2] for item in binary_data_list if item[2] is not None
    }

    remapping: Dict[str, Optional[str]] = {}
    try:
        with open(FALSEPOSITIVES_FILE, "r") as f:
            file_remapping = json.load(f)
            if file_remapping:
                remapping.update(file_remapping)
    except FileNotFoundError:
        print(
            f"Warning: False positives file not found at '{FALSEPOSITIVES_FILE}'. Using empty remapping.",
            file=sys.stderr,
        )
    except json.JSONDecodeError:
        print(
            f"Error: Invalid JSON format in '{FALSEPOSITIVES_FILE}'. Using empty remapping.",
            file=sys.stderr,
        )

    if remapping:
        print(
            f"--- Updating {len(remapping)} false-positive packages from {FALSEPOSITIVES_FILE} ---"
        )
        processed_package_names: List[str] = []
        for pkg in packages_from_repo:
            remapped_name = remapping.get(pkg, pkg)
            if remapped_name is not None:
                processed_package_names.append(remapped_name)

        packages_from_repo = set(processed_package_names)

    unknown_packages: Set[str] = packages_from_repo - set(submodule_list)
    valid_packages: Set[str] = packages_from_repo - unknown_packages

    invalid_packages: List[str] = []
    false_positive_packages: Dict[str, str] = {}

    print(
        f"Found {len(unknown_packages)} unknown packages. Querying OBS in parallel..."
    )
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_package = {
            executor.submit(get_source_package_from_obs, pkg): pkg
            for pkg in unknown_packages
        }

        for future in as_completed(future_to_package):
            package_name = future_to_package[future]
            try:
                obs_package = future.result()
                if obs_package:
                    valid_packages.add(obs_package)
                    false_positive_packages[package_name] = obs_package
                else:
                    invalid_packages.append(package_name)
            except Exception as exc:
                print(
                    f"Package '{package_name}' generated an exception: {exc}",
                    file=sys.stderr,
                )

    if false_positive_packages:
        print(f"Found {len(false_positive_packages)} false-positives packages.")
        remapping.update(false_positive_packages)
        with open(FALSEPOSITIVES_FILE, "w", encoding="utf-8") as f:
            json.dump(remapping, f, indent=4, sort_keys=True)
        print(f"Added false-positives packages to {FALSEPOSITIVES_FILE}.")
    else:
        print("No false-positives packages found.")

    if invalid_packages:
        print(f"Found {len(invalid_packages)} invalid packages.")
        with open(OUTPUT_FILES["invalid_packages"], "w", encoding="utf-8") as f:
            json.dump(sorted(invalid_packages), f, indent=4, sort_keys=True)
        print(f"Saved invalid packages to {OUTPUT_FILES['invalid_packages']}")
    else:
        print("No invalid packages found.")

    return valid_packages


def get_maintainer_data(maintainership_file: str) -> Optional[Dict[str, Any]]:
    """
    Parses the maintainership file and returns its content.
    """
    print(f"--- Parsing maintainership from {maintainership_file} ---")
    try:
        with open(maintainership_file, "r") as f:
            maintainer_data: Dict[str, Any] = json.load(f)
        return maintainer_data
    except FileNotFoundError:
        print(
            f"Error: Maintainership file not found at '{maintainership_file}'",
            file=sys.stderr,
        )
        return None
    except json.JSONDecodeError as e:
        print(
            f"Error: Invalid JSON format in '{maintainership_file}': {e}",
            file=sys.stderr,
        )
        return None


def check_orphan_packages(
    valid_packages: Set[str], maintainer_data: Dict[str, Any]
) -> Optional[List[str]]:
    """
    Checks for packages without a listed maintainer.
    """
    print("--- Checking for orphan packages ---")

    orphan_packages: List[str] = sorted(
        [pkg for pkg in valid_packages if not maintainer_data.get(pkg)]
    )

    return orphan_packages


def check_packages_without_submodule(
    submodule_list: List[str], maintainer_data: Dict[str, Any]
) -> None:
    """
    Checks for packages in maintainership that do not have a git submodule.
    """
    print(
        "--- Checking for packages in maintainership file without equivalent git submodule ---"
    )
    packages_in_maintainership: Set[str] = set(maintainer_data.keys())
    submodule_set: Set[str] = set(submodule_list)

    mismatched_packages: List[str] = sorted(
        list(packages_in_maintainership - submodule_set)
    )

    if mismatched_packages:
        print(
            f"Found {len(mismatched_packages)} packages in maintainership file "
            f"without an equivalent git submodule."
        )
        output_file = OUTPUT_FILES["packages_without_submodule"]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(mismatched_packages, f, indent=4, sort_keys=True)
        print(f"Saved packages without submodule to {output_file}")
    else:
        print(
            "No packages found in maintainership file without an equivalent git submodule."
        )


def main() -> None:
    """
    Main function to run the bugownership checker.
    """
    slfo_repo_info = GIT_REPOSITORIES.get("SLFO", {})
    sles_repo_info = GIT_REPOSITORIES.get("SLES", {})

    if not slfo_repo_info.get("url") or not sles_repo_info.get("url"):
        print(
            "Error: Git repository URL for SLFO or SLES not found in the configuration file.",
            file=sys.stderr,
        )
        return

    with clone_repository(
        slfo_repo_info["url"], slfo_repo_info.get("branch", "main")
    ) as slfo_repo_path, clone_repository(
        sles_repo_info["url"], sles_repo_info.get("branch", "main")
    ) as sles_repo_path:
        if not slfo_repo_path or not sles_repo_path:
            print("Failed to clone one or more repositories. Aborting.", file=sys.stderr)
            return

        maintainership_file = os.path.join(slfo_repo_path, "_maintainership.json")
        productcompose_file = os.path.join(
            sles_repo_path, "000productcompose/default.productcompose"
        )

        binary_data_list: List[Tuple[str, str, Optional[str]]] = (
            get_binary_data_from_repo_metadata()
        )
        if not binary_data_list:
            print(
                "Could not gather any package data from XML files. Aborting.",
                file=sys.stderr,
            )
            return

        binary_set_from_compose: Optional[Set[str]] = get_binaries_from_productcompose(
            productcompose_file
        )
        if binary_set_from_compose is None:
            return

        submodule_list: List[str] = get_packages_from_git_submodules(slfo_repo_path)
        if not submodule_list:
            print(
                "Could not gather any package data from git submodules. Aborting.",
                file=sys.stderr,
            )
            return

        check_binaries_not_shipped(binary_data_list, binary_set_from_compose)

        maintainer_data: Optional[Dict[str, Any]] = get_maintainer_data(
            maintainership_file
        )
        if maintainer_data is None:
            return

        check_packages_without_submodule(submodule_list, maintainer_data)

        valid_packages: Optional[Set[str]] = check_invalid_packages(
            binary_data_list, submodule_list
        )
        if valid_packages is None:
            print("No valid packages found. Aborting.", file=sys.stderr)
            return

        orphan_packages: Optional[List[str]] = check_orphan_packages(
            valid_packages, maintainer_data
        )
        if orphan_packages is not None:
            if orphan_packages:
                print(f"Found {len(orphan_packages)} orphan packages.")
                with open(
                    OUTPUT_FILES["orphan_packages"], "w", encoding="utf-8"
                ) as f:
                    json.dump(orphan_packages, f, indent=4, sort_keys=True)
                print(f"Saved orphan packages to {OUTPUT_FILES['orphan_packages']}")
            else:
                print("No orphan packages found.")


if __name__ == "__main__":
    main()
