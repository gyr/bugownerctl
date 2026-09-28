"""BulkMap domain value object."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BulkMap:
    """Bulk binary-to-source package name mapping for an OBS project.

    Attributes:
        mapping: Binary/subpackage/flavor name to canonical source package name.
        project: OBS project the data was fetched from.
        fetched_at: When the underlying OBS response was fetched.
        packages: Source package names present in the project (the
            `<sourceinfo package>` values), excluding multibuild flavors
            (names containing `:`).
    """

    mapping: Mapping[str, str]
    project: str
    fetched_at: datetime
    packages: frozenset[str]

    @property
    def entry_count(self) -> int:
        """Number of entries in the mapping."""
        return len(self.mapping)
