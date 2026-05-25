"""Tests for OBS repository matching OLD validate_maintainership.py behavior.

The old code uses:
- Command: osc -A https://api.suse.de bse {package}
- Output: Space-separated format "SUSE:SLFO:Main apache2:apache2-devel x86_64"
- Parsing: Filter by project prefix, split by space and colon
"""

from unittest.mock import Mock, patch

from bugowner.repositories.obs_repository import ObsRepositoryImpl


class TestObsRepositoryOldFormat:
    """Test suite matching old validate_maintainership.py behavior."""

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_uses_old_command_format(self, mock_run: Mock) -> None:
        """Should use 'osc -A https://api.suse.de bse {package}' command."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0,
            stdout="SUSE:SLFO:Main apache2:apache2-devel x86_64\n",
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result == "apache2"
        # Verify command matches old format
        mock_run.assert_called_once_with(
            ["osc", "-A", "https://api.suse.de", "bse", "apache2-devel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_parses_space_separated_output(self, mock_run: Mock) -> None:
        """Should parse space-separated output format from old code."""
        # Arrange - Real format: "project source:binary path"
        # Example: SUSE:SLFO:Main kernel-source:kernel-rt SUSE:/SLFO:/Main/...
        mock_run.return_value = Mock(
            returncode=0,
            stdout="SUSE:SLFO:Main kernel-source:kernel-rt aarch64\n",
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("kernel-rt", "SUSE:SLFO:Main")

        # Assert
        assert result == "kernel-source"

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_filters_by_project_prefix(self, mock_run: Mock) -> None:
        """Should filter output lines by 'SUSE:SLFO:Main ' prefix."""
        # Arrange - multiple projects in output
        mock_run.return_value = Mock(
            returncode=0,
            stdout=(
                "SUSE:Other:Project apache2:apache2-devel x86_64\n"
                "SUSE:SLFO:Main apache2:apache2-devel x86_64\n"
                "SUSE:Another:Repo apache2:apache2-devel i586\n"
            ),
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result == "apache2"

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_returns_none_when_project_not_found(self, mock_run: Mock) -> None:
        """Should return None when no lines match the project prefix."""
        # Arrange - output has packages but not in requested project
        mock_run.return_value = Mock(
            returncode=0,
            stdout="SUSE:Other:Project apache2:apache2-devel x86_64\n",
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result is None

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_splits_package_by_colon(self, mock_run: Mock) -> None:
        """Should split package field by colon and take first part as source."""
        # Arrange - package format is "source:binary"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="SUSE:SLFO:Main php8:apache2-mod_php8 x86_64\n",
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-mod_php8", "SUSE:SLFO:Main")

        # Assert
        assert result == "php8"

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_handles_package_without_colon(self, mock_run: Mock) -> None:
        """Should handle package field without colon (take as-is)."""
        # Arrange - package field has no colon separator
        mock_run.return_value = Mock(
            returncode=0,
            stdout="SUSE:SLFO:Main simple-package x86_64\n",
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("simple-package", "SUSE:SLFO:Main")

        # Assert
        assert result == "simple-package"

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_handles_multiple_architectures(self, mock_run: Mock) -> None:
        """Should deduplicate source packages from multiple architectures."""
        # Arrange - same source package for different architectures
        mock_run.return_value = Mock(
            returncode=0,
            stdout=(
                "SUSE:SLFO:Main apache2:apache2-devel x86_64\n"
                "SUSE:SLFO:Main apache2:apache2-devel i586\n"
                "SUSE:SLFO:Main apache2:apache2-devel aarch64\n"
            ),
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result == "apache2"

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    @patch("bugowner.repositories.obs_repository.logger")
    def test_get_source_package_warns_on_multiple_sources(
        self, mock_logger: Mock, mock_run: Mock
    ) -> None:
        """Should log warning when multiple different source packages found."""
        # Arrange - conflicting source packages (should not happen in practice)
        mock_run.return_value = Mock(
            returncode=0,
            stdout=(
                "SUSE:SLFO:Main apache2:apache2-devel x86_64\n"
                "SUSE:SLFO:Main httpd:apache2-devel x86_64\n"
            ),
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result in ["apache2", "httpd"]  # Returns one of them
        # Should log warning about multiple sources
        mock_logger.warning.assert_called_once()
        assert "multiple source packages" in str(mock_logger.warning.call_args).lower()

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    @patch("bugowner.repositories.obs_repository.logger")
    def test_get_source_package_logs_when_not_found(
        self, mock_logger: Mock, mock_run: Mock
    ) -> None:
        """Should log info message when no source package found."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("nonexistent-package", "SUSE:SLFO:Main")

        # Assert
        assert result is None
        # Should log info about not found
        mock_logger.info.assert_called_once()
        assert "no source package found" in str(mock_logger.info.call_args).lower()


