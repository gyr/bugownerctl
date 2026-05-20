"""Tests for CLI argument parsing and routing."""

from unittest.mock import Mock

import pytest

from src.bugowner.cli import create_parser, main


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

    def test_parser_has_whitelist_subcommand(self) -> None:
        """Parser should have 'whitelist' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["whitelist", "update"])
        assert args.command == "whitelist"
        assert args.whitelist_command == "update"

    def test_whitelist_requires_subcommand(self) -> None:
        """Whitelist should require a subcommand (update)."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["whitelist"])

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
        from src.bugowner.commands import query

        parser = create_parser()
        args = parser.parse_args(["query", "package", "test-pkg"])
        assert args.func == query.run_package

    def test_query_maintainer_wires_correct_handler(self) -> None:
        """Query maintainer should wire query.run_maintainer as handler."""
        from src.bugowner.commands import query

        parser = create_parser()
        args = parser.parse_args(["query", "maintainer", "testuser"])
        assert args.func == query.run_maintainer


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
        monkeypatch.setattr("src.bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("src.bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("src.bugowner.cli.create_parser", lambda: mock_parser)

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
        monkeypatch.setattr("src.bugowner.cli.create_parser", lambda: mock_parser)

        result = main()

        assert result == 42
