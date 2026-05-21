#!/bin/bash
# Auto-fix code quality issues
# Runs fixable checks with auto-fix enabled, then validates

set -e  # Exit on first error

echo "Installing dependencies..."
uv sync --extra dev --quiet
echo ""

echo "🔧 Running auto-fix for code quality issues..."
echo ""

echo "Step 1/3: Auto-formatting with ruff..."
uv run ruff format src/ tests/
echo "✅ Code formatted"
echo ""

echo "Step 2/3: Auto-fixing linting issues..."
uv run ruff check src/ tests/ --fix
echo "✅ Linting issues fixed"
echo ""

echo "Step 3/3: Running full validation..."
echo ""
./scripts/check.sh
