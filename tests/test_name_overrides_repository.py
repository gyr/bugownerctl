"""Tests for NameOverridesRepository.

Phase 3 of the OBS source-name resolution refactor. The overrides file is a
hand-curated `binary_name → source_name | None` JSON used by the Phase 4
service to short-circuit the bulk-map lookup for cases the bulk map gets
wrong (e.g. kernel-azure cycles).

Tests cover:
  - Protocol shape.
  - Missing-file path returns empty mapping (NOT FileNotFoundError).
  - Input validation (absolute path, size cap, JSON root shape, value types).
  - Null values preserved as None.
  - Real shipped overrides file is loadable and contains the expected entry.
"""

from importlib.resources import files
from pathlib import Path

import pytest

from bugownerctl.repositories.name_overrides_repository import (
    MAX_OVERRIDES_BYTES,
    NameOverridesRepository,
    NameOverridesRepositoryImpl,
)

# ---------------------------------------------------------------------------
# Protocol


class TestProtocol:
    def test_impl_satisfies_protocol(self) -> None:
        """NameOverridesRepositoryImpl satisfies the protocol via runtime_checkable."""
        assert isinstance(NameOverridesRepositoryImpl(), NameOverridesRepository)


# ---------------------------------------------------------------------------
# Loading behavior


class TestLoad:
    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent overrides path returns {} (empty overrides are valid)."""
        repo = NameOverridesRepositoryImpl()
        result = repo.load(tmp_path / "does_not_exist.json")
        assert result == {}

    def test_load_returns_empty_when_path_is_directory(self, tmp_path: Path) -> None:
        """Path that exists but is a directory is treated like a missing file.

        Guards against IsADirectoryError leaking out of read_text() — the
        docstring promises ValueError for validation failures and {} for the
        missing-file branch, so a directory must take the missing-file branch
        rather than raise an unrelated OSError subclass.
        """
        repo = NameOverridesRepositoryImpl()
        # tmp_path itself is an existing directory; pass it directly.
        result = repo.load(tmp_path)
        assert result == {}

    def test_load_empty_file_returns_empty(self, tmp_path: Path) -> None:
        """A file whose JSON root is {} returns {}."""
        path = tmp_path / "overrides.json"
        path.write_text("{}", encoding="utf-8")
        repo = NameOverridesRepositoryImpl()
        result = repo.load(path)
        assert result == {}

    def test_load_rejects_relative_path(self) -> None:
        """Relative file paths are rejected with ValueError."""
        repo = NameOverridesRepositoryImpl()
        with pytest.raises(ValueError, match="absolute"):
            repo.load(Path("overrides.json"))

    def test_load_rejects_oversize_file(self, tmp_path: Path) -> None:
        """Files larger than MAX_OVERRIDES_BYTES are rejected before parsing.

        Mirrors test_load_bulk_map_rejects_oversized_xml: use multiplication
        to synthesize the body, never allocate a real megabyte in test data.
        """
        path = tmp_path / "overrides.json"
        # Pad inside a JSON string value so the file is still syntactically
        # valid JSON; the size check must fire BEFORE json.loads, so this
        # passes/fails on size alone.
        body = b'{"x": "' + b"a" * (MAX_OVERRIDES_BYTES + 1) + b'"}'
        path.write_bytes(body)
        repo = NameOverridesRepositoryImpl()
        with pytest.raises(ValueError, match="exceeds|size"):
            repo.load(path)

    def test_load_rejects_non_object_root(self, tmp_path: Path) -> None:
        """JSON root must be an object (dict); arrays or scalars are rejected."""
        path = tmp_path / "overrides.json"
        path.write_text("[]", encoding="utf-8")
        repo = NameOverridesRepositoryImpl()
        with pytest.raises(ValueError, match="object|dict|mapping"):
            repo.load(path)

    def test_load_rejects_non_string_values(self, tmp_path: Path) -> None:
        """Override values must be str or None; numbers, lists, dicts rejected.

        (The plan named this test ``rejects_non_string_keys`` but JSON keys are
        always strings by spec; the actual contract is on values. Renamed to
        match the body.)
        """
        repo = NameOverridesRepositoryImpl()

        # Numeric value
        bad_num = tmp_path / "bad_num.json"
        bad_num.write_text('{"foo": 5}', encoding="utf-8")
        with pytest.raises(ValueError, match="value|str|None"):
            repo.load(bad_num)

        # List value
        bad_list = tmp_path / "bad_list.json"
        bad_list.write_text('{"foo": ["a"]}', encoding="utf-8")
        with pytest.raises(ValueError, match="value|str|None"):
            repo.load(bad_list)

        # Nested-object value
        bad_obj = tmp_path / "bad_obj.json"
        bad_obj.write_text('{"foo": {"nested": "x"}}', encoding="utf-8")
        with pytest.raises(ValueError, match="value|str|None"):
            repo.load(bad_obj)

        # Boolean value
        bad_bool = tmp_path / "bad_bool.json"
        bad_bool.write_text('{"foo": true}', encoding="utf-8")
        with pytest.raises(ValueError, match="value|str|None"):
            repo.load(bad_bool)

    def test_load_tolerates_utf8_bom(self, tmp_path: Path) -> None:
        """Files prefixed with a UTF-8 BOM parse successfully.

        Human-edited overrides files saved by some editors (notably on
        Windows) carry a leading b'\\xef\\xbb\\xbf'. Plain utf-8 decoding
        preserves the BOM as U+FEFF, which then crashes json.loads. The
        utf-8-sig codec strips the BOM if present and is a no-op otherwise.
        """
        path = tmp_path / "overrides.json"
        path.write_bytes(b"\xef\xbb\xbf" + b'{"foo": "bar"}')
        repo = NameOverridesRepositoryImpl()
        result = repo.load(path)
        assert result == {"foo": "bar"}

    def test_load_returns_mapping_with_null_values_preserved(self, tmp_path: Path) -> None:
        """JSON null becomes Python None; strings pass through verbatim."""
        path = tmp_path / "overrides.json"
        path.write_text('{"foo": null, "bar": "baz"}', encoding="utf-8")
        repo = NameOverridesRepositoryImpl()
        result = repo.load(path)
        assert result == {"foo": None, "bar": "baz"}

    def test_load_returns_kernel_azure_override_from_shipped_file(self) -> None:
        """The real overrides file shipped in the wheel contains kernel-azure.

        Resolved via importlib.resources so it works from a source checkout
        and from an installed wheel alike.
        """
        resource = files("bugownerctl.data") / "false_positives_overrides.json"
        # importlib.resources.files returns a Traversable; for a file in a
        # regular package it is backed by a real Path. as_file() handles
        # the zipped-wheel case too.
        from importlib.resources import as_file

        with as_file(resource) as path:
            repo = NameOverridesRepositoryImpl()
            result = repo.load(path)
        assert result["kernel-azure"] == "kernel-source-azure"
