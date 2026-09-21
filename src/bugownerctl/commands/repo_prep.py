"""SLFO repository preparation helper.

Loads configuration, resolves a product git reference, clones or updates the
SLFO repository, and returns a context object bundling all resolved values.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
        base_url: Optional per-product package-metadata base URL from config;
            None means the repository default URL is used.
    """

    config: dict[str, Any]
    cache_dir: Path
    slfo_repo_path: Path
    git_repo: GitRepository
    base_url: str | None = None


def _resolve_base_url(product_config: dict[str, Any], version: str) -> str | None:
    """Read and validate the optional per-product `base_url` setting.

    Every rejection happens here, before any directory is created or any
    repository cloned, so a bad URL costs nothing but an error message. A
    plain-http value is accepted but warned about: `requests` applies
    `~/.netrc` credentials regardless of scheme, so such a URL would put them
    on the wire in cleartext.

    Args:
        product_config: The product entry from the `products` config list.
        version: Product version string, used to test-expand `{version}`.

    Returns:
        The validated base URL, or None when the key is absent.

    Raises:
        ConfigError: If `base_url` is present but not a string, is empty or
            whitespace-only, does not end with "/", is not an absolute URL, or
            cannot be expanded with `.format(version=...)`.
    """
    if "base_url" not in product_config:
        return None

    base_url = product_config["base_url"]
    if not isinstance(base_url, str):
        raise ConfigError(
            f"Invalid 'base_url' config for version {version}: "
            f"expected URL string, got {type(base_url).__name__}"
        )
    if not base_url.strip():
        raise ConfigError(
            f"Invalid 'base_url' config for version {version}: "
            "empty or whitespace-only string not allowed"
        )
    if not base_url.endswith("/"):
        raise ConfigError(
            f"Invalid 'base_url' config for version {version}: {base_url!r} "
            "must end with '/' because the metadata path is concatenated, not joined"
        )
    parsed = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ConfigError(
            f"Invalid 'base_url' config for version {version}: {base_url!r} "
            "must be an absolute URL with a scheme and a host"
        )
    try:
        base_url.format(version=version)
    except (KeyError, IndexError, ValueError, AttributeError, TypeError) as exc:
        raise ConfigError(
            f"Invalid 'base_url' config for version {version}: {base_url!r} "
            f"is not a usable format string ({exc})"
        ) from exc
    if parsed.scheme.lower() == "http":
        logger.warning(
            "base_url for version %s uses plain http; any ~/.netrc credentials "
            "for that host are sent unencrypted",
            version,
        )
    return base_url


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
        ConfigError: If config file cannot be found, or the product's
                     optional base_url is invalid.
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

    base_url = _resolve_base_url(product_config, version)

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
    return SlfoRepoContext(config, cache_dir, slfo_repo_path, git_repo, base_url)
