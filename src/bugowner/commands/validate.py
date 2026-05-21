"""Validate command handler.

Executes validation workflow: checks for orphan packages, unmaintained submodules,
and packages shipped but not in submodules.
"""

import argparse
from pathlib import Path

from bugowner.repositories.false_positives_repository import FalsePositivesRepositoryImpl
from bugowner.repositories.git_repository import GitRepositoryImpl
from bugowner.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugowner.repositories.obs_repository import ObsRepositoryImpl
from bugowner.repositories.repo_metadata_repository import RepoMetadataRepositoryImpl
from bugowner.services.validation_service import ValidationService
from bugowner.utils.config import load_config


def run(args: argparse.Namespace) -> int:
    """Execute validate subcommand.

    Args:
        args: Parsed command-line arguments (requires version attribute)

    Returns:
        Exit code (0 = success, 1 = validation failures found)
    """
    # Load configuration
    config = load_config() or {}

    # Get paths from config
    cache_dir = Path(config.get("cache_dir", "~/.cache/bugownership")).expanduser()
    maintainership_file_name = config.get("maintainership_file", "_maintainership.json")
    false_positives_file_name = config.get("false_positives_file", "false_positives.json")

    # Determine current working directory for relative paths
    cwd = Path.cwd()
    maintainership_file = cwd / maintainership_file_name
    false_positives_file = cwd / false_positives_file_name
    repo_path = cwd  # Assume we're in the repository

    # Create repository implementations
    maintainership_repo = MaintainershipRepositoryImpl()
    git_repo = GitRepositoryImpl()
    metadata_repo = RepoMetadataRepositoryImpl()
    obs_repo = ObsRepositoryImpl()
    false_positives_repo = FalsePositivesRepositoryImpl()

    # Download and prepare metadata
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_metadata_file = metadata_repo.download_primary_metadata(args.version, cache_dir)

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

    # Print results
    if result.orphan_packages:
        print("\nOrphan packages (no maintainer):")
        for pkg in result.orphan_packages:
            print(f"  - {pkg}")

    if result.unmaintained_submodules:
        print("\nUnmaintained submodules (not in maintainership file):")
        for sub in result.unmaintained_submodules:
            print(f"  - {sub}")

    if result.shipped_not_in_submodule:
        print("\nShipped packages not in submodules:")
        for pkg in result.shipped_not_in_submodule:
            print(f"  - {pkg}")

    if result.new_false_positives:
        print(f"\nDiscovered {len(result.new_false_positives)} new binary→source mappings")

    # Determine exit code
    has_issues = bool(
        result.orphan_packages or result.unmaintained_submodules or result.shipped_not_in_submodule
    )

    if not has_issues:
        print("\n✅ Validation passed: No issues found")
        return 0
    else:
        print("\n❌ Validation failed: Issues found")
        return 1
