"""Maintainer domain models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Maintainer:
    """Represents a package maintainer (user or group)."""

    name: str
    is_group: bool


@dataclass
class MaintainershipData:
    """Normalized maintainership data."""

    packages: dict[str, list[str]]
