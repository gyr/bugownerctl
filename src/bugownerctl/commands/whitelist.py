"""Whitelist check command handler.

Validates that whitelisted packages are NOT shipped by comparing
whitelist against validated shipped packages from repository metadata.
"""

import argparse
from importlib.resources import as_file, files

from bugownerctl.commands.repo_prep import prepare_slfo_repo
from bugownerctl.repositories.maintainership_repository import MaintainershipRepositoryImpl
from bugownerctl.repositories.name_overrides_repository import NameOverridesRepositoryImpl
from bugownerctl.repositories.obs_bulk_source_info_repository import (
    ObsBulkSourceInfoRepositoryImpl,
)
from bugownerctl.repositories.repo_metadata_repository import RepoMetadataRepositoryImpl
from bugownerctl.services.validation_service import ValidationService
from bugownerctl.services.whitelist_service import WhitelistService
from bugownerctl.utils.file_utils import validate_file_within_directory


def run(args: argparse.Namespace) -> int:
    """Execute whitelist-check subcommand.

    Args:
        args: Parsed command-line arguments (requires version attribute)

    Returns:
        Exit code (0 = no issues, 1 = inconsistencies found)
    """
    slfo_context = prepare_slfo_repo(args.version, args.config)

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
        args.version, slfo_context.cache_dir
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
    if result.unresolved_names:
        print(
            f"INFO: Found {len(result.unresolved_names)} "
            "names with no source mapping (neither in overrides nor bulk_map)."
        )
        print("INFO: Names with no source mapping:")
        for pkg in result.unresolved_names:
            print(f"INFO: - {pkg}")

    # Final verdict — printed last so it remains the takeaway line of output.
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

    # Determine exit code
    has_issues = bool(result.inconsistent_packages)

    return 1 if has_issues else 0
