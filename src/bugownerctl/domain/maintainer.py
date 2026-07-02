"""Maintainer domain models."""

from dataclasses import dataclass


@dataclass
class MaintainershipData:
    """Normalized maintainership data."""

    packages: dict[str, list[str]]
