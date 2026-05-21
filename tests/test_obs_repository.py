"""Tests for OBS repository module."""

from unittest.mock import Mock, patch

from bugowner.repositories.obs_repository import ObsRepositoryImpl


class TestObsRepository:
    """Test suite for ObsRepository implementation."""

    @patch("subprocess.run")
    def test_get_source_package_returns_source_when_found(self, mock_run: Mock) -> None:
        """Should return source package name when osc bse finds a match."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0, stdout="apache2-devel | apache2 | x86_64\n", stderr=""
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result == "apache2"
        mock_run.assert_called_once_with(
            ["osc", "bse", "SUSE:SLFO:Main", "apache2-devel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    @patch("subprocess.run")
    def test_get_source_package_returns_none_when_not_found(self, mock_run: Mock) -> None:
        """Should return None when osc bse finds no match."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("nonexistent-package", "SUSE:SLFO:Main")

        # Assert
        assert result is None

    @patch("subprocess.run")
    def test_get_source_package_returns_none_on_command_failure(self, mock_run: Mock) -> None:
        """Should return None when osc command fails."""
        # Arrange
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error: command failed")
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("package", "SUSE:SLFO:Main")

        # Assert
        assert result is None

    @patch("subprocess.run")
    def test_get_source_package_parses_multiline_output(self, mock_run: Mock) -> None:
        """Should parse first line when osc returns multiple matches."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0,
            stdout="apache2-devel | apache2 | x86_64\napache2-devel | apache2 | i586\n",
            stderr="",
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result == "apache2"

    @patch("subprocess.run")
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

    @patch("subprocess.run")
    def test_get_source_package_handles_whitespace_in_output(self, mock_run: Mock) -> None:
        """Should strip whitespace from parsed source package."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0, stdout="  apache2-devel  |  apache2  |  x86_64  \n", stderr=""
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("apache2-devel", "SUSE:SLFO:Main")

        # Assert
        assert result == "apache2"

    @patch("subprocess.run")
    def test_get_source_package_handles_malformed_output(self, mock_run: Mock) -> None:
        """Should return None when output lacks pipe separators."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0, stdout="malformed-output-without-pipes", stderr=""
        )
        repo = ObsRepositoryImpl()

        # Act
        result = repo.get_source_package("package", "SUSE:SLFO:Main")

        # Assert
        assert result is None

    @patch("subprocess.run")
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

    @patch("subprocess.run")
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

    @patch("subprocess.run")
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
