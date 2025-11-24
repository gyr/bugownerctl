import logging
import gzip
import zstandard as zstd
from lxml import etree
import yaml
import re
import requests
import sys
import json
import hashlib
import subprocess
from typing import List, Set, Dict, Tuple, Optional, Any
import os
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

# --- Configuration ---
load_dotenv()


def load_config(config_file_path: str) -> Dict[str, Any]:
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file '{config_file_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"Invalid YAML format in '{config_file_path}': {e}")
        sys.exit(1)


config = load_config("validate_maintainership.yaml")

CACHE_DIR = os.path.expanduser(config.get("cache_dir", "~/.cache/bugownership"))
BASE_URL = (
    "https://download.suse.de/ibs/SUSE:/SLFO:/Products:/SLES:/{}:/PUBLISH/product/"
)
REPOMD_PATH = "repodata/repomd.xml"
ZST_FILE_PATHS: List[str] = config["zst_file_paths"]
GIT_REPOSITORIES: Dict[str, Dict[str, str]] = config["git_repositories"]
FALSEPOSITIVES_FILE: str = config.get("false_positives_file", "false_positives.json")
CHECK_BINARIES_NOT_SHIPPED: bool = config.get("check_binaries_not_shipped", False)

# Namespaces for XML parsing
NSMAP: Dict[str, str] = {
    "common": "http://linux.duke.edu/metadata/common",
    "rpm": "http://linux.duke.edu/metadata/rpm",
}
COMMON_NS_URI: str = NSMAP["common"]

# Hardcoded output filenames
OUTPUT_FILES: Dict[str, str] = {
    "binary_data_from_repo": "binary_data_from_repo.json",
    "binaries_not_shipped": "binaries_not_shipped.json",
    "missing_packages_in_maintainership": "missing_packages_in_maintainership.json",
    "invalid_packages": "invalid_packages.json",
    "orphan_packages": "orphan_packages.json",
    "packages_without_submodule": "packages_without_submodule.json",
}


