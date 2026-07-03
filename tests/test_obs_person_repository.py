"""Tests for ObsPersonRepository.

Tests cover:
  - Protocol shape.
  - Input validation (login characters).
  - Subprocess invocation (mocked; argv-style; timeout; bytes stdout).
  - Batch boundary logic (ceil-div batching).
  - Failure modes (non-zero exit, timeout, osc not installed).
"""

import subprocess
from unittest.mock import Mock, patch
from urllib.parse import unquote

import pytest

from bugownerctl.exceptions import MissingBinaryError, NetworkTimeoutError
from bugownerctl.repositories.obs_person_repository import (
    DEFAULT_OBS_API,
    ObsPersonRepository,
    ObsPersonRepositoryImpl,
)

# ---------------------------------------------------------------------------
# Helpers


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> Mock:
    proc = Mock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ---------------------------------------------------------------------------
# Protocol


class TestProtocol:
    def test_protocol_methods_present(self) -> None:
        """ObsPersonRepository must expose query_persons."""
        assert hasattr(ObsPersonRepository, "query_persons")

    def test_impl_satisfies_protocol(self) -> None:
        """ObsPersonRepositoryImpl satisfies the protocol."""
        impl: ObsPersonRepository = ObsPersonRepositoryImpl()
        assert callable(impl.query_persons)


# ---------------------------------------------------------------------------
# Input validation


