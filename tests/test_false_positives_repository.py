"""Tests for FalsePositivesRepository - binary→source package mapping cache."""

import contextlib
import json
import tempfile
from pathlib import Path

import pytest

from bugowner.repositories.false_positives_repository import (
    FalsePositivesRepositoryImpl,
)


class TestLoad:
    """Test load() method - loading cached mappings from file."""

    def test_load_returns_empty_dict_when_file_does_not_exist(self):
        """Should return empty dict if file doesn't exist."""
        repo = FalsePositivesRepositoryImpl()
        non_existent = Path("/tmp/does_not_exist_12345.json")

        result = repo.load(non_existent)

        assert result == {}

    def test_load_returns_mappings_from_valid_json_file(self):
        """Should load and return binary→source mappings from JSON file."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            mappings = {
                "apache2-devel": "apache2",
                "apache2-utils": "apache2",
                "SLES-release": None,
            }
            json.dump(mappings, f)
            temp_path = Path(f.name)

        try:
            result = repo.load(temp_path)

            assert result == {
                "apache2-devel": "apache2",
                "apache2-utils": "apache2",
                "SLES-release": None,
            }
        finally:
            temp_path.unlink()

    def test_load_raises_json_decode_error_on_invalid_json(self):
        """Should raise JSONDecodeError if file contains invalid JSON."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json content }")
            temp_path = Path(f.name)

        try:
            with pytest.raises(json.JSONDecodeError):
                repo.load(temp_path)
        finally:
            temp_path.unlink()

    def test_load_handles_empty_json_object(self):
        """Should return empty dict for file containing empty JSON object."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            temp_path = Path(f.name)

        try:
            result = repo.load(temp_path)
            assert result == {}
        finally:
            temp_path.unlink()

    def test_load_rejects_relative_path(self):
        """Should raise ValueError for relative paths (security: path traversal)."""
        repo = FalsePositivesRepositoryImpl()
        relative_path = Path("relative/path.json")

        with pytest.raises(ValueError, match="File path must be absolute"):
            repo.load(relative_path)

    def test_load_rejects_file_too_large(self):
        """Should raise ValueError for files exceeding size limit (security: DoS)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Create a file larger than 10 MB
            large_data = {"package" + str(i): "source" for i in range(500000)}
            json.dump(large_data, f)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Cache file too large"):
                repo.load(temp_path)
        finally:
            temp_path.unlink()


