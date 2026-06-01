"""Whitelist check command handler.

Validates that whitelisted packages are NOT shipped by comparing
whitelist against validated shipped packages from repository metadata.
"""

import argparse
from pathlib import Path

from bugowner.domain.ref_type import RefType
from bugowner.repositories.false_positives_repository import FalsePositivesRepositoryImpl
from bugowner.repositories.git_repository import GitRepositoryImpl
from bugowner.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugowner.repositories.obs_repository import ObsRepositoryImpl
from bugowner.repositories.repo_metadata_repository import RepoMetadataRepositoryImpl
from bugowner.services.validation_service import ValidationService
from bugowner.services.whitelist_service import WhitelistService
from bugowner.utils.config import load_config
from bugowner.utils.file_utils import validate_file_within_directory
from bugowner.utils.seed import (
    FALSE_POSITIVES_CACHE_FILENAME,
    bootstrap_cache_from_seed,
    get_seed_file_path,
)


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
    cache_dir = Path(config.get("cache_dir", "~/.cache/bugownership")).expanduser()
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
    obs_repo = ObsRepositoryImpl()
    false_positives_repo = FalsePositivesRepositoryImpl()
    maintainership_repo = MaintainershipRepositoryImpl()

    # Create validation service
    validation_service = ValidationService(
        maintainership_repo,
        git_repo,
        metadata_repo,
        obs_repo,
        false_positives_repo,
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

    # Use paths from cloned SLFO repository (whitelist) and current directory (cache)
    # Validate to prevent path traversal via config
    whitelist_file = validate_file_within_directory(
        slfo_repo_path, whitelist_file_name, "Whitelist file"
    )
    false_positives_file = cache_dir / FALSE_POSITIVES_CACHE_FILENAME
    bootstrap_cache_from_seed(false_positives_file, get_seed_file_path(config))

    # Execute whitelist check
    result = whitelist_service.check_whitelist(
        whitelist_file=whitelist_file,
        shipped_packages=shipped_packages,
        submodules=submodules,
        false_positives_file=false_positives_file,
    )

    # Print results (INFO prefix, matching validate format)
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

    # New false-positives discovered
    if result.new_false_positives:
        print(f"INFO: Discovered {len(result.new_false_positives)} new binary→source mappings.")

    # Determine exit code
    has_issues = bool(result.inconsistent_packages)

    return 1 if has_issues else 0
