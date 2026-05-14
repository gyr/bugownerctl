import json
import tempfile
from pathlib import Path
import pytest
from validate_maintainership import get_maintainer_data


class TestGetMaintainerData:
    """Tests for get_maintainer_data function with new format."""

    def test_parse_new_format_with_users_only(self):
        """Test parsing new format with only users."""
        new_format_data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "package1": {"groups": [], "users": ["user1", "user2"]},
                "package2": {"groups": [], "users": ["user3"]},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(new_format_data, tmp)
            tmp_path = tmp.name

        try:
            result = get_maintainer_data(tmp_path)

            assert result == {
                "package1": ["user1", "user2"],
                "package2": ["user3"],
            }
        finally:
            Path(tmp_path).unlink()

    def test_parse_new_format_with_groups_only(self):
        """Test parsing new format with only groups."""
        new_format_data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "package1": {"groups": ["group1"], "users": []},
                "package2": {"groups": ["group2", "group3"], "users": []},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(new_format_data, tmp)
            tmp_path = tmp.name

        try:
            result = get_maintainer_data(tmp_path)

            assert result == {
                "package1": ["group1"],
                "package2": ["group2", "group3"],
            }
        finally:
            Path(tmp_path).unlink()

    def test_parse_new_format_with_users_and_groups(self):
        """Test parsing new format with both users and groups."""
        new_format_data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "package1": {"groups": ["group1"], "users": ["user1"]},
                "package2": {"groups": ["group2"], "users": ["user2", "user3"]},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(new_format_data, tmp)
            tmp_path = tmp.name

        try:
            result = get_maintainer_data(tmp_path)

            assert result == {
                "package1": ["user1", "group1"],
                "package2": ["user2", "user3", "group2"],
            }
        finally:
            Path(tmp_path).unlink()

    def test_parse_new_format_with_empty_maintainers(self):
        """Test parsing new format with packages that have no maintainers."""
        new_format_data = {
            "header": {"document": "obs-maintainers", "version": "1.0"},
            "packages": {
                "package1": {"groups": [], "users": []},
                "package2": {"groups": ["group1"], "users": ["user1"]},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(new_format_data, tmp)
            tmp_path = tmp.name

        try:
            result = get_maintainer_data(tmp_path)

            assert result == {
                "package1": [],
                "package2": ["user1", "group1"],
            }
        finally:
            Path(tmp_path).unlink()

    def test_file_not_found(self):
        """Test that FileNotFoundError is raised for non-existent file."""
        with pytest.raises(FileNotFoundError):
            get_maintainer_data("/nonexistent/path/file.json")

    def test_invalid_json(self):
        """Test that JSONDecodeError is raised for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp.write("{ invalid json }")
            tmp_path = tmp.name

        try:
            with pytest.raises(json.JSONDecodeError):
                get_maintainer_data(tmp_path)
        finally:
            Path(tmp_path).unlink()
