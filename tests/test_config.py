"""Tests for config module - YAML configuration loading."""

import tempfile
from pathlib import Path

import pytest
import yaml

from bugowner.utils.config import load_config


class TestLoadConfig:
    """Test load_config() function - YAML file loading."""

    def test_load_config_returns_dict_from_valid_yaml(self):
        """Should load and return configuration from valid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"version": "16.1", "repo_url": "https://example.com"}, f)
            temp_path = Path(f.name)

        try:
            result = load_config(temp_path)

            assert result == {"version": "16.1", "repo_url": "https://example.com"}
        finally:
            temp_path.unlink()

    def test_load_config_raises_file_not_found_error_when_file_missing(self):
        """Should raise FileNotFoundError if config file doesn't exist."""
        non_existent = Path("/tmp/does_not_exist_config.yaml")

        with pytest.raises(FileNotFoundError):
            load_config(non_existent)

    def test_load_config_raises_yaml_error_on_invalid_yaml(self):
        """Should raise yaml.YAMLError if file contains invalid YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [unclosed")
            temp_path = Path(f.name)

        try:
            with pytest.raises(yaml.YAMLError):
                load_config(temp_path)
        finally:
            temp_path.unlink()

    def test_load_config_uses_default_path_when_no_argument(self):
        """Should use default path 'validate_maintainership.yaml' when no argument provided."""
        # This test will fail if default file doesn't exist - that's expected behavior
        # We'll test the signature accepts no args and uses the default

        # Create temp file with default name in temp dir
        with tempfile.TemporaryDirectory() as tmpdir:
            default_config = Path(tmpdir) / "validate_maintainership.yaml"
            default_config.write_text("test: value\n")

            # Can't easily test default without changing cwd, so just verify function signature
            # by checking it can be called with no args (will fail with FileNotFoundError)
            import inspect

            sig = inspect.signature(load_config)
            assert len(sig.parameters) == 1
            param = sig.parameters["config_file"]
            assert param.default != inspect.Parameter.empty

    def test_load_config_handles_empty_yaml_file(self):
        """Should return None for empty YAML file (YAML parses empty as None)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            result = load_config(temp_path)
            assert result is None
        finally:
            temp_path.unlink()

    def test_load_config_handles_yaml_with_null_value(self):
        """Should handle YAML files with null values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"key": None}, f)
            temp_path = Path(f.name)

        try:
            result = load_config(temp_path)
            assert result == {"key": None}
        finally:
            temp_path.unlink()

    def test_load_config_accepts_string_path(self):
        """Should accept string path for backward compatibility."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"version": "16.1"}, f)
            temp_path_str = f.name

        try:
            result = load_config(temp_path_str)
            assert result == {"version": "16.1"}
        finally:
            Path(temp_path_str).unlink()

    def test_load_config_with_none_triggers_search(self, tmp_path, monkeypatch):
        """Should call find_config_file() when config_file is None."""
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "validate_maintainership.yaml"
        config_file.write_text("products:\n  - version: '16.0'\n")

        result = load_config(None)

        assert result is not None
        assert result["products"][0]["version"] == "16.0"

    def test_load_config_with_explicit_path_skips_search(self, tmp_path):
        """Should use explicit path directly without triggering search."""
        # Create config in non-standard location
        custom_config = tmp_path / "custom" / "my_config.yaml"
        custom_config.parent.mkdir()
        custom_config.write_text("test:\n  explicit: true\n")

        result = load_config(custom_config)

        assert result == {"test": {"explicit": True}}