class TestSave:
    """Test save() method - persisting mappings to file."""

    def test_save_creates_file_with_mappings(self):
        """Should create file with JSON mappings."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            mappings = {
                "apache2-devel": "apache2",
                "SLES-release": None,
            }
            repo.save(temp_path, mappings)

            # Verify file exists and contains correct data
            assert temp_path.exists()
            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded == mappings
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_writes_sorted_json_for_consistent_diffs(self):
        """Should write JSON with sorted keys for git-friendly diffs."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Provide unsorted mappings
            mappings = {
                "zebra-package": "zebra",
                "apache2-devel": "apache2",
                "mysql-client": "mysql",
            }
            repo.save(temp_path, mappings)

            # Read raw file content to check ordering
            content = temp_path.read_text()

            # Keys should appear in alphabetical order
            assert content.index("apache2-devel") < content.index("mysql-client")
            assert content.index("mysql-client") < content.index("zebra-package")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_overwrites_existing_file(self):
        """Should overwrite existing file with new mappings."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"old-package": "old-source"}, f)
            temp_path = Path(f.name)

        try:
            new_mappings = {"new-package": "new-source"}
            repo.save(temp_path, new_mappings)

            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded == new_mappings
            assert "old-package" not in loaded
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_handles_empty_mappings(self):
        """Should save empty dict as empty JSON object."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            repo.save(temp_path, {})

            with open(temp_path) as f:
                loaded = json.load(f)
            assert loaded == {}
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_rejects_relative_path(self):
        """Should raise ValueError for relative paths (security: path traversal)."""
        repo = FalsePositivesRepositoryImpl()
        relative_path = Path("relative/path.json")

        with pytest.raises(ValueError, match="File path must be absolute"):
            repo.save(relative_path, {"pkg": "src"})

    def test_save_rejects_symlink(self):
        """Should raise ValueError for symlinks (security: symlink attack)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target.json"
            symlink = Path(tmpdir) / "symlink.json"
            target.write_text("{}")
            symlink.symlink_to(target)

            with pytest.raises(ValueError, match="Refusing to write to symlink"):
                repo.save(symlink, {"pkg": "src"})

    def test_save_rejects_non_dict_mappings(self):
        """Should raise TypeError for non-dict mappings (security: type validation)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            invalid_mappings = ["list", "of", "items"]  # type: ignore
            with pytest.raises(TypeError, match="mappings must be a dict"):
                repo.save(temp_path, invalid_mappings)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_rejects_invalid_key_type(self):
        """Should raise TypeError for non-string keys (security: data validation)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            invalid_mappings = {123: "value"}  # type: ignore
            with pytest.raises(TypeError, match="All keys must be strings"):
                repo.save(temp_path, invalid_mappings)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_rejects_invalid_value_type(self):
        """Should raise TypeError for non-string/None values (security: data validation)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            invalid_mappings = {"key": 123}  # type: ignore
            with pytest.raises(TypeError, match="All values must be str or None"):
                repo.save(temp_path, invalid_mappings)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_rejects_key_too_long(self):
        """Should raise ValueError for excessively long keys (security: DoS)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            long_key = "a" * 1001  # Over 1000 char limit
            with pytest.raises(ValueError, match="Key too long"):
                repo.save(temp_path, {long_key: "value"})
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_rejects_value_too_long(self):
        """Should raise ValueError for excessively long values (security: DoS)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            long_value = "a" * 1001  # Over 1000 char limit
            with pytest.raises(ValueError, match="Value too long"):
                repo.save(temp_path, {"key": long_value})
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_sets_restrictive_permissions(self):
        """Should set 600 permissions on saved file (security: file permissions)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            repo.save(temp_path, {"pkg": "src"})

            # Check file permissions (600 = owner read/write only)
            import stat

            mode = temp_path.stat().st_mode
            assert stat.S_IMODE(mode) == 0o600
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_save_cleans_up_temp_file_on_error(self):
        """Should remove temp file if write fails (security: cleanup)."""
        repo = FalsePositivesRepositoryImpl()

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "test.json"

            # Trigger error after temp file created (invalid data type)
            invalid_mappings = {"key": ["list"]}  # type: ignore
            with contextlib.suppress(TypeError):
                repo.save(temp_path, invalid_mappings)

            # Verify temp file was cleaned up
            temp_file = temp_path.with_name(f".{temp_path.name}.tmp")
            assert not temp_file.exists()


class TestApplyRemapping:
    """Test apply_remapping() method - applying binary→source transformations."""

    def test_apply_remapping_replaces_binary_with_source_name(self):
        """Should replace binary package names with source package names."""
        repo = FalsePositivesRepositoryImpl()

        packages = {"apache2-devel", "apache2-utils", "kernel"}
        mappings = {
            "apache2-devel": "apache2",
            "apache2-utils": "apache2",
        }

        result = repo.apply_remapping(packages, mappings)

        assert result == {"apache2", "kernel"}

    def test_apply_remapping_filters_out_none_mappings(self):
        """Should exclude packages that map to None (ignored packages)."""
        repo = FalsePositivesRepositoryImpl()

        packages = {"apache2", "SLES-release", "kernel"}
        mappings = {
            "SLES-release": None,
        }

        result = repo.apply_remapping(packages, mappings)

        assert result == {"apache2", "kernel"}
        assert "SLES-release" not in result

    def test_apply_remapping_keeps_unmapped_packages(self):
        """Should keep packages that have no mapping entry."""
        repo = FalsePositivesRepositoryImpl()

        packages = {"apache2", "kernel", "gcc"}
        mappings = {
            "apache2": "apache-httpd",
        }

        result = repo.apply_remapping(packages, mappings)

        assert result == {"apache-httpd", "kernel", "gcc"}

    def test_apply_remapping_with_empty_mappings(self):
        """Should return original packages when mappings is empty."""
        repo = FalsePositivesRepositoryImpl()

        packages = {"apache2", "kernel"}
        mappings = {}

        result = repo.apply_remapping(packages, mappings)

        assert result == {"apache2", "kernel"}

    def test_apply_remapping_with_empty_packages(self):
        """Should return empty set when packages is empty."""
        repo = FalsePositivesRepositoryImpl()

        packages = set()
        mappings = {"apache2-devel": "apache2"}

        result = repo.apply_remapping(packages, mappings)

        assert result == set()

    def test_apply_remapping_deduplicates_after_mapping(self):
        """Should deduplicate when multiple binaries map to same source."""
        repo = FalsePositivesRepositoryImpl()

        # Multiple binary packages mapping to same source
        packages = {"apache2-devel", "apache2-utils", "apache2-doc"}
        mappings = {
            "apache2-devel": "apache2",
            "apache2-utils": "apache2",
            "apache2-doc": "apache2",
        }

        result = repo.apply_remapping(packages, mappings)

        # Should deduplicate to single source package
        assert result == {"apache2"}


class TestMergeMappings:
    """Test merge_mappings() method - combining existing and new discoveries."""

    def test_merge_mappings_combines_existing_and_new(self):
        """Should merge existing cache with new OBS discoveries."""
        repo = FalsePositivesRepositoryImpl()

        existing = {
            "apache2-devel": "apache2",
            "SLES-release": None,
        }
        new_discoveries = {
            "mysql-client": "mysql",
            "kernel-devel": "kernel-default",
        }

        result = repo.merge_mappings(existing, new_discoveries)

        assert result == {
            "apache2-devel": "apache2",
            "SLES-release": None,
            "mysql-client": "mysql",
            "kernel-devel": "kernel-default",
        }

    def test_merge_mappings_new_overrides_existing(self):
        """Should let new discoveries override existing mappings."""
        repo = FalsePositivesRepositoryImpl()

        existing = {
            "apache2-devel": "apache2-old",
        }
        new_discoveries = {
            "apache2-devel": "apache2-new",
        }

        result = repo.merge_mappings(existing, new_discoveries)

        assert result["apache2-devel"] == "apache2-new"

    def test_merge_mappings_with_empty_existing(self):
        """Should return new discoveries when existing is empty."""
        repo = FalsePositivesRepositoryImpl()

        existing = {}
        new_discoveries = {"mysql-client": "mysql"}

        result = repo.merge_mappings(existing, new_discoveries)

        assert result == {"mysql-client": "mysql"}

    def test_merge_mappings_with_empty_new_discoveries(self):
        """Should return existing when new discoveries is empty."""
        repo = FalsePositivesRepositoryImpl()

        existing = {"apache2-devel": "apache2"}
        new_discoveries = {}

        result = repo.merge_mappings(existing, new_discoveries)

        assert result == {"apache2-devel": "apache2"}

    def test_merge_mappings_preserves_none_values(self):
        """Should preserve None values from existing mappings."""
        repo = FalsePositivesRepositoryImpl()

        existing = {
            "SLES-release": None,
            "apache2-devel": "apache2",
        }
        new_discoveries = {
            "mysql-client": "mysql",
        }

        result = repo.merge_mappings(existing, new_discoveries)

        assert result["SLES-release"] is None
        assert result["apache2-devel"] == "apache2"
        assert result["mysql-client"] == "mysql"
