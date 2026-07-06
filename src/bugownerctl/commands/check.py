"""Check command handlers.

Executes check subcommands for maintainership validation and whitelist verification.
"""

import argparse
import logging
from importlib.resources import as_file, files

from bugownerctl.commands.repo_prep import prepare_slfo_repo
from bugownerctl.exit_codes import ExitCode
from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugownerctl.repositories.name_overrides_repository import NameOverridesRepositoryImpl
from bugownerctl.repositories.obs_bulk_source_info_repository import (
    ObsBulkSourceInfoRepositoryImpl,
)
from bugownerctl.repositories.obs_person_repository import ObsPersonRepositoryImpl
from bugownerctl.repositories.repo_metadata_repository import RepoMetadataRepositoryImpl
from bugownerctl.services.user_validation_service import UserValidationService
from bugownerctl.services.validation_service import ValidationService
from bugownerctl.services.whitelist_service import WhitelistService
from bugownerctl.utils.file_utils import validate_file_within_directory

logger = logging.getLogger(__name__)


def run_maintainership(args: argparse.Namespace) -> int:
    """Execute check maintainership subcommand.

    Args:
        args: Parsed command-line arguments (requires version attribute)

    Returns:
        Exit code (0 = no issues, 2 = gating findings found)
    """
    slfo_context = prepare_slfo_repo(args.release, args.config)

    maintainership_file_name = slfo_context.config.get(
        "maintainership_file", "_maintainership.json"
    )

    maintainership_repo = MaintainershipRepositoryImpl()
    metadata_repo = RepoMetadataRepositoryImpl()
    bulk_map_repo = ObsBulkSourceInfoRepositoryImpl()
    overrides_repo = NameOverridesRepositoryImpl()

    repo_metadata_file = metadata_repo.download_primary_metadata(
        args.release, slfo_context.cache_dir
    )

    maintainership_file = validate_file_within_directory(
        slfo_context.slfo_repo_path, maintainership_file_name, "Maintainership file"
    )

    service = ValidationService(
        maintainership_repo,
        slfo_context.git_repo,
        metadata_repo,
        bulk_map_repo=bulk_map_repo,
        overrides_repo=overrides_repo,
    )

    overrides_resource = files("bugownerctl.data").joinpath("false_positives_overrides.json")
    with as_file(overrides_resource) as overrides_file:
        result = service.validate_all(
            maintainership_file=maintainership_file,
            repo_metadata_file=repo_metadata_file,
            overrides_file=overrides_file,
            cache_dir=slfo_context.cache_dir,
            git_dir=slfo_context.slfo_repo_path,
            force_refresh=args.refresh_bulk_map,
        )

    # SET 1: Maintained packages without git submodule (count → stdout; list → stderr)
    if result.maintained_packages_without_submodule:
        print(
            f"Found {len(result.maintained_packages_without_submodule)} "
            "maintained packages without an equivalent git submodule."
        )
        logger.info("Maintained packages without an equivalent git submodule:")
        for pkg in result.maintained_packages_without_submodule:
            logger.info("- %s", pkg)

    # SET 3: Shipped packages not found in git submodule (count → stdout; list → stderr)
    if result.shipped_not_in_submodule:
        print(
            f"Found {len(result.shipped_not_in_submodule)} "
            "shipped packages not found in git submodule."
        )
        logger.info("Shipped packages not found in git submodule:")
        for pkg in result.shipped_not_in_submodule:
            logger.info("- %s", pkg)

    # SET 3b: Names with no source mapping (count → stdout; list → stderr)
    if result.unresolved_names:
        print(
            f"Found {len(result.unresolved_names)} "
            "names with no source mapping (neither in overrides nor bulk_map)."
        )
        logger.info("Names with no source mapping:")
        for pkg in result.unresolved_names:
            logger.info("- %s", pkg)

    # SET 4: Orphan packages (gating — all on stdout)
    if result.orphan_packages:
        print(f"Found {len(result.orphan_packages)} orphan packages.")
        print("Orphan packages:")
        for pkg in result.orphan_packages:
            print(f"- {pkg}")
    else:
        print("No orphan packages found.")

    # Determine exit code
    gate = bool(result.orphan_packages)
    if args.strict:
        gate = gate or bool(
            result.shipped_not_in_submodule
            or result.unresolved_names
            or result.maintained_packages_without_submodule
        )
    return ExitCode.ISSUES if gate else ExitCode.OK


