"""Tests for Maintainer domain models."""

import pytest

from bugownerctl.domain.maintainer import Maintainer, MaintainershipData


class TestMaintainer:
    """Tests for Maintainer value object."""

    def test_maintainer_has_name_and_is_group(self):
        """Maintainer should have name and is_group attributes."""
        maintainer = Maintainer(name="user1", is_group=False)
        assert maintainer.name == "user1"
        assert maintainer.is_group is False

    def test_maintainer_group(self):
        """Maintainer should support groups."""
        group = Maintainer(name="group:web", is_group=True)
        assert group.name == "group:web"
        assert group.is_group is True

    def test_maintainer_is_frozen(self):
        """Maintainer should be immutable (frozen dataclass)."""
        maintainer = Maintainer(name="user1", is_group=False)
        with pytest.raises((AttributeError, TypeError)):
            maintainer.name = "user2"

    def test_maintainer_equality(self):
        """Two maintainers with same data should be equal."""
        m1 = Maintainer(name="user1", is_group=False)
        m2 = Maintainer(name="user1", is_group=False)
        assert m1 == m2

    def test_maintainer_inequality_different_name(self):
        """Maintainers with different names should not be equal."""
        m1 = Maintainer(name="user1", is_group=False)
        m2 = Maintainer(name="user2", is_group=False)
        assert m1 != m2

    def test_maintainer_inequality_different_is_group(self):
        """Maintainers with different is_group should not be equal."""
        m1 = Maintainer(name="web", is_group=False)
        m2 = Maintainer(name="web", is_group=True)
        assert m1 != m2

    def test_maintainer_can_be_used_in_set(self):
        """Maintainer should be hashable for use in sets."""
        m1 = Maintainer(name="user1", is_group=False)
        m2 = Maintainer(name="user2", is_group=False)
        m3 = Maintainer(name="user1", is_group=False)
        maintainers = {m1, m2, m3}
        assert len(maintainers) == 2  # m1 and m3 are duplicates


class TestMaintainershipData:
    """Tests for MaintainershipData."""

    def test_maintainership_data_has_packages_dict(self):
        """MaintainershipData should have packages dictionary."""
        data = MaintainershipData(packages={"apache2": ["user1", "group:web"]})
        assert data.packages == {"apache2": ["user1", "group:web"]}

    def test_maintainership_data_empty_packages(self):
        """MaintainershipData should accept empty packages dict."""
        data = MaintainershipData(packages={})
        assert data.packages == {}

    def test_maintainership_data_multiple_packages(self):
        """MaintainershipData should handle multiple packages."""
        data = MaintainershipData(
            packages={
                "apache2": ["user1", "group:web"],
                "nginx": ["user2"],
                "kernel": ["user3", "user4", "group:kernel"],
            }
        )
        assert len(data.packages) == 3
        assert data.packages["apache2"] == ["user1", "group:web"]
        assert data.packages["nginx"] == ["user2"]
        assert data.packages["kernel"] == ["user3", "user4", "group:kernel"]

    def test_maintainership_data_is_mutable(self):
        """MaintainershipData should be mutable (not frozen)."""
        data = MaintainershipData(packages={"apache2": ["user1"]})
        # Should be able to modify packages dict
        data.packages["nginx"] = ["user2"]
        assert "nginx" in data.packages
        assert data.packages["nginx"] == ["user2"]

    def test_maintainership_data_equality(self):
        """Two MaintainershipData with same packages should be equal."""
        data1 = MaintainershipData(packages={"apache2": ["user1"]})
        data2 = MaintainershipData(packages={"apache2": ["user1"]})
        assert data1 == data2

    def test_maintainership_data_inequality(self):
        """MaintainershipData with different packages should not be equal."""
        data1 = MaintainershipData(packages={"apache2": ["user1"]})
        data2 = MaintainershipData(packages={"nginx": ["user2"]})
        assert data1 != data2
