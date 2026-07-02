"""OBS person repository.

Fetches person records from the OBS search API via `osc api`
(SSH-signature auth is delegated to the user's local `osc` install).
"""

import re
import subprocess
from typing import Protocol
from urllib.parse import quote, urlparse

DEFAULT_OBS_API = "https://api.suse.de"
MAX_XML_BYTES = 50 * 1024 * 1024

_VALID_LOGIN = re.compile(r"^[A-Za-z0-9_.@-]+$")

_DEFAULT_TIMEOUT = 60  # seconds


class ObsPersonRepository(Protocol):
    """Fetch OBS person records by login name."""

    def query_persons(
        self,
        logins: list[str],
        api: str = DEFAULT_OBS_API,
        *,
        batch_size: int = 50,
    ) -> dict[str, str | None]:
        """Return a mapping of login → OBS account state string (or None when absent).

        Args:
            logins: OBS login names to query.  Each must match
                ``[A-Za-z0-9_.@-]+``.
            api: OBS API root URL.
            batch_size: Maximum number of logins per subprocess call.

        Returns:
            dict mapping each login found in OBS to its state string
            (e.g. ``"confirmed"``, ``"locked"``), or ``None`` when the
            person record contains no ``<state>`` element. Logins absent
            from the OBS response are absent from the returned dict.

        Raises:
            ValueError: If any login contains characters outside
                ``[A-Za-z0-9_.@-]``.
            RuntimeError: If ``osc api`` exits non-zero, times out, or
                ``osc`` is not installed.
        """
        ...


class ObsPersonRepositoryImpl:
    """Adapter backed by ``osc api /search/person``."""

    def query_persons(
        self,
        logins: list[str],
        api: str = DEFAULT_OBS_API,
        *,
        batch_size: int = 50,
    ) -> dict[str, str | None]:
        if not logins:
            return {}

        parsed = urlparse(api)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"OBS API URL must use HTTPS, got: {api!r}")

        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size!r}")

        for login in logins:
            if not _VALID_LOGIN.fullmatch(login):
                raise ValueError(f"Invalid OBS login {login!r}: must match [A-Za-z0-9_.@-]+")

        n = len(logins)
        num_batches = (n + batch_size - 1) // batch_size

        result: dict[str, str | None] = {}
        for i in range(num_batches):
            batch = logins[i * batch_size : (i + 1) * batch_size]
            _xml_bytes = self._fetch_batch(batch, api)

        return result

    @staticmethod
    def _build_search_url(logins: list[str]) -> str:
        conditions = " or ".join(f"@login='{u}'" for u in logins)
        return f"/search/person?match={quote(f'({conditions})', safe='')}"

    @staticmethod
    def _fetch_batch(logins: list[str], api: str) -> bytes:
        path = ObsPersonRepositoryImpl._build_search_url(logins)
        try:
            proc = subprocess.run(
                ["osc", "-A", api, "api", path],
                capture_output=True,
                check=False,
                timeout=_DEFAULT_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "osc executable not found; install with `zypper install osc` or `pip install osc`"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"osc api {path!r} timed out after {_DEFAULT_TIMEOUT}s") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"osc api {path!r} failed (exit {proc.returncode}):\n{stderr}")

        return proc.stdout
