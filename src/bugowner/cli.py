"""CLI entry point for bugowner package.

This module provides the command-line interface with subcommands for
validating maintainership data, managing whitelists, and querying packages.
"""

import argparse
import logging
import sys

from bugowner.commands import query, validate, whitelist


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser with subcommands.

    Returns:
        Configured ArgumentParser with validate, whitelist, and query subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="bugowner", description="Bug ownership and package maintainership validation tool"
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # bugowner validate
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate maintainership data for inconsistencies and orphan packages",
    )
    validate_parser.add_argument(
        "-v", "--version", required=True, help="SLES version (e.g., '16.1')"
    )
    validate_parser.set_defaults(func=validate.run)

    # bugowner whitelist
    whitelist_parser = subparsers.add_parser("whitelist", help="Manage whitelist file")
    whitelist_subparsers = whitelist_parser.add_subparsers(dest="whitelist_command", required=True)
    update_parser = whitelist_subparsers.add_parser(
        "update", help="Update whitelist with missing submodules"
    )
    update_parser.set_defaults(func=whitelist.run_update)

    # bugowner query
    query_parser = subparsers.add_parser("query", help="Query package and maintainer information")
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    package_parser = query_subparsers.add_parser(
        "package", help="Check maintainership status of a package"
    )
    package_parser.add_argument("package_name", help="Package name to check")
    package_parser.set_defaults(func=query.run_package)

    maintainer_parser = query_subparsers.add_parser(
        "maintainer", help="List packages maintained by a user/group"
    )
    maintainer_parser.add_argument("maintainer_name", help="User or group name")
    maintainer_parser.set_defaults(func=query.run_maintainer)

    return parser


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    parser = create_parser()
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Route to appropriate command handler
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
