"""Tests for repository metadata repository module."""

import gzip
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from bugowner.repositories.repo_metadata_repository import (
    RepoMetadataRepositoryImpl,
)


class TestParseSourcePackages:
    """Test suite for parse_source_packages method."""

    def test_parse_source_packages_extracts_src_arch_packages(self, tmp_path: Path) -> None:
        """Should extract package names with arch='src' from primary XML."""
        # Arrange
        primary_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common">
  <package type="rpm">
    <name>apache2</name>
    <arch>src</arch>
  </package>
  <package type="rpm">
    <name>nginx</name>
    <arch>src</arch>
  </package>
  <package type="rpm">
    <name>apache2-devel</name>
    <arch>x86_64</arch>
  </package>
</metadata>"""

        # Create gzipped file
        xml_file = tmp_path / "primary.xml.gz"
        with gzip.open(xml_file, "wt", encoding="utf-8") as f:
            f.write(primary_xml_content)

        repo = RepoMetadataRepositoryImpl()

        # Act
        result = repo.parse_source_packages(xml_file)

        # Assert
        assert result == {"apache2", "nginx"}

    def test_parse_source_packages_ignores_non_src_packages(self, tmp_path: Path) -> None:
        """Should only extract packages with arch='src', ignore others."""
        # Arrange
        primary_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common">
  <package type="rpm">
    <name>binary-pkg1</name>
    <arch>x86_64</arch>
  </package>
  <package type="rpm">
    <name>source-pkg1</name>
    <arch>src</arch>
  </package>
  <package type="rpm">
    <name>binary-pkg2</name>
    <arch>i586</arch>
  </package>
</metadata>"""

        xml_file = tmp_path / "primary.xml.gz"
        with gzip.open(xml_file, "wt", encoding="utf-8") as f:
            f.write(primary_xml_content)

        repo = RepoMetadataRepositoryImpl()

        # Act
        result = repo.parse_source_packages(xml_file)

        # Assert
        assert result == {"source-pkg1"}

    def test_parse_source_packages_handles_empty_metadata(self, tmp_path: Path) -> None:
        """Should return empty set when no packages found."""
        # Arrange
        primary_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common">
</metadata>"""

        xml_file = tmp_path / "primary.xml.gz"
        with gzip.open(xml_file, "wt", encoding="utf-8") as f:
            f.write(primary_xml_content)

        repo = RepoMetadataRepositoryImpl()

        # Act
        result = repo.parse_source_packages(xml_file)

        # Assert
        assert result == set()

    def test_parse_source_packages_handles_missing_arch_element(self, tmp_path: Path) -> None:
        """Should skip packages without arch element."""
        # Arrange
        primary_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common">
  <package type="rpm">
    <name>incomplete-pkg</name>
  </package>
  <package type="rpm">
    <name>valid-pkg</name>
    <arch>src</arch>
  </package>
</metadata>"""

        xml_file = tmp_path / "primary.xml.gz"
        with gzip.open(xml_file, "wt", encoding="utf-8") as f:
            f.write(primary_xml_content)

        repo = RepoMetadataRepositoryImpl()

        # Act
        result = repo.parse_source_packages(xml_file)

        # Assert
        assert result == {"valid-pkg"}

    def test_parse_source_packages_raises_error_on_missing_file(self) -> None:
        """Should raise FileNotFoundError when XML file doesn't exist."""
        # Arrange
        repo = RepoMetadataRepositoryImpl()
        non_existent_file = Path("/tmp/nonexistent.xml.gz")

        # Act & Assert
        with pytest.raises(FileNotFoundError):
            repo.parse_source_packages(non_existent_file)


