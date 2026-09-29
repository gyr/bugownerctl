"""SLFO repository preparation helper.

Loads configuration, resolves a product git reference, validates the SLFO
repository URL, and returns a context object bundling all resolved values.
Nothing is cloned and nothing is created on disk.
"""

import ipaddress
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit

from bugownerctl.exceptions import ConfigError
from bugownerctl.utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlfoRepoContext:
    """Immutable context produced by prepare_slfo_repo.

    Attributes:
        config: Raw configuration dictionary loaded from the config file.
        cache_dir: Resolved (tilde-expanded) cache root path; not created here.
        slfo_git_url: SLFO git remote URL from config, validated as SSH or
            HTTP(S) format.
        ref: The product's configured branch name.
        base_url: Optional per-product package-metadata base URL from config;
            None means the repository default URL is used.
        obs_project: Optional per-product OBS project name from config (e.g.
            "SUSE:SLFO:Main"); None means the key is absent.
    """

    config: dict[str, Any]
    cache_dir: Path
    slfo_git_url: str
    ref: str
    base_url: str | None = None
    obs_project: str | None = None


def _is_ssh_url(url: str) -> bool:
    """Check if URL is SSH format.

    Args:
        url: Repository URL to check

    Returns:
        True if SSH format (user@host:path), False otherwise
    """
    # SSH format: user@host:path/to/repo.git
    # SCP-style URLs don't support port syntax (use ssh:// scheme for that)
    return bool(re.match(r"^[\w\-\.]+@[\w\-\.]+:[\w\-\./]+\.git$", url))


def _is_http_url(url: str) -> bool:
    """Check if URL is HTTP/HTTPS format.

    Args:
        url: Repository URL to check

    Returns:
        True if HTTP/HTTPS format, False otherwise
    """
    # HTTP/HTTPS format: https://host.com/path/repo.git
    return bool(re.match(r"^https?://[\w\-\.]+(:\d+)?/[\w\-\./]+\.git$", url))


def _is_safe_url(url: str) -> bool:
    """Check if URL is safe (not internal network/metadata service).

    Args:
        url: Repository URL to validate

    Returns:
        True if URL is safe, False if it points to internal network

    Raises:
        ValueError: If URL cannot be parsed
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False

        # Block localhost variants
        localhost_names = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        if hostname.lower() in localhost_names:
            return False

        # Block metadata services
        metadata_services = (
            "169.254.169.254",  # AWS/Azure/GCP metadata
            "metadata.google.internal",  # GCP
            "metadata",
        )
        if hostname.lower() in metadata_services:
            return False

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            # Block private IP ranges, loopback, link-local
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            # Not an IP address - it's a domain name, which is OK
            pass

        return True

    except Exception:
        # If we can't parse URL, reject it
        return False


def _resolve_obs_project(product_config: dict[str, Any], version: str) -> str | None:
    """Read and validate the optional per-product `obs_project` setting.

    A non-string or blank value is rejected here, before any command does
    work; the project-name format is checked later by the OBS repository.
    Whether a missing value is an error is decided by the commands that
    need it.

    Args:
        product_config: The product entry from the `products` config list.
        version: Product version string, used in error messages.

    Returns:
        The OBS project name, or None when the key is absent.

    Raises:
        ConfigError: If `obs_project` is present but not a string, or is
            empty or whitespace-only.
    """
    if "obs_project" not in product_config:
        return None

    obs_project = product_config["obs_project"]
    if not isinstance(obs_project, str):
        raise ConfigError(
            f"Invalid 'obs_project' config for version {version}: "
            f"expected OBS project name string, got {type(obs_project).__name__}"
        )
    if not obs_project.strip():
        raise ConfigError(
            f"Invalid 'obs_project' config for version {version}: "
            "empty or whitespace-only string not allowed"
        )
    return obs_project


def _resolve_base_url(product_config: dict[str, Any], version: str) -> str | None:
    """Read and validate the optional per-product `base_url` setting.

    Every rejection happens here, before any command does work, so a bad
    URL costs nothing but an error message. A plain-http value is accepted
    but warned about: `requests` applies `~/.netrc` credentials regardless
    of scheme, so such a URL would put them on the wire in cleartext.

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
    """Load config, resolve product ref, validate the SLFO URL, return context.

    Performs no git operation and creates nothing on disk; SLFO files are
    fetched later by the commands via git archive.

    Args:
        version: Product version string to look up in config (e.g. "16.1").
        config_file: Optional explicit path to config file; None triggers
                     the standard config search hierarchy.

    Returns:
        SlfoRepoContext with all resolved values.

    Raises:
        ValueError: If version not found, the branch is empty, slfo_git_url
                    is absent from config, is neither SSH nor HTTP(S)
                    format, or is an HTTP(S) URL pointing to an internal
                    network or metadata service.
        ConfigError: If config file cannot be found, the product has no
                     branch configured, or the product's optional base_url
                     or obs_project is invalid.
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
    obs_project = _resolve_obs_project(product_config, version)

    if "branch" not in product_config:
        raise ConfigError(
            f"Product config for version {version} has no 'branch' configured. "
            "Commit pins are not supported: git archive serves only branch or tag "
            "names, never a commit SHA; use 'branch:'."
        )
    git_ref = product_config["branch"]
    if not git_ref:
        raise ValueError(f"Empty git ref for version {version}")

    slfo_git_url = config.get("slfo_git_url")
    if not slfo_git_url:
        raise ValueError("slfo_git_url not found in config")

    is_ssh = _is_ssh_url(slfo_git_url)
    is_http = _is_http_url(slfo_git_url)
    if not is_ssh and not is_http:
        raise ValueError(f"Invalid repository URL format: {slfo_git_url}")

    # SSRF protection - only for HTTP/HTTPS
    # SSH URLs can connect to internal hosts - this is expected for internal git servers
    # (SSH protocol cannot access HTTP metadata services like 169.254.169.254)
    if is_http and not _is_safe_url(slfo_git_url):
        raise ValueError(
            f"Repository URL points to internal network or metadata service: {slfo_git_url}"
        )

    return SlfoRepoContext(config, cache_dir, slfo_git_url, git_ref, base_url, obs_project)
