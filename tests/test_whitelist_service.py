"""Tests for WhitelistService."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.services.whitelist_service import WhitelistCheckResult, WhitelistService


class TestCheckWhitelist:
    """Tests for WhitelistService.check_whitelist() method."""

    def test_check_whitelist_finds_no_inconsistencies_when_none_exist(self, tmp_path: Path) -> None:
        """Should return empty list when validated packages don't overlap with whitelist."""
        # Setup mock validation service (3-tuple return: valid, residue, unresolved)
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_submodule
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist file with different packages
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg3", "pkg4"]')

        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2", "pkg5"},
            submodules=["pkg1", "pkg2"],
            overrides_file=overrides_file,
            cache_dir=cache_dir,
        )

        # Verify
        assert isinstance(result, WhitelistCheckResult)
        assert result.inconsistent_packages == []

    def test_check_whitelist_finds_inconsistencies_when_packages_shipped_and_whitelisted(
        self, tmp_path: Path
    ) -> None:
        """Should find packages that are BOTH shipped AND whitelisted."""
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2", "pkg3"},  # valid_packages
            [],  # shipped_not_in_submodule
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist with pkg1 and pkg2 (overlap with validated shipped)
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1", "pkg2", "pkg4"]')

        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2", "pkg3", "pkg5"},
            submodules=["pkg1", "pkg2", "pkg3"],
            overrides_file=overrides_file,
            cache_dir=cache_dir,
        )

        # Verify - pkg1 and pkg2 are in BOTH validated shipped and whitelist
        assert result.inconsistent_packages == ["pkg1", "pkg2"]

    def test_check_whitelist_handles_empty_whitelist(self, tmp_path: Path) -> None:
        """Should return no inconsistencies when whitelist is empty."""
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_submodule
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        # Create empty whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text("[]")

        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "pkg2"},
            submodules=["pkg1", "pkg2"],
            overrides_file=overrides_file,
            cache_dir=cache_dir,
        )

        # Verify
        assert result.inconsistent_packages == []

    def test_check_whitelist_raises_error_when_whitelist_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when whitelist file doesn't exist."""
        mock_validation_service = Mock()
        service = WhitelistService(mock_validation_service)

        whitelist_file = tmp_path / "nonexistent.json"
        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"

        # Execute and verify
        with pytest.raises(FileNotFoundError, match="Whitelist file .* does not exist"):
            service.check_whitelist(
                whitelist_file=whitelist_file,
                shipped_packages={"pkg1"},
                submodules=["pkg1"],
                overrides_file=overrides_file,
                cache_dir=cache_dir,
            )

    def test_check_whitelist_calls_validation_service_with_correct_parameters(
        self, tmp_path: Path
    ) -> None:
        """Should call validation service with correct parameters."""
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1"},  # valid_packages
            [],  # shipped_not_in_submodule
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1"]')

        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"
        shipped_packages = {"pkg1", "pkg2"}
        submodules = ["pkg1"]
        obs_project = "TEST:PROJECT"

        # Execute
        service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages=shipped_packages,
            submodules=submodules,
            overrides_file=overrides_file,
            cache_dir=cache_dir,
            obs_project=obs_project,
        )

        # Verify validation service was called with correct parameters
        mock_validation_service.find_shipped_without_submodule.assert_called_once_with(
            shipped_packages, submodules, overrides_file, cache_dir, obs_project
        )

    def test_check_whitelist_propagates_unresolved_names(self, tmp_path: Path) -> None:
        """Should propagate validation pipeline's unresolved_names into the result.

        Mirrors ValidationResult.unresolved_names semantics: names that
        fell through the bulk_map/overrides pipeline and aren't submodules.
        """
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"pkg1"},  # valid_packages
            ["mystery-pkg"],  # shipped_not_in_submodule (residue)
            ["mystery-pkg"],  # unresolved_names (strict subset of residue)
        )

        service = WhitelistService(mock_validation_service)

        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["pkg1"]')

        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"

        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"pkg1", "mystery-pkg"},
            submodules=["pkg1"],
            overrides_file=overrides_file,
            cache_dir=cache_dir,
        )

        assert result.unresolved_names == ["mystery-pkg"]

    def test_check_whitelist_returns_sorted_inconsistent_packages(self, tmp_path: Path) -> None:
        """Should return inconsistent packages in sorted order."""
        mock_validation_service = Mock()
        mock_validation_service.find_shipped_without_submodule.return_value = (
            {"zebra", "apple", "banana"},  # valid_packages (unsorted)
            [],  # shipped_not_in_submodule
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        # Create whitelist with same packages (unsorted)
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('["banana", "zebra", "apple"]')

        overrides_file = tmp_path / "overrides.json"
        cache_dir = tmp_path / "cache"

        # Execute
        result = service.check_whitelist(
            whitelist_file=whitelist_file,
            shipped_packages={"zebra", "apple", "banana"},
            submodules=["zebra", "apple", "banana"],
            overrides_file=overrides_file,
            cache_dir=cache_dir,
        )

        # Verify sorted output
        assert result.inconsistent_packages == ["apple", "banana", "zebra"]