class TestDownloadPrimaryMetadata:
    """Test suite for download_primary_metadata method."""

    @patch("requests.get")
    def test_download_primary_metadata_downloads_and_returns_path(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should download repomd.xml, parse it, download primary.xml and return path."""
        # Arrange
        repomd_content = """<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="repodata/primary.xml.gz"/>
    <checksum type="sha256">abc123</checksum>
  </data>
</repomd>"""

        primary_content = b"fake primary xml content"

        # Mock responses
        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()

        mock_primary_response = Mock()
        mock_primary_response.content = primary_content
        mock_primary_response.raise_for_status = Mock()

        mock_get.side_effect = [mock_repomd_response, mock_primary_response]

        repo = RepoMetadataRepositoryImpl()
        cache_dir = tmp_path / "cache"

        # Act
        result = repo.download_primary_metadata("16.1", cache_dir)

        # Assert
        assert result.exists()
        assert result.name == "primary.xml.gz"
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_download_primary_metadata_uses_cached_file_if_exists(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should skip download if cached file exists with matching checksum."""
        # Arrange
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        # Create cached file
        cached_file = cache_dir / "primary.xml.gz"
        cached_content = b"cached content"
        cached_file.write_bytes(cached_content)

        # Checksum matches cached file
        cached_checksum = hashlib.sha256(cached_content).hexdigest()

        repomd_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="repodata/primary.xml.gz"/>
    <checksum type="sha256">{cached_checksum}</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()

        mock_get.return_value = mock_repomd_response

        repo = RepoMetadataRepositoryImpl()

        # Act
        result = repo.download_primary_metadata("16.1", cache_dir)

        # Assert
        assert result == cached_file
        assert mock_get.call_count == 1  # Only downloaded repomd, not primary

    @patch("requests.get")
    def test_download_primary_metadata_redownloads_if_checksum_mismatch(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should re-download primary.xml if cached file checksum doesn't match."""
        # Arrange
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)

        # Create cached file with old content
        cached_file = cache_dir / "primary.xml.gz"
        cached_file.write_bytes(b"old content")

        # New content with different checksum
        new_content = b"new content"
        new_checksum = hashlib.sha256(new_content).hexdigest()

        repomd_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="repodata/primary.xml.gz"/>
    <checksum type="sha256">{new_checksum}</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()

        mock_primary_response = Mock()
        mock_primary_response.content = new_content
        mock_primary_response.raise_for_status = Mock()

        mock_get.side_effect = [mock_repomd_response, mock_primary_response]

        repo = RepoMetadataRepositoryImpl()

        # Act
        result = repo.download_primary_metadata("16.1", cache_dir)

        # Assert
        assert result.read_bytes() == new_content
        assert mock_get.call_count == 2  # Downloaded both repomd and primary

    @patch("requests.get")
    def test_download_primary_metadata_raises_on_network_error(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should raise RuntimeError when network request fails."""
        # Arrange
        mock_get.side_effect = requests.RequestException("Network error")
        repo = RepoMetadataRepositoryImpl()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to download"):
            repo.download_primary_metadata("16.1", tmp_path)

    def test_download_primary_metadata_validates_version_format(self, tmp_path: Path) -> None:
        """Should reject invalid version formats to prevent URL manipulation."""
        # Arrange
        repo = RepoMetadataRepositoryImpl()

        # Act & Assert - empty version
        with pytest.raises(ValueError, match="Invalid version format"):
            repo.download_primary_metadata("", tmp_path)

        # Act & Assert - path traversal attempt
        with pytest.raises(ValueError, match="Invalid version format"):
            repo.download_primary_metadata("../../etc/passwd", tmp_path)

        # Act & Assert - invalid characters
        with pytest.raises(ValueError, match="Invalid version format"):
            repo.download_primary_metadata("16.1; rm -rf /", tmp_path)

    @patch("requests.get")
    def test_download_primary_metadata_rejects_path_traversal_in_href(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should reject primary_href with path traversal sequences (SSRF prevention)."""
        # Arrange - repomd.xml with malicious path traversal
        repomd_content = """<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="../../../admin/sensitive-endpoint"/>
    <checksum type="sha256">abc123</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()
        mock_get.return_value = mock_repomd_response

        repo = RepoMetadataRepositoryImpl()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Invalid primary.xml location"):
            repo.download_primary_metadata("16.1", tmp_path)

    @patch("requests.get")
    def test_download_primary_metadata_rejects_absolute_path_in_href(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should reject primary_href starting with slash (SSRF prevention)."""
        # Arrange - repomd.xml with absolute path
        repomd_content = """<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="/etc/passwd"/>
    <checksum type="sha256">abc123</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()
        mock_get.return_value = mock_repomd_response

        repo = RepoMetadataRepositoryImpl()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Invalid primary.xml location"):
            repo.download_primary_metadata("16.1", tmp_path)

    @patch("requests.get")
    def test_download_primary_metadata_rejects_double_slash_in_href(
        self, mock_get: Mock, tmp_path: Path
    ) -> None:
        """Should reject primary_href with double slash (protocol-relative URL)."""
        # Arrange - repomd.xml with protocol-relative URL
        repomd_content = """<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="//evil.com/malicious.xml.gz"/>
    <checksum type="sha256">abc123</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()
        mock_get.return_value = mock_repomd_response

        repo = RepoMetadataRepositoryImpl()

        # Act & Assert
        with pytest.raises(RuntimeError, match="Invalid primary.xml location"):
            repo.download_primary_metadata("16.1", tmp_path)
