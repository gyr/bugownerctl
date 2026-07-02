"""Tests for CLI argument parsing and routing."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bugownerctl.cli import create_parser, main


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_has_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Parser should support --version flag and print version to stdout."""
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "bugownerctl" in captured.out

    def test_parser_has_debug_flag(self) -> None:
        """Parser should support --debug flag."""
        parser = create_parser()
        args = parser.parse_args(["--debug", "check", "maintainership", "-v", "16.1"])
        assert args.debug is True

    def test_parser_debug_flag_defaults_to_false(self) -> None:
        """Debug flag should default to False."""
        parser = create_parser()
        args = parser.parse_args(["check", "maintainership", "-v", "16.1"])
        assert args.debug is False

    def test_parser_requires_subcommand(self) -> None:
        """Parser should require a subcommand."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parser_has_check_maintainership_subcommand(self) -> None:
        """Parser should have 'check maintainership' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["check", "maintainership", "-v", "16.1"])
        assert args.command == "check"
        assert args.check_command == "maintainership"
        assert args.version == "16.1"

    def test_check_maintainership_requires_version_flag(self) -> None:
        """check maintainership should require -v/--version flag."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["check", "maintainership"])

    def test_check_maintainership_wires_correct_handler(self) -> None:
        """check maintainership should wire check.run_maintainership as handler."""
        from bugownerctl.commands import check

        parser = create_parser()
        args = parser.parse_args(["check", "maintainership", "-v", "16.1"])
        assert args.func == check.run_maintainership

    def test_parser_rejects_whitelist_update_subcommand(self) -> None:
        """Parser should NOT have 'whitelist update' subcommand (removed)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["whitelist", "update"])

    def test_parser_has_check_whitelist_subcommand(self) -> None:
        """Parser should have 'check whitelist' subcommand with version flag."""
        parser = create_parser()
        args = parser.parse_args(["check", "whitelist", "-v", "16.1"])
        assert args.command == "check"
        assert args.check_command == "whitelist"
        assert args.version == "16.1"

    def test_check_whitelist_requires_version_flag(self) -> None:
        """check whitelist should require -v/--version flag."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["check", "whitelist"])

    def test_check_whitelist_wires_correct_handler(self) -> None:
        """check whitelist should wire check.run_whitelist as handler."""
        from bugownerctl.commands import check

        parser = create_parser()
        args = parser.parse_args(["check", "whitelist", "-v", "16.1"])
        assert args.func == check.run_whitelist

    def test_parser_has_query_package_subcommand(self) -> None:
        """Parser should have 'query package' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["query", "package", "test-pkg", "-v", "16.1"])
        assert args.command == "query"
        assert args.query_command == "package"
        assert args.package_name == "test-pkg"
        assert args.version == "16.1"

    def test_parser_has_query_maintainer_subcommand(self) -> None:
        """Parser should have 'query maintainer' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "testuser", "-v", "16.1"])
        assert args.command == "query"
        assert args.query_command == "maintainer"
        assert args.maintainer_name == "testuser"
        assert args.version == "16.1"

    def test_query_requires_subcommand(self) -> None:
        """Query should require a subcommand (package or maintainer)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["query"])

    def test_query_package_wires_correct_handler(self) -> None:
        """Query package should wire query.run_package as handler."""
        from bugownerctl.commands import query

        parser = create_parser()
        args = parser.parse_args(["query", "package", "test-pkg", "-v", "16.1"])
        assert args.func == query.run_package

    def test_query_maintainer_wires_correct_handler(self) -> None:
        """Query maintainer should wire query.run_maintainer as handler."""
        from bugownerctl.commands import query

        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "testuser", "-v", "16.1"])
        assert args.func == query.run_maintainer

    def test_query_package_requires_version_flag(self) -> None:
        """Query package should require -v/--version flag."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["query", "package", "foo"])

    def test_query_maintainer_requires_version_flag(self) -> None:
        """Query maintainer should require -v/--version flag."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["query", "maintainer", "foo"])

    def test_query_package_accepts_config_flag(self) -> None:
        """Query package should accept -c/--config flag."""
        parser = create_parser()
        args = parser.parse_args(["query", "package", "foo", "-v", "16.1", "-c", "/x.yaml"])
        assert args.config == Path("/x.yaml")

    def test_query_package_config_defaults_to_none(self) -> None:
        """Query package config flag should default to None when not provided."""
        parser = create_parser()
        args = parser.parse_args(["query", "package", "foo", "-v", "16.1"])
        assert args.config is None

    def test_query_maintainer_accepts_config_flag(self) -> None:
        """Query maintainer should accept -c/--config flag."""
        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "foo", "-v", "16.1", "-c", "/x.yaml"])
        assert args.config == Path("/x.yaml")

    def test_query_maintainer_config_defaults_to_none(self) -> None:
        """Query maintainer config flag should default to None when not provided."""
        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "foo", "-v", "16.1"])
        assert args.config is None

    def test_check_maintainership_accepts_config_flag(self) -> None:
        """check maintainership should accept --config flag."""
        parser = create_parser()
        args = parser.parse_args(
            ["check", "maintainership", "-v", "16.1", "--config", "/custom/config.yaml"]
        )
        assert args.config == Path("/custom/config.yaml")

    def test_check_maintainership_config_flag_short_form(self) -> None:
        """check maintainership should accept -c short form for config flag."""
        parser = create_parser()
        args = parser.parse_args(
            ["check", "maintainership", "-v", "16.1", "-c", "/custom/config.yaml"]
        )
        assert args.config == Path("/custom/config.yaml")

    def test_check_maintainership_config_flag_defaults_to_none(self) -> None:
        """Config flag should default to None for check maintainership."""
        parser = create_parser()
        args = parser.parse_args(["check", "maintainership", "-v", "16.1"])
        assert args.config is None

    def test_check_maintainership_refresh_bulk_map_defaults_to_false(self) -> None:
        """check maintainership --refresh-bulk-map should default to False."""
        parser = create_parser()
        args = parser.parse_args(["check", "maintainership", "-v", "16.1"])
        assert args.refresh_bulk_map is False

    def test_check_maintainership_accepts_refresh_bulk_map_flag(self) -> None:
        """check maintainership should accept --refresh-bulk-map flag."""
        parser = create_parser()
        args = parser.parse_args(["check", "maintainership", "-v", "16.1", "--refresh-bulk-map"])
        assert args.refresh_bulk_map is True

    def test_check_whitelist_accepts_config_flag(self) -> None:
        """check whitelist should accept --config flag."""
        parser = create_parser()
        args = parser.parse_args(
            ["check", "whitelist", "-v", "16.1", "--config", "/custom/config.yaml"]
        )
        assert args.config == Path("/custom/config.yaml")

    def test_check_whitelist_config_flag_defaults_to_none(self) -> None:
        """Config flag should default to None for check whitelist."""
        parser = create_parser()
        args = parser.parse_args(["check", "whitelist", "-v", "16.1"])
        assert args.config is None

    def test_check_whitelist_refresh_bulk_map_defaults_to_false(self) -> None:
        """check whitelist --refresh-bulk-map should default to False."""
        parser = create_parser()
        args = parser.parse_args(["check", "whitelist", "-v", "16.1"])
        assert args.refresh_bulk_map is False

    def test_check_whitelist_accepts_refresh_bulk_map_flag(self) -> None:
        """check whitelist should accept --refresh-bulk-map flag."""
        parser = create_parser()
        args = parser.parse_args(["check", "whitelist", "-v", "16.1", "--refresh-bulk-map"])
        assert args.refresh_bulk_map is True

    def test_check_requires_subcommand(self) -> None:
        """check should require a subcommand (maintainership or whitelist)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["check"])

    def test_parser_has_init_subcommand(self) -> None:
        """Parser should have 'init' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.command == "init"

    def test_init_location_defaults_to_user(self) -> None:
        """Init subcommand should default location to 'user'."""
        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.location == "user"

    def test_init_force_defaults_to_false(self) -> None:
        """Init subcommand should default force to False."""
        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.force is False

    def test_init_accepts_location_flag(self) -> None:
        """Init should accept --location flag with valid choices."""
        parser = create_parser()
        args = parser.parse_args(["init", "--location", "local"])
        assert args.location == "local"

    def test_init_accepts_location_choices(self) -> None:
        """Init should accept user, local, and system as location choices."""
        parser = create_parser()

        args_user = parser.parse_args(["init", "--location", "user"])
        assert args_user.location == "user"

        args_local = parser.parse_args(["init", "--location", "local"])
        assert args_local.location == "local"

        args_system = parser.parse_args(["init", "--location", "system"])
        assert args_system.location == "system"

    def test_init_rejects_invalid_location(self) -> None:
        """Init should reject invalid location values."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["init", "--location", "invalid"])

    def test_init_accepts_force_flag(self) -> None:
        """Init should accept --force flag."""
        parser = create_parser()
        args = parser.parse_args(["init", "--force"])
        assert args.force is True

    def test_init_wires_correct_handler(self) -> None:
        """Init should wire init.run as handler."""
        from bugownerctl.commands import init

        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.func == init.run


class TestMain:
    """Tests for main entry point."""

    def test_main_configures_logging_info_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Main should configure INFO level logging by default."""
        import logging

        # Mock basicConfig to capture call
        mock_config = Mock()
        monkeypatch.setattr("logging.basicConfig", mock_config)

        # Mock parser to avoid executing command
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=Mock(return_value=0))
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        main()

        # Verify basicConfig called with INFO level
        mock_config.assert_called_once()
        call_kwargs = mock_config.call_args[1]
        assert call_kwargs["level"] == logging.INFO

    def test_main_configures_logging_debug_when_flag_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Main should configure DEBUG level when --debug flag provided."""
        import logging

        mock_config = Mock()
        monkeypatch.setattr("logging.basicConfig", mock_config)

        mock_parser = Mock()
        mock_args = Mock(debug=True, func=Mock(return_value=0))
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        main()

        call_kwargs = mock_config.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    def test_main_calls_command_handler_function(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Main should call the command handler function from args.func."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        mock_handler = Mock(return_value=0)
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=mock_handler)
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        mock_handler.assert_called_once_with(mock_args)
        assert result == 0

    def test_main_returns_command_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Main should return the exit code from command handler."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        mock_handler = Mock(return_value=42)
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=mock_handler)
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 42


class TestMainExceptionHandling:
    """Tests for exception handling at CLI boundary."""

    def test_main_catches_file_not_found_error_and_shows_friendly_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Main should catch FileNotFoundError and show user-friendly error message."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        # Mock command handler that raises FileNotFoundError
        mock_handler = Mock(
            side_effect=FileNotFoundError("Config file not found at /path/to/config.yaml")
        )
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=mock_handler)
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        # Should return error exit code
        assert result == 1

        # Should print friendly error message to stderr
        captured = capsys.readouterr()
        assert "ERROR: Config file not found at /path/to/config.yaml" in captured.err
        # Should NOT show Python stack trace
        assert "Traceback" not in captured.err

    def test_main_catches_value_error_and_shows_friendly_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Main should catch ValueError and show user-friendly error message."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        mock_handler = Mock(side_effect=ValueError("Version 16.1 not found in config"))
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=mock_handler)
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR: Version 16.1 not found in config" in captured.err
        assert "Traceback" not in captured.err

    def test_main_shows_stack_trace_in_debug_mode(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Main should show full stack trace when --debug flag is set."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        mock_handler = Mock(side_effect=FileNotFoundError("Config file not found"))
        mock_parser = Mock()
        mock_args = Mock(debug=True, func=mock_handler)  # debug=True
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 1
        captured = capsys.readouterr()
        # In debug mode, should show stack trace
        assert "Traceback" in captured.err
        assert "FileNotFoundError" in captured.err

    def test_main_catches_keyboard_interrupt_gracefully(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Main should handle Ctrl+C (KeyboardInterrupt) gracefully."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        mock_handler = Mock(side_effect=KeyboardInterrupt())
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=mock_handler)
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 130  # Standard exit code for SIGINT
        captured = capsys.readouterr()
        assert "Interrupted" in captured.err or captured.err == ""  # Allow silent exit

    def test_main_catches_unexpected_exceptions(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Main should catch unexpected exceptions and show generic error."""

        monkeypatch.setattr("logging.basicConfig", Mock())

        mock_handler = Mock(side_effect=RuntimeError("Unexpected error"))
        mock_parser = Mock()
        mock_args = Mock(debug=False, func=mock_handler)
        mock_parser.parse_args.return_value = mock_args
        monkeypatch.setattr("bugownerctl.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR: Unexpected error" in captured.err
        assert "Traceback" not in captured.err


class TestCheckUsersSubcommand:
    """Tests for 'check users' CLI subcommand parsing."""

    def test_check_users_parses_check_command_and_version(self) -> None:
        """check users -v 16.1 should parse check_command='users', version='16.1'."""
        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1"])
        assert args.command == "check"
        assert args.check_command == "users"
        assert args.version == "16.1"

    def test_check_users_requires_version_flag(self) -> None:
        """-v/--version is required for check users (raises SystemExit when omitted)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["check", "users"])

    def test_check_users_wires_correct_handler(self) -> None:
        """check users should wire check.run_users as handler."""
        from bugownerctl.commands import check

        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1"])
        assert args.func == check.run_users

    def test_check_users_api_defaults_to_api_suse_de(self) -> None:
        """--api should default to 'https://api.suse.de' when not supplied."""
        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1"])
        assert args.api == "https://api.suse.de"

    def test_check_users_batch_size_defaults_to_50(self) -> None:
        """--batch-size should default to 50 when not supplied."""
        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1"])
        assert args.batch_size == 50

    def test_check_users_batch_size_zero_raises_system_exit(self) -> None:
        """--batch-size 0 is rejected by positive_int and raises SystemExit."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["check", "users", "-v", "16.1", "--batch-size", "0"])

    def test_check_users_batch_size_negative_raises_system_exit(self) -> None:
        """--batch-size -1 is rejected by positive_int and raises SystemExit."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["check", "users", "-v", "16.1", "--batch-size", "-1"])

    def test_check_users_batch_size_valid_value_is_stored_as_int(self) -> None:
        """--batch-size 25 is accepted by positive_int and stored as int 25."""
        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1", "--batch-size", "25"])
        assert args.batch_size == 25

    def test_check_users_accepts_config_flag(self) -> None:
        """check users should accept -c/--config flag and store it as a Path."""
        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1", "-c", "/custom/config.yaml"])
        assert args.config == Path("/custom/config.yaml")

    def test_check_users_config_flag_defaults_to_none(self) -> None:
        """Config flag should default to None for check users when not provided."""
        parser = create_parser()
        args = parser.parse_args(["check", "users", "-v", "16.1"])
        assert args.config is None
