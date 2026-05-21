import logging
import argparse
import gzip
from lxml import etree
import yaml
import requests
import json
import hashlib
import subprocess
from typing import List, Set, Dict, Optional, Any, Union
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum


class RefType(Enum):
    """Enum to represent the type of a git reference."""

    BRANCH = "branch"
    TAG = "tag"
    COMMIT = "commit"


# --- Configuration ---


def load_config(config_file_path: str) -> Dict[str, Any]:
    """Loads a YAML configuration file.

    :param config_file_path: The path to the configuration file.
    :type config_file_path: str
    :raises FileNotFoundError: If the configuration file is not found.
    :raises yaml.YAMLError: If the configuration file is not valid YAML.
    :return: The loaded configuration as a dictionary.
    :rtype: Dict[str, Any]
    """
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file '{config_file_path}' not found.")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Invalid YAML format in '{config_file_path}': {e}")
        raise


config = load_config("validate_maintainership.yaml")

CACHE_DIR = Path(config.get("cache_dir", "~/.cache/bugownership")).expanduser()
BASE_URL = (
    "https://download.suse.de/ibs/SUSE:/SLFO:/Products:/SLES:/{}:/PUBLISH/product/"
)
REPOMD_PATH = "repodata/repomd.xml"
FALSEPOSITIVES_FILE: str = config.get("false_positives_file", "false_positives.json")

# Hardcoded output filenames
OUTPUT_FILES: Dict[str, str] = {
    "shipped_packages_not_in_submodule": "shipped_packages_not_in_submodule.json",
    "orphan_packages": "orphan_packages.json",
    "maintained_packages_without_submodule": "maintained_packages_without_submodule.json",
}


def download_file(
    url: str, destination_folder: Union[str, Path] = ".", filename: Optional[str] = None
) -> str:
    """Downloads a file from a given URL to a specified destination folder.

    :param url: The URL of the file to download.
    :type url: str
    :param destination_folder: The folder where the file will be saved.
        Defaults to the current directory.
    :type destination_folder: Union[str, Path]
    :param filename: The name to save the file as. If None, the filename is
        extracted from the URL.
    :type filename: Optional[str]
    :return: The path to the downloaded file.
    :rtype: str
    :raises requests.exceptions.RequestException: If a download error occurs.
    """
    dest_dir = Path(destination_folder)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = Path(url).name

    destination_path = dest_dir / filename

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
        return str(destination_path)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading the file: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise


