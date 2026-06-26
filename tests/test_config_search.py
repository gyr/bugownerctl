"""Tests for config file search hierarchy."""

import pytest

from bugownerctl.utils.config import find_config_file


class TestFindConfigFile:
    """Tests for find_config_file() search hierarchy."""

    def test_explicit_path_highest_priority(self, tmp_path):
        """CLI argument overrides all other locations."""
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("products: []")

        result = find_config_file(explicit_path=config_file)

        assert result == config_file

    def test_explicit_path_not_found_raises(self, tmp_path):
        """Explicit path that doesn't exist raises clear error."""
        missing_file = tmp_path / "missing.yaml"

        with pytest.raises(FileNotFoundError, match="specified via --config not found"):
            find_config_file(explicit_path=missing_file)

    def test_env_var_second_priority(self, tmp_path, monkeypatch):
        """BUGOWNERCTL_CONFIG env var overrides default locations."""
        config_file = tmp_path / "env-config.yaml"
        config_file.write_text("products: []")
        monkeypatch.setenv("BUGOWNERCTL_CONFIG", str(config_file))

        result = find_config_file()

        assert result == config_file

    def test_env_var_not_found_raises(self, tmp_path, monkeypatch):
        """Invalid BUGOWNERCTL_CONFIG raises clear error."""
        monkeypatch.setenv("BUGOWNERCTL_CONFIG", "/nonexistent/config.yaml")

        with pytest.raises(FileNotFoundError, match="BUGOWNERCTL_CONFIG not found"):
            find_config_file()

    def test_project_local_third_priority(self, tmp_path, monkeypatch):
        """Project-local config found in CWD."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BUGOWNERCTL_CONFIG", raising=False)
        config_file = tmp_path / "validate_maintainership.yaml"
        config_file.write_text("products: []")

        result = find_config_file()

        assert result == config_file

    def test_user_config_fourth_priority(self, tmp_path, monkeypatch):
        """User XDG config directory."""
        monkeypatch.chdir(tmp_path)  # No project-local config
        monkeypatch.delenv("BUGOWNERCTL_CONFIG", raising=False)
        user_config_dir = tmp_path / ".config" / "bugownerctl"
        user_config_dir.mkdir(parents=True)
        user_config = user_config_dir / "config.yaml"
        user_config.write_text("products: []")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        result = find_config_file()

        assert result == user_config

    def test_no_config_found_clear_error(self, tmp_path, monkeypatch):
        """No config in any location shows helpful error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BUGOWNERCTL_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        with pytest.raises(FileNotFoundError) as exc_info:
            find_config_file()

        error_msg = str(exc_info.value)
        assert "Searched locations:" in error_msg
        assert "Project directory:" in error_msg
        assert "User config (XDG):" in error_msg
        assert "System config:" in error_msg
        assert "Solutions:" in error_msg

    def test_explicit_path_overrides_env_var(self, tmp_path, monkeypatch):
        """Explicit path has higher priority than BUGOWNERCTL_CONFIG."""
        explicit_file = tmp_path / "explicit.yaml"
        explicit_file.write_text("products: []")

        env_file = tmp_path / "env.yaml"
        env_file.write_text("products: []")
        monkeypatch.setenv("BUGOWNERCTL_CONFIG", str(env_file))

        result = find_config_file(explicit_path=explicit_file)

        assert result == explicit_file.resolve()

    def test_env_var_overrides_project_local(self, tmp_path, monkeypatch):
        """BUGOWNERCTL_CONFIG has higher priority than project-local."""
        monkeypatch.chdir(tmp_path)

        env_file = tmp_path / "env.yaml"
        env_file.write_text("products: []")
        monkeypatch.setenv("BUGOWNERCTL_CONFIG", str(env_file))

        project_file = tmp_path / "validate_maintainership.yaml"
        project_file.write_text("products: []")

        result = find_config_file()

        assert result == env_file.resolve()

    def test_project_local_overrides_user_config(self, tmp_path, monkeypatch):
        """Project-local has higher priority than user XDG config."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BUGOWNERCTL_CONFIG", raising=False)

        project_file = tmp_path / "validate_maintainership.yaml"
        project_file.write_text("products: []")

        user_config_dir = tmp_path / ".config" / "bugownerctl"
        user_config_dir.mkdir(parents=True)
        user_config = user_config_dir / "config.yaml"
        user_config.write_text("products: []")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        result = find_config_file()

        assert result == project_file.resolve()

    def test_respects_xdg_config_home(self, tmp_path, monkeypatch):
        """Custom XDG_CONFIG_HOME is honored."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BUGOWNERCTL_CONFIG", raising=False)
        custom_config_dir = tmp_path / "my_config" / "bugownerctl"
        custom_config_dir.mkdir(parents=True)
        config_file = custom_config_dir / "config.yaml"
        config_file.write_text("products: []")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "my_config"))

        result = find_config_file()

        assert result == config_file.resolve()

    def test_path_normalization(self, tmp_path):
        """Path traversal attempts are normalized."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("products: []")

        # Create a path with .. traversal
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        traversal_path = subdir / ".." / "config.yaml"

        result = find_config_file(explicit_path=traversal_path)

        # Should resolve to normalized path
        assert result == config_file.resolve()