class TestObsRepositorySecurityValidation:
    """Security-focused tests for input validation and attack prevention."""

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_handles_empty_string_package(self, mock_run: Mock) -> None:
        """Should handle empty package name gracefully."""
        # Arrange
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("", "SUSE:SLFO:Main")

        # Assert
        assert result is None
        # Should not call osc for empty package
        mock_run.assert_not_called()

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_handles_whitespace_only_package(self, mock_run: Mock) -> None:
        """Should handle whitespace-only package name gracefully."""
        # Arrange
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("   ", "SUSE:SLFO:Main")

        # Assert
        assert result is None
        # Should not call osc for whitespace-only package
        mock_run.assert_not_called()

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_validates_project_parameter(self, mock_run: Mock) -> None:
        """Should return None when project parameter is empty or whitespace."""
        # Arrange
        repo = ObsRepositoryImpl()

        # Act - empty project
        result1 = repo.get_source_package("package", "")

        # Act - whitespace only project
        result2 = repo.get_source_package("package", "   ")

        # Assert
        assert result1 is None
        assert result2 is None
        # Should not call osc for invalid project
        mock_run.assert_not_called()

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_rejects_flag_injection_in_package(self, mock_run: Mock) -> None:
        """Should reject package names starting with dashes (potential flag injection)."""
        # Arrange
        repo = ObsRepositoryImpl()

        # Act
        result1 = repo.get_source_package("--help", "SUSE:SLFO:Main")
        result2 = repo.get_source_package("-v", "SUSE:SLFO:Main")
        result3 = repo.get_source_package("  --flag", "SUSE:SLFO:Main")

        # Assert
        assert result1 is None
        assert result2 is None
        assert result3 is None
        # Should not call osc for flag-like inputs
        mock_run.assert_not_called()

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_rejects_flag_injection_in_project(self, mock_run: Mock) -> None:
        """Should reject project names starting with dashes (potential flag injection)."""
        # Arrange
        repo = ObsRepositoryImpl()

        # Act
        result1 = repo.get_source_package("package", "--help")
        result2 = repo.get_source_package("package", "-v")
        result3 = repo.get_source_package("package", "  -flag")

        # Assert
        assert result1 is None
        assert result2 is None
        assert result3 is None
        # Should not call osc for flag-like inputs
        mock_run.assert_not_called()

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_handles_timeout(self, mock_run: Mock) -> None:
        """Should handle subprocess timeout gracefully."""
        # Arrange
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("osc", 30)
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("package", "SUSE:SLFO:Main")

        # Assert
        assert result is None
        # Should have attempted to call osc with correct args
        mock_run.assert_called_once_with(
            ["osc", "-A", "https://api.suse.de", "bse", "package"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    @patch("bugowner.repositories.obs_repository.logger")
    def test_get_source_package_logs_flag_injection_attempt(
        self, mock_logger: Mock, mock_run: Mock
    ) -> None:
        """Should log warning when flag injection is detected."""
        # Arrange
        repo = ObsRepositoryImpl()

        # Act
        repo.get_source_package("--malicious", "SUSE:SLFO:Main")

        # Assert
        mock_logger.warning.assert_called_once()
        # Check that log message mentions flag injection
        call_args = str(mock_logger.warning.call_args)
        assert "flag injection" in call_args.lower()
        assert "--malicious" in call_args

    @patch("bugowner.repositories.obs_repository.subprocess.run")
    def test_get_source_package_returns_none_on_command_failure(self, mock_run: Mock) -> None:
        """Should return None when osc command fails."""
        # Arrange
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error: command failed")
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("package", "SUSE:SLFO:Main")

        # Assert
        assert result is None
