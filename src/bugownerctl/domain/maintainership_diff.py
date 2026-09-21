"""MaintainershipDiffRow domain value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintainershipDiffRow:
    """One package whose maintainers differ between two git refs.

    `None` means the package is absent at that ref; an empty tuple means the
    package is present there but has no maintainers at all.
    """

    package: str
    maintainers_a: tuple[str, ...] | None
    maintainers_b: tuple[str, ...] | None
