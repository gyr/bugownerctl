"""Integration tests for end-to-end CLI workflows.

Tests complete workflows from CLI entry through to results,
using real fixtures and minimal mocking.
"""

import gzip
import json
from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import patch

from bugownerctl.cli import main
from bugownerctl.domain.obs_source_info import ObsSourceInfo


class TestValidateWorkflow:
    """Integration tests for 'bugownerctl validate' workflow."""

    def test_validate_workflow_with_valid_data(self, tmp_path, monkeypatch):
        """Should complete full validation workflow with valid maintainership data.

        Workflow:
        1. Load maintainership data
        2. Download and parse repo metadata
        3. Load the OBS source info (binary→source mapping + OBS package set)
        4. Resolve binary→source via source-info + overrides pipeline
        5. Report validation results against the OBS package set
        """
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup test data files
        maintainership_data = {
            "packages": {
                "test-package": {"users": ["user1"], "groups": ["team1"]},
                "another-package": {"users": ["user2"], "groups": []},
            }
        }

        # Create minimal config file with new format
        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "products": [{"version": "16.1", "branch": "main", "obs_project": "TEST:Project:1.0"}],
        }
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        # Mock external calls
        with (
            patch(
                "bugownerctl.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.download_primary_metadata"
            ) as mock_download,
            patch(
                "bugownerctl.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.parse_source_packages"
            ) as mock_parse,
            patch(
                "bugownerctl.repositories.obs_source_info_repository.ObsSourceInfoRepositoryImpl.load_source_info"
            ) as mock_source_info,
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                return_value=json.dumps(maintainership_data).encode(),
            ) as mock_fetch,
            patch("sys.argv", ["bugownerctl", "check", "maintainership", "-r", "16.1"]),
        ):
            mock_download.return_value = tmp_path / "primary.xml.gz"
            mock_parse.return_value = {"test-package", "another-package"}
            mock_source_info.return_value = ObsSourceInfo(
                mapping={},
                project="test-project",
                fetched_at=datetime.now(UTC),
                packages=frozenset({"test-package", "another-package"}),
            )

            # Execute
            exit_code = main()

            # Verify
            assert exit_code == 0, "Validate should succeed with valid data"
            # The product's configured OBS project is the one queried.
            assert mock_source_info.call_args.args[0] == "TEST:Project:1.0"
            # The maintainership file is read from the remote at the product branch.
            mock_fetch.assert_called_once_with(
                "git@example.com:test/repo.git", "main", "_maintainership.json"
            )

    def test_validate_workflow_finds_orphan_packages(self, tmp_path, monkeypatch):
        """Should detect packages in repo without maintainers."""
        # Change to test directory
        monkeypatch.chdir(tmp_path)

        # Setup: package in repo but not in maintainership
        maintainership_data = {
            "packages": {"maintained-package": {"users": ["user1"], "groups": []}}
        }

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "products": [{"version": "16.1", "branch": "main", "obs_project": "TEST:Project:1.0"}],
        }
        (tmp_path / "validate_maintainership.yaml").write_text(json.dumps(config_data))

        with (
            patch(
                "bugownerctl.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.download_primary_metadata"
            ) as mock_download,
            patch(
                "bugownerctl.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.parse_source_packages"
            ) as mock_parse,
            patch(
                "bugownerctl.repositories.obs_source_info_repository.ObsSourceInfoRepositoryImpl.load_source_info"
            ) as mock_source_info,
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                return_value=json.dumps(maintainership_data).encode(),
            ),
            patch("sys.argv", ["bugownerctl", "check", "maintainership", "-r", "16.1"]),
        ):
            mock_download.return_value = tmp_path / "primary.xml.gz"
            mock_parse.return_value = {"maintained-package", "orphan-package"}
            mock_source_info.return_value = ObsSourceInfo(
                mapping={},
                project="test-project",
                fetched_at=datetime.now(UTC),
                packages=frozenset({"maintained-package", "orphan-package"}),
            )

            # Execute
            exit_code = main()

            # Verify - should report issues found
            assert exit_code == 2, "Should return 2 when orphan packages found"


def _serve_files(files: dict[str, bytes]) -> Callable[[str, str, str], bytes]:
    """Build a fetch_file side effect serving `files` by name, as if at the product ref."""

    def fetch_file(repo_url: str, ref: str, file_path: str) -> bytes:
        return files[file_path]

    return fetch_file


