# Bugownership CLI

[![CI](https://github.com/gyr/bugownership/actions/workflows/ci.yml/badge.svg)](https://github.com/gyr/bugownership/actions/workflows/ci.yml)

Package maintainership validation and management tool for SUSE Linux Enterprise.

Validates package ownership, manages whitelists, and queries maintainer information using a unified CLI interface.

## Installation

```bash
# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Quick Start

```bash
# Validate maintainership for SLES 16.1
bugowner validate -v 16.1

# Update whitelist with missing submodules
bugowner whitelist update

# Check package maintainership
bugowner query package apache2

# List packages maintained by user
bugowner query maintainer user1
```

## Commands

### `bugowner validate`

Validates package maintainership data for consistency.

**Usage:**
```bash
bugowner validate -v <version> [--debug]
```

**What it checks:**
- Orphan packages (in repo, no maintainer)
- Unmaintained submodules (not in maintainership file)
- Shipped packages missing submodules
- Binary→source package mappings (cached for performance)

**Examples:**
```bash
# Validate SLES 16.1
bugowner validate -v 16.1

# Validate with debug logging
bugowner validate -v 16.0 --debug
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

### `bugowner whitelist update`

Updates whitelist file with submodules missing from maintainership.

**Usage:**
```bash
bugowner whitelist update
```

**What it does:**
- Compares git submodules with `_maintainership.json`
- Adds missing submodules to whitelist
- Removes packages that now have maintainers
- Reports packages in maintainership but not in submodules

**Example:**
```bash
bugowner whitelist update
```

**Exit code:** Always `0`

**Output:**
- Packages added to whitelist
- Packages removed from whitelist
- Packages in maintainership but not submodules

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

Create `validate_maintainership.yaml` in project root:

```yaml
# Cache directory for downloads
cache_dir: ~/.cache/bugownership

# Git repository URL
slfo_git_url: gitea@src.suse.de:products/SLFO.git

# False positives cache file
false_positives_file: false_positives.json

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

Auto-generated whitelist for unmaintained submodules:

```json
[
  "legacy-package1",
  "legacy-package2"
]
```

### `false_positives.json`

Binary→source package mapping cache (auto-generated/updated):

```json
{
  "apache2-devel": "apache2",
  "apache2-utils": "apache2",
  "SLES-release": null
}
```

**Purpose:** Avoid slow OBS queries on every run. Maps binary packages to source names, or `null` to ignore.

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
| `create_whitelist_maintainership.py` | `bugowner whitelist update` |
| `check_package_maintainer.py <pkg>` | `bugowner query package <pkg>` |
| N/A | `bugowner query maintainer <user>` |

**Migration steps:**
1. Install new CLI: `uv pip install -e .`
2. Test new commands alongside old scripts
3. Update scripts/automation to use `bugowner` CLI
4. Remove old script calls once verified

**Compatibility:** All functionality preserved. Data files (`_maintainership.json`, `false_positives.json`, etc.) shared between old and new.

## Troubleshooting

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