class TestInputValidation:
    def test_invalid_login_char_apostrophe_raises_value_error(self) -> None:
        """Login with apostrophe must raise ValueError before any subprocess call."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError):
            repo.query_persons(["bad'login"])

    def test_invalid_login_char_space_raises_value_error(self) -> None:
        """Login with space must raise ValueError before any subprocess call."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError):
            repo.query_persons(["bad login"])

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_valid_login_chars_accepted(self, mock_run: Mock, mock_which: Mock) -> None:
        """Login with valid chars must not raise."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        # Must not raise
        repo.query_persons(["user.name_123@host-org"])

    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_empty_logins_returns_empty_dict(self, mock_run: Mock) -> None:
        """query_persons([]) must return {} with zero subprocess calls."""
        repo = ObsPersonRepositoryImpl()
        result = repo.query_persons([])
        assert result == {}
        mock_run.assert_not_called()

    def test_non_https_api_url_raises_value_error(self) -> None:
        """Non-HTTPS api URL must raise ValueError before any subprocess call."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError, match="HTTPS"):
            repo.query_persons(["alice"], api="http://evil.example.com")

    def test_batch_size_zero_raises_value_error(self) -> None:
        """batch_size=0 must raise ValueError, not ZeroDivisionError."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError, match="batch_size"):
            repo.query_persons(["alice"], batch_size=0)

    def test_batch_size_negative_raises_value_error(self) -> None:
        """batch_size < 1 must raise ValueError before any subprocess call."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError, match="batch_size"):
            repo.query_persons(["alice"], batch_size=-1)

    def test_empty_string_login_raises_value_error(self) -> None:
        """Empty-string login must raise ValueError (regex requires at least one char)."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError):
            repo.query_persons([""])

    def test_https_url_without_netloc_raises_value_error(self) -> None:
        """'https://' has correct scheme but no host; must raise ValueError."""
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(ValueError, match="HTTPS"):
            repo.query_persons(["alice"], api="https://")


# ---------------------------------------------------------------------------
# Subprocess invocation


class TestSubprocessInvocation:
    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_query_persons_runs_osc_api_with_correct_argv(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """One login 'alice': argv must match expected pattern."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        repo.query_persons(["alice"])
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        argv = args[0]
        assert argv[0] == "/usr/bin/osc"
        assert argv[1] == "-A"
        assert argv[2] == DEFAULT_OBS_API
        assert argv[3] == "api"
        path = argv[4]
        assert path.startswith("/search/person?match=")
        assert kwargs.get("capture_output") is True
        assert kwargs.get("check") is False
        assert kwargs.get("timeout") is not None
        assert kwargs.get("timeout") > 0
        # text=True must NOT be set — bytes stdout required
        assert kwargs.get("text") is not True

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_query_persons_url_contains_encoded_xpath(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """Path must contain URL-encoded XPath matching @login='alice'."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        repo.query_persons(["alice"])
        args, _ = mock_run.call_args
        path = args[0][4]
        # Decoding must yield the expected XPath prefix
        assert unquote(path).startswith("/search/person?match=(@login='alice')")

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_subprocess_nonzero_raises_runtime_error(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """Non-zero returncode must raise RuntimeError mentioning 'osc'."""
        mock_run.return_value = _make_proc(returncode=1, stderr=b"auth failed")
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(RuntimeError, match="osc"):
            repo.query_persons(["alice"])

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_subprocess_timeout_raises_network_timeout_error(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """TimeoutExpired must raise NetworkTimeoutError."""
        mock_run.side_effect = subprocess.TimeoutExpired("osc", 30)
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(NetworkTimeoutError):
            repo.query_persons(["alice"])

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_osc_not_installed_raises_missing_binary_error(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """FileNotFoundError must raise MissingBinaryError."""
        mock_run.side_effect = FileNotFoundError("osc")
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(MissingBinaryError):
            repo.query_persons(["alice"])

    @patch("bugownerctl.repositories.obs_person_repository.shutil.which")
    def test_shutil_which_returns_none_raises_missing_binary_error(self, mock_which: Mock) -> None:
        """shutil.which('osc') returning None must raise MissingBinaryError before subprocess."""
        mock_which.return_value = None
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(MissingBinaryError):
            repo.query_persons(["alice"])


# ---------------------------------------------------------------------------
# Batch boundary


class TestBatchBoundary:
    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_exactly_50_logins_produces_one_subprocess_call(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """50 logins with default batch_size=50 → exactly 1 subprocess call."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        logins = [f"user{i}" for i in range(50)]
        repo.query_persons(logins)
        assert mock_run.call_count == 1

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_exactly_51_logins_produces_two_subprocess_calls(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """51 logins with default batch_size=50 → exactly 2 subprocess calls."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        logins = [f"user{i}" for i in range(51)]
        repo.query_persons(logins)
        assert mock_run.call_count == 2

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_custom_batch_size_respected(self, mock_run: Mock, mock_which: Mock) -> None:
        """10 logins, batch_size=3 → ceil(10/3)=4 subprocess calls."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        logins = [f"user{i}" for i in range(10)]
        repo.query_persons(logins, batch_size=3)
        assert mock_run.call_count == 4

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_default_batch_size_is_50(self, mock_run: Mock, mock_which: Mock) -> None:
        """100 logins with default batch_size → exactly 2 subprocess calls."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsPersonRepositoryImpl()
        logins = [f"user{i}" for i in range(100)]
        repo.query_persons(logins)
        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# XML parsing


class TestXmlParse:
    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_parse_returns_login_state_mapping(self, mock_run: Mock, mock_which: Mock) -> None:
        """Valid XML with two persons returns login→state mapping."""
        xml = (
            b"<directory>"
            b"<person><login>alice</login><state>confirmed</state></person>"
            b"<person><login>bob</login><state>locked</state></person>"
            b"</directory>"
        )
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsPersonRepositoryImpl()
        result = repo.query_persons(["alice", "bob"])
        assert result == {"alice": "confirmed", "bob": "locked"}

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_parse_person_without_state_returns_none(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """Person element with no <state> child maps to None."""
        xml = b"<directory><person><login>alice</login></person></directory>"
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsPersonRepositoryImpl()
        result = repo.query_persons(["alice"])
        assert result == {"alice": None}

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_login_absent_from_response_is_absent_from_result(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """Login not present in XML response is absent from the returned dict."""
        xml = (
            b"<directory><person><login>alice</login><state>confirmed</state></person></directory>"
        )
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsPersonRepositoryImpl()
        result = repo.query_persons(["alice", "bob"])
        assert result == {"alice": "confirmed"}

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_malformed_xml_raises_runtime_error(self, mock_run: Mock, mock_which: Mock) -> None:
        """Malformed XML bytes raise RuntimeError."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"not xml at all <<<")
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(RuntimeError):
            repo.query_persons(["alice"])

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_doctype_in_person_response_raises_runtime_error(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """DOCTYPE in response raises RuntimeError with 'DOCTYPE' in message."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<!DOCTYPE foo><directory/>")
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(RuntimeError, match="DOCTYPE"):
            repo.query_persons(["alice"])

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_oversized_response_raises_runtime_error(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """Response exceeding 50 MB raises RuntimeError with 'exceeds' in message."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"x" * (51 * 1024 * 1024))
        repo = ObsPersonRepositoryImpl()
        with pytest.raises(RuntimeError, match="exceeds"):
            repo.query_persons(["alice"])

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_person_without_login_element_is_skipped(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """<person> with no <login> child is silently skipped."""
        xml = b"<directory><person><state>confirmed</state></person></directory>"
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        result = ObsPersonRepositoryImpl().query_persons(["alice"])
        assert result == {}

    @patch(
        "bugownerctl.repositories.obs_person_repository.shutil.which", return_value="/usr/bin/osc"
    )
    @patch("bugownerctl.repositories.obs_person_repository.subprocess.run")
    def test_person_with_empty_login_element_is_skipped(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """<person> with empty <login/> is silently skipped."""
        xml = b"<directory><person><login/><state>confirmed</state></person></directory>"
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        result = ObsPersonRepositoryImpl().query_persons(["alice"])
        assert result == {}
