"""Repository metadata operations for downloading and parsing package data."""

import gzip
import hashlib
import logging
import re
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)


class RepoMetadataRepository(Protocol):
    """Interface for repository metadata operations."""

    def download_primary_metadata(self, version: str, cache_dir: Path) -> Path:
        """Download and cache primary repository metadata.

        Downloads repomd.xml, parses it to find primary XML location,
        then downloads primary XML file. Uses checksums to validate
        and avoid re-downloading unchanged files.

        Args:
            version: SLES version (e.g., "16.1")
            cache_dir: Cache directory for downloads

        Returns:
            Path to downloaded primary XML file

        Raises:
            RuntimeError: If download or parsing fails
        """
        ...

    def parse_source_packages(self, primary_xml_path: Path) -> set[str]:
        """Parse primary XML to extract source package names.

        Parses gzipped primary XML file using iterparse for memory efficiency.
        Extracts only packages with architecture='src'.

        Args:
            primary_xml_path: Path to primary.xml.gz file

        Returns:
            Set of source package names with 'src' architecture

        Raises:
            FileNotFoundError: If primary_xml_path doesn't exist
        """
        ...


class RepoMetadataRepositoryImpl:
    """Implementation of repository metadata operations."""

    def __init__(self, base_url: str | None = None):
        """Initialize repository metadata repository.

        Args:
            base_url: Base URL for repository metadata (defaults to SUSE IBS repo)
        """
        self.base_url = (
            base_url
            or "https://download.suse.de/ibs/SUSE:/SLFO:/Products:/SLES:/{version}:/PUBLISH/product/"
        )

    def download_primary_metadata(self, version: str, cache_dir: Path) -> Path:
        """Download and cache primary repository metadata.

        Downloads repomd.xml, parses it to find primary XML location,
        then downloads primary XML file. Uses checksums to validate
        and avoid re-downloading unchanged files.

        Args:
            version: SLES version (e.g., "16.1")
            cache_dir: Cache directory for downloads

        Returns:
            Path to downloaded primary XML file

        Raises:
            ValueError: If version format is invalid
            RuntimeError: If download or parsing fails
        """
        # Validate version format to prevent URL manipulation
        if not version or not re.match(r"^\d+\.\d+$", version):
            raise ValueError(f"Invalid version format: {version!r} (expected: X.Y)")

        # Create version-specific cache directory
        metadata_cache_dir = cache_dir / "repodata" / version
        metadata_cache_dir.mkdir(parents=True, exist_ok=True)

        # Download repomd.xml
        logger.info("Downloading repomd.xml for version %s", version)
        try:
            repomd_url = self.base_url.format(version=version) + "repodata/repomd.xml"
            # NOTE: verify=False is required to access internal SUSE infrastructure
            # that uses self-signed certificates. This is acceptable for internal use
            # but should NOT be used in production environments with untrusted sources.
            repomd_response = requests.get(repomd_url, verify=False, timeout=30)
            repomd_response.raise_for_status()

            # Cache repomd.xml for future use
            repomd_cache_file = metadata_cache_dir / "repomd.xml"
            repomd_cache_file.write_bytes(repomd_response.content)
            logger.debug("Cached repomd.xml to %s", repomd_cache_file)

        except (requests.RequestException, requests.Timeout, OSError) as e:
            logger.error("Failed to download repomd.xml for version %s: %s", version, e)
            raise RuntimeError(f"Failed to download repomd.xml: {e}") from e

        # Parse repomd.xml to find primary.xml location and checksum
        try:
            repomd_root = ET.fromstring(repomd_response.content)
            # Find primary data element
            ns = {"ns": "http://linux.duke.edu/metadata/repo"}
            primary_data = repomd_root.find('.//ns:data[@type="primary"]', ns)
            if primary_data is None:
                # Try without namespace
                primary_data = repomd_root.find('.//*[@type="primary"]')
            if primary_data is None:
                raise RuntimeError("Primary metadata not found in repomd.xml")

            # Extract location and checksum
            location_elem = primary_data.find(".//{*}location")
            if location_elem is None:
                location_elem = primary_data.find(".//location")

            checksum_elem = primary_data.find(".//{*}checksum")
            if checksum_elem is None:
                checksum_elem = primary_data.find(".//checksum")

            if location_elem is None or checksum_elem is None:
                raise RuntimeError("Missing location or checksum in repomd.xml")

            primary_href = location_elem.get("href")
            expected_checksum = checksum_elem.text
            checksum_type = checksum_elem.get("type", "sha256")

            if not primary_href or not expected_checksum:
                raise RuntimeError("Invalid location or checksum in repomd.xml")

            # Log primary metadata info (matches old validate_maintainership.py format)
            logger.info("Primary data location from repomd.xml: %s", primary_href)
            logger.info("Expected %s checksum: %s", checksum_type, expected_checksum)

            # Validate primary_href to prevent SSRF
            # (path traversal, absolute paths, protocol-relative URLs)
            if (
                primary_href.startswith("/")
                or primary_href.startswith("..")
                or "//" in primary_href
            ):
                raise RuntimeError(f"Invalid primary.xml location: {primary_href!r}")

        except ET.ParseError as e:
            raise RuntimeError(f"Failed to parse repomd.xml: {e}") from e

        # Check if cached file exists with matching checksum
        cached_file = metadata_cache_dir / "primary.xml.gz"
        if cached_file.exists():
            # Calculate checksum of cached file
            cached_checksum = hashlib.sha256(cached_file.read_bytes()).hexdigest()
            if cached_checksum == expected_checksum:
                # Cache hit - return cached file
                logger.info(
                    "File %s already exists in cache and checksum matches. Skipping download.",
                    cached_file.name,
                )
                return cached_file
            # Checksum mismatch - delete corrupted file and re-download
            logger.warning(
                "Checksum mismatch for %s in cache. Deleting and re-downloading.",
                cached_file.name,
            )
            cached_file.unlink()
        else:
            logger.info("Cache miss for version %s (file not found)", version)

        # Download primary.xml
        logger.info("Downloading primary.xml for version %s", version)
        try:
            primary_url = self.base_url.format(version=version) + primary_href
            # NOTE: verify=False is required for internal SUSE infrastructure (see above)
            primary_response = requests.get(primary_url, verify=False, timeout=30, stream=True)
            primary_response.raise_for_status()

            # Write to cache using streaming (memory-efficient)
            with cached_file.open("wb") as f:
                for chunk in primary_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info("Successfully downloaded and cached primary.xml for version %s", version)

            return cached_file

        except (requests.RequestException, requests.Timeout, OSError) as e:
            logger.error("Failed to download primary.xml for version %s: %s", version, e)
            raise RuntimeError(f"Failed to download primary.xml: {e}") from e

    def parse_source_packages(self, primary_xml_path: Path) -> set[str]:
        """Parse primary XML to extract source package names.

        Parses gzipped primary XML file using iterparse for memory efficiency.
        Extracts only packages with architecture='src'.

        Args:
            primary_xml_path: Path to primary.xml.gz file

        Returns:
            Set of source package names with 'src' architecture

        Raises:
            FileNotFoundError: If primary_xml_path doesn't exist
        """
        if not primary_xml_path.exists():
            raise FileNotFoundError(f"Primary XML file not found: {primary_xml_path}")

        source_packages: set[str] = set()

        # Open gzipped XML file
        with gzip.open(primary_xml_path, "rt", encoding="utf-8") as f:
            # Use iterparse for memory efficiency on large files
            # Parse iteratively
            context = ET.iterparse(f, events=("start", "end"))
            context = iter(context)

            current_package_name: str | None = None
            current_arch: str | None = None

            for event, elem in context:
                # Strip namespace from tag
                tag = elem.tag.replace("{http://linux.duke.edu/metadata/common}", "")

                if event == "end":
                    if tag == "name" and elem.text:
                        current_package_name = elem.text
                    elif tag == "arch" and elem.text:
                        current_arch = elem.text
                    elif tag == "package":
                        # End of package element - check if it's a source package
                        if current_package_name and current_arch == "src":
                            source_packages.add(current_package_name)

                        # Reset for next package
                        current_package_name = None
                        current_arch = None

                        # Clear element to free memory
                        elem.clear()

        return source_packages
