"""Tests for file_utils module - JSON file I/O utilities."""

import json
import tempfile
from pathlib import Path

import pytest

from src.bugowner.utils.file_utils import load_json, save_json


class TestLoadJson:
    """Test load_json() function - JSON file loading."""

    def test_load_json_returns_data_from_valid_json_file(self):
        """Should load and return data from valid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value", "number": 42}, f)
            temp_path = Path(f.name)

        try:
            result = load_json(temp_path)

            assert result == {"key": "value", "number": 42}
        finally:
            temp_path.unlink()

    def test_load_json_handles_list_data(self):
        """Should load JSON arrays as lists."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([1, 2, 3, "test"], f)
            temp_path = Path(f.name)

        try:
            result = load_json(temp_path)

            assert result == [1, 2, 3, "test"]
        finally:
            temp_path.unlink()

    def test_load_json_handles_nested_structures(self):
        """Should load nested JSON structures."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"outer": {"inner": [1, 2, {"deep": "value"}]}}
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            result = load_json(temp_path)

            assert result == data
        finally:
            temp_path.unlink()

    def test_load_json_raises_file_not_found_error_when_file_missing(self):
        """Should raise FileNotFoundError if JSON file doesn't exist."""
        non_existent = Path("/tmp/does_not_exist_file.json")

        with pytest.raises(FileNotFoundError):
            load_json(non_existent)

    def test_load_json_raises_json_decode_error_on_invalid_json(self):
        """Should raise json.JSONDecodeError if file contains invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json content}")
            temp_path = Path(f.name)

        try:
            with pytest.raises(json.JSONDecodeError):
                load_json(temp_path)
        finally:
            temp_path.unlink()

    def test_load_json_handles_empty_json_object(self):
        """Should return empty dict for empty JSON object."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            temp_path = Path(f.name)

        try:
            result = load_json(temp_path)
            assert result == {}
        finally:
            temp_path.unlink()

    def test_load_json_handles_null_value(self):
        """Should return None for JSON null."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("null")
            temp_path = Path(f.name)

        try:
            result = load_json(temp_path)
            assert result is None
        finally:
            temp_path.unlink()

    def test_load_json_accepts_string_path(self):
        """Should accept string path for backward compatibility."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "data"}, f)
            temp_path_str = f.name

        try:
            result = load_json(temp_path_str)
            assert result == {"test": "data"}
        finally:
            Path(temp_path_str).unlink()


class TestSaveJson:
    """Test save_json() function - JSON file saving."""

    def test_save_json_creates_file_with_data(self):
        """Should create file with JSON data."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            data = {"key": "value", "number": 42}
            save_json(temp_path, data)

            # Verify file exists and contains correct data
            assert temp_path.exists()
            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_writes_sorted_keys_by_default(self):
        """Should write JSON with sorted keys by default."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Provide unsorted data
            data = {"zebra": 1, "apple": 2, "middle": 3}
            save_json(temp_path, data)

            # Read raw file content to check ordering
            content = temp_path.read_text()

            # Keys should appear in alphabetical order
            assert content.index("apple") < content.index("middle")
            assert content.index("middle") < content.index("zebra")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_respects_sorted_keys_false(self):
        """Should preserve insertion order when sorted_keys=False."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Python 3.7+ dicts preserve insertion order
            data = {"zebra": 1, "apple": 2, "middle": 3}
            save_json(temp_path, data, sorted_keys=False)

            # Should preserve insertion order (not sorted)
            content = temp_path.read_text()

            # zebra should come before apple (insertion order)
            assert content.index("zebra") < content.index("apple")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_handles_list_data(self):
        """Should save lists as JSON arrays."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            data = [1, 2, 3, "test"]
            save_json(temp_path, data)

            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_overwrites_existing_file(self):
        """Should overwrite existing file with new data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"old": "data"}, f)
            temp_path = Path(f.name)

        try:
            new_data = {"new": "data"}
            save_json(temp_path, new_data)

            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded == new_data
            assert "old" not in loaded
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_handles_none_value(self):
        """Should save None as JSON null."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            save_json(temp_path, None)

            content = temp_path.read_text()
            assert "null" in content

            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded is None
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_formats_with_indentation(self):
        """Should format JSON with indentation for readability."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            data = {"key": {"nested": "value"}}
            save_json(temp_path, data)

            content = temp_path.read_text()

            # Should have indentation (not single line)
            assert "\n" in content
            assert "  " in content or "\t" in content
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_json_accepts_string_path(self):
        """Should accept string path for backward compatibility."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path_str = f.name

        try:
            data = {"test": "data"}
            save_json(temp_path_str, data)

            # Verify file was written correctly
            with open(temp_path_str) as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            temp_path = Path(temp_path_str)
            if temp_path.exists():
                temp_path.unlink()