def get_file_checksum(
    file_path: Union[str, Path], checksum_type: str = "sha256"
) -> Optional[str]:
    """Calculates the checksum of a file.

    :param file_path: The path to the file.
    :type file_path: Union[str, Path]
    :param checksum_type: The checksum algorithm to use (e.g., 'sha256').
    :type checksum_type: str
    :return: The hexadecimal checksum of the file, or None if the file doesn't exist.
    :rtype: Optional[str]
    """
    path = Path(file_path)
    if not path.exists():
        return None

    hash_func = hashlib.new(checksum_type)
    with path.open("rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            hash_func.update(byte_block)
    return hash_func.hexdigest()


def parse_repomd(file_path: Union[str, Path]) -> Optional[Dict[str, str]]:
    """Parses a repomd.xml file to find the location and checksum of the primary data.

    :param file_path: The path to the repomd.xml file.
    :type file_path: Union[str, Path]
    :return: A dictionary with 'href', 'checksum', and 'checksum_type',
        or None if the 'primary' data element is not found.
    :rtype: Optional[Dict[str, str]]
    :raises etree.ParseError: If the XML file is malformed.
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
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during parsing: {e}")
        raise


def download_repo_metadata(version: str, cache_dir: Path) -> str:
    """Downloads and verifies the primary repository metadata.

    This function handles downloading the `repomd.xml` file, parsing it to
    find the primary XML data, and then downloading the primary XML file itself.
    It uses a cache to avoid re-downloading and verifies file integrity using
    checksums.

    :param version: The SLES version string (e.g., "16.0").
    :type version: str
    :param cache_dir: The root directory for caching downloaded files.
    :type cache_dir: Path
    :return: The local path to the downloaded primary XML file.
    :rtype: str
    :raises RuntimeError: If downloading or parsing metadata fails.
    """
    base_url = BASE_URL.format(version)
    repomd_url = urljoin(base_url, REPOMD_PATH)

    metadata_cache_dir = cache_dir / "repodata" / version

    downloaded_repomd_path = download_file(
        repomd_url, destination_folder=str(metadata_cache_dir), filename="repomd.xml"
    )
    if not downloaded_repomd_path:
        raise RuntimeError(f"Failed to download repomd.xml from {repomd_url}")

    primary_info = parse_repomd(downloaded_repomd_path)
    if not primary_info:
        raise RuntimeError(
            f"Failed to parse primary info from {downloaded_repomd_path}"
        )

    primary_location_href = primary_info["href"]
    expected_checksum = primary_info["checksum"]
    checksum_type = primary_info["checksum_type"]

    logging.info(f"Primary data location from repomd.xml: {primary_location_href}")
    logging.info(f"Expected {checksum_type} checksum: {expected_checksum}")

    primary_filename = Path(primary_location_href).name
    primary_file_path_in_cache = metadata_cache_dir / primary_filename

    existing_checksum = get_file_checksum(
        str(primary_file_path_in_cache), checksum_type
    )

    if existing_checksum == expected_checksum:
        logging.info(
            f"File {primary_filename} already exists in cache and checksum matches. Skipping download."
        )
        return str(primary_file_path_in_cache)
    else:
        if existing_checksum is not None:
            logging.warning(
                f"Checksum mismatch for {primary_filename} in cache. Deleting and re-downloading."
            )
            primary_file_path_in_cache.unlink()

        primary_file_url = urljoin(base_url, primary_location_href)
        logging.info(f"Full URL for primary file: {primary_file_url}")

        downloaded_primary_path = download_file(
            primary_file_url, destination_folder=str(metadata_cache_dir)
        )
        if not downloaded_primary_path:
            raise RuntimeError(
                f"Failed to download primary XML from {primary_file_url}"
            )
        return downloaded_primary_path


def parse_primary_xml(file_path: Union[str, Path], debug: bool) -> Set[str]:
    """Parses a gzipped primary XML file to extract 'src' package names.

    :param file_path: The path to the gzipped primary XML file.
    :type file_path: Union[str, Path]
    :param debug: If True, save the extracted package names to a JSON file.
    :type debug: bool
    :return: A set of package names with 'src' architecture. Returns an
        empty set if the file cannot be parsed.
    :rtype: Set[str]
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
        logging.info(
            f"Successfully extracted {len(unique_packages)} unique 'src' package names"
        )
        if debug:
            output_filename = "src_packages.json"
            with open(output_filename, "w") as f_out:
                json.dump(unique_packages, f_out, indent=4)
            logging.info(f"Saved 'src' package names to {output_filename}")

    except (etree.ParseError, gzip.BadGzipFile) as e:
        logging.error(f"Error parsing or decompressing file: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    return package_names


def manage_git_repository(
    repo_url: str, git_ref: str, cache_dir: Path, ref_type: RefType
) -> str:
    """Clones or updates a Git repository in the cache directory.

    If the repository does not exist, it's cloned. It then checks out the
    specified git reference. If the repository exists and the ref is a
    branch, it's fetched and reset to the latest commit.

    :param repo_url: The URL of the Git repository.
    :type repo_url: str
    :param git_ref: The branch, tag, or commit to checkout.
    :type git_ref: str
    :param cache_dir: The root directory for caching the repository.
    :type cache_dir: Path
    :param ref_type: The type of the git reference.
    :type ref_type: RefType
    :return: The local path to the managed repository.
    :rtype: str
    :raises RuntimeError: If any Git command fails.
    """
    repo_name = Path(repo_url).stem
    repo_path = cache_dir / repo_name

    try:
        if not repo_path.exists():
            logging.info(
                f"--- Cloning {repo_url} with --no-remote-submodules into {repo_path} ---"
            )
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-remote-submodules",
                    repo_url,
                    str(repo_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            logging.info(f"Checking out {ref_type.value} {git_ref}")
            subprocess.run(
                ["git", "checkout", git_ref],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            logging.info(f"--- Updating repository {repo_path} ---")
            if ref_type == RefType.BRANCH:
                # --prune removes remote-tracking refs that no longer exist.
                subprocess.run(
                    ["git", "fetch", "--prune", "origin"],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )

                # Check current branch
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )
                current_ref = result.stdout.strip()
                if current_ref != git_ref:
                    logging.info(f"Switching from {current_ref} to {git_ref}")
                    subprocess.run(
                        ["git", "checkout", git_ref],
                        cwd=str(repo_path),
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                # Reset to remote branch state
                logging.info(
                    f"Updating {repo_path} to latest version of branch {git_ref}"
                )
                subprocess.run(
                    ["git", "reset", "--hard", f"origin/{git_ref}"],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )
            else:
                logging.info(f"Checking out {ref_type.value} {git_ref}")
                subprocess.run(
                    ["git", "checkout", git_ref],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )

        return str(repo_path)

    except subprocess.CalledProcessError as e:
        logging.error(f"Error managing repository {repo_url}: {e.stderr}")
        raise RuntimeError(
            f"Failed to manage git repository {repo_url}: {e.stderr.strip()}"
        ) from e


def get_source_package_from_obs(package: str) -> Optional[str]:
    """Gets the source package from OBS for a given binary package.

    This function queries the SUSE OBS instance to find the corresponding
    source package for a given binary package name within the
    'SUSE:SLFO:Main' project.

    :param package: The name of the binary package.
    :type package: str
    :return: The name of the source package, or None if not found.
    :rtype: Optional[str]
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
    """Executes `git submodule status` in the given directory.

    :param slfo_git_repo_path: The local path to the git repository.
    :type slfo_git_repo_path: str
    :return: The standard output of the `git submodule status` command.
    :rtype: str
    :raises RuntimeError: If the git command fails or 'git' is not found.
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
        raise RuntimeError(f"Git command failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        logging.error(
            " Error: 'git' command not found. Ensure Git is installed and in your PATH."
        )
        raise RuntimeError(
            "'git' command not found. Ensure Git is installed and in your PATH."
        )


def parse_git_submodules(git_output: str) -> List[str]:
    """Parses the output of `git submodule status` to extract submodule names.

    :param git_output: The raw string output from the git command.
    :type git_output: str
    :return: A list of submodule names.
    :rtype: List[str]
    """
    names: List[str] = []
    for line in git_output.splitlines():
        parts: List[str] = line.strip().split()
        if len(parts) >= 2:
            names.append(parts[1])
    return names


def get_packages_from_git_submodules(slfo_git_repo_path: str) -> List[str]:
    """Retrieves a sorted list of submodule names from the Git repository.

    This function orchestrates running `git submodule status` and parsing
    the output to get a clean, sorted list of submodule names.

    :param slfo_git_repo_path: The local path to the git repository.
    :type slfo_git_repo_path: str
    :return: A sorted list of submodule names.
    :rtype: List[str]
    """
    logging.info(f"--- Getting submodule names from {slfo_git_repo_path} ---")
    raw: str = run_git_submodule(slfo_git_repo_path)

    submodule_names = parse_git_submodules(raw)
    submodule_names.sort()

    return submodule_names


def find_shipped_packages_without_submodule(
    packages_from_repo: Set[str], submodule_list: List[str], debug: bool
) -> Set[str]:
    """Checks for shipped packages that are not in the git submodules.

    This function identifies packages that are present in the repository
    metadata but are not declared as git submodules. It consults and updates
    a false positives file and queries OBS for packages that might be
    valid but are just mapped differently.

    :param packages_from_repo: A set of source package names from the repo.
    :type packages_from_repo: Set[str]
    :param submodule_list: A list of declared git submodule names.
    :type submodule_list: List[str]
    :param debug: If True, save the list of packages to a file.
    :type debug: bool
    :return: A set of packages considered valid after checking. This includes
        the original valid packages plus any newly validated ones.
    :rtype: Set[str]
    """
    logging.info("--- Checking for shipped packages not found in git submodules ---")

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

    shipped_not_in_submodule: List[str] = []
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
                    shipped_not_in_submodule.append(package_name)
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

    if shipped_not_in_submodule:
        logging.info(
            f"Found {len(shipped_not_in_submodule)} shipped packages not found in git submodule."
        )
        logging.info("Shipped packages not found in git submodule:")
        for package in sorted(shipped_not_in_submodule):
            logging.info(f"- {package}")
        if debug:
            with open(
                OUTPUT_FILES["shipped_packages_not_in_submodule"], "w", encoding="utf-8"
            ) as f:
                json.dump(sorted(shipped_not_in_submodule), f, indent=4, sort_keys=True)
            logging.info(
                "Saved shipped packages not in submodule to "
                f"{OUTPUT_FILES['shipped_packages_not_in_submodule']}"
            )
    else:
        logging.info("No shipped packages not found in git submodule were found.")

    return valid_packages


def get_maintainer_data(maintainership_file: Union[str, Path]) -> Dict[str, List[str]]:
    """Parses the JSON maintainership file and returns normalized content.

    Expects new format with "packages" key containing package objects.
    Returns normalized format: {"package": ["maintainer1", "maintainer2"]}

    :param maintainership_file: The path to the _maintainership.json file.
    :type maintainership_file: Union[str, Path]
    :return: The normalized maintainer data as a dictionary.
    :rtype: Dict[str, List[str]]
    :raises FileNotFoundError: If the maintainership file is not found.
    :raises json.JSONDecodeError: If the file is not valid JSON.
    :raises KeyError: If the file does not contain the expected 'packages' key.
    """
    logging.info(f"--- Parsing maintainership from {maintainership_file} ---")
    try:
        with open(maintainership_file, "r") as f:
            raw_data: Dict[str, Any] = json.load(f)

        # Extract packages from new format
        packages_data = raw_data.get("packages", {})

        # Normalize: merge users and groups into single list
        maintainer_data: Dict[str, List[str]] = {}
        for pkg, maintainers in packages_data.items():
            users = maintainers.get("users", [])
            groups = maintainers.get("groups", [])
            maintainer_data[pkg] = users + groups

        return maintainer_data
    except FileNotFoundError:
        logging.error(f"Maintainership file not found at '{maintainership_file}'")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format in '{maintainership_file}': {e}")
        raise
    except KeyError as e:
        logging.error(f"Missing expected key in '{maintainership_file}': {e}")
        raise


def check_orphan_packages(
    shipped_packages: Set[str], maintainer_data: Dict[str, List[str]]
) -> List[str]:
    """Checks for shipped packages that do not have a listed maintainer.

    :param shipped_packages: A set of package names considered shipped.
    :type shipped_packages: Set[str]
    :param maintainer_data: The maintainership data dictionary.
    :type maintainer_data: Dict[str, List[str]]
    :return: A sorted list of orphan packages.
    :rtype: List[str]
    """
    logging.info("--- Checking for orphan packages ---")

    orphan_packages: List[str] = sorted(
        [pkg for pkg in shipped_packages if not maintainer_data.get(pkg)]
    )

    return orphan_packages


def find_maintained_packages_without_submodule(
    submodule_list: List[str], maintainer_data: Dict[str, List[str]], debug: bool
) -> None:
    """Finds maintained packages that are not git submodules.

    :param submodule_list: A list of declared git submodule names.
    :type submodule_list: List[str]
    :param maintainer_data: The maintainership data dictionary.
    :type maintainer_data: Dict[str, List[str]]
    :param debug: If True, save the list of packages to a file.
    :type debug: bool
    """
    logging.info("--- Finding maintained packages without equivalent git submodule ---")
    packages_in_maintainership: Set[str] = set(maintainer_data.keys())
    # Filter out any empty strings that might have come from maintainer_data.keys()
    packages_in_maintainership = {pkg for pkg in packages_in_maintainership if pkg}
    submodule_set: Set[str] = set(submodule_list)

    mismatched_packages: List[str] = sorted(
        list(packages_in_maintainership - submodule_set)
    )

    if mismatched_packages:
        logging.info(
            f"Found {len(mismatched_packages)} maintained packages without an equivalent git submodule."
        )
        logging.info("Maintained packages without an equivalent git submodule:")
        for package in mismatched_packages:
            logging.info(f"- {package}")
        if debug:
            output_file = OUTPUT_FILES["maintained_packages_without_submodule"]
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(mismatched_packages, f, indent=4, sort_keys=True)
            logging.info(
                f"Saved maintained packages without submodule to {output_file}"
            )
    else:
        logging.info(
            "No maintained packages without an equivalent git submodule were found."
        )


def main() -> None:
    """Main function to run the bugownership validation process.

    This function orchestrates the entire validation process, from loading
    configuration and downloading metadata to checking for invalid, orphan,
    and mismatched packages.
    """
    parser = argparse.ArgumentParser(
        description="Validate bug ownership and package maintainership."
    )
    parser.add_argument(
        "-v",
        "--version",
        type=str,
        required=True,
        help="SLES version to validate (e.g., '16.1').",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging and output."
    )
    args = parser.parse_args()

    sles_version = args.version
    debug = args.debug

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    CACHE_DIR.mkdir(exist_ok=True)
    logging.info(f"Using cache directory: {CACHE_DIR}")
    slfo_git_url = config.get("slfo_git_url")
    products = config.get("products", [])

    if not slfo_git_url:
        logging.error("slfo_git_url is not set in the configuration file.")
        return

    # Find the product configuration for the specified SLES version
    product_config = None
    for p in products:
        if p.get("version") == sles_version:
            product_config = p
            break

    if not product_config:
        logging.error(
            f"No product configuration found for SLES version: {sles_version}"
        )
        return

    git_ref: str
    ref_type: RefType
    if product_config.get("branch"):
        git_ref = product_config["branch"]
        ref_type = RefType.BRANCH
        logging.info(f"Using git branch: {git_ref}")
    elif product_config.get("tag"):
        git_ref = product_config["tag"]
        ref_type = RefType.TAG
        logging.info(f"Using git tag: {git_ref}")
    elif product_config.get("commit"):
        git_ref = product_config["commit"]
        ref_type = RefType.COMMIT
        logging.info(f"Using git commit: {git_ref}")
    else:
        logging.error(
            f"Neither 'branch', 'tag', nor 'commit' is set for product version {sles_version} in the configuration file."
        )
        return

    slfo_repo_path: str = manage_git_repository(
        slfo_git_url, git_ref, CACHE_DIR, ref_type
    )

    primary_xml_file: str = download_repo_metadata(sles_version, CACHE_DIR)

    maintainership_file = Path(slfo_repo_path) / "_maintainership.json"

    src_package_list: Set[str] = parse_primary_xml(primary_xml_file, args.debug)

    submodule_list: List[str] = get_packages_from_git_submodules(slfo_repo_path)

    maintainer_data: Dict[str, List[str]] = get_maintainer_data(maintainership_file)

    find_maintained_packages_without_submodule(
        submodule_list, maintainer_data, args.debug
    )

    shipped_packages: Set[str] = find_shipped_packages_without_submodule(
        src_package_list, submodule_list, args.debug
    )
    if not shipped_packages:
        logging.error("No shipped packages found. Aborting.")
        return

    orphan_packages: List[str] = check_orphan_packages(
        shipped_packages, maintainer_data
    )
    if orphan_packages:
        logging.info(f"Found {len(orphan_packages)} orphan packages.")
        logging.info("Orphan packages:")
        for package in sorted(orphan_packages):
            logging.info(f"- {package}")
        with open(OUTPUT_FILES["orphan_packages"], "w", encoding="utf-8") as f:
            json.dump(orphan_packages, f, indent=4, sort_keys=True)
        logging.info(f"Saved orphan packages to {OUTPUT_FILES['orphan_packages']}")
    else:
        logging.info("No orphan packages found.")


if __name__ == "__main__":
    # DEPRECATION WARNING
    print("\n" + "=" * 80, file=sys.stderr)
    print("WARNING: This script is DEPRECATED", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print("", file=sys.stderr)
    print("Please use the new unified CLI instead:", file=sys.stderr)
    print("  Old: python validate_maintainership.py -v 16.1", file=sys.stderr)
    print("  New: bugowner validate -v 16.1", file=sys.stderr)
    print("", file=sys.stderr)
    print("Installation: uv pip install -e .", file=sys.stderr)
    print("Help:         bugowner --help", file=sys.stderr)
    print("", file=sys.stderr)
    print("This script will be removed in a future release.", file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)

    main()
