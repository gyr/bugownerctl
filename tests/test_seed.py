"""Tests for seed file utilities."""

import json
from unittest.mock import patch

import pytest

from bugowner.utils.seed import bootstrap_cache_from_seed, get_seed_file_path


class TestGetSeedFilePath:
    def test_default_bundled_seed(self):
        seed_path = get_seed_file_path()
        assert seed_path.name == "false_positives.seed.json"
        assert seed_path.exists()

    def test_config_override(self, tmp_path):
        custom = tmp_path / "custom.seed.json"
        custom.write_text("{}")
        result = get_seed_file_path({"false_positives_seed": str(custom)})
        assert result == custom.resolve()

    def test_config_override_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Seed file from config"):
            get_seed_file_path({"false_positives_seed": str(tmp_path / "nope.json")})

    def test_expanduser_in_override(self, tmp_path, monkeypatch):
        custom = tmp_path / "seed.json"
        custom.write_text("{}")
        monkeypatch.setenv("HOME", str(tmp_path))
        result = get_seed_file_path({"false_positives_seed": "~/seed.json"})
        assert result == custom.resolve()

    def test_no_config_uses_bundled(self):
        result = get_seed_file_path(None)
        assert result.name == "false_positives.seed.json"

    def test_empty_config_uses_bundled(self):
        result = get_seed_file_path({})
        assert result.name == "false_positives.seed.json"

    def test_missing_bundled_seed_raises(self, tmp_path):
        missing = tmp_path / "false_positives.seed.json"
        with patch("bugowner.utils.seed.files") as mock_files:
            mock_files.return_value.joinpath.return_value = missing
            with pytest.raises(FileNotFoundError, match="Bundled seed file not found"):
                get_seed_file_path()


class TestBootstrapCacheFromSeed:
    def test_first_run_copies_seed(self, tmp_path):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"a": "x", "b": None, "c": "y"}))
        cache = tmp_path / "cache" / "false_positives.json"

        n = bootstrap_cache_from_seed(cache, seed)

        assert n == 3
        assert cache.exists()
        assert json.loads(cache.read_text()) == {"a": "x", "b": None, "c": "y"}

    def test_idempotent_when_cache_exists(self, tmp_path):
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"existing": "data"}))
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"different": "data"}))

        assert bootstrap_cache_from_seed(cache, seed) == 0
        assert json.loads(cache.read_text()) == {"existing": "data"}

    def test_missing_seed_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Seed file not found"):
            bootstrap_cache_from_seed(tmp_path / "c.json", tmp_path / "nope.json")

    def test_creates_parent_dirs(self, tmp_path):
        seed = tmp_path / "seed.json"
        seed.write_text("{}")
        cache = tmp_path / "deeply" / "nested" / "cache.json"

        bootstrap_cache_from_seed(cache, seed)

        assert cache.exists()
        assert cache.parent.is_dir()

    def test_empty_seed_returns_zero_entries(self, tmp_path):
        seed = tmp_path / "seed.json"
        seed.write_text("{}")
        cache = tmp_path / "cache.json"

        n = bootstrap_cache_from_seed(cache, seed)

        assert n == 0
        assert cache.exists()

    def test_dangling_symlink_at_cache_is_skipped(self, tmp_path):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"a": "b"}))
        arbitrary_target = tmp_path / "other.json"  # does not exist
        cache = tmp_path / "cache.json"
        cache.symlink_to(arbitrary_target)

        # Should not follow the symlink and write to arbitrary_target
        assert bootstrap_cache_from_seed(cache, seed) == 0
        assert not arbitrary_target.exists()

    def test_seed_content_preserved_exactly(self, tmp_path):
        data = {"pkg-bin": "pkg-src", "other-bin": None}
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps(data))
        cache = tmp_path / "cache.json"

        bootstrap_cache_from_seed(cache, seed)

        assert json.loads(cache.read_text()) == data