def run_whitelist(args: argparse.Namespace) -> int:
    """Execute check whitelist subcommand.

    Args:
        args: Parsed command-line arguments (requires version attribute)

    Returns:
        Exit code (0 = no issues, 2 = gating findings found)
    """
    slfo_context = prepare_slfo_repo(args.release, args.config)

    whitelist_file_name = slfo_context.config.get("whitelist_file", "whitelist_maintainership.json")

    maintainership_repo = MaintainershipRepositoryImpl()
    metadata_repo = RepoMetadataRepositoryImpl()
    bulk_map_repo = ObsBulkSourceInfoRepositoryImpl()
    overrides_repo = NameOverridesRepositoryImpl()

    validation_service = ValidationService(
        maintainership_repo,
        slfo_context.git_repo,
        metadata_repo,
        bulk_map_repo=bulk_map_repo,
        overrides_repo=overrides_repo,
    )
    whitelist_service = WhitelistService(validation_service)

    repo_metadata_file = metadata_repo.download_primary_metadata(
        args.release, slfo_context.cache_dir
    )

    shipped_packages = metadata_repo.parse_source_packages(repo_metadata_file)
    submodules = slfo_context.git_repo.list_submodules(slfo_context.slfo_repo_path)

    # Use paths from cloned SLFO repository (whitelist) and cache_dir (XDG)
    # Validate to prevent path traversal via config
    whitelist_file = validate_file_within_directory(
        slfo_context.slfo_repo_path, whitelist_file_name, "Whitelist file"
    )

    # Resolve the shipped overrides JSON via importlib.resources so it
    # works whether the package is installed as a wheel or run from source.
    overrides_resource = files("bugownerctl.data").joinpath("false_positives_overrides.json")
    with as_file(overrides_resource) as overrides_file:
        result = whitelist_service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages=shipped_packages,
            submodules=submodules,
            overrides_file=overrides_file,
            cache_dir=slfo_context.cache_dir,
            force_refresh=args.refresh_bulk_map,
        )

    # Names with no source mapping (mirrors validate command's SET 3b).
    # Unresolved names (count → stdout; list → stderr)
    if result.unresolved_names:
        print(
            f"Found {len(result.unresolved_names)} "
            "names with no source mapping (neither in overrides nor bulk_map)."
        )
        logger.info("Names with no source mapping:")
        for pkg in result.unresolved_names:
            logger.info("- %s", pkg)

    # Final verdict — printed last so it remains the takeaway line of output.
    if result.inconsistent_packages:
        print(
            f"Found {len(result.inconsistent_packages)} "
            "packages that are BOTH shipped AND whitelisted (inconsistency)."
        )
        print("Inconsistent packages (should NOT be shipped if whitelisted):")
        for pkg in result.inconsistent_packages:
            print(f"- {pkg}")
    else:
        print("No inconsistencies found. All whitelisted packages are NOT shipped.")

    # Determine exit code
    gate = bool(result.inconsistent_packages)
    if args.strict:
        gate = gate or bool(result.unresolved_names)
    return ExitCode.ISSUES if gate else ExitCode.OK


def run_users(args: argparse.Namespace) -> int:
    """Execute check users subcommand.

    Args:
        args: Parsed command-line arguments (requires version, config, api, batch_size).

    Returns:
        Exit code (0 = all confirmed, 2 = any invalid or not found).
    """
    slfo_context = prepare_slfo_repo(args.release, args.config)
    maintainership_file_name = slfo_context.config.get(
        "maintainership_file", "_maintainership.json"
    )
    maintainership_file = validate_file_within_directory(
        slfo_context.slfo_repo_path, maintainership_file_name, "Maintainership file"
    )

    maintainership_repo = MaintainershipRepositoryImpl()
    person_repo = ObsPersonRepositoryImpl()
    service = UserValidationService(maintainership_repo, person_repo)

    result = service.validate(maintainership_file, args.api, args.batch_size)

    if result.confirmed:
        print(f"Found {len(result.confirmed)} confirmed OBS accounts.")
        logger.info("Confirmed accounts:")
        for login in result.confirmed:
            logger.info("- %s", login)
    if result.invalid:
        print(f"Found {len(result.invalid)} invalid (locked / non-confirmed) accounts.")
        print("Invalid accounts:")
        for login in result.invalid:
            print(f"- {login}")
    if result.not_found:
        print(f"Found {len(result.not_found)} accounts not found in OBS.")
        print("Accounts not found in OBS:")
        for login in result.not_found:
            print(f"- {login}")
    total = len(result.confirmed) + len(result.invalid) + len(result.not_found)
    not_ok = len(result.invalid) + len(result.not_found)
    if result.invalid or result.not_found:
        print(f"{not_ok} of {total} users are not confirmed OBS accounts.")
    else:
        print(f"All {total} users are confirmed OBS accounts.")

    return ExitCode.ISSUES if (result.invalid or result.not_found) else ExitCode.OK
