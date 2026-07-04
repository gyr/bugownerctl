"""Query command handlers.

Executes query subcommands for package and maintainer information.
"""

import argparse
import logging

from bugownerctl.commands.repo_prep import prepare_slfo_repo
from bugownerctl.exit_codes import ExitCode
from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugownerctl.services.query_service import PackageStatus, QueryService
from bugownerctl.utils.file_utils import validate_file_within_directory

logger = logging.getLogger(__name__)


def run_package(args: argparse.Namespace) -> int:
    """Execute query package subcommand.

    Args:
        args: Parsed command-line arguments with package_name, version, config

    Returns:
        Exit code (0 = success)
    """
    logger.info("querying package %r...", args.package_name)
    slfo_context = prepare_slfo_repo(args.version, args.config)

    maintainership_file_name = slfo_context.config.get(
        "maintainership_file", "_maintainership.json"
    )
    whitelist_file_name = slfo_context.config.get("whitelist_file", "whitelist_maintainership.json")

    maintainership_file = validate_file_within_directory(
        slfo_context.slfo_repo_path, maintainership_file_name, "Maintainership file"
    )
    whitelist_file = validate_file_within_directory(
        slfo_context.slfo_repo_path, whitelist_file_name, "Whitelist file"
    )

    maintainership_repo = MaintainershipRepositoryImpl()
    service = QueryService(maintainership_repo)
    result = service.check_package_maintainership(
        args.package_name, maintainership_file, whitelist_file
    )

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

    return ExitCode.OK


def run_maintainer(args: argparse.Namespace) -> int:
    """Execute query maintainer subcommand.

    Args:
        args: Parsed command-line arguments with maintainer_name, version, config

    Returns:
        Exit code (0 = success)
    """
    logger.info("querying maintainer %r...", args.maintainer_name)
    slfo_context = prepare_slfo_repo(args.version, args.config)

    maintainership_file_name = slfo_context.config.get(
        "maintainership_file", "_maintainership.json"
    )

    maintainership_file = validate_file_within_directory(
        slfo_context.slfo_repo_path, maintainership_file_name, "Maintainership file"
    )

    maintainership_repo = MaintainershipRepositoryImpl()
    service = QueryService(maintainership_repo)
    packages = service.get_packages_by_maintainer(args.maintainer_name, maintainership_file)

    print(f"\nMaintainer: {args.maintainer_name}")

    if packages:
        print(f"Packages ({len(packages)}):")
        for pkg in packages:
            print(f"  - {pkg}")
    else:
        print("No packages found")

    return ExitCode.OK
