"""Tests for ExitCode enum — asserts the public numeric contract."""

from bugownerctl.exit_codes import ExitCode


def test_exit_code_ok_is_0() -> None:
    assert ExitCode.OK == 0


def test_exit_code_error_is_1() -> None:
    assert ExitCode.ERROR == 1


def test_exit_code_issues_is_2() -> None:
    assert ExitCode.ISSUES == 2


def test_exit_code_usage_is_64() -> None:
    assert ExitCode.USAGE == 64


def test_exit_code_timeout_is_124() -> None:
    assert ExitCode.TIMEOUT == 124


def test_exit_code_missing_binary_is_127() -> None:
    assert ExitCode.MISSING_BINARY == 127


def test_exit_code_interrupt_is_130() -> None:
    assert ExitCode.INTERRUPT == 130
