"""Tests for BulkMap domain value object."""

from datetime import datetime, timezone

import pytest

from bugownerctl.domain.bulk_map import BulkMap


class TestBulkMap:
    """Tests for BulkMap value object."""

    def test_bulk_map_exposes_constructor_fields(self):
        """BulkMap should expose mapping, project, and fetched_at."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        bm = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
        )
        assert bm.mapping == {"apache2-devel": "apache2"}
        assert bm.project == "SUSE:SLFO:Main"
        assert bm.fetched_at == fetched

    def test_bulk_map_is_frozen(self):
        """BulkMap should be immutable (frozen dataclass)."""
        bm = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises((AttributeError, TypeError)):
            bm.project = "openSUSE:Factory"

    def test_entry_count_matches_len_of_mapping(self):
        """entry_count should equal len(mapping) for non-empty mapping."""
        bm = BulkMap(
            mapping={"apache2-devel": "apache2", "libapr1": "apr"},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert bm.entry_count == 2
        assert bm.entry_count == len(bm.mapping)

    def test_entry_count_zero_for_empty_mapping(self):
        """entry_count should be 0 for empty mapping."""
        bm = BulkMap(
            mapping={},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert bm.entry_count == 0

    def test_bulk_map_equality(self):
        """Two BulkMaps with identical fields should be equal."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        bm1 = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
        )
        bm2 = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
        )
        assert bm1 == bm2

    def test_bulk_map_inequality_different_project(self):
        """BulkMaps with different project should not be equal."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        bm1 = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
        )
        bm2 = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="openSUSE:Factory",
            fetched_at=fetched,
        )
        assert bm1 != bm2

    def test_bulk_map_inequality_different_mapping(self):
        """BulkMaps with different mapping should not be equal."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        bm1 = BulkMap(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
        )
        bm2 = BulkMap(
            mapping={"libapr1": "apr"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
        )
        assert bm1 != bm2

    def test_mapping_lookup_returns_canonical_source(self):
        """Mapping should resolve binary/subpackage name to source package."""
        bm = BulkMap(
            mapping={"apache2-devel": "apache2", "libapr1": "apr"},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert bm.mapping["apache2-devel"] == "apache2"
        assert bm.mapping["libapr1"] == "apr"