class TestQueryPackageWorkflow:
    """Integration tests for 'bugownerctl query package' workflow."""

    def test_query_package_finds_maintained_package(self, tmp_path, monkeypatch):
        """Should find and display package maintainers."""
        maintainership_data = {
            "packages": {"test-package": {"users": ["user1", "user2"], "groups": ["team1"]}}
        }

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }

        with (
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                side_effect=_serve_files(
                    {
                        "_maintainership.json": json.dumps(maintainership_data).encode(),
                        "whitelist_maintainership.json": json.dumps([]).encode(),
                    }
                ),
            ),
            patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
            patch("sys.argv", ["bugownerctl", "query", "package", "test-package", "-r", "16.1"]),
        ):
            exit_code = main()
            assert exit_code == 0, "Should succeed when package found"

    def test_query_package_finds_whitelisted_package(self, tmp_path, monkeypatch):
        """Should indicate when package is whitelisted (no maintainer)."""
        maintainership_data = {"packages": {}}

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }

        with (
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                side_effect=_serve_files(
                    {
                        "_maintainership.json": json.dumps(maintainership_data).encode(),
                        "whitelist_maintainership.json": json.dumps(
                            ["whitelisted-package"]
                        ).encode(),
                    }
                ),
            ),
            patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
            patch(
                "sys.argv",
                ["bugownerctl", "query", "package", "whitelisted-package", "-r", "16.1"],
            ),
        ):
            exit_code = main()
            assert exit_code == 0, "Should succeed when package whitelisted"

    def test_query_package_not_found(self, tmp_path, monkeypatch):
        """Should report when package not found in maintainership or whitelist."""
        maintainership_data = {"packages": {}}

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "maintainership_file": "_maintainership.json",
            "whitelist_file": "whitelist_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }

        with (
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                side_effect=_serve_files(
                    {
                        "_maintainership.json": json.dumps(maintainership_data).encode(),
                        "whitelist_maintainership.json": json.dumps([]).encode(),
                    }
                ),
            ),
            patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
            patch("sys.argv", ["bugownerctl", "query", "package", "unknown-package", "-r", "16.1"]),
        ):
            exit_code = main()
            assert exit_code == 0, "Query always returns 0, but prints 'Not found'"


class TestQueryMaintainerWorkflow:
    """Integration tests for 'bugownerctl query maintainer' workflow."""

    def test_query_maintainer_lists_all_packages(self, tmp_path, monkeypatch):
        """Should list all packages maintained by user or group."""
        maintainership_data = {
            "packages": {
                "package1": {"users": ["user1", "user2"], "groups": []},
                "package2": {"users": ["user1"], "groups": ["team1"]},
                "package3": {"users": ["user3"], "groups": []},
                "package4": {"users": [], "groups": ["team1"]},
            }
        }

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }

        with (
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                side_effect=_serve_files(
                    {
                        "_maintainership.json": json.dumps(maintainership_data).encode(),
                    }
                ),
            ),
            patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
            patch("sys.argv", ["bugownerctl", "query", "maintainer", "user1", "-r", "16.1"]),
        ):
            exit_code = main()
            assert exit_code == 0, "Should succeed when maintainer found"

    def test_query_maintainer_finds_group_packages(self, tmp_path, monkeypatch):
        """Should find packages maintained by a group."""
        maintainership_data = {
            "packages": {
                "package1": {"users": ["user1"], "groups": ["team1"]},
                "package2": {"users": [], "groups": ["team1"]},
                "package3": {"users": ["user1"], "groups": []},
            }
        }

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }

        with (
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                side_effect=_serve_files(
                    {
                        "_maintainership.json": json.dumps(maintainership_data).encode(),
                    }
                ),
            ),
            patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
            patch("sys.argv", ["bugownerctl", "query", "maintainer", "team1", "-r", "16.1"]),
        ):
            exit_code = main()
            assert exit_code == 0, "Should succeed when group found"

    def test_query_maintainer_not_found(self, tmp_path, monkeypatch):
        """Should report when maintainer has no packages."""
        maintainership_data = {"packages": {"package1": {"users": ["user1"], "groups": []}}}

        config_data = {
            "cache_dir": str(tmp_path / "cache"),
            "slfo_git_url": "git@example.com:test/repo.git",
            "maintainership_file": "_maintainership.json",
            "products": [{"version": "16.1", "branch": "main"}],
        }

        with (
            patch(
                "bugownerctl.repositories.remote_archive_repository.RemoteArchiveRepositoryImpl.fetch_file",
                side_effect=_serve_files(
                    {
                        "_maintainership.json": json.dumps(maintainership_data).encode(),
                    }
                ),
            ),
            patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
            patch("sys.argv", ["bugownerctl", "query", "maintainer", "unknown-user", "-r", "16.1"]),
        ):
            exit_code = main()
            assert exit_code == 0, "Should succeed but show empty list"


