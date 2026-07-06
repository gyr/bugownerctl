# Bugownership CLI

[![CI](https://github.com/gyr/bugownerctl/actions/workflows/ci.yml/badge.svg)](https://github.com/gyr/bugownerctl/actions/workflows/ci.yml)

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
bugownerctl init

# Validate maintainership for SLES 16.1
bugownerctl check maintainership -r 16.1

# Check whitelist against shipped packages
bugownerctl check whitelist -r 16.1

# Validate user logins in maintainership file are confirmed OBS accounts
bugownerctl check users -r 16.1

# Check package maintainership
bugownerctl query package apache2 -r 16.1

# List packages maintained by user
bugownerctl query maintainer user1 -r 16.1
```

## Commands

### Global flags

Global flags must be placed **before** the subcommand name:

```bash
bugownerctl --version            # print installed version and exit
bugownerctl --help               # show subcommands
bugownerctl -q check …           # quiet: ERROR only
bugownerctl -v check …           # verbose: INFO on stderr
bugownerctl -d check …           # debug: DEBUG on stderr
```

| Flag | Level | What you see |
|------|-------|--------------|
| `-q, --quiet` | ERROR | errors only |
| *(none)* | WARNING | warnings + errors |
| `-v, --verbose` | INFO | progress + warnings + errors |
| `-d, --debug` | DEBUG | everything |

Results always go to **stdout**. Log records go to **stderr**.

### `bugownerctl init`

Create initial configuration file from bundled template.

**Usage:**
```bash
bugownerctl init [--location {user,local,system}] [--force]
```

**Options:**
- `--location` - Where to create config (default: `user`)
  - `user` - `~/.config/bugownerctl/config.yaml` (recommended)
  - `local` - `./validate_maintainership.yaml` (project-specific)
  - `system` - `/etc/bugownerctl/config.yaml` (system-wide, requires sudo)
- `--force` - Overwrite existing config file

**Examples:**
```bash
# Create user config (recommended for first-time setup)
bugownerctl init

# Create project-local config
bugownerctl init --location local

# Create system-wide config
sudo bugownerctl init --location system

# Overwrite existing config
bugownerctl init --force
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
  Location: /home/user/.config/bugownerctl/config.yaml

Next steps:
  1. Edit config: /home/user/.config/bugownerctl/config.yaml
  2. Update slfo_git_url and products
  3. Run: bugownerctl check maintainership -r 16.1
```

---

### `bugownerctl check maintainership`

Validates package maintainership data for consistency.

**Usage:**
```bash
bugownerctl check maintainership -r <version> [--config <path>] [--strict] [--refresh-bulk-map]
```

**Options:**
- `-r, --release` - SLES version (required, e.g., "16.1")
- `-c, --config` - Path to config file (optional, uses search hierarchy)
- `--strict` - Also gate on secondary findings (see table below)
- `--refresh-bulk-map` - Force re-fetch of OBS bulk source-info map, ignoring cache
- `-v, --verbose` - Enable verbose (INFO) logging (global flag, must precede subcommand)
- `-d, --debug` - Enable debug logging (global flag, must precede subcommand)

**Gate / `--strict` table:**

| Finding | Default gate | With `--strict` |
|---------|-------------|-----------------|
| Orphan packages | exit 2 | exit 2 |
| Shipped-not-in-submodule | — (informational) | exit 2 |
| Unresolved names | — (informational) | exit 2 |
| Maintained-without-submodule | — (informational) | exit 2 |

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
bugownerctl check maintainership -r 16.1

# Validate with explicit config file
bugownerctl check maintainership -r 16.1 --config /custom/config.yaml

# Validate with debug logging (global flag before subcommand)
bugownerctl -d check maintainership -r 16.0

# Use environment variable for config
export BUGOWNERCTL_CONFIG=/path/to/config.yaml
bugownerctl check maintainership -r 16.1

# Also gate on secondary findings
bugownerctl check maintainership -r 16.1 --strict
```

**Exit codes:**
- `0` - No gating findings
- `2` - Gating findings present (orphan packages; or secondary findings with `--strict`)
- `64` - Usage/config error (missing `-r`, missing config file)
- `127` - `git` binary not found

---

### `bugownerctl check whitelist`

Validates that whitelisted packages are NOT shipped in the distribution.

**Purpose:** Detect when packages expected to be unshipped are actually shipped (inconsistency).

**Usage:**
```bash
bugownerctl check whitelist -r <version> [--config <path>] [--strict] [--refresh-bulk-map]
```

**Options:**
- `-r, --release` - SLES version (required)
- `-c, --config` - Path to config file (optional, uses search hierarchy)
- `--strict` - Also gate on unresolved names (see table below)
- `--refresh-bulk-map` - Force re-fetch of OBS bulk source-info map, ignoring cache

**Gate / `--strict` table:**

| Finding | Default gate | With `--strict` |
|---------|-------------|-----------------|
| Inconsistent packages | exit 2 | exit 2 |
| Unresolved names | — (informational) | exit 2 |

**What it does:**
- Downloads repository metadata (primary.xml.gz)
- Clones/updates git repository
- Extracts validated shipped packages (same pipeline as `check maintainership`)
- Loads whitelist file (`whitelist_maintainership.json`)
- Finds intersection: packages that are BOTH shipped AND whitelisted
- Reports inconsistencies

**Examples:**
```bash
# Check whitelist with automatic config discovery
bugownerctl check whitelist -r 16.1

# Check whitelist with explicit config
bugownerctl check whitelist -r 16.1 --config /path/to/config.yaml

# Also gate on unresolved names
bugownerctl check whitelist -r 16.1 --strict
```

**Exit codes:**
- `0` - No inconsistencies found (all whitelisted packages are NOT shipped)
- `2` - Inconsistencies found (some whitelisted packages ARE shipped); or unresolved names with `--strict`
- `64` - Usage/config error (missing `-r`, missing config file)
- `127` - `git` binary not found

**Output (clean):**
```
No inconsistencies found. All whitelisted packages are NOT shipped.
```

**Output (with inconsistencies):**
```
Found 3 packages that are BOTH shipped AND whitelisted (inconsistency).
Inconsistent packages (should NOT be shipped if whitelisted):
- package1
- package2
- package3
```

**Whitelist File Location:**

The whitelist file is read from the **cloned SLFO git repository**, not the current working directory.

Example path: `~/.cache/bugownerctl/SLFO/whitelist_maintainership.json`

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

The old `bugownerctl whitelist update` command has been removed. The whitelist file is now manually maintained as a reference for validation.

---

### `bugownerctl check users`

Validates that user logins in the maintainership file are confirmed OBS accounts.

**Purpose:** Detect logins that are locked, non-confirmed, or absent from OBS before they
cause maintainership data to reference invalid accounts. Groups are not checked (only the
`users` key per package).

**Usage:**
```bash
bugownerctl check users -r <version> [--config <path>] [--api <url>] [--batch-size <n>]
```

**Options:**
- `-r, --release` - SLES version (required, e.g., "16.1")
- `-c, --config` - Path to config file (optional, uses search hierarchy)
- `--api` - OBS API base URL (default: `https://api.suse.de`)
- `--batch-size` - Max logins per OBS API call (default: `50`, must be ≥ 1)

**What it does:**
1. Clones/updates the SLFO git repository
2. Loads `_maintainership.json` from the repo
3. Extracts all unique user logins across all packages
4. Queries OBS `/search/person` in batches (requires a logged-in `osc` session)
5. Classifies each login: confirmed, invalid (locked / non-confirmed), or not found

**Examples:**
```bash
# Validate user logins for SLES 16.1
bugownerctl check users -r 16.1

# Use a different OBS instance
bugownerctl check users -r 16.1 --api https://api.opensuse.org

# Use a smaller batch size
bugownerctl check users -r 16.1 --batch-size 25

# With explicit config file
bugownerctl check users -r 16.1 --config /path/to/config.yaml
```

**Exit codes:**
- `0` - All user logins are confirmed OBS accounts
- `2` - One or more logins are invalid or not found in OBS
- `64` - Usage/config error
- `124` - `osc` API call timed out
- `127` - `osc` binary not found

**Output (when issues found):**
```
Found 5 confirmed OBS accounts.
Found 1 invalid (locked / non-confirmed) accounts.
Invalid accounts:
- lockeduser
Found 2 accounts not found in OBS.
Accounts not found in OBS:
- ghost1
- ghost2
3 of 8 users are not confirmed OBS accounts.
```

Note: confirmed account names are only shown on **stderr** with `-v/--verbose`. The confirmed **count** is always shown on stdout.

**Output (all confirmed):**
```
Found 8 confirmed OBS accounts.
All 8 users are confirmed OBS accounts.
```

**Requirements:**
- `osc` must be installed and logged in to the target OBS instance (`osc api <url>`)
- Only user logins are validated; group names in `groups` keys are intentionally skipped

---

### `bugownerctl query package`

Check maintainership status of a package.

**Usage:**
```bash
bugownerctl query package <package_name> -r <version> [-c <config>]
```

**Examples:**
```bash
# Check if apache2 is maintained
bugownerctl query package apache2 -r 16.1

# Check whitelisted package
bugownerctl query package legacy-pkg -r 16.1

# With explicit config
bugownerctl query package apache2 -r 16.1 --config /path/to/config.yaml
```

**Exit codes:**
- `0` - Query completed successfully
- `1` - Bad version (no matching product in config) or maintainership file not found

**Maintainership File Location:**

The maintainership and whitelist files are read from the **cloned SLFO git repository**, not the current working directory.

Example path: `~/.cache/bugownerctl/SLFO/_maintainership.json`

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

### `bugownerctl query maintainer`

List all packages maintained by a user or group.

**Usage:**
```bash
bugownerctl query maintainer <maintainer_name> -r <version> [-c <config>]
```

**Examples:**
```bash
# List packages for user
bugownerctl query maintainer user1 -r 16.1

# List packages for group
bugownerctl query maintainer team1 -r 16.1

# With explicit config
bugownerctl query maintainer user1 -r 16.1 --config /path/to/config.yaml
```

**Exit codes:**
- `0` - Query completed successfully
- `1` - Bad version (no matching product in config) or maintainership file not found

**Maintainership File Location:**

The maintainership file is read from the **cloned SLFO git repository**, not the current working directory.

Example path: `~/.cache/bugownerctl/SLFO/_maintainership.json`

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

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Clean — no gating findings |
| 1 | Internal/unexpected error; missing data file |
| 2 | Gating findings present (see `--strict`) |
| 64 | Usage/config error: bad arguments, missing or invalid config file |
| 124 | Network/subprocess timeout (`osc`, HTTP) |
| 127 | Required binary missing (`git`, `osc`) |
| 130 | SIGINT (Ctrl+C) |

Exit code `2` means findings that require action. Exit code `1` is reserved for unexpected
failures (bugs, missing data files). These are distinct so CI pipelines can tell
"distro has orphans — act" from "`osc` not on PATH — fix infra".

---

## Configuration

### Config File Location

The tool uses a **standard search hierarchy** to find configuration:

**Search order (highest to lowest priority):**
1. **CLI flag:** `--config /path/to/config.yaml` (explicit override)
2. **Environment variable:** `BUGOWNERCTL_CONFIG=/path/to/config.yaml`
3. **Project-local:** `./validate_maintainership.yaml` (current directory)
4. **User config:** `~/.config/bugownerctl/config.yaml` (recommended)
5. **System config:** `/etc/bugownerctl/config.yaml` (system-wide)

**XDG Base Directory support:**
- Respects `XDG_CONFIG_HOME` environment variable
- Default user config: `$XDG_CONFIG_HOME/bugownerctl/config.yaml`
- Fallback: `~/.config/bugownerctl/config.yaml`

**Best practices:**
- **First-time users:** Run `bugownerctl init` to create user config
- **Project-specific:** Use `bugownerctl init --location local` for per-project configs
- **CI/CD:** Use `--config` flag or `BUGOWNERCTL_CONFIG` env var for explicit control
- **System-wide:** Use `sudo bugownerctl init --location system` for shared config

**Examples:**
```bash
# Let tool find config automatically (searches hierarchy)
bugownerctl check maintainership -r 16.1

# Explicit config (highest priority, skips search)
bugownerctl check maintainership -r 16.1 --config /ci/config.yaml

# Environment variable (second priority)
export BUGOWNERCTL_CONFIG=/team/shared-config.yaml
bugownerctl check maintainership -r 16.1

# Create user config (recommended first step)
bugownerctl init
```

**Error handling:**
- If explicit `--config` or `BUGOWNERCTL_CONFIG` is set but file doesn't exist → **exit 64** (config error)
- If no config found in search hierarchy → **exit 64** with clear error showing all searched locations

### Config File Format

Create config file manually or use `bugownerctl init` to generate from template:

```yaml
# Cache directory for downloads (version-specific subdirs created automatically)
# Structure: {cache_dir}/repodata/{version}/
cache_dir: ~/.cache/bugownerctl

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

**Note:** This file is no longer auto-generated. It serves as a reference list for validation via `bugownerctl check whitelist`.

### `false_positives_overrides.json`

Hand-curated mapping of binary/subpackage names to canonical source package names. Used to correct cases the OBS bulk map gets wrong:

```json
{
  "kernel-azure": "kernel-source-azure"
}
```

**Location:** `bugownerctl/data/false_positives_overrides.json`, shipped inside the wheel. Resolved at runtime via `importlib.resources` — there is no separate file to deploy.

**Editing:** Send a PR against `src/bugownerctl/data/false_positives_overrides.json` in this repo. Schema is `{"binary_or_subpkg_name": "source_pkg_name" | null}` — `null` means "treat as not-shipped, do not flag".

**Why a file, not a cache:** Earlier versions auto-populated `~/.cache/bugownerctl/false_positives.json` from OBS lookups. That cache silently shadowed real bugs (a stale entry could hide a missing maintainership row). Hand-curated overrides put a human in the loop and make every entry diff-reviewable. Full rationale, alternatives considered, and consequences are recorded in `docs/adr/0001-source-name-resolution.md`.

### How `bugownerctl check maintainership` resolves source names

For every shipped binary name `n` found in the SLES repo, the resolver picks the first hit from this pipeline:

1. **Overrides file** — `false_positives_overrides.json` lookup. Wins outright; `null` means "skip this name".
2. **OBS bulk map** — single `osc api /source/SUSE:SLFO:Main?view=info&parse=1` fetched once per run and cached on disk for 7 days (`{cache_dir}/obs_bulk_map.xml`). Maps subpackage → source. Pass `--refresh-bulk-map` to force an immediate re-fetch without waiting for the TTL to expire.
3. **Identity fallthrough** — assume `n` is itself the source name.
4. **Residue** — if the resolved name is not present in SLFO submodules, the name lands in `shipped_not_in_submodule`. Names that fell through step 3 AND aren't a submodule are additionally surfaced under "Names with no source mapping" so reviewers can decide whether to add an override.

## Cache System

### Repository Metadata Cache

The tool caches repository metadata for performance and to support multiple SLES versions simultaneously.

**Cache directory structure:**
```
~/.cache/bugownerctl/repodata/
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
   - Example: `~/.cache/bugownerctl/repodata/16.1/`

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
ls -lh ~/.cache/bugownerctl/repodata/

# Clear cache for specific version
rm -rf ~/.cache/bugownerctl/repodata/16.1/

# Clear all cached metadata
rm -rf ~/.cache/bugownerctl/repodata/

# Cache will automatically rebuild on next run
bugownerctl check maintainership -r 16.1
```

**Performance impact:**
- First run: Downloads ~20-50MB metadata (one-time cost)
- Subsequent runs: 0 downloads if metadata unchanged
- Memory usage: ~8KB during download (streaming)
- Multi-version: Each version cached independently

## Dependencies

**Runtime:**
- Python 3.13+
- `defusedxml` - Safe XML parsing (XXE/DTD protection)
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
pytest --cov=src/bugownerctl --cov-report=term-missing

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
pytest --cov=src/bugownerctl --cov-report=term-missing --cov-fail-under=90
```

### Build & Wheel Verification

```bash
# Build the wheel
uv build

# Verify bundled data files are present in the wheel
unzip -l dist/*.whl | grep -E "example|overrides"
```

Expected output includes both:
- `bugownerctl/data/config.example.yaml`
- `bugownerctl/data/false_positives_overrides.json`

### Releasing

Version is derived automatically from git tags via `hatch-vcs` — there is no `version =` field in `pyproject.toml` to edit manually.

```bash
# 1. Ensure master is clean and all changes are committed
git status -sb

# 2. Annotated tag (add -s to GPG-sign)
git tag -a v0.3.0 -m "Release 0.3.0 — <summary>"

# 3. Push commit and tag
git push origin master
git push origin v0.3.0
```

Untagged commits produce a PEP 440 dev version automatically (e.g. `0.2.0.dev3+gabcdef1`). The `fallback-version = "0.0.0+unknown"` in `pyproject.toml` applies only when no git history is available (e.g. a tarball export with no `.git/`).

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

**All legacy scripts, including `validate_maintainership.py`, have been removed.**

| Old Script | New Command |
|------------|-------------|
| `validate_maintainership.py -v 16.1` | `bugownerctl check maintainership -r 16.1` |
| `validate_maintainer.py -v 16.1` | `bugownerctl check users -r 16.1` (new) |
| N/A | `bugownerctl query maintainer <user>` (new) |
| N/A | `bugownerctl check whitelist -r <version>` (new) |
| N/A | `bugownerctl init` (new) |

**Migration steps:**
1. Install new CLI: `uv pip install -e .`
2. **Initialize config:** `bugownerctl init` (creates `~/.config/bugownerctl/config.yaml`)
3. **Edit config:** Update `slfo_git_url` and `products` in generated config
4. Test new commands alongside old scripts
5. Update scripts/automation to use `bugownerctl` CLI
6. Remove old script calls once verified

**Configuration migration:**
- Old: Required `validate_maintainership.yaml` in current directory
- New: Supports **config search hierarchy** (CLI flag → env var → project → user → system)
- **Backward compatible:** Project-local config (`./validate_maintainership.yaml`) still works
- **Recommended:** Use `bugownerctl init` to create user config for global access

**Compatibility:** `_maintainership.json` and other data files shared between old and new. **Breaking:** the runtime `false_positives.json` cache is no longer used. Source-name overrides now ship in the wheel at `bugownerctl/data/false_positives_overrides.json` and are edited via PR. Any leftover `~/.cache/bugownerctl/false_positives.json` from a previous version is harmless and can be removed with `rm ~/.cache/bugownerctl/false_positives.json`. See `docs/adr/0001-source-name-resolution.md`.

## Troubleshooting

**"Config file not found"**
```bash
# Option 1: Create user config (recommended)
bugownerctl init

# Option 2: Create project-local config
bugownerctl init --location local

# Option 3: Explicitly specify config location
bugownerctl check maintainership -r 16.1 --config /path/to/config.yaml

# Option 4: Use environment variable
export BUGOWNERCTL_CONFIG=/path/to/config.yaml
bugownerctl check maintainership -r 16.1

# View search locations (error message shows all paths checked)
bugownerctl check maintainership -r 16.1  # If no config found, shows search hierarchy
```

**"Config file exists" (when running init)**
```bash
# Overwrite existing config
bugownerctl init --force

# Or manually edit existing config
vim ~/.config/bugownerctl/config.yaml
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
pytest --cov=src/bugownerctl --cov-report=html
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
rm -rf ~/.cache/bugownerctl/repodata/16.1/

# Retry validation (will re-download)
bugownerctl check maintainership -r 16.1
```

**"Cache corruption or stale data"**
```bash
# Clear all cached metadata
rm -rf ~/.cache/bugownerctl/repodata/

# Or clear specific version
rm -rf ~/.cache/bugownerctl/repodata/16.0/

# Cache rebuilds automatically on next run
```

**"OBS bulk map is stale or corrupt"**
```bash
# Force re-fetch without touching repodata cache
bugownerctl check maintainership -r 16.1 --refresh-bulk-map

# Or delete the cache files manually (re-fetched on next run)
rm -f ~/.cache/bugownerctl/obs_bulk_map.xml ~/.cache/bugownerctl/obs_bulk_map.meta.json
```

**"Disk space issues"**
```bash
# Check cache size (each version ~20-50MB)
du -sh ~/.cache/bugownerctl/repodata/*/

# Remove old/unused version caches
rm -rf ~/.cache/bugownerctl/repodata/15.*/
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
(outside /home/user/.cache/bugownerctl/SLFO)
```

### File Location Security

- **Whitelist file:** Read from cloned SLFO repository (validated)
- **Maintainership file:** Read from cloned SLFO repository (validated)
- **Source-name overrides:** Read-only from `bugownerctl/data/false_positives_overrides.json` (wheel-resident). Loader caps body at 1 MiB, treats missing or non-regular paths as `{}` (no overrides), requires a JSON object root with `str | None` values, tolerates a UTF-8 BOM.
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
- Help: `bugownerctl --help`
- CI Status: Check GitHub Actions tab
