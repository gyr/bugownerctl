"""Git repository operations.

This module provides GitRepository for managing git operations including
listing submodules and cloning/updating repositories.
"""

import ipaddress
import logging
import re
import subprocess
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from ..domain.ref_type import RefType


class GitRepository(Protocol):
    """Interface for git operations."""

    def list_submodules(self, repo_path: Path) -> list[str]:
        """Get list of git submodule names."""
        ...

    def clone_or_update(
        self,
        repo_url: str,
        git_ref: str,
        cache_dir: Path,
        ref_type: RefType,
    ) -> Path:
        """Clone repository or update existing clone."""
        ...


class GitRepositoryImpl:
    """Concrete implementation of GitRepository."""

    def _is_safe_url(self, url: str) -> bool:
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

    def _run_git_command(
        self, args: list[str], cwd: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run git command with standard error handling.

        Args:
            args: Git command arguments (e.g., ["git", "clone", "..."])
            cwd: Working directory for command (optional)

        Returns:
            CompletedProcess from subprocess.run

        Raises:
            RuntimeError: If git command fails or git not found
        """
        try:
            return subprocess.run(
                args,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            cmd_str = " ".join(args)
            cwd_str = f" in {cwd}" if cwd else ""
            raise RuntimeError(
                f"Git command failed{cwd_str}: {cmd_str}\n"
                f"Exit code: {e.returncode}\n"
                f"Stderr: {e.stderr.strip()}"
            ) from e
        except FileNotFoundError as e:
            raise RuntimeError(
                "'git' command not found. Ensure Git is installed and in your PATH."
            ) from e

    def list_submodules(self, repo_path: Path) -> list[str]:
        """Get list of git submodule names.

        Args:
            repo_path: Path to git repository

        Returns:
            Sorted list of submodule names

        Raises:
            RuntimeError: If git command fails or git not found
        """
        try:
            result = subprocess.run(
                ["git", "submodule", "status"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(repo_path),
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Git command failed in {repo_path}: git submodule status\n"
                    f"Exit code: {result.returncode}\n"
                    f"Stderr: {result.stderr.strip()}"
                )

            # Parse output: each line has format " <hash> <name> (<ref>)"
            names: list[str] = []
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    names.append(parts[1])

            return sorted(names)

        except FileNotFoundError as e:
            raise RuntimeError(
                "'git' command not found. Ensure Git is installed and in your PATH."
            ) from e

    def clone_or_update(
        self,
        repo_url: str,
        git_ref: str,
        cache_dir: Path,
        ref_type: RefType,
    ) -> Path:
        """Clone repository or update existing clone.

        If repository doesn't exist, clones it. If it exists and ref is a
        branch, fetches and resets to latest. For tags/commits, just checks out.

        Args:
            repo_url: Git repository URL (must be HTTP/HTTPS)
            git_ref: Branch, tag, or commit hash
            cache_dir: Directory for caching repos
            ref_type: Type of git reference

        Returns:
            Path to local repository

        Raises:
            ValueError: If inputs are invalid or path traversal detected
            RuntimeError: If git operations fail
        """
        # Validate repo_url format (HTTP/HTTPS URLs only)
        if not re.match(r"^https?://[\w\-\.]+(:\d+)?/[\w\-\./]+\.git$", repo_url):
            raise ValueError(f"Invalid repository URL format: {repo_url}")

        # SSRF protection - block internal networks and metadata services
        if not self._is_safe_url(repo_url):
            raise ValueError(
                f"Repository URL points to internal network or metadata service: {repo_url}"
            )

        # Block git option injection (refs starting with -)
        if git_ref.startswith("-"):
            raise ValueError(f"Git reference cannot start with '-': {git_ref}")

        # Block path traversal in git refs
        if ".." in git_ref:
            raise ValueError(f"Path traversal not allowed in git reference: {git_ref}")

        # Validate git_ref doesn't contain dangerous characters (removed - from allowed)
        if not re.match(r"^[\w\./]+$", git_ref):
            raise ValueError(f"Invalid git reference format: {git_ref}")

        # Create cache_dir if doesn't exist
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Extract repo name robustly
        match = re.search(r"/([^/]+?)(\.git)?$", repo_url)
        if not match:
            raise ValueError(f"Cannot extract repository name from URL: {repo_url}")
        repo_name = match.group(1)

        repo_path = cache_dir / repo_name

        # Verify repo_path is within cache_dir (prevent path traversal)
        try:
            repo_path.resolve().relative_to(cache_dir.resolve())
        except ValueError as e:
            raise ValueError(f"Repository path escapes cache directory: {repo_path}") from e

        if not repo_path.exists():
            # Clone repository
            logging.info(f"Cloning {repo_url} into {repo_path}")
            self._run_git_command(
                ["git", "clone", "--no-remote-submodules", repo_url, str(repo_path)]
            )

            # Checkout specified ref
            logging.info(f"Checking out {ref_type.value} {git_ref}")
            self._run_git_command(["git", "checkout", git_ref], cwd=str(repo_path))
        else:
            # Verify it's a valid git repository
            if not (repo_path / ".git").exists():
                raise RuntimeError(f"Path exists but is not a git repository: {repo_path}")

            logging.info(f"Updating repository {repo_path}")

            # Repository exists - update it
            if ref_type == RefType.BRANCH:
                # For branches: fetch and reset to latest
                logging.debug(f"Fetching latest changes for branch {git_ref}")
                self._run_git_command(["git", "fetch", "--prune", "origin"], cwd=str(repo_path))

                # Check current branch
                result = self._run_git_command(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo_path)
                )
                current_ref = result.stdout.strip()

                # Switch branch if needed
                if current_ref != git_ref:
                    logging.info(f"Switching from {current_ref} to {git_ref}")
                    self._run_git_command(["git", "checkout", git_ref], cwd=str(repo_path))

                # Reset to remote branch state
                # Validate ref doesn't contain slash (except for remote refs we create)
                remote_ref = f"origin/{git_ref}"
                logging.debug(f"Resetting to {remote_ref}")
                self._run_git_command(
                    ["git", "reset", "--hard", remote_ref],
                    cwd=str(repo_path),
                )
            else:
                # For tags/commits: just checkout
                logging.info(f"Checking out {ref_type.value} {git_ref}")
                self._run_git_command(["git", "checkout", git_ref], cwd=str(repo_path))

        return repo_path
