"""Tests for Package domain models."""

import pytest

from bugownerctl.domain.package import MaintainedPackage, Package


class TestPackage:
    """Tests for Package value object."""

    def test_package_has_name_attribute(self):
        """Package should have a name attribute."""
        pkg = Package(name="apache2")
        assert pkg.name == "apache2"

    def test_package_is_frozen(self):
        """Package should be immutable (frozen dataclass)."""
        pkg = Package(name="apache2")
        with pytest.raises((AttributeError, TypeError)):
            pkg.name = "nginx"

    def test_package_equality_by_name(self):
        """Two packages with same name should be equal."""
        pkg1 = Package(name="apache2")
        pkg2 = Package(name="apache2")
        assert pkg1 == pkg2

    def test_package_inequality_different_names(self):
        """Two packages with different names should not be equal."""
        pkg1 = Package(name="apache2")
        pkg2 = Package(name="nginx")
        assert pkg1 != pkg2

    def test_package_can_be_used_in_set(self):
        """Package should be hashable for use in sets."""
        pkg1 = Package(name="apache2")
        pkg2 = Package(name="nginx")
        pkg3 = Package(name="apache2")
        packages = {pkg1, pkg2, pkg3}
        assert len(packages) == 2  # pkg1 and pkg3 are duplicates

    def test_package_string_representation(self):
        """Package should have readable string representation."""
        pkg = Package(name="apache2")
        assert "apache2" in str(pkg)


class TestMaintainedPackage:
    """Tests for MaintainedPackage value object."""

    def test_maintained_package_has_name_and_maintainers(self):
        """MaintainedPackage should have name and maintainers attributes."""
        pkg = MaintainedPackage(name="apache2", maintainers=("user1", "group:web"))
        assert pkg.name == "apache2"
        assert pkg.maintainers == ("user1", "group:web")

    def test_maintained_package_empty_maintainers(self):
        """MaintainedPackage should accept empty maintainers tuple."""
        pkg = MaintainedPackage(name="orphan", maintainers=())
        assert pkg.name == "orphan"
        assert pkg.maintainers == ()

    def test_maintained_package_is_frozen(self):
        """MaintainedPackage should be immutable (frozen dataclass)."""
        pkg = MaintainedPackage(name="apache2", maintainers=("user1",))
        with pytest.raises((AttributeError, TypeError)):
            pkg.name = "nginx"

    def test_maintained_package_maintainers_tuple_immutable(self):
        """MaintainedPackage maintainers field should be frozen."""
        pkg = MaintainedPackage(name="apache2", maintainers=("user1",))
        with pytest.raises((AttributeError, TypeError)):
            pkg.maintainers = ("user2",)

    def test_maintained_package_equality(self):
        """Two MaintainedPackages with same data should be equal."""
        pkg1 = MaintainedPackage(name="apache2", maintainers=("user1",))
        pkg2 = MaintainedPackage(name="apache2", maintainers=("user1",))
        assert pkg1 == pkg2

    def test_maintained_package_inequality_different_maintainers(self):
        """MaintainedPackages with different maintainers should not be equal."""
        pkg1 = MaintainedPackage(name="apache2", maintainers=("user1",))
        pkg2 = MaintainedPackage(name="apache2", maintainers=("user2",))
        assert pkg1 != pkg2

    def test_maintained_package_inequality_different_name(self):
        """MaintainedPackages with different names should not be equal."""
        pkg1 = MaintainedPackage(name="apache2", maintainers=("user1",))
        pkg2 = MaintainedPackage(name="nginx", maintainers=("user1",))
        assert pkg1 != pkg2

    def test_maintained_package_can_be_used_in_set(self):
        """MaintainedPackage should be hashable for use in sets."""
        pkg1 = MaintainedPackage(name="apache2", maintainers=("user1",))
        pkg2 = MaintainedPackage(name="nginx", maintainers=("user2",))
        pkg3 = MaintainedPackage(name="apache2", maintainers=("user1",))
        packages = {pkg1, pkg2, pkg3}
        assert len(packages) == 2  # pkg1 and pkg3 are duplicates
