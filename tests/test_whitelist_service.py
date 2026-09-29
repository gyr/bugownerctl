"""Tests for WhitelistService."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bugownerctl.services.whitelist_service import WhitelistCheckResult, WhitelistService

# Synthetic OBS project name passed to every check_whitelist call.
_OBS_PROJECT = "TEST:Project:1.0"


class TestLoadWhitelist:
    """Tests for WhitelistService.load_whitelist() method."""

    def test_load_whitelist_parses_bytes_payload(self) -> None:
        """Should return the package names from a JSON-array bytes payload."""
        service = WhitelistService(Mock())

        assert service.load_whitelist(b'["pkg1", "pkg2"]') == {"pkg1", "pkg2"}

    def test_load_whitelist_rejects_oversized_payload(self) -> None:
        """Should raise ValueError when the payload exceeds MAX_WHITELIST_SIZE."""
        service = WhitelistService(Mock())
        # Valid JSON array one byte over the limit, so only the size check can reject it.
        oversized = b"[" + b" " * (WhitelistService.MAX_WHITELIST_SIZE - 1) + b"]"

        with pytest.raises(
            ValueError,
            match=(
                rf"^Whitelist is too large: {len(oversized)} bytes "
                rf"\(max {WhitelistService.MAX_WHITELIST_SIZE}\)$"
            ),
        ):
            service.load_whitelist(oversized)

    def test_load_whitelist_rejects_non_array(self) -> None:
        """Should raise ValueError when the payload is not a JSON array."""
        service = WhitelistService(Mock())

        with pytest.raises(ValueError, match=r"^Whitelist must contain a JSON array, got dict$"):
            service.load_whitelist(b'{"pkg1": 1}')

    def test_load_whitelist_rejects_non_string_elements(self) -> None:
        """Should raise ValueError when an array element is not a string."""
        service = WhitelistService(Mock())

        with pytest.raises(ValueError, match=r"^Whitelist must contain only strings$"):
            service.load_whitelist(b'["pkg1", 1]')


class TestCheckWhitelist:
    """Tests for WhitelistService.check_whitelist() method."""

    def test_check_whitelist_finds_no_inconsistencies_when_none_exist(self, tmp_path: Path) -> None:
        """Should return empty list when validated packages don't overlap with whitelist."""
        # Setup mock validation service (3-tuple return: valid, residue, unresolved)
        mock_validation_service = Mock()
        mock_validation_service.resolve_shipped_packages.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_obs
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        whitelist_content = b'["pkg3", "pkg4"]'

        overrides_file = tmp_path / "overrides.json"

        # Execute
        result = service.check_whitelist(
            whitelist_content=whitelist_content,
            shipped_packages={"pkg1", "pkg2", "pkg5"},
            overrides_file=overrides_file,
            obs_project=_OBS_PROJECT,
        )

        # Verify
        assert isinstance(result, WhitelistCheckResult)
        assert result.inconsistent_packages == []

    def test_check_whitelist_finds_inconsistencies_when_packages_shipped_and_whitelisted(
        self, tmp_path: Path
    ) -> None:
        """Should find packages that are BOTH shipped AND whitelisted."""
        mock_validation_service = Mock()
        mock_validation_service.resolve_shipped_packages.return_value = (
            {"pkg1", "pkg2", "pkg3"},  # valid_packages
            [],  # shipped_not_in_obs
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        whitelist_content = b'["pkg1", "pkg2", "pkg4"]'

        overrides_file = tmp_path / "overrides.json"

        # Execute
        result = service.check_whitelist(
            whitelist_content=whitelist_content,
            shipped_packages={"pkg1", "pkg2", "pkg3", "pkg5"},
            overrides_file=overrides_file,
            obs_project=_OBS_PROJECT,
        )

        # Verify - pkg1 and pkg2 are in BOTH validated shipped and whitelist
        assert result.inconsistent_packages == ["pkg1", "pkg2"]

    def test_check_whitelist_handles_empty_whitelist(self, tmp_path: Path) -> None:
        """Should return no inconsistencies when whitelist is empty."""
        mock_validation_service = Mock()
        mock_validation_service.resolve_shipped_packages.return_value = (
            {"pkg1", "pkg2"},  # valid_packages
            [],  # shipped_not_in_obs
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        whitelist_content = b"[]"

        overrides_file = tmp_path / "overrides.json"

        # Execute
        result = service.check_whitelist(
            whitelist_content=whitelist_content,
            shipped_packages={"pkg1", "pkg2"},
            overrides_file=overrides_file,
            obs_project=_OBS_PROJECT,
        )

        # Verify
        assert result.inconsistent_packages == []

    def test_check_whitelist_calls_validation_service_with_correct_parameters(
        self, tmp_path: Path
    ) -> None:
        """Should pre-load source_info then call resolve_shipped_packages with source_info=.

        After Fix 1, check_whitelist pre-loads source_info (via source_info_repo.load_source_info)
        and passes it as source_info= to resolve_shipped_packages.
        """
        mock_source_info = Mock(name="source_info")
        mock_validation_service = Mock()
        mock_validation_service.source_info_repo.load_source_info.return_value = mock_source_info
        mock_validation_service.resolve_shipped_packages.return_value = (
            {"pkg1"},  # valid_packages
            [],  # shipped_not_in_obs
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        whitelist_content = b'["pkg1"]'

        overrides_file = tmp_path / "overrides.json"
        shipped_packages = {"pkg1", "pkg2"}
        obs_project = "TEST:PROJECT"

        # Execute
        service.check_whitelist(
            whitelist_content=whitelist_content,
            shipped_packages=shipped_packages,
            overrides_file=overrides_file,
            obs_project=obs_project,
        )

        # source_info loaded at orchestration layer
        mock_validation_service.source_info_repo.load_source_info.assert_called_once_with(
            obs_project
        )
        # resolve_shipped_packages receives the preloaded source_info=
        mock_validation_service.resolve_shipped_packages.assert_called_once_with(
            shipped_packages,
            overrides_file,
            obs_project,
            source_info=mock_source_info,
        )

    def test_check_whitelist_propagates_unresolved_names(self, tmp_path: Path) -> None:
        """Should propagate validation pipeline's unresolved_names into the result.

        Mirrors ValidationResult.unresolved_names semantics: names that
        fell through the source_info/overrides pipeline and aren't in the OBS package set.
        """
        mock_validation_service = Mock()
        mock_validation_service.resolve_shipped_packages.return_value = (
            {"pkg1"},  # valid_packages
            ["mystery-pkg"],  # shipped_not_in_obs (residue)
            ["mystery-pkg"],  # unresolved_names (strict subset of residue)
        )

        service = WhitelistService(mock_validation_service)

        whitelist_content = b'["pkg1"]'

        overrides_file = tmp_path / "overrides.json"

        result = service.check_whitelist(
            whitelist_content=whitelist_content,
            shipped_packages={"pkg1", "mystery-pkg"},
            overrides_file=overrides_file,
            obs_project=_OBS_PROJECT,
        )

        assert result.unresolved_names == ["mystery-pkg"]

    def test_check_whitelist_requires_obs_project(self, tmp_path: Path) -> None:
        """Omitting obs_project is a TypeError — there is no silent default project."""
        service = WhitelistService(Mock())
        whitelist_content = b"[]"

        with pytest.raises(TypeError, match="obs_project"):
            service.check_whitelist(  # type: ignore[call-arg]  # omission under test
                whitelist_content=whitelist_content,
                shipped_packages={"pkg1"},
                overrides_file=tmp_path / "overrides.json",
            )

    def test_check_whitelist_returns_sorted_inconsistent_packages(self, tmp_path: Path) -> None:
        """Should return inconsistent packages in sorted order."""
        mock_validation_service = Mock()
        mock_validation_service.resolve_shipped_packages.return_value = (
            {"zebra", "apple", "banana"},  # valid_packages (unsorted)
            [],  # shipped_not_in_obs
            [],  # unresolved_names
        )

        service = WhitelistService(mock_validation_service)

        whitelist_content = b'["banana", "zebra", "apple"]'

        overrides_file = tmp_path / "overrides.json"

        # Execute
        result = service.check_whitelist(
            whitelist_content=whitelist_content,
            shipped_packages={"zebra", "apple", "banana"},
            overrides_file=overrides_file,
            obs_project=_OBS_PROJECT,
        )

        # Verify sorted output
        assert result.inconsistent_packages == ["apple", "banana", "zebra"]
