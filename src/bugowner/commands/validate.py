"""Validate command handler.

Executes validation workflow: checks for orphan packages, unmaintained submodules,
and packages shipped but not in submodules.
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
from bugowner.utils.config import load_config
from bugowner.utils.file_utils import validate_file_within_directory
from bugowner.utils.seed import (
    FALSE_POSITIVES_CACHE_FILENAME,
    bootstrap_cache_from_seed,
    get_seed_file_path,
)


def run(args: argparse.Namespace) -> int:
    """Execute validate subcommand.

    Args:
        args: Parsed command-line arguments (requires version attribute)

    Returns:
        Exit code (0 = success, 1 = validation failures found)
    """
    # Load configuration - pass explicit config from CLI if provided
    # If args.config is None, load_config() searches standard locations
    config = load_config(args.config) or {}

    # Get paths from config
    cache_dir = Path(config.get("cache_dir", "~/.cache/bugownership")).expanduser()
    maintainership_file_name = config.get("maintainership_file", "_maintainership.json")

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
    maintainership_repo = MaintainershipRepositoryImpl()
    git_repo = GitRepositoryImpl()
    metadata_repo = RepoMetadataRepositoryImpl()
    obs_repo = ObsRepositoryImpl()
    false_positives_repo = FalsePositivesRepositoryImpl()

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

    # Use paths from cloned SLFO repository
    # Validate to prevent path traversal via config
    maintainership_file = validate_file_within_directory(
        slfo_repo_path, maintainership_file_name, "Maintainership file"
    )
    false_positives_file = cache_dir / FALSE_POSITIVES_CACHE_FILENAME
    bootstrap_cache_from_seed(false_positives_file, get_seed_file_path(config))
    repo_path = slfo_repo_path

    # Create validation service
    service = ValidationService(
        maintainership_repo,
        git_repo,
        metadata_repo,
        obs_repo,
        false_positives_repo,
    )

    # Execute validation
    result = service.validate_all(
        maintainership_file=maintainership_file,
        repo_metadata_file=repo_metadata_file,
        false_positives_file=false_positives_file,
        git_dir=repo_path,
    )

    # Print results matching old script format (INFO prefix, SET labels)

    # SET 1: Maintained packages without git submodule
    if result.maintained_packages_without_submodule:
        print(
            f"INFO: Found {len(result.maintained_packages_without_submodule)} "
            "maintained packages without an equivalent git submodule."
        )
        print("INFO: Maintained packages without an equivalent git submodule:")
        for pkg in result.maintained_packages_without_submodule:
            print(f"INFO: - {pkg}")
    else:
        print("INFO: No maintained packages without an equivalent git submodule were found.")

    # SET 3: Shipped packages not found in git submodule
    if result.shipped_not_in_submodule:
        print(
            f"INFO: Found {len(result.shipped_not_in_submodule)} "
            "shipped packages not found in git submodule."
        )
        print("INFO: Shipped packages not found in git submodule:")
        for pkg in result.shipped_not_in_submodule:
            print(f"INFO: - {pkg}")

    # SET 4: Orphan packages
    if result.orphan_packages:
        print(f"INFO: Found {len(result.orphan_packages)} orphan packages.")
        print("INFO: Orphan packages:")
        for pkg in result.orphan_packages:
            print(f"INFO: - {pkg}")
    else:
        print("INFO: No orphan packages found.")

    # New false-positives discovered
    if result.new_false_positives:
        print(f"INFO: Discovered {len(result.new_false_positives)} new binary→source mappings.")

    # Determine exit code
    has_issues = bool(result.orphan_packages or result.shipped_not_in_submodule)

    return 1 if has_issues else 0
