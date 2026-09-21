"""Tests for prepare_slfo_repo helper (repo_prep module)."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from bugownerctl.commands.repo_prep import prepare_slfo_repo
from bugownerctl.domain.ref_type import RefType
from bugownerctl.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

BASE_CONFIG: dict[str, Any] = {
    "cache_dir": "~/.cache/bugownerctl",
    "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
    "products": [
        {"version": "16.1", "branch": "slfo-main"},
        {"version": "16.0", "commit": "9d679ed"},
    ],
}


def _make_mock_git_cls(return_path: Path = Path("/cache/SLFO")) -> tuple[Mock, Mock]:
    """Build a (mock_cls, mock_instance) pair for GitRepositoryImpl."""
    mock_instance = Mock()
    mock_instance.clone_or_update.return_value = return_path
    mock_cls = Mock(return_value=mock_instance)
    return mock_cls, mock_instance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPrepareSlfoRepoRefTypes:
    """Tests that verify correct RefType and git_ref forwarded to clone_or_update."""

    def test_branch_ref_uses_branch_ref_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product with branch key → clone_or_update receives RefType.BRANCH and the branch name."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_repo_path == Path("/cache/SLFO")
        mock_git_instance.clone_or_update.assert_called_once_with(
            repo_url="gitea@src.suse.de:products/SLFO.git",
            git_ref="slfo-main",
            cache_dir=Path.home() / ".cache" / "bugownerctl",
            ref_type=RefType.BRANCH,
        )

    def test_commit_ref_uses_commit_ref_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product with commit key → clone_or_update receives RefType.COMMIT and the commit hash."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        prepare_slfo_repo(version="16.0", config_file=None)

        mock_git_instance.clone_or_update.assert_called_once_with(
            repo_url="gitea@src.suse.de:products/SLFO.git",
            git_ref="9d679ed",
            cache_dir=Path.home() / ".cache" / "bugownerctl",
            ref_type=RefType.COMMIT,
        )


class TestPrepareSlfoRepoCacheDir:
    """Tests that verify cache_dir tilde expansion and forwarding."""

    def test_cache_dir_tilde_is_expanded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache_dir with leading tilde is expanded to absolute home-based path."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        expected_cache_dir = Path.home() / ".cache" / "bugownerctl"
        assert ctx.cache_dir == expected_cache_dir
        call_kwargs = mock_git_instance.clone_or_update.call_args.kwargs
        assert call_kwargs["cache_dir"] == expected_cache_dir


class TestPrepareSlfoRepoContextFields:
    """Tests that verify the returned SlfoRepoContext fields."""

    def test_ctx_git_repo_is_same_instance_as_constructed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ctx.git_repo is the exact instance returned by GitRepositoryImpl(), not a new one."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, mock_git_instance = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.git_repo is mock_git_instance

    def test_ctx_slfo_repo_path_equals_clone_return(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ctx.slfo_repo_path equals the path returned by clone_or_update."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls(return_path=Path("/cache/SLFO"))
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_repo_path == Path("/cache/SLFO")

    def test_ctx_config_equals_loaded_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ctx.config is the exact dict object returned by load_config (identity check)."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.config is loaded_config


class TestPrepareSlfoRepoBaseUrl:
    """Tests for the optional per-product base_url key."""

    @staticmethod
    def _config_with_base_url(base_url: Any, include_key: bool = True) -> dict[str, Any]:
        """Build a config whose 16.1 product entry optionally carries base_url."""
        product: dict[str, Any] = {"version": "16.1", "branch": "slfo-main"}
        if include_key:
            product["base_url"] = base_url
        return {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [product],
        }

    @staticmethod
    def _patch(monkeypatch: pytest.MonkeyPatch, loaded_config: dict[str, Any]) -> Mock:
        """Patch load_config and GitRepositoryImpl; return the GitRepositoryImpl mock class."""
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)
        return mock_git_cls

    def test_base_url_absent_yields_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product entry without base_url key → ctx.base_url is None."""
        self._patch(monkeypatch, self._config_with_base_url(None, include_key=False))

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.base_url is None

    def test_base_url_valid_is_carried_verbatim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid per-product base_url reaches the context unmodified."""
        url = "https://download.suse.de/ibs/SUSE:/SLFO:/Products:/SLES:/16.1:/TEST/product/"
        self._patch(monkeypatch, self._config_with_base_url(url))

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.base_url == url

    def test_base_url_with_version_placeholder_is_not_expanded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A {version} placeholder is validated but left unexpanded on the context."""
        url = "https://example.test/SLES:/{version}:/TEST/product/"
        self._patch(monkeypatch, self._config_with_base_url(url))

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.base_url == url

    @pytest.mark.parametrize(
        ("bad_value", "type_name"),
        [
            (42, "int"),
            (["https://example.test/"], "list"),
            (None, "NoneType"),
            (True, "bool"),
        ],
    )
    def test_base_url_rejects_non_string(
        self, bad_value: Any, type_name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-string base_url raises ConfigError naming the received type."""
        self._patch(monkeypatch, self._config_with_base_url(bad_value))

        with pytest.raises(ConfigError, match=f"'base_url'.*{type_name}"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_base_url_rejects_blank_string(
        self, blank: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty or whitespace-only base_url raises ConfigError."""
        self._patch(monkeypatch, self._config_with_base_url(blank))

        with pytest.raises(ConfigError, match="'base_url'.*empty or whitespace-only"):
            prepare_slfo_repo(version="16.1", config_file=None)

    def test_base_url_rejects_missing_trailing_slash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A base_url not ending in '/' raises ConfigError explaining concatenation."""
        url = "https://example.test/SLES:/16.1:/TEST/product"
        self._patch(monkeypatch, self._config_with_base_url(url))

        with pytest.raises(ConfigError) as exc_info:
            prepare_slfo_repo(version="16.1", config_file=None)

        message = str(exc_info.value)
        assert "base_url" in message
        assert url in message
        assert "concatenat" in message

    @pytest.mark.parametrize(
        "bad_url",
        [
            "download.suse.de/ibs/SUSE:/SLFO:/Products:/SLES:/16.1:/TEST/product/",
            "not a url/",
            "/",
            "   /",
        ],
    )
    def test_base_url_rejects_url_without_scheme_or_host(
        self, bad_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A base_url missing a scheme or host is a config error, not a download failure."""
        self._patch(monkeypatch, self._config_with_base_url(bad_url))

        with pytest.raises(ConfigError, match="absolute URL"):
            prepare_slfo_repo(version="16.1", config_file=None)

    def test_base_url_rejection_happens_before_any_clone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An invalid base_url aborts before GitRepositoryImpl is ever constructed."""
        mock_git_cls = self._patch(monkeypatch, self._config_with_base_url(42))

        with pytest.raises(ConfigError):
            prepare_slfo_repo(version="16.1", config_file=None)

        mock_git_cls.assert_not_called()

    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://example.test/SLES:/{version/product/",
            "https://example.test/SLES:/{unknown}/product/",
            "https://example.test/SLES:/{0}/product/",
            "https://example.test/SLES:/{version.foo}/product/",
            "https://example.test/SLES:/{version[a]}/product/",
        ],
    )
    def test_base_url_rejects_unformattable_value(
        self, bad_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A base_url that cannot be .format()ted raises ConfigError, not a raw KeyError."""
        self._patch(monkeypatch, self._config_with_base_url(bad_url))

        with pytest.raises(ConfigError) as exc_info:
            prepare_slfo_repo(version="16.1", config_file=None)

        message = str(exc_info.value)
        assert "base_url" in message
        assert bad_url in message

    @staticmethod
    def _repo_prep_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
        """Warning messages emitted by the repo_prep logger only."""
        return [
            record.getMessage()
            for record in caplog.records
            if record.levelno == logging.WARNING and record.name == "bugownerctl.commands.repo_prep"
        ]

    @pytest.mark.parametrize("url", ["http://mirror.test/product/", "HTTP://mirror.test/product/"])
    def test_base_url_over_plain_http_warns_about_netrc_credentials(
        self, url: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A plain-http base_url warns that ~/.netrc credentials travel unencrypted.

        The scheme comparison is case-insensitive: RFC 3986 schemes are, and
        `requests` treats HTTP:// as cleartext just the same.
        """
        self._patch(monkeypatch, self._config_with_base_url(url))

        with caplog.at_level(logging.WARNING, logger="bugownerctl.commands.repo_prep"):
            ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.base_url == url
        assert any("netrc" in msg for msg in self._repo_prep_warnings(caplog))

    def test_base_url_over_https_does_not_warn(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An https base_url is silent — the warning is specific to cleartext transport."""
        self._patch(monkeypatch, self._config_with_base_url("https://mirror.test/product/"))

        with caplog.at_level(logging.WARNING, logger="bugownerctl.commands.repo_prep"):
            prepare_slfo_repo(version="16.1", config_file=None)

        assert not self._repo_prep_warnings(caplog)

    def test_base_url_on_other_product_is_not_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """base_url set on a different product entry does not leak into the requested one."""
        loaded_config: dict[str, Any] = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [
                {"version": "16.0", "commit": "9d679ed", "base_url": "https://example.test/a/"},
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        self._patch(monkeypatch, loaded_config)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.base_url is None


class TestPrepareSlfoRepoErrors:
    """Tests that verify ValueError is raised for invalid inputs."""

    def test_raises_version_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Requesting a version absent from products list raises ValueError."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="Version 99.9 not found in config"):
            prepare_slfo_repo(version="99.9", config_file=None)

    def test_raises_neither_branch_nor_commit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product config missing both branch and commit keys raises ValueError."""
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [
                {"version": "16.1"},  # neither branch nor commit
            ],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="has neither branch nor commit"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize("empty_ref", ["", None])
    def test_raises_empty_git_ref(
        self, empty_ref: str | None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string or None git ref raises ValueError."""
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [
                {"version": "16.1", "branch": empty_ref},
            ],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="Empty git ref for version 16.1"):
            prepare_slfo_repo(version="16.1", config_file=None)

    def test_raises_missing_slfo_git_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config without slfo_git_url raises ValueError."""
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            # slfo_git_url is absent
            "products": [
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.GitRepositoryImpl",
            Mock(),
        )

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            prepare_slfo_repo(version="16.1", config_file=None)


class TestPrepareSlfoRepoConfigFile:
    """Tests for config_file forwarding and cache_dir default."""

    def test_config_file_forwarded_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit config_file path is passed verbatim to load_config."""
        mock_load = Mock(return_value=dict(BASE_CONFIG))
        monkeypatch.setattr("bugownerctl.commands.repo_prep.load_config", mock_load)
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        prepare_slfo_repo(version="16.1", config_file=Path("/explicit/config.yaml"))

        mock_load.assert_called_once_with(Path("/explicit/config.yaml"))

    def test_cache_dir_defaults_when_key_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config without cache_dir key falls back to ~/.cache/bugownerctl."""
        loaded_config: dict[str, Any] = {
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [{"version": "16.1", "branch": "slfo-main"}],
            # cache_dir key intentionally absent
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_git_cls, _ = _make_mock_git_cls()
        monkeypatch.setattr("bugownerctl.commands.repo_prep.GitRepositoryImpl", mock_git_cls)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.cache_dir == Path.home() / ".cache" / "bugownerctl"


class TestPrepareSlfoRepoMissingConfig:
    """Tests that verify ConfigError is raised when the config file is missing."""

    def test_missing_config_file_raises_config_error(self) -> None:
        """Nonexistent explicit config path raises ConfigError, not FileNotFoundError."""
        nonexistent = Path("/nonexistent/path/that/cannot/exist/config.yaml")

        with pytest.raises(ConfigError):
            prepare_slfo_repo(version="16.1", config_file=nonexistent)
