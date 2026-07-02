"""User validation service.

Validates OBS user logins referenced in a maintainership file against the OBS
person API and classifies each login as confirmed, invalid, or not found.
"""

from dataclasses import dataclass
from pathlib import Path

from bugownerctl.repositories.maintainership_repository import MaintainershipRepository
from bugownerctl.repositories.obs_person_repository import ObsPersonRepository


@dataclass
class UserValidationResult:
    """Result of a user validation run.

    Attributes:
        confirmed: Logins whose OBS state is "confirmed" (sorted).
        invalid: Logins present in OBS with a state other than "confirmed",
            or with no state element (state=None) (sorted).
        not_found: Logins absent from the OBS response entirely (sorted).
    """

    confirmed: list[str]
    invalid: list[str]
    not_found: list[str]


class UserValidationService:
    """Service that validates OBS user logins found in a maintainership file."""

    def __init__(
        self,
        maintainership_repo: MaintainershipRepository,
        person_repo: ObsPersonRepository,
    ) -> None:
        """Initialize the service with repository dependencies.

        Args:
            maintainership_repo: Repository for loading maintainership data.
            person_repo: Repository for querying OBS person records.
        """
        self.maintainership_repo = maintainership_repo
        self.person_repo = person_repo

    def validate(
        self,
        maintainership_file: Path,
        api: str,
        batch_size: int,
    ) -> UserValidationResult:
        """Validate OBS user logins from a maintainership file.

        Loads user logins per package, deduplicates and sorts them, queries OBS
        for each login, then classifies results as confirmed, invalid, or not
        found.  Only ``"confirmed"`` state passes; any other non-None state as
        well as ``None`` (no ``<state>`` element) is treated as invalid.

        Args:
            maintainership_file: Path to the _maintainership.json file.
            api: OBS API root URL.
            batch_size: Maximum number of logins per OBS API call.

        Returns:
            UserValidationResult with three sorted lists.

        Raises:
            ValueError: If any login contains characters outside
                ``[A-Za-z0-9_.@-]`` (propagated from ObsPersonRepository).
        """
        users_by_package = self.maintainership_repo.load_users_by_package(maintainership_file)

        # Flatten, deduplicate, and sort all user logins
        all_logins: list[str] = sorted(
            {login for logins in users_by_package.values() for login in logins}
        )

        if not all_logins:
            return UserValidationResult(confirmed=[], invalid=[], not_found=[])

        person_map = self.person_repo.query_persons(all_logins, api, batch_size=batch_size)

        confirmed: list[str] = []
        invalid: list[str] = []
        not_found: list[str] = []

        for login in all_logins:
            if login not in person_map:
                not_found.append(login)
            elif person_map[login] == "confirmed":
                confirmed.append(login)
            else:
                invalid.append(login)

        # all_logins is already sorted; partitioning preserves order within each list
        return UserValidationResult(
            confirmed=confirmed,
            invalid=invalid,
            not_found=not_found,
        )
