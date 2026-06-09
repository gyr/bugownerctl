# Bugownership CLI

[![CI](https://github.com/gyr/bugownership/actions/workflows/ci.yml/badge.svg)](https://github.com/gyr/bugownership/actions/workflows/ci.yml)

Package maintainership validation and management tool for SUSE Linux Enterprise.

Validates package ownership, checks whitelists, and queries maintainer information using a unified CLI interface.

## Installation

```bash
# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Quick Start

```bash
# First time: Initialize config file (recommended)
bugowner init

# Validate maintainership for SLES 16.1
bugowner validate -v 16.1

# Check whitelist against shipped packages
bugowner whitelist-check -v 16.1

# Check package maintainership
bugowner query package apache2

# List packages maintained by user
bugowner query maintainer user1
```

## Commands

### `bugowner init`

Create initial configuration file from bundled template.

**Usage:**
```bash
bugowner init [--location {user,local,system}] [--force]
```

**Options:**
- `--location` - Where to create config (default: `user`)
  - `user` - `~/.config/bugownership/config.yaml` (recommended)
  - `local` - `./validate_maintainership.yaml` (project-specific)
  - `system` - `/etc/bugownership/config.yaml` (system-wide, requires sudo)
- `--force` - Overwrite existing config file

**Examples:**
```bash
# Create user config (recommended for first-time setup)
bugowner init

# Create project-local config
bugowner init --location local

# Create system-wide config
sudo bugowner init --location system

# Overwrite existing config
bugowner init --force
```

**What it does:**
1. Loads bundled example template
2. Creates parent directories if needed
3. Copies template to target location
4. Shows next steps (edit config, run validate)

**Exit codes:**
- `0` - Config created successfully
- `1` - Error (file exists, permission denied, etc.)

**Output:**
```
✓ Created user config
  Location: /home/user/.config/bugownership/config.yaml

Next steps:
  1. Edit config: /home/user/.config/bugownership/config.yaml
  2. Update slfo_git_url and products
  3. Run: bugowner validate -v 16.1
```

---

### `bugowner validate`

Validates package maintainership data for consistency.

**Usage:**
```bash
bugowner validate -v <version> [--config <path>] [--debug]
```

**Options:**
- `-v, --version` - SLES version (required, e.g., "16.1")
- `-c, --config` - Path to config file (optional, uses search hierarchy)
- `-d, --debug` - Enable debug logging

**What it checks:**
- Orphan packages (in repo, no maintainer)
- Unmaintained submodules (not in maintainership file)
- Shipped packages missing submodules
- Binary→source package mappings (cached for performance)

**Performance features:**
- Version-specific cache isolation (no data corruption across versions)
- Memory-efficient streaming downloads (~8KB vs ~50MB)
- Repomd.xml caching for faster subsequent runs
- Cache hits skip unnecessary network requests

**Examples:**
```bash
# Validate SLES 16.1 (uses config search hierarchy)
bugowner validate -v 16.1

# Validate with explicit config file
bugowner validate -v 16.1 --config /custom/config.yaml

# Validate with debug logging
bugowner validate -v 16.0 --debug

# Use environment variable for config
export BUGOWNER_CONFIG=/path/to/config.yaml
bugowner validate -v 16.1
```

**Exit codes:**
- `0` - No issues found
- `1` - Issues found (orphans, unmaintained, etc.)

**Output:**
- Orphan packages list
- Unmaintained submodules list
- Shipped packages not in submodules
- New binary→source mappings discovered

---

### `bugowner whitelist-check`

Validates that whitelisted packages are NOT shipped in the distribution.

**Purpose:** Detect when packages expected to be unshipped are actually shipped (inconsistency).

**Usage:**
```bash
bugowner whitelist-check -v <version> [--config <path>]
```

**Options:**
- `-v, --version` - SLES version (required)
- `-c, --config` - Path to config file (optional, uses search hierarchy)

**What it does:**
- Downloads repository metadata (primary.xml.gz)
- Clones/updates git repository
- Extracts validated shipped packages (same pipeline as `validate`)
- Loads whitelist file (`whitelist_maintainership.json`)
- Finds intersection: packages that are BOTH shipped AND whitelisted
- Reports inconsistencies

**Examples:**
```bash
# Check whitelist with automatic config discovery
bugowner whitelist-check -v 16.1

# Check whitelist with explicit config
bugowner whitelist-check -v 16.1 --config /path/to/config.yaml
```

**Exit codes:**
- `0` - No inconsistencies found (all whitelisted packages are NOT shipped)
- `1` - Inconsistencies found (some whitelisted packages ARE shipped)

**Output:**
```
INFO: No inconsistencies found. All whitelisted packages are NOT shipped.
```

or:

```
INFO: Found 3 packages that are BOTH shipped AND whitelisted (inconsistency).
INFO: Inconsistent packages (should NOT be shipped if whitelisted):
INFO: - package1
INFO: - package2
INFO: - package3
INFO: Discovered 5 new binary→source mappings.
```

**Whitelist File Location:**

The whitelist file is read from the **cloned SLFO git repository**, not the current working directory.

Example path: `~/.cache/bugownership/SLFO/whitelist_maintainership.json`

**Whitelist File Format:**

Create `whitelist_maintainership.json` in the SLFO git repository with package names expected to be NOT shipped:

```json
[
  "package1",
  "package2",
  "package3"
]
```

**Security:**

Config file names are validated to prevent path traversal attacks. Invalid file names (e.g., `../../../etc/passwd`) are rejected with a clear error message.

**Migration Note:**

The old `bugowner whitelist update` command has been removed. The whitelist file is now manually maintained as a reference for validation.

---

### `bugowner query package`

Check maintainership status of a package.

**Usage:**
```bash
bugowner query package <package_name>
```

**Examples:**
```bash
# Check if apache2 is maintained
bugowner query package apache2

# Check whitelisted package
bugowner query package legacy-pkg
```

**Exit code:** Always `0`

**Output:**
```
Package: apache2
Status: Maintained
Maintainers:
  - user1
  - user2
  - team1
```

**Status values:**
- `Maintained` - Has maintainers in `_maintainership.json`
- `Whitelisted` - In `whitelist_maintainership.json`
- `Not found` - Not in either file

---

### `bugowner query maintainer`

List all packages maintained by a user or group.

**Usage:**
```bash
bugowner query maintainer <maintainer_name>
```

**Examples:**
```bash
# List packages for user
bugowner query maintainer user1

# List packages for group
bugowner query maintainer team1
```

**Exit code:** Always `0`

**Output:**
```
Maintainer: user1
Packages (5):
  - apache2
  - nginx
  - package1
  - package2
  - package3
```

---

## Configuration

### Config File Location

The tool uses a **standard search hierarchy** to find configuration:

**Search order (highest to lowest priority):**
1. **CLI flag:** `--config /path/to/config.yaml` (explicit override)
2. **Environment variable:** `BUGOWNER_CONFIG=/path/to/config.yaml`
3. **Project-local:** `./validate_maintainership.yaml` (current directory)
4. **User config:** `~/.config/bugownership/config.yaml` (recommended)
5. **System config:** `/etc/bugownership/config.yaml` (system-wide)

**XDG Base Directory support:**
- Respects `XDG_CONFIG_HOME` environment variable
- Default user config: `$XDG_CONFIG_HOME/bugownership/config.yaml`
- Fallback: `~/.config/bugownership/config.yaml`

**Best practices:**
- **First-time users:** Run `bugowner init` to create user config
- **Project-specific:** Use `bugowner init --location local` for per-project configs
- **CI/CD:** Use `--config` flag or `BUGOWNER_CONFIG` env var for explicit control
- **System-wide:** Use `sudo bugowner init --location system` for shared config

**Examples:**
```bash
# Let tool find config automatically (searches hierarchy)
bugowner validate -v 16.1

# Explicit config (highest priority, skips search)
bugowner validate -v 16.1 --config /ci/config.yaml

# Environment variable (second priority)
export BUGOWNER_CONFIG=/team/shared-config.yaml
bugowner validate -v 16.1

# Create user config (recommended first step)
bugowner init
```

**Error handling:**
- If explicit `--config` or `BUGOWNER_CONFIG` is set but file doesn't exist → **hard error**
- If no config found in search hierarchy → **clear error showing all searched locations**

### Config File Format

Create config file manually or use `bugowner init` to generate from template:

```yaml
# Cache directory for downloads (version-specific subdirs created automatically)
# Structure: {cache_dir}/repodata/{version}/
cache_dir: ~/.cache/bugownership

# Git repository URL
slfo_git_url: gitea@src.suse.de:products/SLFO.git

# Maintainership file name
maintainership_file: _maintainership.json

# Whitelist file name
whitelist_file: whitelist_maintainership.json

# Product version mappings
products:
  - version: "16.0"
    commit: 9d679ed
  - version: "16.1"
    branch: slfo-main
```

## Data Files

### `_maintainership.json`

Primary maintainership data (from SLFO git repo):

```json
{
  "header": {
    "document": "obs-maintainers",
    "version": "1.0"
  },
  "packages": {
    "apache2": {
      "users": ["user1", "user2"],
      "groups": ["webserver-team"]
    }
  }
}
```

### `whitelist_maintainership.json`

Manually maintained whitelist for packages expected to be NOT shipped:

```json
[
  "legacy-package1",
  "legacy-package2"
]
```

**Note:** This file is no longer auto-generated. It serves as a reference list for validation via `bugowner whitelist-check`.

### `false_positives_overrides.json`

Hand-curated mapping of binary/subpackage names to canonical source package names. Used to correct cases the OBS bulk map gets wrong:

```json
{
  "kernel-azure": "kernel-source-azure"
}
```

**Location:** `bugowner/data/false_positives_overrides.json`, shipped inside the wheel. Resolved at runtime via `importlib.resources` — there is no separate file to deploy.

**Editing:** Send a PR against `src/bugowner/data/false_positives_overrides.json` in this repo. Schema is `{"binary_or_subpkg_name": "source_pkg_name" | null}` — `null` means "treat as not-shipped, do not flag".

**Why a file, not a cache:** Earlier versions auto-populated `~/.cache/bugownership/false_positives.json` from OBS lookups. That cache silently shadowed real bugs (a stale entry could hide a missing maintainership row). Hand-curated overrides put a human in the loop and make every entry diff-reviewable. Full rationale, alternatives considered, and consequences are recorded in `docs/adr/0001-source-name-resolution.md`.

### How `bugowner validate` resolves source names

For every shipped binary name `n` found in the SLES repo, the resolver picks the first hit from this pipeline:

1. **Overrides file** — `false_positives_overrides.json` lookup. Wins outright; `null` means "skip this name".
2. **OBS bulk map** — single `osc api /source/SUSE:SLFO:Main?view=info&parse=1` fetched once per run and cached on disk for 7 days. Maps subpackage → source.
3. **Identity fallthrough** — assume `n` is itself the source name.
4. **Residue** — if the resolved name is not present in SLFO submodules, the name lands in `shipped_not_in_submodule`. Names that fell through step 3 AND aren't a submodule are additionally surfaced under "Names with no source mapping" so reviewers can decide whether to add an override.

## Cache System

### Repository Metadata Cache

The tool caches repository metadata for performance and to support multiple SLES versions simultaneously.

**Cache directory structure:**
```
~/.cache/bugownership/repodata/
├── 16.0/
│   ├── repomd.xml                      # Repository metadata index
│   └── {checksum}-primary.xml.gz       # Package metadata (20-50MB)
├── 16.1/
│   ├── repomd.xml
│   └── {checksum}-primary.xml.gz
└── {version}/
    └── ...
```

**Key features:**

1. **Version-specific isolation** - Each SLES version has its own cache directory
   - Prevents data corruption when switching between versions
   - Allows parallel validation of multiple versions
   - Example: `~/.cache/bugownership/repodata/16.1/`

2. **Memory-efficient streaming** - Downloads use 8KB chunks instead of loading entire files
   - Reduces memory footprint from ~50MB to ~8KB
   - Handles large metadata files without memory issues

3. **Smart caching** - Checksum validation prevents unnecessary downloads
   - Repomd.xml cached for faster subsequent runs
   - Primary metadata only re-downloaded when checksums change
   - Cache hits skip all network requests

**Cache management:**
```bash
# View cache contents
ls -lh ~/.cache/bugownership/repodata/

# Clear cache for specific version
rm -rf ~/.cache/bugownership/repodata/16.1/

# Clear all cached metadata
rm -rf ~/.cache/bugownership/repodata/

# Cache will automatically rebuild on next run
bugowner validate -v 16.1
```

**Performance impact:**
- First run: Downloads ~20-50MB metadata (one-time cost)
- Subsequent runs: 0 downloads if metadata unchanged
- Memory usage: ~8KB during download (streaming)
- Multi-version: Each version cached independently

## Dependencies

**Runtime:**
- Python 3.10+
- `lxml` - XML parsing
- `PyYAML` - Config file parsing
- `requests` - HTTP downloads

**External tools:**
- `git` - Repository operations
- `osc` - OBS queries (requires logged-in session to `https://api.suse.de`)

**Development:**
- `pytest` - Testing
- `pytest-cov` - Coverage reports
- `mypy` - Type checking
- `ruff` - Linting and formatting
- `bandit` - Security scanning

**Install all:**
```bash
# Runtime + dev dependencies (recommended)
uv sync --extra dev

# Or with pip (editable install + dev extras)
uv pip install -e ".[dev]"

# Runtime only
uv pip install -e .
```

## Development

### Setup

```bash
# Clone repository
git clone <repo-url>
cd bugownership

# Install in editable mode with dev dependencies
uv sync --extra dev

# Alternative: pip-style
uv pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/bugowner --cov-report=term-missing

# Run specific test file
pytest tests/test_validation_service.py

# Run single test
pytest tests/test_validation_service.py::test_find_orphan_packages
```

### Code Quality

**Run CI checks locally (recommended):**
```bash
# Check all (mirrors CI exactly)
./scripts/check.sh

# Auto-fix + check
./scripts/fix.sh
```

**Individual checks:**
```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/

# Security scan
bandit -c .bandit -r src/

# Tests with coverage
pytest --cov=src/bugowner --cov-report=term-missing --cov-fail-under=90
```

### Build & Wheel Verification

```bash
# Build the wheel
uv build

# Verify bundled data files are present in the wheel
unzip -l dist/*.whl | grep -E "example|overrides"
```

Expected output includes both:
- `bugowner/data/config.example.yaml`
- `bugowner/data/false_positives_overrides.json`

### CI/CD Pipeline

**GitHub Actions workflow runs on:**
- Push to `master`
- Pull requests to `master`

**Quality gates (all must pass):**
1. ✅ Ruff linting
2. ✅ Ruff formatting
3. ✅ MyPy type checking
4. ✅ Bandit security scanning
5. ✅ Pytest with 90% coverage

**Local validation:**
```bash
# Run same checks as CI
./scripts/check.sh

# Auto-fix issues first
./scripts/fix.sh
```

**Scripts:**
- `scripts/check.sh` - Run all CI checks locally (read-only)
- `scripts/fix.sh` - Auto-fix formatting/linting, then validate

### Architecture

```
CLI Layer (cli.py)
    ↓
Command Layer (commands/)
    ↓
Service Layer (services/)
    ↓
Repository Layer (repositories/)
    ↓
External Systems (Git, OBS, Files)
```

**Principles:**
- TDD (Red-Green-Refactor)
- SOLID design
- Protocol-based interfaces
- Dependency injection

See `IMPLEMENTATION_PLAN.md` for detailed architecture.

## Migration from Legacy Scripts

**Old scripts are deprecated but still functional.**

| Old Script | New Command |
|------------|-------------|
| `validate_maintainership.py -v 16.1` | `bugowner validate -v 16.1` |
| `create_whitelist_maintainership.py` | ~~`bugowner whitelist update`~~ (removed) |
| `check_package_maintainer.py <pkg>` | `bugowner query package <pkg>` |
| N/A | `bugowner query maintainer <user>` (new) |
| N/A | `bugowner whitelist-check -v <version>` (new) |
| N/A | `bugowner init` (new) |

**Migration steps:**
1. Install new CLI: `uv pip install -e .`
2. **Initialize config:** `bugowner init` (creates `~/.config/bugownership/config.yaml`)
3. **Edit config:** Update `slfo_git_url` and `products` in generated config
4. Test new commands alongside old scripts
5. Update scripts/automation to use `bugowner` CLI
6. Remove old script calls once verified

**Configuration migration:**
- Old: Required `validate_maintainership.yaml` in current directory
- New: Supports **config search hierarchy** (CLI flag → env var → project → user → system)
- **Backward compatible:** Project-local config (`./validate_maintainership.yaml`) still works
- **Recommended:** Use `bugowner init` to create user config for global access

**Compatibility:** `_maintainership.json` and other data files shared between old and new. **Breaking:** the runtime `false_positives.json` cache is no longer used. Source-name overrides now ship in the wheel at `bugowner/data/false_positives_overrides.json` and are edited via PR. Any leftover `~/.cache/bugownership/false_positives.json` from a previous version is harmless and can be removed with `rm ~/.cache/bugownership/false_positives.json`. See `docs/adr/0001-source-name-resolution.md`.

## Troubleshooting

**"Config file not found"**
```bash
# Option 1: Create user config (recommended)
bugowner init

# Option 2: Create project-local config
bugowner init --location local

# Option 3: Explicitly specify config location
bugowner validate -v 16.1 --config /path/to/config.yaml

# Option 4: Use environment variable
export BUGOWNER_CONFIG=/path/to/config.yaml
bugowner validate -v 16.1

# View search locations (error message shows all paths checked)
bugowner validate -v 16.1  # If no config found, shows search hierarchy
```

**"Config file exists" (when running init)**
```bash
# Overwrite existing config
bugowner init --force

# Or manually edit existing config
vim ~/.config/bugownership/config.yaml
```

**"ModuleNotFoundError"**
```bash
# Reinstall package
uv pip install -e .
```

**"osc command failed"**
```bash
# Ensure logged into OBS
osc api https://api.suse.de
```

**"Git clone failed"**
```bash
# Verify SSH keys configured for Gitea
ssh -T gitea@src.suse.de
```

**"Coverage below 90%"**
```bash
# Run full test suite
pytest --cov=src/bugowner --cov-report=html
firefox htmlcov/index.html
```

**"CI checks failing locally but passing in CI"**
```bash
# Use exact CI commands
./scripts/check.sh
```

**"Download or parsing errors"**
```bash
# Clear cache for affected version
rm -rf ~/.cache/bugownership/repodata/16.1/

# Retry validation (will re-download)
bugowner validate -v 16.1
```

**"Cache corruption or stale data"**
```bash
# Clear all cached metadata
rm -rf ~/.cache/bugownership/repodata/

# Or clear specific version
rm -rf ~/.cache/bugownership/repodata/16.0/

# Cache rebuilds automatically on next run
```

**"Disk space issues"**
```bash
# Check cache size (each version ~20-50MB)
du -sh ~/.cache/bugownership/repodata/*/

# Remove old/unused version caches
rm -rf ~/.cache/bugownership/repodata/15.*/
```

## Security

### Path Traversal Protection

Config file names (e.g., `whitelist_file`, `maintainership_file`) are validated to prevent path traversal attacks.

**Validated:**
- ✅ Simple filenames: `whitelist.json`
- ✅ Subdirectories: `config/whitelist.json`

**Rejected:**
- ❌ Parent directory traversal: `../etc/passwd`
- ❌ Absolute paths: `/etc/passwd`
- ❌ Hidden traversal: `subdir/../../etc/passwd`

**Implementation:**

Uses `Path.resolve() + relative_to()` pattern to ensure config file names stay within their intended directories. Symlinks are followed and validated to prevent symlink attacks.

**Error Example:**
```
ValueError: Whitelist file escapes base directory: 
'../../../etc/passwd' resolves to /home/user/etc/passwd 
(outside /home/user/.cache/bugownership/SLFO)
```

### File Location Security

- **Whitelist file:** Read from cloned SLFO repository (validated)
- **Maintainership file:** Read from cloned SLFO repository (validated)
- **Source-name overrides:** Read-only from `bugowner/data/false_positives_overrides.json` (wheel-resident). Loader caps body at 1 MiB, treats missing or non-regular paths as `{}` (no overrides), requires a JSON object root with `str | None` values, tolerates a UTF-8 BOM.
- **OBS bulk source-info cache:** Read/write at `{cache_dir}/obs_bulk_map.xml` plus a `obs_bulk_map.meta.json` sidecar (`{project, fetched_at, sha256}`). Symlinks rejected; atomic temp+rename on write; SHA-256 integrity check on read; 7-day TTL; cache files chmod 0o600 (parent dir 0o700). Filenames are constant — switching projects triggers a re-fetch via the meta `project` cross-check, not a per-project filename.

## Contributing

1. Create feature branch: `git checkout -b feature/description`
2. Follow TDD: write tests first
3. Run quality checks: `./scripts/check.sh`
4. Ensure 90%+ coverage
5. Create PR with descriptive commit messages

**Pre-commit workflow:**
```bash
# Before committing
./scripts/fix.sh      # Auto-fix issues
./scripts/check.sh    # Verify all checks pass
git add <files>
git commit
```

**Commit format:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `ci:`, `docs:`)

## License

[Add license info]

## Support

- Issues: [GitHub Issues](link)
- Documentation: See `IMPLEMENTATION_PLAN.md`
- Help: `bugowner --help`
- CI Status: Check GitHub Actions tab
