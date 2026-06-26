"""Git reference type enumeration."""

from enum import Enum


class RefType(Enum):
    """Enum to represent the type of a git reference."""

    BRANCH = "branch"
    TAG = "tag"
    COMMIT = "commit"
