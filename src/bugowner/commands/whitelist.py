"""Whitelist command handler.

Executes whitelist update workflow: compares git submodules with maintainership
file and updates whitelist with packages missing from maintainership.
"""

import argparse
from pathlib import Path

from src.bugowner.repositories.git_repository import GitRepositoryImpl
from src.bugowner.repositories.maintainership_repository import MaintainershipRepositoryImpl
from src.bugowner.services.whitelist_service import WhitelistService
from src.bugowner.utils.config import load_config


def run_update(args: argparse.Namespace) -> int:
    """Execute whitelist update subcommand.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success)
    """
    # Load configuration
    config = load_config() or {}

    # Get paths from config
    maintainership_file_name = config.get("maintainership_file", "_maintainership.json")
    whitelist_file_name = config.get("whitelist_file", "whitelist_maintainership.json")

    # Determine current working directory for relative paths
    cwd = Path.cwd()
    maintainership_file = cwd / maintainership_file_name
    whitelist_file = cwd / whitelist_file_name
    repo_path = cwd  # Assume we're in the repository

    # Create repository implementations
    maintainership_repo = MaintainershipRepositoryImpl()
    git_repo = GitRepositoryImpl()

    # Create whitelist service
    service = WhitelistService(maintainership_repo, git_repo)

    # Execute whitelist update
    result = service.update_whitelist(
        repo_path=repo_path,
        maintainership_file=maintainership_file,
        whitelist_file=whitelist_file,
    )

    # Print results
    if result.added:
        print("\nAdded to whitelist (submodules missing from maintainership):")
        for pkg in result.added:
            print(f"  - {pkg}")

    if result.removed:
        print("\nRemoved from whitelist (no longer needed):")
        for pkg in result.removed:
            print(f"  - {pkg}")

    if result.in_maintainership_not_submodule:
        print("\nIn maintainership but not in submodules:")
        for pkg in result.in_maintainership_not_submodule:
            print(f"  - {pkg}")

    if not result.added and not result.removed and not result.in_maintainership_not_submodule:
        print("\n✅ Whitelist is up to date")

    return 0
