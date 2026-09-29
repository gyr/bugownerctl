"""Query command handlers.

Executes query subcommands for package and maintainer information.
"""

import argparse
import logging

from bugownerctl.commands.product_context import resolve_product_context
from bugownerctl.exit_codes import ExitCode
from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugownerctl.repositories.remote_archive_repository import (
    FileNotFoundAtRefError,
    RemoteArchiveRepository,
    RemoteArchiveRepositoryImpl,
)
from bugownerctl.services.query_service import PackageStatus, QueryService

logger = logging.getLogger(__name__)


def run_package(
    args: argparse.Namespace, archive_repo: RemoteArchiveRepository | None = None
) -> int:
    """Execute query package subcommand.

    Args:
        args: Parsed command-line arguments with package_name, version, config
        archive_repo: Injection seam for tests; a RemoteArchiveRepositoryImpl is
            constructed when omitted, since argparse calls the handler with the
            namespace alone.

    Returns:
        Exit code (0 = success)

    Raises:
        ValueError: From the archive fetch, if the configured maintainership file
            is absent at the product ref, or if either fetch fails for any other
            operator-input reason. A whitelist absent at the ref is not an error:
            the query runs without one.
    """
    logger.info("querying package %r...", args.package_name)
    product_context = resolve_product_context(args.release, args.config)

    maintainership_file_name = product_context.config.get(
        "maintainership_file", "_maintainership.json"
    )
    whitelist_file_name = product_context.config.get(
        "whitelist_file", "whitelist_maintainership.json"
    )
    repo = archive_repo if archive_repo is not None else RemoteArchiveRepositoryImpl()

    maintainership_content = repo.fetch_file(
        product_context.slfo_git_url, product_context.ref, maintainership_file_name
    )
    whitelist_content: bytes | None
    try:
        whitelist_content = repo.fetch_file(
            product_context.slfo_git_url, product_context.ref, whitelist_file_name
        )
    except FileNotFoundAtRefError:
        whitelist_content = None

    maintainership_repo = MaintainershipRepositoryImpl()
    service = QueryService(maintainership_repo)
    result = service.check_package_maintainership(
        args.package_name, maintainership_content, whitelist_content
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


def run_maintainer(
    args: argparse.Namespace, archive_repo: RemoteArchiveRepository | None = None
) -> int:
    """Execute query maintainer subcommand.

    Args:
        args: Parsed command-line arguments with maintainer_name, version, config
        archive_repo: Injection seam for tests; a RemoteArchiveRepositoryImpl is
            constructed when omitted, since argparse calls the handler with the
            namespace alone.

    Returns:
        Exit code (0 = success)

    Raises:
        ValueError: From the archive fetch, if the configured maintainership file
            is absent at the product ref.
    """
    logger.info("querying maintainer %r...", args.maintainer_name)
    product_context = resolve_product_context(args.release, args.config)

    maintainership_file_name = product_context.config.get(
        "maintainership_file", "_maintainership.json"
    )
    repo = archive_repo if archive_repo is not None else RemoteArchiveRepositoryImpl()

    maintainership_content = repo.fetch_file(
        product_context.slfo_git_url, product_context.ref, maintainership_file_name
    )

    maintainership_repo = MaintainershipRepositoryImpl()
    service = QueryService(maintainership_repo)
    packages = service.get_packages_by_maintainer(args.maintainer_name, maintainership_content)

    print(f"\nMaintainer: {args.maintainer_name}")

    if packages:
        print(f"Packages ({len(packages)}):")
        for pkg in packages:
            print(f"  - {pkg}")
    else:
        print("No packages found")

    return ExitCode.OK
