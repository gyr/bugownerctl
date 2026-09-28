"""Tests for ObsBulkSourceInfoRepository.

Phase 2 of the OBS source-name resolution refactor. Tests cover:
  - Protocol shape.
  - Input validation (project name).
  - Subprocess invocation (mocked; argv-style; timeout).
  - XML parsing (alias/subpack/originpackage chain; collision rules).
  - No caching (osc runs on every call; nothing written to disk).
  - Failure modes (non-zero exit, timeout, malformed XML, osc not installed).
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bugownerctl.domain.bulk_map import BulkMap
from bugownerctl.exceptions import MissingBinaryError, NetworkTimeoutError
from bugownerctl.repositories.obs_bulk_source_info_repository import (
    MAX_XML_BYTES,
    ObsBulkSourceInfoRepository,
    ObsBulkSourceInfoRepositoryImpl,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "obs_bulk_sample.xml"


# ---------------------------------------------------------------------------
# Helpers


def _fixture_xml() -> bytes:
    return FIXTURE_PATH.read_bytes()


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> Mock:
    proc = Mock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ---------------------------------------------------------------------------
# Protocol / input validation


class TestProtocol:
    def test_protocol_methods_present(self) -> None:
        """ObsBulkSourceInfoRepository must expose load_bulk_map."""
        assert hasattr(ObsBulkSourceInfoRepository, "load_bulk_map")

    def test_impl_satisfies_protocol(self) -> None:
        """ObsBulkSourceInfoRepositoryImpl satisfies the protocol."""
        impl: ObsBulkSourceInfoRepository = ObsBulkSourceInfoRepositoryImpl()
        assert callable(impl.load_bulk_map)


class TestInputValidation:
    def test_load_bulk_map_rejects_invalid_project_chars(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(ValueError, match="project"):
            repo.load_bulk_map("../etc")

    def test_project_with_shell_metachars_rejected(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(ValueError, match="project"):
            repo.load_bulk_map("SUSE; rm -rf /")

    def test_project_with_newline_rejected(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(ValueError, match="project"):
            repo.load_bulk_map("SUSE\nfoo")

    def test_project_with_path_traversal_rejected(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(ValueError, match="project"):
            repo.load_bulk_map("../etc/passwd")

    def test_empty_project_rejected(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(ValueError, match="project"):
            repo.load_bulk_map("")

    def test_project_exceeding_200_chars_rejected(self) -> None:
        """Real OBS project names are <100 chars; bound at 200 to cap argv/URL growth."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(ValueError, match="project"):
            repo.load_bulk_map("A" * 201)


# ---------------------------------------------------------------------------
# Subprocess invocation


