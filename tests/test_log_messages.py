"""Tests for cache log messages matching old format."""

import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bugowner.repositories.repo_metadata_repository import RepoMetadataRepositoryImpl


class TestCacheLogMessages:
    """Test suite for cache log messages matching validate_maintainership.py format."""

    @patch("requests.get")
    def test_logs_primary_location_and_checksum_after_parsing_repomd(
        self, mock_get: Mock, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log primary data location and expected checksum after parsing repomd.xml.

        Old format (validate_maintainership.py lines 203-204):
        - "Primary data location from repomd.xml: {href}"
        - "Expected {checksum_type} checksum: {checksum}"
        """
        # Arrange
        primary_href = "repodata/primary.xml.gz"
        expected_checksum = "abc123def456"
        checksum_type = "sha256"

        repomd_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="{primary_href}"/>
    <checksum type="{checksum_type}">{expected_checksum}</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()

        mock_primary_response = Mock()
        mock_primary_response.iter_content = Mock(return_value=[b"primary content"])
        mock_primary_response.raise_for_status = Mock()

        mock_get.side_effect = [mock_repomd_response, mock_primary_response]

        repo = RepoMetadataRepositoryImpl()
        cache_dir = tmp_path / "cache"

        # Act
        with caplog.at_level("INFO"):
            repo.download_primary_metadata("16.1", cache_dir)

        # Assert - verify both log messages exist
        log_messages = [record.message for record in caplog.records]

        assert any(
            f"Primary data location from repomd.xml: {primary_href}" in msg for msg in log_messages
        ), f"Should log primary location. Got: {log_messages}"

        assert any(
            f"Expected {checksum_type} checksum: {expected_checksum}" in msg for msg in log_messages
        ), f"Should log expected checksum. Got: {log_messages}"

    @patch("requests.get")
    def test_cache_hit_logs_detailed_message_with_filename(
        self, mock_get: Mock, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log detailed cache hit message with filename and reason.

        Old format (validate_maintainership.py lines 212-214):
        "File {filename} already exists in cache and checksum matches. Skipping download."
        """
        # Arrange - Create cached file
        cache_dir = tmp_path / "cache"
        version_cache_dir = cache_dir / "repodata" / "16.1"
        version_cache_dir.mkdir(parents=True)

        cached_file = version_cache_dir / "primary.xml.gz"
        cached_content = b"cached content"
        cached_file.write_bytes(cached_content)
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
        with caplog.at_level("INFO"):
            repo.download_primary_metadata("16.1", cache_dir)

        # Assert - verify detailed cache hit message
        log_messages = [record.message for record in caplog.records]

        assert any(
            "File primary.xml.gz already exists in cache and checksum matches. Skipping download."
            in msg
            for msg in log_messages
        ), f"Should log detailed cache hit message. Got: {log_messages}"

    @patch("requests.get")
    def test_checksum_mismatch_logs_warning_and_deletes_file(
        self, mock_get: Mock, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log WARNING and delete corrupted file on checksum mismatch.

        Old format (validate_maintainership.py lines 217-221):
        logging.warning("Checksum mismatch for {filename} in cache. Deleting and re-downloading.")
        + file.unlink()
        """
        # Arrange - Create cached file with wrong checksum
        cache_dir = tmp_path / "cache"
        version_cache_dir = cache_dir / "repodata" / "16.1"
        version_cache_dir.mkdir(parents=True)

        cached_file = version_cache_dir / "primary.xml.gz"
        old_content = b"old corrupted content"
        cached_file.write_bytes(old_content)

        # Expected checksum doesn't match
        new_content = b"new correct content"
        expected_checksum = hashlib.sha256(new_content).hexdigest()

        repomd_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<repomd>
  <data type="primary">
    <location href="repodata/primary.xml.gz"/>
    <checksum type="sha256">{expected_checksum}</checksum>
  </data>
</repomd>"""

        mock_repomd_response = Mock()
        mock_repomd_response.content = repomd_content.encode()
        mock_repomd_response.raise_for_status = Mock()

        mock_primary_response = Mock()
        mock_primary_response.iter_content = Mock(return_value=[new_content])
        mock_primary_response.raise_for_status = Mock()

        mock_get.side_effect = [mock_repomd_response, mock_primary_response]

        repo = RepoMetadataRepositoryImpl()

        # Act
        with caplog.at_level("WARNING"):
            result = repo.download_primary_metadata("16.1", cache_dir)

        # Assert - verify WARNING log message
        warning_messages = [
            record.message for record in caplog.records if record.levelname == "WARNING"
        ]

        assert any(
            "Checksum mismatch for primary.xml.gz in cache. Deleting and re-downloading." in msg
            for msg in warning_messages
        ), f"Should log WARNING about checksum mismatch. Got: {warning_messages}"

        # Verify file was re-downloaded with new content (not old corrupted content)
        assert result.read_bytes() == new_content, "Should have new content after re-download"
