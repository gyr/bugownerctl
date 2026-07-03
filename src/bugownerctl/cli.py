"""CLI entry point for bugownerctl package.

This module provides the command-line interface with subcommands for
init, check, and query subcommands.
"""

import argparse
import logging
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

from bugownerctl.commands import check, init, query


def positive_int(value: str) -> int:
    """Convert string to a positive integer (>= 1) for argparse type validation.

    Args:
        value: String value to convert.

    Returns:
        Integer >= 1.

    Raises:
        argparse.ArgumentTypeError: If the value is < 1.
    """
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser with subcommands.

    Returns:
        Configured ArgumentParser with init, check, and query subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="bugownerctl", description="Bug ownership and package maintainership validation tool"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {pkg_version('bugownerctl')}",
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # bugownerctl init
    init_parser = subparsers.add_parser("init", help="Create initial configuration file")
    init_parser.add_argument(
        "--location",
        choices=["user", "local", "system"],
        default="user",
        help="Config location: user (default), local, or system",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing config")
    init_parser.set_defaults(func=init.run)

    # bugownerctl check
    check_parser = subparsers.add_parser("check", help="Check maintainership and whitelist data")
    check_subparsers = check_parser.add_subparsers(dest="check_command", required=True)

    # check maintainership
    maintainership_parser = check_subparsers.add_parser(
        "maintainership",
        help="Validate maintainership data for inconsistencies and orphan packages",
    )
    maintainership_parser.add_argument(
        "-v", "--version", required=True, help="SLES version (e.g., '16.1')"
    )
    maintainership_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    maintainership_parser.add_argument(
        "--refresh-bulk-map",
        action="store_true",
        default=False,
        help="Force re-fetch of the OBS bulk source-info map, ignoring cached data",
    )
    maintainership_parser.set_defaults(func=check.run_maintainership)

    # check whitelist
    whitelist_parser = check_subparsers.add_parser(
        "whitelist",
        help="Validate that whitelisted packages are NOT shipped",
    )
    whitelist_parser.add_argument(
        "-v", "--version", required=True, help="SLES version (e.g., '16.1')"
    )
    whitelist_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    whitelist_parser.add_argument(
        "--refresh-bulk-map",
        action="store_true",
        default=False,
        help="Force re-fetch of the OBS bulk source-info map, ignoring cached data",
    )
    whitelist_parser.set_defaults(func=check.run_whitelist)

    # check users
    users_parser = check_subparsers.add_parser(
        "users",
        help="Validate that user logins in maintainership file are confirmed OBS accounts",
    )
    users_parser.add_argument("-v", "--version", required=True, help="SLES version (e.g., '16.1')")
    users_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    users_parser.add_argument(
        "--api",
        default="https://api.suse.de",
        help="OBS API URL (default: https://api.suse.de)",
    )
    users_parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=50,
        help="Max logins per OBS API call (default: 50)",
    )
    users_parser.set_defaults(func=check.run_users)

    # bugownerctl query
    query_parser = subparsers.add_parser("query", help="Query package and maintainer information")
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    package_parser = query_subparsers.add_parser(
        "package", help="Check maintainership status of a package"
    )
    package_parser.add_argument("package_name", help="Package name to check")
    package_parser.add_argument(
        "-v", "--version", required=True, help="SLES version (e.g., '16.1')"
    )
    package_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    package_parser.set_defaults(func=query.run_package)

    maintainer_parser = query_subparsers.add_parser(
        "maintainer", help="List packages maintained by a user/group"
    )
    maintainer_parser.add_argument("maintainer_name", help="User or group name")
    maintainer_parser.add_argument(
        "-v", "--version", required=True, help="SLES version (e.g., '16.1')"
    )
    maintainer_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to config file (default: search standard locations)",
    )
    maintainer_parser.set_defaults(func=query.run_maintainer)

    return parser


def _handle_exception(exception: Exception, debug: bool) -> None:
    """Handle exception by printing to stderr with optional traceback.

    Args:
        exception: The exception to handle
        debug: Whether to show full traceback (True) or clean message (False)
    """
    if debug:
        import traceback

        traceback.print_exc()
    else:
        sys.stderr.write(f"ERROR: {exception}\n")


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

    # Route to appropriate command handler with exception handling
    try:
        exit_code: int = args.func(args)
        return exit_code
    except KeyboardInterrupt:
        # User pressed Ctrl+C - exit gracefully
        sys.stderr.write("\nInterrupted\n")
        return 130  # Standard exit code for SIGINT
    except (FileNotFoundError, ValueError) as e:
        # Expected errors - show friendly message
        _handle_exception(e, args.debug)
        return 1
    except Exception as e:
        # Unexpected errors
        _handle_exception(e, args.debug)
        return 1


if __name__ == "__main__":
    sys.exit(main())