class TestSubprocessInvocation:
    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_runs_osc_api_with_correct_args(self, mock_run: Mock) -> None:
        mock_run.return_value = _make_proc(returncode=0, stdout=_fixture_xml())
        repo = ObsBulkSourceInfoRepositoryImpl()
        repo.load_bulk_map("SUSE:SLFO:Main")
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == [
            "osc",
            "-A",
            "https://api.suse.de",
            "api",
            "/source/SUSE:SLFO:Main?view=info&parse=1",
        ]
        assert kwargs.get("capture_output") is True
        assert kwargs.get("check") is False
        # Timeout MUST be set (no unbounded subprocess).
        assert kwargs.get("timeout") is not None
        assert kwargs.get("timeout") > 0

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_subprocess_nonzero_raises_runtime_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _make_proc(returncode=1, stderr=b"auth failed")
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(RuntimeError, match="osc"):
            repo.load_bulk_map("SUSE:SLFO:Main")

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_subprocess_timeout_raises_network_timeout_error(
        self, mock_run: Mock
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osc", timeout=120)
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(NetworkTimeoutError, match="timed out"):
            repo.load_bulk_map("SUSE:SLFO:Main")

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_osc_not_installed_raises_missing_binary_error(self, mock_run: Mock) -> None:
        mock_run.side_effect = FileNotFoundError("osc")
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(MissingBinaryError, match="osc"):
            repo.load_bulk_map("SUSE:SLFO:Main")


# ---------------------------------------------------------------------------
# Parsing


class TestParsing:
    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_parses_fixture_into_expected_mapping(self, mock_run: Mock) -> None:
        mock_run.return_value = _make_proc(returncode=0, stdout=_fixture_xml())
        repo = ObsBulkSourceInfoRepositoryImpl()
        bm = repo.load_bulk_map("SUSE:SLFO:Main")
        assert isinstance(bm, BulkMap)
        assert bm.project == "SUSE:SLFO:Main"
        m = bm.mapping
        # identity
        assert m["apache2"] == "apache2"
        assert m["nginx"] == "nginx"
        assert m["389-ds"] == "389-ds"
        # single subpack alias
        assert m["nginx-devel"] == "nginx"
        # multi-subpack
        assert m["389-ds-devel"] == "389-ds"
        assert m["lib389"] == "389-ds"
        # originpackage multibuild chain (one level)
        assert m["kernel-azure"] == "kernel-source-azure-base"
        assert m["kernel-source-azure-base"] == "kernel-source-azure-base"
        # linked example: parser tolerates <linked>, picks up identity
        assert m["cross-linked-example"] == "cross-linked-example"
        # subpack-only name
        assert m["apache2-doc"] == "apache2-doc-source"
        assert m["apache2-doc-source"] == "apache2-doc-source"
        # collision: identity wins
        assert m["collision-pkg"] == "collision-pkg"
        assert m["other-source"] == "other-source"
        # 3-level origin chain collapses to root
        assert m["chain-a"] == "chain-c"
        assert m["chain-b"] == "chain-c"
        assert m["chain-c"] == "chain-c"

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_packages_exclude_multibuild_flavors(self, mock_run: Mock) -> None:
        """packages holds plain <sourceinfo package> names; `pkg:flav` flavors are excluded."""
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="pkg"><subpacks>pkg</subpacks></sourceinfo>'
            b'<sourceinfo package="pkg:flav">'
            b"<originpackage>pkg</originpackage><subpacks>pkg-flav</subpacks>"
            b"</sourceinfo>"
            b'<sourceinfo package="other"><subpacks>other-devel</subpacks></sourceinfo>'
            b"</sourceinfolist>"
        )
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsBulkSourceInfoRepositoryImpl()
        bm = repo.load_bulk_map("SUSE:SLFO:Main")
        assert bm.packages == frozenset({"pkg", "other"})

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_packages_keep_linked_packages_without_colon(
        self, mock_run: Mock
    ) -> None:
        """An <originpackage> without `:` in the name is a real package, not a flavor."""
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="pkg"><subpacks>pkg</subpacks></sourceinfo>'
            b'<sourceinfo package="linked-src">'
            b"<originpackage>pkg</originpackage><subpacks>linked-src</subpacks>"
            b"</sourceinfo>"
            b"</sourceinfolist>"
        )
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsBulkSourceInfoRepositoryImpl()
        bm = repo.load_bulk_map("SUSE:SLFO:Main")
        assert bm.packages == frozenset({"pkg", "linked-src"})

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_sourceinfo_with_error_stays_in_packages_and_warns(
        self, mock_run: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A <sourceinfo> carrying <error> is still a project package; a warning names it."""
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="pkg-ok"><subpacks>pkg-ok</subpacks></sourceinfo>'
            b'<sourceinfo package=" pkg-broken ">'
            b"<error>  bad build configuration, no build type defined or detected  </error>"
            b"</sourceinfo>"
            b"</sourceinfolist>"
        )
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsBulkSourceInfoRepositoryImpl()

        with caplog.at_level("WARNING"):
            bm = repo.load_bulk_map("SUSE:SLFO:Main")

        assert bm.packages == frozenset({"pkg-ok", "pkg-broken"})
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any(
            "pkg-broken" in msg
            and "bad build configuration, no build type defined or detected" in msg
            and " pkg-broken " not in msg
            for msg in warnings
        ), warnings

    def test_extract_package_names_does_not_warn_for_flavor_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A flavor is not in packages, so its <error> is not warned about."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="pkg"/>'
            b'<sourceinfo package="pkg:flav"><error>flavor broke</error></sourceinfo>'
            b"</sourceinfolist>"
        )
        root = repo._parse_sourceinfolist(xml)

        with caplog.at_level("WARNING"):
            packages = repo._extract_package_names(root)

        assert packages == frozenset({"pkg"})
        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    @pytest.mark.parametrize("error_element", [b"<error/>", b"<error>   </error>"])
    def test_extract_package_names_warns_for_error_without_text(
        self, error_element: bytes, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An <error> with no text is still an error: warned with an empty message."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b'<sourceinfolist><sourceinfo package="pkg">'
            + error_element
            + b"</sourceinfo></sourceinfolist>"
        )
        root = repo._parse_sourceinfolist(xml)

        with caplog.at_level("WARNING"):
            packages = repo._extract_package_names(root)

        assert packages == frozenset({"pkg"})
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert warnings == ["OBS reports an error for package pkg: "]

    def test_extract_package_names_skips_empty_and_missing_package_attribute(self) -> None:
        """Empty or absent `package` attributes never yield an empty-string name."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package=""><subpacks>x</subpacks></sourceinfo>'
            b"<sourceinfo><subpacks>y</subpacks></sourceinfo>"
            b'<sourceinfo package="real"/>'
            b"</sourceinfolist>"
        )
        root = repo._parse_sourceinfolist(xml)
        assert repo._extract_package_names(root) == frozenset({"real"})

    def test_extract_package_names_strips_surrounding_whitespace(self) -> None:
        """A padded `package` attribute yields the bare name: " bash " is "bash"."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = b'<sourceinfolist><sourceinfo package=" bash "/></sourceinfolist>'
        root = repo._parse_sourceinfolist(xml)
        assert repo._extract_package_names(root) == frozenset({"bash"})

    def test_build_bulk_map_strips_package_attribute_whitespace(self) -> None:
        """A padded `package` attribute keys and attributes to the bare name."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package=" bash "><subpacks>bash-doc</subpacks></sourceinfo>'
            b"</sourceinfolist>"
        )
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        assert m == {"bash": "bash", "bash-doc": "bash"}

    def test_whitespace_only_package_attribute_is_skipped(self) -> None:
        """A `package` attribute that is empty after stripping yields no name."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="   "><subpacks>x</subpacks></sourceinfo>'
            b'<sourceinfo package="real"/>'
            b"</sourceinfolist>"
        )
        root = repo._parse_sourceinfolist(xml)
        assert repo._extract_package_names(root) == frozenset({"real"})
        assert repo._build_bulk_map(root) == {"real": "real"}

    def test_build_bulk_map_strips_originpackage_whitespace(self) -> None:
        """A padded <originpackage> attributes the flavor's subpacks to the bare parent."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="kernel:azure">'
            b"<originpackage> kernel </originpackage>"
            b"<subpacks>kernel-azure</subpacks>"
            b"</sourceinfo>"
            b"</sourceinfolist>"
        )
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        assert m == {"kernel:azure": "kernel", "kernel-azure": "kernel"}

    def test_build_bulk_map_strips_subpacks_whitespace(self) -> None:
        """A padded <subpacks> name maps under its bare name."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="bash"><subpacks> bash-doc </subpacks></sourceinfo>'
            b"</sourceinfolist>"
        )
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        assert m == {"bash": "bash", "bash-doc": "bash"}

    def test_build_bulk_map_treats_whitespace_only_originpackage_as_absent(self) -> None:
        """A whitespace-only <originpackage> behaves exactly like no originpackage."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="kernel:azure">'
            b"<originpackage>   </originpackage>"
            b"<subpacks>kernel-azure</subpacks>"
            b"</sourceinfo>"
            b"</sourceinfolist>"
        )
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        assert m == {"kernel:azure": "kernel:azure", "kernel-azure": "kernel:azure"}

    def test_build_bulk_map_resolves_originpackage_chain(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = b"""<sourceinfolist>
          <sourceinfo package="C"><subpacks>C</subpacks></sourceinfo>
          <sourceinfo package="B">
            <originpackage>C</originpackage><subpacks>B</subpacks>
          </sourceinfo>
          <sourceinfo package="A">
            <originpackage>B</originpackage><subpacks>A</subpacks>
          </sourceinfo>
        </sourceinfolist>"""
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        assert m["A"] == "C"
        assert m["B"] == "C"
        assert m["C"] == "C"

    def test_build_bulk_map_collision_prefers_identity_over_alias(self) -> None:
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = b"""<sourceinfolist>
          <sourceinfo package="X"><subpacks>X</subpacks></sourceinfo>
          <sourceinfo package="Y">
            <subpacks>Y</subpacks><subpacks>X</subpacks>
          </sourceinfo>
        </sourceinfolist>"""
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        # Identity wins: X → X, NOT X → Y.
        assert m["X"] == "X"
        assert m["Y"] == "Y"

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_invalid_xml_raises_runtime_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _make_proc(returncode=0, stdout=b"not xml at all")
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(RuntimeError, match="not valid XML"):
            repo.load_bulk_map("SUSE:SLFO:Main")

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_status_reply_raises_with_project_root_tag_and_summary(self, mock_run: Mock) -> None:
        """An OBS <status> error document stops the run."""
        xml = b'<status code="unknown_project"><summary> Project not found </summary></status>'
        mock_run.return_value = _make_proc(returncode=0, stdout=xml)
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(RuntimeError) as exc_info:
            repo.load_bulk_map("SUSE:SLFO:Main")
        assert str(exc_info.value) == (
            "OBS reply for project SUSE:SLFO:Main is not a package list "
            "(root element <status>): Project not found"
        )
        # Distinct from the empty-<sourceinfolist> error.
        assert "lists no packages" not in str(exc_info.value)

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_non_sourceinfolist_reply_without_summary_ends_at_root_tag(
        self, mock_run: Mock
    ) -> None:
        """No <summary> child: the message ends after the root element, no dangling colon."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<directory/>")
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(RuntimeError) as exc_info:
            repo.load_bulk_map("SUSE:SLFO:Main")
        assert str(exc_info.value) == (
            "OBS reply for project SUSE:SLFO:Main is not a package list (root element <directory>)"
        )

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_empty_sourceinfolist_raises_no_packages(self, mock_run: Mock) -> None:
        """A valid but empty <sourceinfolist> stops the run."""
        mock_run.return_value = _make_proc(returncode=0, stdout=b"<sourceinfolist/>")
        repo = ObsBulkSourceInfoRepositoryImpl()
        with pytest.raises(RuntimeError) as exc_info:
            repo.load_bulk_map("SUSE:SLFO:Main")
        message = str(exc_info.value)
        assert message == (
            "OBS project SUSE:SLFO:Main lists no packages; check 'obs_project' in your config"
        )
        # Distinct from the non-<sourceinfolist> error.
        assert "not a package list" not in message
        assert "root element" not in message

    def test_parse_sourceinfolist_rejects_doctype_declaration(self) -> None:
        """DOCTYPE declarations enable billion-laughs entity-expansion DoS; refuse them."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        evil = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY a "evil">]><sourceinfolist/>'
        with pytest.raises(RuntimeError, match="DOCTYPE"):
            repo._parse_sourceinfolist(evil)

    def test_parse_sourceinfolist_rejects_doctype_beyond_4096_bytes(self) -> None:
        """DOCTYPE beyond the 4096-byte scan window must still be rejected."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        # 5001-byte comment pushes <!DOCTYPE past the former [:4096] scan window.
        padding = b"<!-- " + b"x" * 5001 + b" -->"
        evil = padding + b'<!DOCTYPE foo [<!ENTITY a "x">]><sourceinfolist/>'
        with pytest.raises(RuntimeError, match="DOCTYPE"):
            repo._parse_sourceinfolist(evil)

    def test_build_bulk_map_ignores_whitespace_only_subpacks(self) -> None:
        """A <subpacks>   </subpacks> element must not produce a whitespace key.

        Python truthiness considers a whitespace string truthy, so the original
        filter `if s.text` admitted these and created mapping entries like
        `{"   ": "pkg"}`. Strip then re-check truthiness.
        """
        repo = ObsBulkSourceInfoRepositoryImpl()
        xml = (
            b"<sourceinfolist>"
            b'<sourceinfo package="pkg">'
            b"<subpacks>   </subpacks>"
            b"<subpacks>\n\t</subpacks>"
            b"<subpacks>real-binary</subpacks>"
            b"</sourceinfo>"
            b"</sourceinfolist>"
        )
        m = repo._build_bulk_map(repo._parse_sourceinfolist(xml))
        # No whitespace-only keys at all.
        assert all(k.strip() == k and k for k in m)
        # The real subpack survives.
        assert m["real-binary"] == "pkg"
        # The source identity remains.
        assert m["pkg"] == "pkg"

    def test_parse_sourceinfolist_rejects_oversized_xml(self) -> None:
        """Bodies larger than MAX_XML_BYTES are rejected before parsing."""
        repo = ObsBulkSourceInfoRepositoryImpl()
        # Use multiplication, not a real 50 MB allocation.
        oversized = b"x" * (MAX_XML_BYTES + 1)
        with pytest.raises(RuntimeError, match="exceeds"):
            repo._parse_sourceinfolist(oversized)


# ---------------------------------------------------------------------------
# No caching


class TestNoCache:
    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_runs_osc_on_every_call(self, mock_run: Mock) -> None:
        """Two consecutive calls each fetch from OBS; nothing is reused between them."""
        mock_run.return_value = _make_proc(returncode=0, stdout=_fixture_xml())
        repo = ObsBulkSourceInfoRepositoryImpl()
        repo.load_bulk_map("SUSE:SLFO:Main")
        repo.load_bulk_map("SUSE:SLFO:Main")
        assert mock_run.call_count == 2

    @patch("bugownerctl.repositories.obs_bulk_source_info_repository.subprocess.run")
    def test_load_bulk_map_writes_no_files(
        self, mock_run: Mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The reply is parsed in memory; no file is created, not even in cwd."""
        monkeypatch.chdir(tmp_path)
        mock_run.return_value = _make_proc(returncode=0, stdout=_fixture_xml())
        repo = ObsBulkSourceInfoRepositoryImpl()
        repo.load_bulk_map("SUSE:SLFO:Main")
        assert list(tmp_path.rglob("obs_bulk_map.*")) == []
        assert list(tmp_path.iterdir()) == []
