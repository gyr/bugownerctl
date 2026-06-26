"""BulkMap domain value object."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BulkMap:
    """Bulk binary-to-source package name mapping for an OBS project."""

    mapping: Mapping[str, str]
    project: str
    fetched_at: datetime

    @property
    def entry_count(self) -> int:
        """Number of entries in the mapping."""
        return len(self.mapping)
