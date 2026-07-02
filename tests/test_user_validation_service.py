"""Tests for UserValidationService."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bugownerctl.services.user_validation_service import (
    UserValidationResult,
    UserValidationService,
)


class TestUserValidationService:
    """Tests for UserValidationService.validate() method."""

    def test_validate_calls_load_users_by_package_and_queries_only_users(
        self, tmp_path: Path
    ) -> None:
        """Service calls load_users_by_package and passes only user logins to query_persons."""
        maintainership_file = tmp_path / "maintainership.json"

        mock_maintainership_repo = Mock()
        mock_maintainership_repo.load_users_by_package.return_value = {
            "pkg-a": ["alice", "bob"],
            "pkg-b": ["carol"],
        }

        mock_person_repo = Mock()
        mock_person_repo.query_persons.return_value = {
            "alice": "confirmed",
            "bob": "confirmed",
            "carol": "confirmed",
        }

        service = UserValidationService(mock_maintainership_repo, mock_person_repo)
        result = service.validate(maintainership_file, api="https://api.suse.de", batch_size=50)

        mock_maintainership_repo.load_users_by_package.assert_called_once_with(maintainership_file)

        # query_persons must be called with exactly the user logins — sorted, deduped
        call_args = mock_person_repo.query_persons.call_args
        queried_logins = call_args.args[0]
        assert sorted(queried_logins) == ["alice", "bob", "carol"]
        assert call_args.args[1] == "https://api.suse.de"
        assert call_args.kwargs["batch_size"] == 50
        # No group name (e.g. starting with "group:") should be present; by construction
        # there are none, so the real assertion is that only user logins from
        # load_users_by_package are ever forwarded.
        assert isinstance(result, UserValidationResult)

    def test_validate_deduplicates_and_sorts_logins_across_packages(self, tmp_path: Path) -> None:
        """Logins appearing in multiple packages are queried only once; result lists are sorted."""
        maintainership_file = tmp_path / "maintainership.json"

        mock_maintainership_repo = Mock()
        # "alice" appears in both packages
        mock_maintainership_repo.load_users_by_package.return_value = {
            "pkg-a": ["alice", "bob"],
            "pkg-b": ["alice", "carol"],
        }

        mock_person_repo = Mock()
        mock_person_repo.query_persons.return_value = {
            "alice": "confirmed",
            "bob": "confirmed",
            "carol": "confirmed",
        }

        service = UserValidationService(mock_maintainership_repo, mock_person_repo)
        result = service.validate(maintainership_file, api="https://api.suse.de", batch_size=50)

        # query_persons called exactly once (not once per package)
        mock_person_repo.query_persons.assert_called_once()
        call_args = mock_person_repo.query_persons.call_args
        queried_logins = call_args.args[0]
        # alice appears only once in the passed list
        assert queried_logins.count("alice") == 1
        # passed list is sorted
        assert queried_logins == sorted(queried_logins)

        # result lists are sorted
        assert result.confirmed == sorted(result.confirmed)
        assert result.invalid == sorted(result.invalid)
        assert result.not_found == sorted(result.not_found)

    def test_validate_classifies_confirmed_invalid_not_found(self, tmp_path: Path) -> None:
        """confirmed→confirmed, non-"confirmed" state→invalid, absent login→not_found."""
        maintainership_file = tmp_path / "maintainership.json"

        mock_maintainership_repo = Mock()
        mock_maintainership_repo.load_users_by_package.return_value = {
            "pkg-a": ["u1", "u2", "u3", "u4"],
        }

        mock_person_repo = Mock()
        # u1: confirmed, u2: locked (non-confirmed), u4: None (no state element)
        # u3: absent from response → not_found
        mock_person_repo.query_persons.return_value = {
            "u1": "confirmed",
            "u2": "locked",
            "u4": None,
        }

        service = UserValidationService(mock_maintainership_repo, mock_person_repo)
        result = service.validate(maintainership_file, api="https://api.suse.de", batch_size=50)

        assert result.confirmed == ["u1"]
        assert result.invalid == ["u2", "u4"]
        assert result.not_found == ["u3"]

    def test_validate_treats_none_state_as_invalid(self, tmp_path: Path) -> None:
        """A person record with no <state> element (state=None) is classified as invalid."""
        maintainership_file = tmp_path / "maintainership.json"

        mock_maintainership_repo = Mock()
        mock_maintainership_repo.load_users_by_package.return_value = {
            "pkg-a": ["stateless_user"],
        }

        mock_person_repo = Mock()
        # state=None means OBS returned a <person> with no <state> child
        mock_person_repo.query_persons.return_value = {"stateless_user": None}

        service = UserValidationService(mock_maintainership_repo, mock_person_repo)
        result = service.validate(maintainership_file, api="https://api.suse.de", batch_size=50)

        assert result.invalid == ["stateless_user"]
        assert result.confirmed == []
        assert result.not_found == []

    def test_validate_empty_users_returns_empty_result_with_zero_calls(
        self, tmp_path: Path
    ) -> None:
        """When load_users_by_package returns no users, query_persons is never called."""
        maintainership_file = tmp_path / "maintainership.json"

        mock_maintainership_repo = Mock()
        mock_maintainership_repo.load_users_by_package.return_value = {}

        mock_person_repo = Mock()

        service = UserValidationService(mock_maintainership_repo, mock_person_repo)
        result = service.validate(maintainership_file, api="https://api.suse.de", batch_size=50)

        mock_person_repo.query_persons.assert_not_called()
        assert result.confirmed == []
        assert result.invalid == []
        assert result.not_found == []

    def test_validate_propagates_value_error_from_query_persons(self, tmp_path: Path) -> None:
        """ValueError raised by query_persons (invalid login char) propagates to the caller."""
        maintainership_file = tmp_path / "maintainership.json"

        mock_maintainership_repo = Mock()
        mock_maintainership_repo.load_users_by_package.return_value = {
            "pkg-a": ["bad login!"],
        }

        mock_person_repo = Mock()
        mock_person_repo.query_persons.side_effect = ValueError(
            "Invalid OBS login 'bad login!': must match [A-Za-z0-9_.@-]+"
        )

        service = UserValidationService(mock_maintainership_repo, mock_person_repo)

        with pytest.raises(ValueError, match="Invalid OBS login"):
            service.validate(maintainership_file, api="https://api.suse.de", batch_size=50)
