"""Tests for init command."""

from pathlib import Path
from unittest.mock import Mock, patch

from bugownerctl.commands.init import run


class TestInitCommand:
    """Test init command functionality."""

    def test_init_user_location_creates_config(self, tmp_path, monkeypatch):
        """Should create config in user XDG config directory."""
        # Mock HOME to use tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))
        config_home = tmp_path / ".config" / "bugownerctl"

        # Mock bundled example
        example_content = "products:\n  - version: '16.0'\n"
        example_file = tmp_path / "example.yaml"
        example_file.write_text(example_content)

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = example_file

            args = Mock(location="user", force=False)
            exit_code = run(args)

            assert exit_code == 0
            target_file = config_home / "config.yaml"
            assert target_file.exists()
            assert target_file.read_text() == example_content

    def test_init_local_location_creates_config(self, tmp_path, monkeypatch):
        """Should create config in current directory."""
        monkeypatch.chdir(tmp_path)

        example_content = "products:\n  - version: '16.1'\n"
        example_file = tmp_path / "example.yaml"
        example_file.write_text(example_content)

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = example_file

            args = Mock(location="local", force=False)
            exit_code = run(args)

            assert exit_code == 0
            target_file = tmp_path / "validate_maintainership.yaml"
            assert target_file.exists()

    def test_init_system_location_creates_config(self, tmp_path, monkeypatch):
        """Should create config in /etc directory (mocked)."""
        # Mock the system config path to use tmp_path
        system_config = tmp_path / "etc" / "bugownerctl" / "config.yaml"

        example_content = "products:\n  - version: '16.0'\n"
        example_file = tmp_path / "example.yaml"
        example_file.write_text(example_content)

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = example_file

            with patch("bugownerctl.commands.init.Path") as mock_path_class:
                # Make Path("/etc/...") return our tmp_path version
                def path_side_effect(path_str):
                    if str(path_str).startswith("/etc"):
                        return system_config
                    return Path(path_str)

                mock_path_class.side_effect = path_side_effect

                args = Mock(location="system", force=False)
                exit_code = run(args)

                assert exit_code == 0
                assert system_config.exists()

    def test_init_refuses_overwrite_without_force(self, tmp_path, monkeypatch):
        """Should refuse to overwrite existing config without --force."""
        config_home = tmp_path / ".config" / "bugownerctl"
        config_home.mkdir(parents=True)
        existing_config = config_home / "config.yaml"
        existing_config.write_text("existing content")

        monkeypatch.setenv("HOME", str(tmp_path))

        args = Mock(location="user", force=False)
        exit_code = run(args)

        assert exit_code == 1
        assert existing_config.read_text() == "existing content"  # Unchanged

    def test_init_overwrites_with_force(self, tmp_path, monkeypatch):
        """Should overwrite existing config with --force."""
        config_home = tmp_path / ".config" / "bugownerctl"
        config_home.mkdir(parents=True)
        existing_config = config_home / "config.yaml"
        existing_config.write_text("old content")

        monkeypatch.setenv("HOME", str(tmp_path))

        new_content = "new content"
        example_file = tmp_path / "example.yaml"
        example_file.write_text(new_content)

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = example_file

            args = Mock(location="user", force=True)
            exit_code = run(args)

            assert exit_code == 0
            assert existing_config.read_text() == new_content

    def test_init_handles_permission_error(self, tmp_path, monkeypatch):
        """Should handle permission errors gracefully."""
        monkeypatch.setenv("HOME", str(tmp_path))

        example_file = tmp_path / "example.yaml"
        example_file.write_text("content")

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = example_file

            with patch("shutil.copy2", side_effect=PermissionError("Access denied")):
                args = Mock(location="user", force=False)
                exit_code = run(args)

                assert exit_code == 1

    def test_init_handles_missing_bundled_example(self, tmp_path, monkeypatch):
        """Should handle missing bundled example gracefully."""
        monkeypatch.setenv("HOME", str(tmp_path))

        # Mock files() to return a path that doesn't exist
        missing_file = tmp_path / "nonexistent.yaml"

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = missing_file

            args = Mock(location="user", force=False)
            exit_code = run(args)

            assert exit_code == 1

    def test_init_handles_invalid_location(self, tmp_path, monkeypatch):
        """Should handle invalid location gracefully."""
        monkeypatch.setenv("HOME", str(tmp_path))

        args = Mock(location="invalid", force=False)
        exit_code = run(args)

        assert exit_code == 1

    def test_init_handles_files_import_error(self, tmp_path, monkeypatch):
        """Should handle errors when locating bundled example."""
        monkeypatch.setenv("HOME", str(tmp_path))

        with patch("bugownerctl.commands.init.files", side_effect=Exception("Import failed")):
            args = Mock(location="user", force=False)
            exit_code = run(args)

            assert exit_code == 1

    def test_init_creates_parent_directory(self, tmp_path, monkeypatch):
        """Should create parent directories if they don't exist."""
        monkeypatch.setenv("HOME", str(tmp_path))

        # Don't create .config/bugownerctl directory - let init create it
        example_content = "products:\n  - version: '16.0'\n"
        example_file = tmp_path / "example.yaml"
        example_file.write_text(example_content)

        with patch("bugownerctl.commands.init.files") as mock_files:
            mock_files.return_value.joinpath.return_value = example_file

            args = Mock(location="user", force=False)
            exit_code = run(args)

            assert exit_code == 0
            config_home = tmp_path / ".config" / "bugownerctl"
            assert config_home.exists()
            assert (config_home / "config.yaml").exists()
