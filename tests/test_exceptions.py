import pytest

from bugownerctl.exceptions import (
    BugownerctlError,
    ConfigError,
    MissingBinaryError,
    NetworkTimeoutError,
)

# ---------------------------------------------------------------------------
# BugownerctlError
# ---------------------------------------------------------------------------


def test_bugownerctl_error_is_exception_subclass():
    assert issubclass(BugownerctlError, Exception)


def test_bugownerctl_error_message_passthrough():
    exc = BugownerctlError("something went wrong")
    assert str(exc) == "something went wrong"


# ---------------------------------------------------------------------------
# ConfigError
# ---------------------------------------------------------------------------


def test_config_error_is_bugownerctl_error_subclass():
    assert issubclass(ConfigError, BugownerctlError)


def test_config_error_is_exception_subclass():
    assert issubclass(ConfigError, Exception)


def test_config_error_message_passthrough():
    exc = ConfigError("bad config")
    assert str(exc) == "bad config"


def test_config_error_isinstance_bugownerctl_error():
    exc = ConfigError("bad config")
    assert isinstance(exc, BugownerctlError)


# ---------------------------------------------------------------------------
# MissingBinaryError
# ---------------------------------------------------------------------------


def test_missing_binary_error_is_bugownerctl_error_subclass():
    assert issubclass(MissingBinaryError, BugownerctlError)


def test_missing_binary_error_stores_binary_attribute():
    exc = MissingBinaryError("osc")
    assert exc.binary == "osc"


def test_missing_binary_error_exact_message():
    exc = MissingBinaryError("osc")
    assert str(exc) == "Required binary not found: osc"


def test_missing_binary_error_message_varies_with_binary():
    exc = MissingBinaryError("git")
    assert str(exc) == "Required binary not found: git"


def test_missing_binary_error_isinstance_bugownerctl_error():
    exc = MissingBinaryError("osc")
    assert isinstance(exc, BugownerctlError)


def test_missing_binary_error_isinstance_exception():
    exc = MissingBinaryError("osc")
    assert isinstance(exc, Exception)


def test_missing_binary_error_raiseable_and_catchable_as_base():
    with pytest.raises(BugownerctlError, match="Required binary not found: osc"):
        raise MissingBinaryError("osc")


# ---------------------------------------------------------------------------
# NetworkTimeoutError
# ---------------------------------------------------------------------------


def test_network_timeout_is_bugownerctl_error_subclass():
    assert issubclass(NetworkTimeoutError, BugownerctlError)


def test_network_timeout_stores_label_attribute():
    exc = NetworkTimeoutError("OBS API", 30.0)
    assert exc.label == "OBS API"


def test_network_timeout_stores_timeout_attribute():
    exc = NetworkTimeoutError("OBS API", 30.0)
    assert exc.timeout == 30.0


def test_network_timeout_exact_message():
    exc = NetworkTimeoutError("OBS API", 30.0)
    assert str(exc) == "OBS API timed out after 30s"


def test_network_timeout_message_varies_with_label_and_timeout():
    exc = NetworkTimeoutError("git fetch", 10.5)
    assert str(exc) == "git fetch timed out after 10.5s"


def test_network_timeout_isinstance_bugownerctl_error():
    exc = NetworkTimeoutError("OBS API", 30.0)
    assert isinstance(exc, BugownerctlError)


def test_network_timeout_isinstance_exception():
    exc = NetworkTimeoutError("OBS API", 30.0)
    assert isinstance(exc, Exception)


def test_network_timeout_raiseable_and_catchable_as_base():
    with pytest.raises(BugownerctlError, match="OBS API timed out after 30s"):
        raise NetworkTimeoutError("OBS API", 30.0)


def test_network_timeout_accepts_integer_timeout_stored_as_given():
    exc = NetworkTimeoutError("probe", 5)
    assert exc.timeout == 5


def test_network_timeout_integer_timeout_message():
    exc = NetworkTimeoutError("probe", 5)
    assert str(exc) == "probe timed out after 5s"
