"""OBS person repository.

Fetches person records from the OBS search API via `osc api`
(SSH-signature auth is delegated to the user's local `osc` install).
"""

import logging
import re
import shutil
import subprocess
from typing import Protocol
from urllib.parse import quote, urlparse

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from bugownerctl.exceptions import MissingBinaryError, NetworkTimeoutError

DEFAULT_OBS_API = "https://api.suse.de"
MAX_XML_BYTES = 50 * 1024 * 1024

_VALID_LOGIN = re.compile(r"^[A-Za-z0-9_.@-]+$")

_DEFAULT_TIMEOUT = 60  # seconds

logger = logging.getLogger(__name__)


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
            MissingBinaryError: If ``osc`` is not in PATH.
            NetworkTimeoutError: If the ``osc api`` subprocess exceeds the timeout.
            RuntimeError: If ``osc api`` exits non-zero.
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
            logger.debug("querying batch of %d logins from %s", len(batch), api)
            xml_bytes = self._fetch_batch(batch, api)
            result.update(self._parse_persons(xml_bytes))
            logger.debug("batch %d/%d: %d results", i + 1, num_batches, len(result))

        return result

    @staticmethod
    def _build_search_url(logins: list[str]) -> str:
        conditions = " or ".join(f"@login='{u}'" for u in logins)
        return f"/search/person?match={quote(f'({conditions})', safe='')}"

    @staticmethod
    def _parse_persons(xml_bytes: bytes) -> dict[str, str | None]:
        if len(xml_bytes) > MAX_XML_BYTES:
            raise RuntimeError(f"OBS person response exceeds {MAX_XML_BYTES} bytes")
        try:
            root = ET.fromstring(xml_bytes, forbid_dtd=True)
        except DefusedXmlException as exc:
            raise RuntimeError("OBS person response contains forbidden DOCTYPE") from exc
        except ET.ParseError as exc:
            raise RuntimeError(f"OBS person response is not valid XML: {exc}") from exc
        result: dict[str, str | None] = {}
        for person in root.findall("person"):
            login_el = person.find("login")
            if login_el is None or login_el.text is None:
                logger.warning("skipping person record: missing or empty login element")
                continue
            state_el = person.find("state")
            result[login_el.text] = state_el.text if state_el is not None else None
        return result

    @staticmethod
    def _fetch_batch(logins: list[str], api: str) -> bytes:
        path = ObsPersonRepositoryImpl._build_search_url(logins)
        osc_bin = shutil.which("osc")
        if osc_bin is None:
            raise MissingBinaryError("osc")
        try:
            proc = subprocess.run(
                [osc_bin, "-A", api, "api", path],
                capture_output=True,
                check=False,
                timeout=_DEFAULT_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise MissingBinaryError("osc") from exc
        except subprocess.TimeoutExpired as exc:
            raise NetworkTimeoutError(f"osc api {path!r}", _DEFAULT_TIMEOUT) from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"osc api {path!r} failed (exit {proc.returncode}):\n{stderr}")

        return proc.stdout
