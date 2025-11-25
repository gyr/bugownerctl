import logging
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

# --- Configuration ---


def load_config(config_file_path: str) -> Dict[str, Any]:
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
DEBUG: bool = config.get("debug", False)

# Namespaces for XML parsing
NSMAP: Dict[str, str] = {
    "common": "http://linux.duke.edu/metadata/common",
    "rpm": "http://linux.duke.edu/metadata/rpm",
}
COMMON_NS_URI: str = NSMAP["common"]

# Hardcoded output filenames
OUTPUT_FILES: Dict[str, str] = {
    "missing_packages_in_maintainership": "missing_packages_in_maintainership.json",
    "invalid_packages": "invalid_packages.json",
    "orphan_packages": "orphan_packages.json",
    "packages_without_submodule": "packages_without_submodule.json",
}


def download_file(
    url: str, destination_folder: Union[str, Path] = ".", filename: Optional[str] = None
) -> Optional[str]:
    """
    Downloads a file from a given URL to a specified destination folder.

    Args:
        url (str): The URL of the file to download.
        destination_folder (Union[str, Path]): The folder where the file will be saved.
                                 Defaults to the current directory.
        filename (str, optional): The name to save the file as. If None,
                                  the filename is extracted from the URL.
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
    """
    Calculates the checksum of a file.

    Args:
        file_path (Union[str, Path]): The path to the file.
        checksum_type (str): The checksum algorithm to use (e.g., 'sha256').

    Returns:
        str: The hexadecimal checksum of the file, or None if the file doesn't exist.
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


def parse_repomd(file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    Parses a repomd.xml file to find the location and checksum of the primary data.

    Args:
        file_path (Union[str, Path]): The path to the repomd.xml file.

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
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during parsing: {e}")
        raise


def download_repo_metadata(version: str, cache_dir: Path) -> str:
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


def parse_primary_xml(file_path: Union[str, Path]) -> Set[str]:
    """
    Parses a gzipped primary XML file to extract package names with 'src' architecture.

    Args:
        file_path (Union[str, Path]): The path to the gzipped primary XML file.
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
        if DEBUG:
            output_filename = "src_packages.json"
            with open(output_filename, "w") as f_out:
                json.dump(unique_packages, f_out, indent=4)
            logging.info(f"Saved 'src' package names to {output_filename}")

    except (etree.ParseError, gzip.BadGzipFile) as e:
        logging.error(f"Error parsing or decompressing file: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    return package_names


def manage_git_repository(repo_url: str, branch: str, cache_dir: Path) -> str:
    """
    Clones or updates a Git repository in the cache directory.
    """
    repo_name = Path(repo_url).stem
    repo_path = cache_dir / repo_name

    try:
        if not repo_path.exists():
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
                    str(repo_path),
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
            current_branch = result.stdout.strip()
            if current_branch != branch:
                logging.info(f"Switching branch from {current_branch} to {branch}")
                subprocess.run(
                    ["git", "checkout", branch],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )

            # Reset to remote branch state
            logging.info(f"Updating {repo_path} to latest version of branch {branch}")
            subprocess.run(
                ["git", "reset", "--hard", f"origin/{branch}"],
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
        raise RuntimeError(f"Git command failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        logging.error(
            " Error: 'git' command not found. Ensure Git is installed and in your PATH."
        )
        raise RuntimeError(
            "'git' command not found. Ensure Git is installed and in your PATH."
        )


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
    raw: str = run_git_submodule(slfo_git_repo_path)

    submodule_names = parse_git_submodules(raw)
    submodule_names.sort()

    return submodule_names


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
        if DEBUG:
            with open(OUTPUT_FILES["invalid_packages"], "w", encoding="utf-8") as f:
                json.dump(sorted(invalid_packages), f, indent=4, sort_keys=True)
            logging.info(
                f"Saved invalid packages to {OUTPUT_FILES['invalid_packages']}"
            )
    else:
        logging.info("No invalid packages found.")

    return valid_packages


def get_maintainer_data(maintainership_file: Union[str, Path]) -> Dict[str, Any]:
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
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format in '{maintainership_file}': {e}")
        raise


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
        if DEBUG:
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
    CACHE_DIR.mkdir(exist_ok=True)
    logging.info(f"Using cache directory: {CACHE_DIR}")
    slfo_repo_info = config.get("slfo_git_repository", {})
    sles_version = config.get("sles_version")

    if not slfo_repo_info.get("url") or not sles_version:
        raise ValueError(
            "slfo_git_repository URL not found or sles_version is not set in the configuration file."
        )

    slfo_repo_path: str = manage_git_repository(
        slfo_repo_info["url"], slfo_repo_info.get("branch", "main"), CACHE_DIR
    )

    primary_xml_file: str = download_repo_metadata(sles_version, CACHE_DIR)

    maintainership_file = Path(slfo_repo_path) / "_maintainership.json"

    src_package_list: Set[str] = parse_primary_xml(primary_xml_file)

    submodule_list: List[str] = get_packages_from_git_submodules(slfo_repo_path)

    maintainer_data: Dict[str, Any] = get_maintainer_data(maintainership_file)

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