# Binaries and their src.rpm: cpp16/gcc16 come from gcc16 (on two arches); the
# shared -devel binary is built by both openblas flavours; the src entry is not a binary.
_PRIMARY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common"
          xmlns:rpm="http://linux.duke.edu/metadata/rpm">
  <package type="rpm"><name>gcc16</name><arch>x86_64</arch>
    <format><rpm:sourcerpm>gcc16-16.1.0-1.1.src.rpm</rpm:sourcerpm></format></package>
  <package type="rpm"><name>cpp16</name><arch>x86_64</arch>
    <format><rpm:sourcerpm>gcc16-16.1.0-1.1.src.rpm</rpm:sourcerpm></format></package>
  <package type="rpm"><name>cpp16</name><arch>aarch64</arch>
    <format><rpm:sourcerpm>gcc16-16.1.0-1.1.src.rpm</rpm:sourcerpm></format></package>
  <package type="rpm"><name>openblas-common-devel</name><arch>x86_64</arch>
    <format><rpm:sourcerpm>openblas_pthreads-0.3.30-1.1.src.rpm</rpm:sourcerpm></format></package>
  <package type="rpm"><name>openblas-common-devel</name><arch>x86_64</arch>
    <format><rpm:sourcerpm>openblas_openmp-0.3.30-1.1.src.rpm</rpm:sourcerpm></format></package>
  <package type="rpm"><name>gcc16</name><arch>src</arch>
    <format><rpm:sourcerpm>gcc16-16.1.0-1.1.src.rpm</rpm:sourcerpm></format></package>
</metadata>
"""


def _run_binpkg_source(tmp_path, binary_name):
    """Run 'query binpkg-source' through main() with only the metadata download faked.

    The download returns an inline gzipped primary.xml, so the real parser runs.
    Returns the exit code.
    """
    primary_xml = tmp_path / "primary.xml.gz"
    with gzip.open(primary_xml, "wt", encoding="utf-8") as f:
        f.write(_PRIMARY_XML)

    config_data = {
        "cache_dir": str(tmp_path / "cache"),
        "slfo_git_url": "git@example.com:test/repo.git",
        "products": [{"version": "16.1", "branch": "main"}],
    }

    with (
        patch(
            "bugownerctl.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.download_primary_metadata",
            return_value=primary_xml,
        ),
        patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
        patch("sys.argv", ["bugownerctl", "query", "binpkg-source", "-r", "16.1", binary_name]),
    ):
        return main()


class TestQueryBinpkgSourceWorkflow:
    """Integration tests for 'bugownerctl query binpkg-source' workflow."""

    def test_query_binpkg_source_prints_source_of_binary(self, tmp_path, capsys):
        """Should print the source package a binary is built from, once across arches."""
        exit_code = _run_binpkg_source(tmp_path, "cpp16")

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == "gcc16\n"

    def test_query_binpkg_source_prints_all_sources_of_multi_source_binary(self, tmp_path, capsys):
        """Should print every source that builds the binary, sorted, one per line."""
        exit_code = _run_binpkg_source(tmp_path, "openblas-common-devel")

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == "openblas_openmp\nopenblas_pthreads\n"

    def test_query_binpkg_source_not_found_reports_on_stderr_with_exit_zero(self, tmp_path, capsys):
        """An unknown binary leaves stdout empty, explains on stderr, and exits 0."""
        exit_code = _run_binpkg_source(tmp_path, "cpp61")

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == ""
        assert (
            "Binary package 'cpp61' not found in release 16.1 repository metadata" in captured.err
        )


def _run_srcpkg_binaries(tmp_path, source_name):
    """Run 'query srcpkg-binaries' through main() with only the metadata download faked.

    The download returns an inline gzipped primary.xml, so the real parser runs.
    Returns the exit code.
    """
    primary_xml = tmp_path / "primary.xml.gz"
    with gzip.open(primary_xml, "wt", encoding="utf-8") as f:
        f.write(_PRIMARY_XML)

    config_data = {
        "cache_dir": str(tmp_path / "cache"),
        "slfo_git_url": "git@example.com:test/repo.git",
        "products": [{"version": "16.1", "branch": "main"}],
    }

    with (
        patch(
            "bugownerctl.repositories.repo_metadata_repository.RepoMetadataRepositoryImpl.download_primary_metadata",
            return_value=primary_xml,
        ),
        patch("bugownerctl.commands.product_context.load_config", return_value=config_data),
        patch("sys.argv", ["bugownerctl", "query", "srcpkg-binaries", "-r", "16.1", source_name]),
    ):
        return main()


class TestQuerySrcpkgBinariesWorkflow:
    """Integration tests for 'bugownerctl query srcpkg-binaries' workflow."""

    def test_query_srcpkg_binaries_prints_binaries_sorted_once_across_arches(
        self, tmp_path, capsys
    ):
        """Should print every binary built from the source, sorted, once across arches."""
        exit_code = _run_srcpkg_binaries(tmp_path, "gcc16")

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == "cpp16\ngcc16\n"

    def test_query_srcpkg_binaries_not_found_reports_on_stderr_with_exit_zero(
        self, tmp_path, capsys
    ):
        """An unknown source leaves stdout empty, explains on stderr, and exits 0."""
        exit_code = _run_srcpkg_binaries(tmp_path, "gcc61")

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == ""
        assert (
            "Source package 'gcc61' not found in release 16.1 repository metadata" in captured.err
        )
