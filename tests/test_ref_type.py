"""Tests for RefType enum."""

from bugowner.domain.ref_type import RefType


def test_ref_type_has_branch_member():
    """RefType should have BRANCH member with value 'branch'."""
    assert RefType.BRANCH.value == "branch"


def test_ref_type_has_tag_member():
    """RefType should have TAG member with value 'tag'."""
    assert RefType.TAG.value == "tag"


def test_ref_type_has_commit_member():
    """RefType should have COMMIT member with value 'commit'."""
    assert RefType.COMMIT.value == "commit"


def test_ref_type_has_exactly_three_members():
    """RefType should have exactly three members."""
    assert len(list(RefType)) == 3


def test_ref_type_values_are_unique():
    """All RefType member values should be unique."""
    values = [member.value for member in RefType]
    assert len(values) == len(set(values))


def test_ref_type_can_be_compared():
    """RefType members should be comparable."""
    assert RefType.BRANCH == RefType.BRANCH
    assert RefType.BRANCH != RefType.TAG
