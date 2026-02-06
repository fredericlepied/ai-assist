#!/bin/bash
# Development environment setup script

set -e

echo "🔧 Setting up ai-assist development environment..."
echo ""

# Check if Python 3.12+ is available
if ! python3 --version | grep -qE 'Python 3\.(1[2-9]|[2-9][0-9])'; then
    echo "❌ Error: Python 3.12 or later is required"
    exit 1
fi

echo "✓ Python version OK"

# Install package with dev dependencies
echo "📦 Installing ai-assist with dev dependencies..."
pip install -e ".[dev]"

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Run pre-commit on all files to ensure everything is formatted correctly
echo "🔍 Running initial pre-commit checks..."
pre-commit run --all-files || {
    echo ""
    echo "⚠️  Some pre-commit checks failed. This is normal on first run."
    echo "   Files have been auto-formatted. Please review changes and commit."
    exit 0
}

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "Next steps:"
echo "  • Run tests: make test"
echo "  • Format code: make format"
echo "  • Run all checks: make all-checks"
echo "  • See all commands: make help"
echo ""
echo "Pre-commit hooks are now active and will run on every commit."
