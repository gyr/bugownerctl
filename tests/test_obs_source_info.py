"""Tests for ObsSourceInfo domain value object."""

from datetime import UTC, datetime

import pytest

from bugownerctl.domain.obs_source_info import ObsSourceInfo


class TestObsSourceInfo:
    """Tests for ObsSourceInfo value object."""

    def test_source_info_exposes_constructor_fields(self):
        """ObsSourceInfo should expose mapping, project, fetched_at, and packages."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        bm = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
            packages=frozenset({"apache2"}),
        )
        assert bm.mapping == {"apache2-devel": "apache2"}
        assert bm.project == "SUSE:SLFO:Main"
        assert bm.fetched_at == fetched
        assert bm.packages == frozenset({"apache2"})

    def test_source_info_is_frozen(self):
        """ObsSourceInfo should be immutable (frozen dataclass)."""
        bm = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            packages=frozenset(),
        )
        with pytest.raises((AttributeError, TypeError)):
            bm.project = "openSUSE:Factory"

    def test_entry_count_matches_len_of_mapping(self):
        """entry_count should equal len(mapping) for non-empty mapping."""
        bm = ObsSourceInfo(
            mapping={"apache2-devel": "apache2", "libapr1": "apr"},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            packages=frozenset(),
        )
        assert bm.entry_count == 2
        assert bm.entry_count == len(bm.mapping)

    def test_entry_count_zero_for_empty_mapping(self):
        """entry_count should be 0 for empty mapping."""
        bm = ObsSourceInfo(
            mapping={},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            packages=frozenset(),
        )
        assert bm.entry_count == 0

    def test_source_info_equality(self):
        """Two ObsSourceInfo instances with identical fields should be equal."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        bm1 = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
            packages=frozenset(),
        )
        bm2 = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
            packages=frozenset(),
        )
        assert bm1 == bm2

    def test_source_info_inequality_different_project(self):
        """ObsSourceInfo instances with different project should not be equal."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        bm1 = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
            packages=frozenset(),
        )
        bm2 = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="openSUSE:Factory",
            fetched_at=fetched,
            packages=frozenset(),
        )
        assert bm1 != bm2

    def test_source_info_inequality_different_mapping(self):
        """ObsSourceInfo instances with different mapping should not be equal."""
        fetched = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        bm1 = ObsSourceInfo(
            mapping={"apache2-devel": "apache2"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
            packages=frozenset(),
        )
        bm2 = ObsSourceInfo(
            mapping={"libapr1": "apr"},
            project="SUSE:SLFO:Main",
            fetched_at=fetched,
            packages=frozenset(),
        )
        assert bm1 != bm2

    def test_mapping_lookup_returns_canonical_source(self):
        """Mapping should resolve binary/subpackage name to source package."""
        bm = ObsSourceInfo(
            mapping={"apache2-devel": "apache2", "libapr1": "apr"},
            project="SUSE:SLFO:Main",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            packages=frozenset(),
        )
        assert bm.mapping["apache2-devel"] == "apache2"
        assert bm.mapping["libapr1"] == "apr"
