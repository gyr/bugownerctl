"""SLFO repository preparation helper.

Loads configuration, resolves a product git reference, clones or updates the
SLFO repository, and returns a context object bundling all resolved values.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bugownerctl.domain.ref_type import RefType
from bugownerctl.exceptions import ConfigError
from bugownerctl.repositories.git_repository import GitRepository, GitRepositoryImpl
from bugownerctl.utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlfoRepoContext:
    """Immutable context produced by prepare_slfo_repo.

    Attributes:
        config: Raw configuration dictionary loaded from the config file.
        cache_dir: Resolved (tilde-expanded) path used as the git cache root.
        slfo_repo_path: Path to the local SLFO repository clone.
        git_repo: The GitRepository instance used for clone/update operations.
    """

    config: dict[str, Any]
    cache_dir: Path
    slfo_repo_path: Path
    git_repo: GitRepository


def prepare_slfo_repo(version: str, config_file: Path | None) -> SlfoRepoContext:
    """Load config, resolve product ref, clone/update SLFO repo, return context.

    Args:
        version: Product version string to look up in config (e.g. "16.1").
        config_file: Optional explicit path to config file; None triggers
                     the standard config search hierarchy.

    Returns:
        SlfoRepoContext with all resolved values.

    Raises:
        ValueError: If version not found, ref is missing/empty, or
                    slfo_git_url is absent from config.
        ConfigError: If config file cannot be found.
        RuntimeError: If git operations fail.
    """
    logger.info("preparing SLFO repo for version %s", version)
    try:
        config = load_config(config_file) or {}
    except FileNotFoundError as exc:
        raise ConfigError(str(exc)) from exc
    cache_dir = Path(config.get("cache_dir", "~/.cache/bugownerctl")).expanduser()

    products = config.get("products", [])
    product_config = None
    for product in products:
        if product.get("version") == version:
            product_config = product
            break
    if product_config is None:
        raise ValueError(f"Version {version} not found in config")

    if "branch" in product_config:
        git_ref = product_config["branch"]
        ref_type = RefType.BRANCH
    elif "commit" in product_config:
        git_ref = product_config["commit"]
        ref_type = RefType.COMMIT
    else:
        raise ValueError(f"Product config for version {version} has neither branch nor commit")
    if not git_ref:
        raise ValueError(f"Empty git ref for version {version}")

    slfo_git_url = config.get("slfo_git_url")
    if not slfo_git_url:
        raise ValueError("slfo_git_url not found in config")

    git_repo = GitRepositoryImpl()
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("cloning/updating %s at ref %s", slfo_git_url, git_ref)
    slfo_repo_path = git_repo.clone_or_update(
        repo_url=slfo_git_url,
        git_ref=git_ref,
        cache_dir=cache_dir,
        ref_type=ref_type,
    )
    return SlfoRepoContext(config, cache_dir, slfo_repo_path, git_repo)
