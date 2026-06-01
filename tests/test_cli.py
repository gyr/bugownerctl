"""Tests for CLI argument parsing and routing."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.cli import create_parser, main


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_has_debug_flag(self) -> None:
        """Parser should support --debug flag."""
        parser = create_parser()
        args = parser.parse_args(["--debug", "validate", "-v", "16.1"])
        assert args.debug is True

    def test_parser_debug_flag_defaults_to_false(self) -> None:
        """Debug flag should default to False."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-v", "16.1"])
        assert args.debug is False

    def test_parser_requires_subcommand(self) -> None:
        """Parser should require a subcommand."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parser_has_validate_subcommand(self) -> None:
        """Parser should have 'validate' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-v", "16.1"])
        assert args.command == "validate"
        assert args.version == "16.1"

    def test_validate_requires_version_flag(self) -> None:
        """Validate subcommand should require -v/--version flag."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["validate"])

    def test_parser_rejects_whitelist_update_subcommand(self) -> None:
        """Parser should NOT have 'whitelist update' subcommand (removed)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["whitelist", "update"])

    def test_parser_has_whitelist_check_subcommand(self) -> None:
        """Parser should have 'whitelist-check' subcommand with version flag."""
        parser = create_parser()
        args = parser.parse_args(["whitelist-check", "-v", "16.1"])
        assert args.command == "whitelist-check"
        assert args.version == "16.1"

    def test_whitelist_check_requires_version_flag(self) -> None:
        """Whitelist-check should require -v/--version flag."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["whitelist-check"])

    def test_whitelist_check_wires_correct_handler(self) -> None:
        """Whitelist-check should wire whitelist.run as handler."""
        from bugowner.commands import whitelist

        parser = create_parser()
        args = parser.parse_args(["whitelist-check", "-v", "16.1"])
        assert args.func == whitelist.run

    def test_parser_has_query_package_subcommand(self) -> None:
        """Parser should have 'query package' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["query", "package", "test-pkg"])
        assert args.command == "query"
        assert args.query_command == "package"
        assert args.package_name == "test-pkg"

    def test_parser_has_query_maintainer_subcommand(self) -> None:
        """Parser should have 'query maintainer' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "testuser"])
        assert args.command == "query"
        assert args.query_command == "maintainer"
        assert args.maintainer_name == "testuser"

    def test_query_requires_subcommand(self) -> None:
        """Query should require a subcommand (package or maintainer)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["query"])

    def test_query_package_wires_correct_handler(self) -> None:
        """Query package should wire query.run_package as handler."""
        from bugowner.commands import query

        parser = create_parser()
        args = parser.parse_args(["query", "package", "test-pkg"])
        assert args.func == query.run_package

    def test_query_maintainer_wires_correct_handler(self) -> None:
        """Query maintainer should wire query.run_maintainer as handler."""
        from bugowner.commands import query

        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "testuser"])
        assert args.func == query.run_maintainer

    def test_validate_accepts_config_flag(self) -> None:
        """Validate subcommand should accept --config flag."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-v", "16.1", "--config", "/custom/config.yaml"])
        assert args.config == Path("/custom/config.yaml")

    def test_validate_config_flag_short_form(self) -> None:
        """Validate subcommand should accept -c short form for config flag."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-v", "16.1", "-c", "/custom/config.yaml"])
        assert args.config == Path("/custom/config.yaml")

    def test_validate_config_flag_defaults_to_none(self) -> None:
        """Config flag should default to None when not provided."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-v", "16.1"])
        assert args.config is None

    def test_validate_config_flag_is_path_type(self) -> None:
        """Config flag should be converted to Path type."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-v", "16.1", "--config", "/custom/config.yaml"])
        assert isinstance(args.config, Path)

    def test_whitelist_check_accepts_config_flag(self) -> None:
        """Whitelist-check subcommand should accept --config flag."""
        parser = create_parser()
        args = parser.parse_args(
            ["whitelist-check", "-v", "16.1", "--config", "/custom/config.yaml"]
        )
        assert args.config == Path("/custom/config.yaml")

    def test_whitelist_check_config_flag_short_form(self) -> None:
        """Whitelist-check subcommand should accept -c short form."""
        parser = create_parser()
        args = parser.parse_args(["whitelist-check", "-v", "16.1", "-c", "/custom/config.yaml"])
        assert args.config == Path("/custom/config.yaml")

    def test_whitelist_check_config_flag_defaults_to_none(self) -> None:
        """Config flag should default to None for whitelist-check."""
        parser = create_parser()
        args = parser.parse_args(["whitelist-check", "-v", "16.1"])
        assert args.config is None

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
        from bugowner.commands import init

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("bugowner.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR: Unexpected error" in captured.err
        assert "Traceback" not in captured.err
