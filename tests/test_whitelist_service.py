"""Tests for WhitelistService."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.services.whitelist_service import WhitelistCheckResult, WhitelistService


class TestCheckWhitelist:
    """Tests for WhitelistService.check_whitelist() method."""

    def test_check_whitelist_finds_no_inconsistencies_when_none_exist(self, tmp_path: Path) -> None:
        """Should return empty list when validated packages don't overlap with whitelist."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist file with different packages
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg3", "pkg4"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2", "pkg5"},
            submodules=["pkg1", "pkg2"],
            false_positives_file=false_positives_file,
        )

        # Verify
        assert isinstance(result, WhitelistCheckResult)
        assert result.inconsistent_packages == []
        assert result.new_false_positives == {}

    def test_check_whitelist_finds_inconsistencies_when_packages_shipped_and_whitelisted(
        self, tmp_path: Path
    ) -> None:
        """Should find packages that are BOTH shipped AND whitelisted."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2", "pkg3"},  # valid_packages (validated shipped)
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist with pkg1 and pkg2 (overlap with validated shipped)
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1", "pkg2", "pkg4"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2", "pkg3", "pkg5"},
            submodules=["pkg1", "pkg2", "pkg3"],
            false_positives_file=false_positives_file,
        )

        # Verify - pkg1 and pkg2 are in BOTH validated shipped and whitelist
        assert result.inconsistent_packages == ["pkg1", "pkg2"]
        assert result.new_false_positives == {}

    def test_check_whitelist_handles_empty_whitelist(self, tmp_path: Path) -> None:
        """Should return no inconsistencies when whitelist is empty."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create empty whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text("[]")

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2"},
            submodules=["pkg1", "pkg2"],
            false_positives_file=false_positives_file,
        )

        # Verify
        assert result.inconsistent_packages == []
        assert result.new_false_positives == {}

    def test_check_whitelist_returns_new_false_positives_from_validation_pipeline(
        self, tmp_path: Path
    ) -> None:
        """Should return new false positives discovered during validation."""
        # Setup mock validation service with new false positives
        mock_validation_service = Mock()
        new_fps = {"apache2-devel": "apache2", "kernel-default": "kernel-source"}
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"apache2", "kernel-source"},  # valid_packages
            [],  # shipped_not_in_submodule
            new_fps,  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"apache2-devel", "kernel-default"},
            submodules=["apache2", "kernel-source"],
            false_positives_file=false_positives_file,
        )

        # Verify new false positives are returned
        assert result.new_false_positives == new_fps

    def test_check_whitelist_raises_error_when_whitelist_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when whitelist file doesn't exist."""
        mock_validation_service = Mock()
        service = WhitelistService(mock_validation_service)

        whitelist_file = tmp_path / "nonexistent.json"
        false_positives_file = tmp_path / "false_positives.json"

        # Execute and verify
        with pytest.raises(FileNotFoundError, match="Whitelist file .* does not exist"):
            service.check_whitelist(
                whitelist_file=whitelist_file,
                shipped_packages={"pkg1"},
                submodules=["pkg1"],
                false_positives_file=false_positives_file,
            )

    def test_check_whitelist_calls_validation_service_with_correct_parameters(
        self, tmp_path: Path
    ) -> None:
        """Should call validation service with correct parameters."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1"},  # valid_packages
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1"]')

        false_positives_file = tmp_path / "false_positives.json"
        shipped_packages = {"pkg1", "pkg2"}
        submodules = ["pkg1"]
        obs_project = "TEST:PROJECT"

        # Execute
        service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages=shipped_packages,
            submodules=submodules,
            false_positives_file=false_positives_file,
            obs_project=obs_project,
        )

        # Verify validation service was called with correct parameters
        mock_validation_service.find_shipped_without_submodule.assert_called_once_with(
            shipped_packages, submodules, false_positives_file, obs_project
        )

    def test_check_whitelist_returns_sorted_inconsistent_packages(self, tmp_path: Path) -> None:
        """Should return inconsistent packages in sorted order."""
        # Setup mock validation service
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"zebra", "apple", "banana"},  # valid_packages (unsorted)
            [],  # shipped_not_in_submodule
            {},  # new_false_positives
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist with same packages (unsorted)
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["banana", "zebra", "apple"]')

        false_positives_file = tmp_path / "false_positives.json"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"zebra", "apple", "banana"},
            submodules=["zebra", "apple", "banana"],
            false_positives_file=false_positives_file,
        )

        # Verify sorted output
        assert result.inconsistent_packages == ["apple", "banana", "zebra"]
