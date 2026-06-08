"""Tests for whitelist-check command handler."""

import argparse
from pathlib import Path
from unittest.mock import Mock

import pytest

from bugowner.commands.whitelist import run
from bugowner.domain.ref_type import RefType
from bugowner.services.whitelist_service import WhitelistCheckResult


def _empty_result() -> WhitelistCheckResult:
    """Build a WhitelistCheckResult with no inconsistencies."""
    return WhitelistCheckResult(inconsistent_packages=[])


def _patch_repos(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    """Patch all repository impls used by whitelist.run."""
    mock_git_repo = Mock()
    mock_git_repo.clone_or_update.return_value = Path("/cache/slfo")
    mock_git_repo.list_submodules.return_value = ["pkg1"]
    mock_git_cls = Mock(return_value=mock_git_repo)

    mock_meta_repo = Mock()
    mock_meta_repo.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
    mock_meta_repo.parse_source_packages.return_value = {"pkg1"}
    mock_meta_cls = Mock(return_value=mock_meta_repo)

    mock_bulk_cls = Mock()
    mock_over_cls = Mock()
    mock_maint_cls = Mock()

    monkeypatch.setattr("bugowner.commands.whitelist.GitRepositoryImpl", mock_git_cls)
    monkeypatch.setattr("bugowner.commands.whitelist.RepoMetadataRepositoryImpl", mock_meta_cls)
    monkeypatch.setattr(
        "bugowner.commands.whitelist.ObsBulkSourceInfoRepositoryImpl", mock_bulk_cls
    )
    monkeypatch.setattr("bugowner.commands.whitelist.NameOverridesRepositoryImpl", mock_over_cls)
    monkeypatch.setattr("bugowner.commands.whitelist.MaintainershipRepositoryImpl", mock_maint_cls)

    return {
        "git_cls": mock_git_cls,
        "git_repo": mock_git_repo,
        "metadata_cls": mock_meta_cls,
        "metadata_repo": mock_meta_repo,
        "bulk_map": mock_bulk_cls,
        "overrides": mock_over_cls,
        "maintainership": mock_maint_cls,
    }


def _patch_services(
    monkeypatch: pytest.MonkeyPatch, result: WhitelistCheckResult | None = None
) -> dict[str, Mock]:
    """Patch ValidationService and WhitelistService. Returns the mocks."""
    mock_validation_service = Mock()
    mock_validation_cls = Mock(return_value=mock_validation_service)
    monkeypatch.setattr("bugowner.commands.whitelist.ValidationService", mock_validation_cls)

    mock_whitelist_service = Mock()
    mock_whitelist_service.check_whitelist.return_value = (
        result if result is not None else _empty_result()
    )
    mock_whitelist_cls = Mock(return_value=mock_whitelist_service)
    monkeypatch.setattr("bugowner.commands.whitelist.WhitelistService", mock_whitelist_cls)

    return {
        "validation_cls": mock_validation_cls,
        "validation_service": mock_validation_service,
        "whitelist_cls": mock_whitelist_cls,
        "whitelist_service": mock_whitelist_service,
    }


class TestWhitelistCheckCommand:
    """Tests for whitelist-check command handler."""

    def test_run_creates_all_repository_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create all repository implementation instances."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        repos = _patch_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        repos["git_cls"].assert_called_once()
        repos["metadata_cls"].assert_called_once()
        repos["bulk_map"].assert_called_once()
        repos["overrides"].assert_called_once()
        repos["maintainership"].assert_called_once()

    def test_run_creates_validation_service_with_new_repos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create ValidationService with bulk_map+overrides repos."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        # Explicit mock instances so the ValidationService wiring can be verified.
        mock_maint_inst = Mock()
        mock_git_inst = Mock()
        mock_git_inst.clone_or_update.return_value = Path("/cache/slfo")
        mock_git_inst.list_submodules.return_value = ["pkg1"]
        mock_meta_inst = Mock()
        mock_meta_inst.download_primary_metadata.return_value = Path("/cache/primary.xml.gz")
        mock_meta_inst.parse_source_packages.return_value = {"pkg1"}
        mock_bulk_inst = Mock()
        mock_over_inst = Mock()

        monkeypatch.setattr(
            "bugowner.commands.whitelist.MaintainershipRepositoryImpl",
            Mock(return_value=mock_maint_inst),
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.GitRepositoryImpl", Mock(return_value=mock_git_inst)
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.RepoMetadataRepositoryImpl",
            Mock(return_value=mock_meta_inst),
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.ObsBulkSourceInfoRepositoryImpl",
            Mock(return_value=mock_bulk_inst),
        )
        monkeypatch.setattr(
            "bugowner.commands.whitelist.NameOverridesRepositoryImpl",
            Mock(return_value=mock_over_inst),
        )

        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        # ValidationService called with positional (maint, git, metadata) +
        # kwargs (bulk_map_repo, overrides_repo).
        services["validation_cls"].assert_called_once_with(
            mock_maint_inst,
            mock_git_inst,
            mock_meta_inst,
            bulk_map_repo=mock_bulk_inst,
            overrides_repo=mock_over_inst,
        )

    def test_run_creates_whitelist_service_with_validation_dependency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should create WhitelistService with ValidationService dependency."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        services["whitelist_cls"].assert_called_once_with(services["validation_service"])

    def test_run_calls_check_whitelist_with_correct_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should call WhitelistService.check_whitelist() with correct parameters."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        repos = _patch_repos(monkeypatch)
        repos["git_repo"].list_submodules.return_value = ["pkg1", "pkg2"]
        repos["metadata_repo"].parse_source_packages.return_value = {"pkg1", "pkg2", "pkg3"}

        services = _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        services["whitelist_service"].check_whitelist.assert_called_once()
        call_args = services["whitelist_service"].check_whitelist.call_args[1]
        # whitelist_file should come from cloned SLFO repo (like validate command)
        assert call_args["whitelist_file"] == Path("/cache/slfo/whitelist_maintainership.json")
        assert call_args["shipped_packages"] == {"pkg1", "pkg2", "pkg3"}
        assert call_args["submodules"] == ["pkg1", "pkg2"]
        # cache_dir should come from config (XDG user cache)
        expected_cache_dir = Path("~/.cache/bugownership").expanduser()
        assert call_args["cache_dir"] == expected_cache_dir
        # overrides_file must resolve via importlib.resources to the
        # shipped JSON; verify basename.
        assert isinstance(call_args["overrides_file"], Path)
        assert call_args["overrides_file"].name == "false_positives_overrides.json"

    def test_run_returns_zero_when_no_inconsistencies_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 0 exit code when no inconsistencies found."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        result = run(args)

        assert result == 0

    def test_run_returns_one_when_inconsistencies_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 1 exit code when inconsistencies found."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(inconsistent_packages=["pkg1", "pkg2"]),
        )

        args = argparse.Namespace(version="16.1", config=None)
        result = run(args)

        assert result == 1

    def test_run_prints_inconsistent_packages_with_info_prefix(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print inconsistent packages with INFO prefix."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(inconsistent_packages=["apache2", "kernel-source"]),
        )

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        captured = capsys.readouterr()
        assert "INFO: Found 2 packages that are BOTH shipped AND whitelisted" in captured.out
        assert "INFO: Inconsistent packages" in captured.out
        assert "INFO: - apache2" in captured.out
        assert "INFO: - kernel-source" in captured.out

    def test_run_prints_success_message_when_no_issues(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print success message with INFO prefix when no issues."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        captured = capsys.readouterr()
        assert "INFO: No inconsistencies found" in captured.out

    def test_run_raises_error_when_version_not_found_in_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError when version not in config."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="99.9", config=None)

        with pytest.raises(ValueError, match="Version 99.9 not found in config"):
            run(args)

    def test_run_raises_error_when_product_config_has_no_branch_or_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError when product config has neither branch nor commit."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1"}],  # Missing branch and commit
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", config=None)

        with pytest.raises(ValueError, match="has neither branch nor commit"):
            run(args)

    def test_run_raises_error_when_git_ref_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise ValueError when git ref is empty."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": ""}],  # Empty branch
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", config=None)

        with pytest.raises(ValueError, match="Empty git ref for version 16.1"):
            run(args)

    def test_run_raises_error_when_slfo_git_url_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ValueError when slfo_git_url not in config."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            # Missing slfo_git_url
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        args = argparse.Namespace(version="16.1", config=None)

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            run(args)

    def test_run_supports_commit_ref_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should support commit ref type (not just branch)."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "commit": "abc123def"}],  # Commit instead of branch
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        repos = _patch_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        result = run(args)

        # Verify clone_or_update called with COMMIT ref type
        assert repos["git_repo"].clone_or_update.called
        call_kwargs = repos["git_repo"].clone_or_update.call_args[1]
        assert call_kwargs["git_ref"] == "abc123def"
        assert call_kwargs["ref_type"] == RefType.COMMIT
        assert result == 0

    def test_whitelist_prints_unresolved_names_section(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should print the unresolved-names section when unresolved_names is non-empty."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_services(
            monkeypatch,
            WhitelistCheckResult(
                inconsistent_packages=[],
                unresolved_names=["mystery-pkg"],
            ),
        )

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" in captured.out
        assert "mystery-pkg" in captured.out

    def test_whitelist_omits_unresolved_section_when_empty(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should NOT print the unresolved-names section when unresolved_names is empty."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        monkeypatch.setattr(
            "bugowner.commands.whitelist.load_config", Mock(return_value=mock_config)
        )

        _patch_repos(monkeypatch)
        _patch_services(monkeypatch)  # default: empty result, unresolved=[]

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        captured = capsys.readouterr()
        assert "Names with no source mapping" not in captured.out

    def test_run_passes_config_path_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should pass args.config to load_config() when provided."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.whitelist.load_config", mock_load_config)

        _patch_repos(monkeypatch)
        _patch_services(monkeypatch)

        config_path = Path("/custom/config.yaml")
        args = argparse.Namespace(version="16.1", config=config_path)
        run(args)

        mock_load_config.assert_called_once_with(config_path)

    def test_run_passes_none_to_load_config_when_no_config_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should pass None to load_config() when args.config is None (triggers search)."""
        mock_config = {
            "cache_dir": "~/.cache/bugownership",
            "whitelist_file": "whitelist_maintainership.json",
            "slfo_git_url": "https://github.com/example/slfo.git",
            "products": [{"version": "16.1", "branch": "SLFO-1.1"}],
        }
        mock_load_config = Mock(return_value=mock_config)
        monkeypatch.setattr("bugowner.commands.whitelist.load_config", mock_load_config)

        _patch_repos(monkeypatch)
        _patch_services(monkeypatch)

        args = argparse.Namespace(version="16.1", config=None)
        run(args)

        mock_load_config.assert_called_once_with(None)
