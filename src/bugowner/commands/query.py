"""Query command handlers.

Executes query subcommands for package and maintainer information.
"""

import argparse
from pathlib import Path

from bugowner.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugowner.services.query_service import PackageStatus, QueryService
from bugowner.utils.config import load_config


def run_package(args: argparse.Namespace) -> int:
    """Execute query package subcommand.

    Args:
        args: Parsed command-line arguments with package_name

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

    # Create repository implementation
    maintainership_repo = MaintainershipRepositoryImpl()

    # Create query service
    service = QueryService(maintainership_repo)

    # Execute package query
    result = service.check_package_maintainership(
        args.package_name, maintainership_file, whitelist_file
    )

    # Print results
    print(f"\nPackage: {result.package_name}")

    if result.status == PackageStatus.MAINTAINED:
        print("Status: Maintained")
        print("Maintainers:")
        for maintainer in result.maintainers:
            print(f"  - {maintainer}")
    elif result.status == PackageStatus.WHITELISTED:
        print("Status: Whitelisted")
    else:
        print("Status: Not found")

    return 0


def run_maintainer(args: argparse.Namespace) -> int:
    """Execute query maintainer subcommand.

    Args:
        args: Parsed command-line arguments with maintainer_name

    Returns:
        Exit code (0 = success)
    """
    # Load configuration
    config = load_config() or {}

    # Get paths from config
    maintainership_file_name = config.get("maintainership_file", "_maintainership.json")

    # Determine current working directory for relative paths
    cwd = Path.cwd()
    maintainership_file = cwd / maintainership_file_name

    # Create repository implementation
    maintainership_repo = MaintainershipRepositoryImpl()

    # Create query service
    service = QueryService(maintainership_repo)

    # Execute maintainer query
    packages = service.get_packages_by_maintainer(args.maintainer_name, maintainership_file)

    # Print results
    print(f"\nMaintainer: {args.maintainer_name}")

    if packages:
        print(f"Packages ({len(packages)}):")
        for pkg in packages:
            print(f"  - {pkg}")
    else:
        print("No packages found")

    return 0