def download_file(
    url: str, destination_folder: str = ".", filename: Optional[str] = None
) -> Optional[str]:
    """
    Downloads a file from a given URL to a specified destination folder.

    Args:
        url (str): The URL of the file to download.
        destination_folder (str): The folder where the file will be saved.
                                 Defaults to the current directory.
        filename (str, optional): The name to save the file as. If None,
                                  the filename is extracted from the URL.
    """
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    if filename is None:
        filename = os.path.basename(url)

    destination_path = os.path.join(destination_folder, filename)

    try:
        logging.info(f"Downloading {url} to {destination_path}...")
        requests.packages.urllib3.disable_warnings(
            requests.packages.urllib3.exceptions.InsecureRequestWarning
        )
        response = requests.get(url, stream=True, verify=False)
        response.raise_for_status()  # Raise an exception for bad status codes

        with open(destination_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info(f"Successfully downloaded {filename}")
        return destination_path
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading the file: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    return None


def get_file_checksum(file_path: str, checksum_type: str = "sha256") -> Optional[str]:
    """
    Calculates the checksum of a file.

    Args:
        file_path (str): The path to the file.
        checksum_type (str): The checksum algorithm to use (e.g., 'sha256').

    Returns:
        str: The hexadecimal checksum of the file, or None if the file doesn't exist.
    """
    if not os.path.exists(file_path):
        return None

    hash_func = hashlib.new(checksum_type)
    with open(file_path, "rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            hash_func.update(byte_block)
    return hash_func.hexdigest()


def parse_repomd(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Parses a repomd.xml file to find the location and checksum of the primary data.

    Args:
        file_path (str): The path to the repomd.xml file.

    Returns:
        dict: A dictionary with 'href', 'checksum', and 'checksum_type', or None if not found.
    """
    try:
        tree = etree.parse(file_path)
        root = tree.getroot()
        # The namespace is required to find the elements
        namespace = {"repo": "http://linux.duke.edu/metadata/repo"}
        data_element = root.find("repo:data[@type='primary']", namespace)
        if data_element is not None:
            location_element = data_element.find("repo:location", namespace)
            checksum_element = data_element.find("repo:checksum", namespace)
            if location_element is not None and checksum_element is not None:
                return {
                    "href": location_element.get("href"),
                    "checksum": checksum_element.text,
                    "checksum_type": checksum_element.get("type"),
                }
    except etree.ParseError as e:
        logging.error(f"Error parsing XML file: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during parsing: {e}")
    return None


def download_repo_metadata(version: str, cache_dir: str) -> Optional[str]:
    base_url = BASE_URL.format(version)
    repomd_url = os.path.join(base_url, REPOMD_PATH)

    metadata_cache_dir = os.path.join(cache_dir, "repodata", version)

    downloaded_repomd_path = download_file(
        repomd_url, destination_folder=metadata_cache_dir, filename="repomd.xml"
    )
    if downloaded_repomd_path:
        primary_info = parse_repomd(downloaded_repomd_path)
        if primary_info:
            primary_location_href = primary_info["href"]
            expected_checksum = primary_info["checksum"]
            checksum_type = primary_info["checksum_type"]

            logging.info(
                f"Primary data location from repomd.xml: {primary_location_href}"
            )
            logging.info(f"Expected {checksum_type} checksum: {expected_checksum}")

            primary_filename = os.path.basename(primary_location_href)
            primary_file_path_in_cache = os.path.join(
                metadata_cache_dir, primary_filename
            )

            existing_checksum = get_file_checksum(
                primary_file_path_in_cache, checksum_type
            )

            if existing_checksum == expected_checksum:
                logging.info(
                    f"File {primary_filename} already exists in cache and checksum matches. Skipping download."
                )
                return primary_file_path_in_cache
            else:
                if existing_checksum is not None:
                    logging.warning(
                        f"Checksum mismatch for {primary_filename} in cache. Deleting and re-downloading."
                    )
                    os.remove(primary_file_path_in_cache)

                primary_file_url = os.path.join(base_url, primary_location_href)
                logging.info(f"Full URL for primary file: {primary_file_url}")

                downloaded_primary_path = download_file(
                    primary_file_url, destination_folder=metadata_cache_dir
                )
                return downloaded_primary_path
    return None


def parse_primary_xml(file_path: str) -> Set[str]:
    """
    Parses a gzipped primary XML file to extract package names with 'src' architecture.

    Args:
        file_path (str): The path to the gzipped primary XML file.
    """
    logging.info(f"Parsing {file_path}...")
    package_names = set()
    try:
        with gzip.open(file_path, "rb") as f:
            # Use iterparse for memory-efficient parsing of large files
            # The namespace is required to find the elements
            namespace = {
                "common": "http://linux.duke.edu/metadata/common",
                "rpm": "http://linux.duke.edu/metadata/rpm",
            }

            for event, elem in etree.iterparse(f, events=("end",)):
                if (
                    event == "end"
                    and elem.tag == "{http://linux.duke.edu/metadata/common}package"
                ):
                    if elem.get("type") == "rpm":
                        arch = elem.find("common:arch", namespace)
                        if arch is not None and arch.text == "src":
                            name = elem.find("common:name", namespace)
                            if name is not None:
                                package_names.add(name.text)
                    # Clear the element to free memory
                    elem.clear()

        unique_packages = sorted(list(package_names))
        output_filename = "src_packages.json"
        with open(output_filename, "w") as f_out:
            json.dump(unique_packages, f_out, indent=4)

        logging.info(
            f"Successfully extracted {len(unique_packages)} unique 'src' package names to {output_filename}"
        )
    except (etree.ParseError, gzip.BadGzipFile) as e:
        logging.error(f"Error parsing or decompressing file: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    return package_names


def manage_git_repository(repo_url: str, branch: str, cache_dir: str) -> Optional[str]:
    """
    Clones or updates a Git repository in the cache directory.
    """
    repo_name = os.path.splitext(os.path.basename(repo_url))[0]
    repo_path = os.path.join(cache_dir, repo_name)

    try:
        if not os.path.exists(repo_path):
            logging.info(
                f"--- Cloning {repo_url} (branch: {branch}) with --depth 1 and --no-remote-submodules into {repo_path} ---"
            )
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
                    repo_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            logging.info(f"--- Updating repository {repo_path} ---")
            # Fetch only the latest commit for the specified branch
            subprocess.run(
                ["git", "fetch", "--depth=1", "origin", branch],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Check current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            current_branch = result.stdout.strip()
            if current_branch != branch:
                logging.info(f"Switching branch from {current_branch} to {branch}")
                subprocess.run(
                    ["git", "checkout", branch],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            # Reset to remote branch state
            logging.info(f"Updating {repo_path} to latest version of branch {branch}")
            subprocess.run(
                ["git", "reset", "--hard", f"origin/{branch}"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

        return repo_path
    except subprocess.CalledProcessError as e:
        logging.error(f"Error managing repository {repo_url}: {e.stderr}")
        return None


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
        logging.info(f"No source package found for {package} in {project}.")
        return None
    packages: List[str] = []
    for line in filtered_output:
        items: List[str] = line.split()
        item: List[str] = items[1].split(":")
        if len(item) > 0:
            packages.append(item[0])
    source_package: Set[str] = set(packages)
    if len(source_package) != 1:
        logging.warning(
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
        logging.error(f" Error running git command: {e}")
        logging.error(" Ensure you are in the root of a Git repository.")
        sys.exit(1)
    except FileNotFoundError:
        logging.error(
            " Error: 'git' command not found. Ensure Git is installed and in your PATH."
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
    logging.info(f"--- Getting submodule names from {slfo_git_repo_path} ---")
    submodule_names: List[str] = []
    try:
        raw: str = run_git_submodule(slfo_git_repo_path)
    except RuntimeError as err:
        logging.error(f"{err}")
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
    logging.info(f"--- Parsing binary packages from {zst_file} ---")
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
        logging.error(f"Error: The file '{zst_file}' was not found.")
    except Exception as e:
        logging.error(f"An error occurred while parsing '{zst_file}': {e}")
    return binary_data_set


def get_binary_data_from_repo_metadata() -> List[Tuple[str, str, Optional[str]]]:
    """
    Parses repository metadata from .zst files in parallel.
    Returns a sorted list of unique tuples: (binary_name, sourcerpm_filename, package_name)
    """
    logging.info("--- Parsing repository metadata ---")
    binary_data_set: Set[Tuple[str, str, Optional[str]]] = set()

    with ProcessPoolExecutor() as executor:
        results = executor.map(_parse_zst_file, ZST_FILE_PATHS)
        for result in results:
            binary_data_set.update(result)

    sorted_binary_data: List[Tuple[str, str, Optional[str]]] = sorted(
        list(binary_data_set)
    )

    output_json_file: str = OUTPUT_FILES["binary_data_from_repo"]
    logging.info(f"--- Saving repository metadata to {output_json_file} ---")
    try:
        binary_data_as_dict_list = [
            {"binary_name": row[0], "source_rpm": row[1], "package_name": row[2]}
            for row in sorted_binary_data
        ]
        with open(output_json_file, "w", encoding="utf-8") as f:
            json.dump(binary_data_as_dict_list, f, indent=4, sort_keys=True)
        logging.info(f"Successfully saved data to {output_json_file}")
    except IOError as e:
        logging.error(f"Error writing to JSON file: {e}")

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
    logging.info(f"--- Parsing binaries from {productcompose_file} ---")
    try:
        with open(productcompose_file, "r") as f:
            content: str = f.read()

        marker: str = "#  ### AUTOMATICALLY GENERATED, DO NOT EDIT ###"
        content_to_parse: str = content
        if marker in content:
            content_to_parse = content[content.find(marker) :]
        else:
            logging.warning(f"Marker '{marker}' not found. Parsing the whole file.")

        yaml_docs = yaml.safe_load_all(content_to_parse)
        for doc in yaml_docs:
            if doc:
                find_binaries_in_productcompose(doc, binaries)

    except FileNotFoundError:
        logging.error(f"Error: The file '{productcompose_file}' was not found.")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML in '{productcompose_file}': {e}")
        return None

    logging.info(f"Found {len(binaries)} unique binaries in the productcompose file.")
    return binaries


def check_binaries_not_shipped(
    binary_data_list: List[Tuple[str, str, Optional[str]]],
    binary_set_from_compose: Set[str],
) -> None:
    """
    This function compares the binaries from the productcompose file with the binaries
    from the repository metadata and writes any not shipped binaries to a file.
    """
    logging.info("--- Checking for binaries not shipped ---")
    binaries_from_repo: Set[str] = {item[0] for item in binary_data_list}
    binaries_not_shipped: List[str] = sorted(
        list(binary_set_from_compose - binaries_from_repo)
    )

    if binaries_not_shipped:
        logging.info(f"Found {len(binaries_not_shipped)} binaries not shipped.")
        with open(OUTPUT_FILES["binaries_not_shipped"], "w", encoding="utf-8") as f:
            json.dump(binaries_not_shipped, f, indent=4, sort_keys=True)
        logging.info(
            f"Saved binaries not shipped to {OUTPUT_FILES['binaries_not_shipped']}"
        )
    else:
        logging.info("No binaries not shipped found.")


def check_invalid_packages(
    packages_from_repo: Set[str], submodule_list: List[str]
) -> Optional[Set[str]]:
    """
    Checks for packages that are not in the git submodules and not in the false positives file.
    This function identifies packages that are not part of the git submodules,
    checks them against a list of false positives, and queries OBS for the source package in parallel.
    Invalid packages are written to a file.
    """
    logging.info("--- Checking for invalid packages ---")

    remapping: Dict[str, Optional[str]] = {}
    try:
        with open(FALSEPOSITIVES_FILE, "r") as f:
            file_remapping = json.load(f)
            if file_remapping:
                remapping.update(file_remapping)
    except FileNotFoundError:
        logging.warning(
            f"False positives file not found at '{FALSEPOSITIVES_FILE}'. Using empty remapping."
        )
    except json.JSONDecodeError:
        logging.error(
            f"Invalid JSON format in '{FALSEPOSITIVES_FILE}'. Using empty remapping."
        )

    if remapping:
        logging.info(
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

    logging.info(
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
                logging.error(f"Package '{package_name}' generated an exception: {exc}")

    if false_positive_packages:
        logging.info(f"Found {len(false_positive_packages)} false-positives packages.")
        remapping.update(false_positive_packages)
        with open(FALSEPOSITIVES_FILE, "w", encoding="utf-8") as f:
            json.dump(remapping, f, indent=4, sort_keys=True)
        logging.info(f"Added false-positives packages to {FALSEPOSITIVES_FILE}.")
    else:
        logging.info("No false-positives packages found.")

    if invalid_packages:
        logging.info(f"Found {len(invalid_packages)} invalid packages.")
        with open(OUTPUT_FILES["invalid_packages"], "w", encoding="utf-8") as f:
            json.dump(sorted(invalid_packages), f, indent=4, sort_keys=True)
        logging.info(f"Saved invalid packages to {OUTPUT_FILES['invalid_packages']}")
    else:
        logging.info("No invalid packages found.")

    return valid_packages


def get_maintainer_data(maintainership_file: str) -> Optional[Dict[str, Any]]:
    """
    Parses the maintainership file and returns its content.
    """
    logging.info(f"--- Parsing maintainership from {maintainership_file} ---")
    try:
        with open(maintainership_file, "r") as f:
            maintainer_data: Dict[str, Any] = json.load(f)
        return maintainer_data
    except FileNotFoundError:
        logging.error(f"Maintainership file not found at '{maintainership_file}'")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format in '{maintainership_file}': {e}")
        return None


def check_orphan_packages(
    valid_packages: Set[str], maintainer_data: Dict[str, Any]
) -> Optional[List[str]]:
    """
    Checks for packages without a listed maintainer.
    """
    logging.info("--- Checking for orphan packages ---")

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
    logging.info(
        "--- Checking for packages in maintainership file without equivalent git submodule ---"
    )
    packages_in_maintainership: Set[str] = set(maintainer_data.keys())
    submodule_set: Set[str] = set(submodule_list)

    mismatched_packages: List[str] = sorted(
        list(packages_in_maintainership - submodule_set)
    )

    if mismatched_packages:
        logging.info(
            f"Found {len(mismatched_packages)} packages in maintainership file "
            f"without an equivalent git submodule."
        )
        output_file = OUTPUT_FILES["packages_without_submodule"]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(mismatched_packages, f, indent=4, sort_keys=True)
        logging.info(f"Saved packages without submodule to {output_file}")
    else:
        logging.info(
            "No packages found in maintainership file without an equivalent git submodule."
        )


def main() -> None:
    """
    Main function to run the bugownership checker.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    os.makedirs(CACHE_DIR, exist_ok=True)
    logging.info(f"Using cache directory: {CACHE_DIR}")
    slfo_repo_info = GIT_REPOSITORIES.get("SLFO", {})
    sles_repo_info = GIT_REPOSITORIES.get("SLES", {})

    if not slfo_repo_info.get("url") or not sles_repo_info.get("url"):
        logging.error(
            "Git repository URL for SLFO or SLES not found in the configuration file."
        )
        return

    slfo_repo_path = manage_git_repository(
        slfo_repo_info["url"], slfo_repo_info.get("branch", "main"), CACHE_DIR
    )
    sles_repo_path = manage_git_repository(
        sles_repo_info["url"], sles_repo_info.get("branch", "main"), CACHE_DIR
    )
    if not slfo_repo_path or not sles_repo_path:
        logging.error("Failed to clone or update one or more repositories. Aborting.")
        return

    primary_xml_file = download_repo_metadata(sles_repo_info.get("branch"), CACHE_DIR)
    if not primary_xml_file:
        logging.error("Failed to download repo metadata. Aborting.")
        return

    maintainership_file = os.path.join(slfo_repo_path, "_maintainership.json")
    productcompose_file = os.path.join(
        sles_repo_path, "000productcompose/default.productcompose"
    )

    # src_package_list: Set[str] = parse_primary_xml(primary_xml_file)
    src_package_list: Set[str] = parse_primary_xml(primary_xml_file)
    if not src_package_list:
        logging.error("Could not gather any source package data from XML files. Aborting.")
        return

    binary_data_list: List[Tuple[str, str, Optional[str]]] = (
        get_binary_data_from_repo_metadata()
    )
    if not binary_data_list:
        logging.error("Could not gather any package data from XML files. Aborting.")
        return

    if CHECK_BINARIES_NOT_SHIPPED:
        logging.info("--- Running optional check for binaries not shipped ---")
        binary_set_from_compose: Optional[Set[str]] = get_binaries_from_productcompose(
            productcompose_file
        )
        if binary_set_from_compose is not None:
            check_binaries_not_shipped(binary_data_list, binary_set_from_compose)

    submodule_list: List[str] = get_packages_from_git_submodules(slfo_repo_path)
    if not submodule_list:
        logging.error(
            "Could not gather any package data from git submodules. Aborting."
        )
        return

    maintainer_data: Optional[Dict[str, Any]] = get_maintainer_data(maintainership_file)
    if maintainer_data is None:
        return

    check_packages_without_submodule(submodule_list, maintainer_data)

    valid_packages: Optional[Set[str]] = check_invalid_packages(
        src_package_list, submodule_list
    )
    if valid_packages is None:
        logging.error("No valid packages found. Aborting.")
        return

    orphan_packages: Optional[List[str]] = check_orphan_packages(
        valid_packages, maintainer_data
    )
    if orphan_packages is not None:
        if orphan_packages:
            logging.info(f"Found {len(orphan_packages)} orphan packages.")
            with open(OUTPUT_FILES["orphan_packages"], "w", encoding="utf-8") as f:
                json.dump(orphan_packages, f, indent=4, sort_keys=True)
            logging.info(f"Saved orphan packages to {OUTPUT_FILES['orphan_packages']}")
        else:
            logging.info("No orphan packages found.")


if __name__ == "__main__":
    main()
