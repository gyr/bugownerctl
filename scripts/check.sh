#!/bin/bash
# Run all CI validation checks locally
# Same commands as .github/workflows/ci.yml

set -e  # Exit on first error

echo "Installing dependencies..."
uv sync --extra dev --quiet
echo ""

echo "Running CI validation checks..."
echo ""

echo "Step 1/5: Linting with ruff..."
uv run ruff check src/ tests/
echo "✅ Linting passed"
echo ""

echo "Step 2/5: Checking code formatting..."
uv run ruff format --check src/ tests/
echo "✅ Formatting passed"
echo ""

echo "Step 3/5: Type checking with mypy..."
uv run mypy src/
echo "✅ Type checking passed"
echo ""

echo "Step 4/5: Security scanning with bandit..."
uv run bandit -c .bandit -r src/
echo "✅ Security scan passed"
echo ""

echo "Step 5/5: Running tests with coverage..."
uv run pytest -v --cov=src/bugownerctl --cov-report=term --cov-report=xml --cov-fail-under=90
echo "✅ Tests passed"
echo ""

echo "🎉 All validation checks passed!"
