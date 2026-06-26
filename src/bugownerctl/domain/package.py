"""Package domain models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Package:
    """Represents a source package."""

    name: str


@dataclass(frozen=True)
class MaintainedPackage:
    """Represents a package with its maintainers."""

    name: str
    maintainers: tuple[str, ...]
