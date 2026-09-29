"""Tests for prepare_slfo_repo helper (repo_prep module)."""

import logging
from importlib.resources import files
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

from bugownerctl.commands.repo_prep import prepare_slfo_repo
from bugownerctl.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

BASE_CONFIG: dict[str, Any] = {
    "cache_dir": "~/.cache/bugownerctl",
    "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
    "products": [
        {"version": "16.1", "branch": "slfo-main"},
        {"version": "16.0", "branch": "slfo-1.2"},
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPrepareSlfoRepoCacheDir:
    """Tests that verify cache_dir tilde expansion."""

    def test_cache_dir_tilde_is_expanded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cache_dir with leading tilde is expanded to absolute home-based path."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.cache_dir == Path.home() / ".cache" / "bugownerctl"


class TestPrepareSlfoRepoContextFields:
    """Tests that verify the returned SlfoRepoContext fields."""

    def test_ctx_carries_slfo_git_url_and_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ctx.slfo_git_url and ctx.ref are the configured URL and the product's branch."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

        ctx = prepare_slfo_repo(version="16.0", config_file=None)

        assert ctx.slfo_git_url == "gitea@src.suse.de:products/SLFO.git"
        assert ctx.ref == "slfo-1.2"

    def test_ctx_config_equals_loaded_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ctx.config is the exact dict object returned by load_config (identity check)."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

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
    def _patch(monkeypatch: pytest.MonkeyPatch, loaded_config: dict[str, Any]) -> None:
        """Patch load_config to return the given config."""
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

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
                {"version": "16.0", "branch": "slfo-1.2", "base_url": "https://example.test/a/"},
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        self._patch(monkeypatch, loaded_config)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.base_url is None


class TestPrepareSlfoRepoObsProject:
    """Tests for the per-product obs_project key."""

    @staticmethod
    def _config_with_obs_project(obs_project: Any, include_key: bool = True) -> dict[str, Any]:
        """Build a config whose 16.1 product entry optionally carries obs_project."""
        product: dict[str, Any] = {"version": "16.1", "branch": "slfo-main"}
        if include_key:
            product["obs_project"] = obs_project
        return {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [product],
        }

    @staticmethod
    def _patch(monkeypatch: pytest.MonkeyPatch, loaded_config: dict[str, Any]) -> None:
        """Patch load_config to return the given config."""
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

    def test_obs_project_absent_yields_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Product entry without obs_project key → ctx.obs_project is None."""
        self._patch(monkeypatch, self._config_with_obs_project(None, include_key=False))

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.obs_project is None

    def test_obs_project_valid_is_carried_verbatim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A configured obs_project reaches the context unmodified."""
        self._patch(monkeypatch, self._config_with_obs_project("EXAMPLE:Project:1.0"))

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.obs_project == "EXAMPLE:Project:1.0"

    @pytest.mark.parametrize(
        ("bad_value", "type_name"),
        [
            (42, "int"),
            (1.3, "float"),
            (["EXAMPLE:Project"], "list"),
            (None, "NoneType"),
            (True, "bool"),
        ],
    )
    def test_obs_project_rejects_non_string(
        self, bad_value: Any, type_name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-string obs_project raises ConfigError naming the received type."""
        self._patch(monkeypatch, self._config_with_obs_project(bad_value))

        with pytest.raises(ConfigError, match=f"'obs_project'.*{type_name}"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_obs_project_rejects_blank_string(
        self, blank: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty or whitespace-only obs_project raises ConfigError."""
        self._patch(monkeypatch, self._config_with_obs_project(blank))

        with pytest.raises(ConfigError, match="'obs_project'.*empty or whitespace-only"):
            prepare_slfo_repo(version="16.1", config_file=None)

    def test_obs_project_on_other_product_is_not_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """obs_project set on a different product entry does not leak into the requested one."""
        loaded_config: dict[str, Any] = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [
                {"version": "16.0", "branch": "slfo-1.2", "obs_project": "EXAMPLE:Other"},
                {"version": "16.1", "branch": "slfo-main"},
            ],
        }
        self._patch(monkeypatch, loaded_config)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.obs_project is None

    def test_bundled_example_config_sets_obs_project_for_every_product(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The template `init` installs maps each product to its own OBS project.

        Otherwise a freshly initialised config would make `check maintainership`
        and `check whitelist` fail with a ConfigError straight away, or resolve
        a release against another release's project.
        """
        template = files("bugownerctl").joinpath("data/config.example.yaml").read_text()
        example_config = yaml.safe_load(template)
        self._patch(monkeypatch, example_config)

        resolved = {
            product["version"]: prepare_slfo_repo(
                version=product["version"], config_file=None
            ).obs_project
            for product in example_config["products"]
        }
        assert resolved == {"16.0": "SUSE:SLFO:1.2", "16.1": "SUSE:SLFO:Main"}


class TestPrepareSlfoRepoErrors:
    """Tests that verify ValueError is raised for invalid inputs."""

    def test_raises_version_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Requesting a version absent from products list raises ValueError."""
        loaded_config = dict(BASE_CONFIG)
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

        with pytest.raises(ValueError, match="Version 99.9 not found in config"):
            prepare_slfo_repo(version="99.9", config_file=None)

    @pytest.mark.parametrize(
        "product",
        [
            {"version": "16.1"},
            {"version": "16.0", "commit": "9d679ed"},
        ],
    )
    def test_missing_branch_raises_config_error(
        self, product: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A product without a branch key raises ConfigError, commit pin or not.

        git archive serves only branch or tag names, so a commit pin can never
        be honoured.
        """
        loaded_config = {
            "cache_dir": "~/.cache/bugownerctl",
            "slfo_git_url": "gitea@src.suse.de:products/SLFO.git",
            "products": [product],
        }
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )

        version = product["version"]
        with pytest.raises(ConfigError, match=f"version {version} has no 'branch' configured"):
            prepare_slfo_repo(version=version, config_file=None)

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

        with pytest.raises(ValueError, match="slfo_git_url not found in config"):
            prepare_slfo_repo(version="16.1", config_file=None)


class TestPrepareSlfoRepoConfigFile:
    """Tests for config_file forwarding and cache_dir default."""

    def test_config_file_forwarded_to_load_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit config_file path is passed verbatim to load_config."""
        mock_load = Mock(return_value=dict(BASE_CONFIG))
        monkeypatch.setattr("bugownerctl.commands.repo_prep.load_config", mock_load)

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

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.cache_dir == Path.home() / ".cache" / "bugownerctl"


class TestPrepareSlfoRepoNoClone:
    """Tests that context resolution touches neither git nor the filesystem."""

    def test_context_resolution_never_clones_or_creates_cache_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No subprocess runs and cache_dir is not created; SLFO files come from git archive."""
        cache_dir = tmp_path / "cache"
        loaded_config = {**BASE_CONFIG, "cache_dir": str(cache_dir)}
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value=loaded_config),
        )
        mock_run = Mock()
        monkeypatch.setattr("subprocess.run", mock_run)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.cache_dir == cache_dir
        assert not cache_dir.exists()
        mock_run.assert_not_called()


class TestPrepareSlfoRepoUrlValidation:
    """Tests for the slfo_git_url format and SSRF checks done during context resolution."""

    @staticmethod
    def _patch_url(monkeypatch: pytest.MonkeyPatch, slfo_git_url: str) -> None:
        """Patch load_config to return BASE_CONFIG with the given slfo_git_url."""
        monkeypatch.setattr(
            "bugownerctl.commands.repo_prep.load_config",
            Mock(return_value={**BASE_CONFIG, "slfo_git_url": slfo_git_url}),
        )

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "not-a-url",
            "https://github.com/repo",  # Missing .git
            "ftp://example.com/repo.git",  # Not HTTP/HTTPS
            "https://example.com/repo.git; rm -rf /",  # Command injection attempt
            "git@github.com",  # SSH missing path
            "git@:repo.git",  # SSH missing host
            "@github.com:repo.git",  # SSH missing user
            "user@host:",  # SSH missing path
        ],
    )
    def test_rejects_invalid_url_format(
        self, invalid_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A slfo_git_url that is neither SSH nor HTTP(S) raises ValueError."""
        self._patch_url(monkeypatch, invalid_url)

        with pytest.raises(ValueError, match="Invalid repository URL format"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize(
        "ssh_url",
        [
            "git@github.com:user/repo.git",
            "git@src.suse.de:products/SLFO.git",
            "user@host.com:path/to/repo.git",
            "git@gitlab.com:group/subgroup/repo.git",
        ],
    )
    def test_accepts_valid_ssh_urls(self, ssh_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid SCP-style SSH slfo_git_url is accepted and carried on the context."""
        self._patch_url(monkeypatch, ssh_url)

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_git_url == ssh_url

    @pytest.mark.parametrize(
        "ssh_url_with_port",
        [
            "git@github.com:22:user/repo.git",
            "git@gitlab.com:443:group/repo.git",
            "user@host.com:8080:path/repo.git",
        ],
    )
    def test_rejects_ssh_url_with_port_syntax(
        self, ssh_url_with_port: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SCP-style SSH URLs have no port syntax; user@host:PORT:path is rejected."""
        self._patch_url(monkeypatch, ssh_url_with_port)

        with pytest.raises(ValueError, match="Invalid repository URL format"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize(
        "internal_url",
        [
            "https://127.0.0.1/repo.git",
            "https://localhost/repo.git",
            "https://0.0.0.0/repo.git",
        ],
    )
    def test_rejects_ssrf_to_localhost(
        self, internal_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An HTTP(S) slfo_git_url pointing at localhost raises ValueError."""
        self._patch_url(monkeypatch, internal_url)

        with pytest.raises(ValueError, match="internal network or metadata service"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize(
        "metadata_url",
        [
            "https://169.254.169.254/latest/meta-data.git",
            "https://metadata.google.internal/computeMetadata/v1.git",
        ],
    )
    def test_rejects_ssrf_to_metadata_service(
        self, metadata_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An HTTP(S) slfo_git_url pointing at a cloud metadata service raises ValueError."""
        self._patch_url(monkeypatch, metadata_url)

        with pytest.raises(ValueError, match="internal network or metadata service"):
            prepare_slfo_repo(version="16.1", config_file=None)

    @pytest.mark.parametrize(
        "private_url",
        [
            "https://10.0.0.1/repo.git",  # Private class A
            "https://172.16.0.1/repo.git",  # Private class B
            "https://192.168.1.1/repo.git",  # Private class C
        ],
    )
    def test_rejects_ssrf_to_private_networks(
        self, private_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An HTTP(S) slfo_git_url pointing at a private IP range raises ValueError."""
        self._patch_url(monkeypatch, private_url)

        with pytest.raises(ValueError, match="internal network or metadata service"):
            prepare_slfo_repo(version="16.1", config_file=None)

    def test_accepts_ssh_url_to_internal_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The SSRF check applies to HTTP(S) only; SSH to an internal git server is allowed."""
        self._patch_url(monkeypatch, "git@10.0.0.1:products/SLFO.git")

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_git_url == "git@10.0.0.1:products/SLFO.git"

    def test_accepts_public_https_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A well-formed HTTPS slfo_git_url on a public host is accepted."""
        self._patch_url(monkeypatch, "https://src.example.test/products/SLFO.git")

        ctx = prepare_slfo_repo(version="16.1", config_file=None)

        assert ctx.slfo_git_url == "https://src.example.test/products/SLFO.git"


class TestPrepareSlfoRepoMissingConfig:
    """Tests that verify ConfigError is raised when the config file is missing."""

    def test_missing_config_file_raises_config_error(self) -> None:
        """Nonexistent explicit config path raises ConfigError, not FileNotFoundError."""
        nonexistent = Path("/nonexistent/path/that/cannot/exist/config.yaml")

        with pytest.raises(ConfigError):
            prepare_slfo_repo(version="16.1", config_file=nonexistent)
