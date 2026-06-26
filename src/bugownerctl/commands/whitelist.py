"""Whitelist check command handler.

Validates that whitelisted packages are NOT shipped by comparing
whitelist against validated shipped packages from repository metadata.
"""

import argparse
from importlib.resources import as_file, files
from pathlib import Path

from bugownerctl.domain.ref_type import RefType
from bugownerctl.repositories.git_repository import GitRepositoryImpl
from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugownerctl.repositories.name_overrides_repository import NameOverridesRepositoryImpl
from bugownerctl.repositories.obs_bulk_source_info_repository import (
    ObsBulkSourceInfoRepositoryImpl,
)
from bugownerctl.repositories.repo_metadata_repository import RepoMetadataRepositoryImpl
from bugownerctl.services.validation_service import ValidationService
from bugownerctl.services.whitelist_service import WhitelistService
from bugownerctl.utils.config import load_config
from bugownerctl.utils.file_utils import validate_file_within_directory


def run(args: argparse.Namespace) -> int:
    """Execute whitelist-check subcommand.

    Args:
        args: Parsed command-line arguments (requires version attribute)

    Returns:
        Exit code (0 = no issues, 1 = inconsistencies found)
    """
    # Load configuration - pass explicit config from CLI if provided
    # If args.config is None, load_config() searches standard locations
    config = load_config(args.config) or {}

    # Get paths from config
    cache_dir = Path(config.get("cache_dir", "~/.cache/bugownerctl")).expanduser()
    whitelist_file_name = config.get("whitelist_file", "whitelist_maintainership.json")

    # Find product config for requested version
    products = config.get("products", [])
    product_config = None
    for product in products:
        if product.get("version") == args.version:
            product_config = product
            break

    if not product_config:
        raise ValueError(f"Version {args.version} not found in config")

    # Determine git ref and ref type
    if "branch" in product_config:
        git_ref = product_config["branch"]
        ref_type = RefType.BRANCH
    elif "commit" in product_config:
        git_ref = product_config["commit"]
        ref_type = RefType.COMMIT
    else:
        raise ValueError(f"Product config for version {args.version} has neither branch nor commit")

    # Validate git ref is not empty or None
    if not git_ref:
        raise ValueError(f"Empty git ref for version {args.version}")

    # Get SLFO git URL from config
    slfo_git_url = config.get("slfo_git_url")
    if not slfo_git_url:
        raise ValueError("slfo_git_url not found in config")

    # Create repository implementations
    git_repo = GitRepositoryImpl()
    metadata_repo = RepoMetadataRepositoryImpl()
    bulk_map_repo = ObsBulkSourceInfoRepositoryImpl()
    overrides_repo = NameOverridesRepositoryImpl()
    maintainership_repo = MaintainershipRepositoryImpl()

    # Create validation service
    validation_service = ValidationService(
        maintainership_repo,
        git_repo,
        metadata_repo,
        bulk_map_repo=bulk_map_repo,
        overrides_repo=overrides_repo,
    )

    # Create whitelist service
    whitelist_service = WhitelistService(validation_service)

    # Download and prepare metadata
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_metadata_file = metadata_repo.download_primary_metadata(args.version, cache_dir)

    # Clone or update SLFO repository
    slfo_repo_path = git_repo.clone_or_update(
        repo_url=slfo_git_url,
        git_ref=git_ref,
        cache_dir=cache_dir,
        ref_type=ref_type,
    )

    # Parse shipped packages and get submodules
    shipped_packages = metadata_repo.parse_source_packages(repo_metadata_file)
    submodules = git_repo.list_submodules(slfo_repo_path)

    # Use paths from cloned SLFO repository (whitelist) and cache_dir (XDG)
    # Validate to prevent path traversal via config
    whitelist_file = validate_file_within_directory(
        slfo_repo_path, whitelist_file_name, "Whitelist file"
    )

    # Resolve the shipped overrides JSON via importlib.resources so it
    # works whether the package is installed as a wheel or run from source.
    overrides_resource = files("bugownerctl.data").joinpath("false_positives_overrides.json")
    with as_file(overrides_resource) as overrides_file:
        # Execute whitelist check
        result = whitelist_service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages=shipped_packages,
            submodules=submodules,
            overrides_file=overrides_file,
            cache_dir=cache_dir,
            force_refresh=args.refresh_bulk_map,
        )

    # Names with no source mapping (mirrors validate command's SET 3b).
    if result.unresolved_names:
        print(
            f"INFO: Found {len(result.unresolved_names)} "
            "names with no source mapping (neither in overrides nor bulk_map)."
        )
        print("INFO: Names with no source mapping:")
        for pkg in result.unresolved_names:
            print(f"INFO: - {pkg}")

    # Final verdict — printed last so it remains the takeaway line of output.
    if result.inconsistent_packages:
        print(
            f"INFO: Found {len(result.inconsistent_packages)} "
            "packages that are BOTH shipped AND whitelisted (inconsistency)."
        )
        print("INFO: Inconsistent packages (should NOT be shipped if whitelisted):")
        for pkg in result.inconsistent_packages:
            print(f"INFO: - {pkg}")
    else:
        print("INFO: No inconsistencies found. All whitelisted packages are NOT shipped.")

    # Determine exit code
    has_issues = bool(result.inconsistent_packages)

    return 1 if has_issues else 0
