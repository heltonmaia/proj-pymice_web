#!/bin/bash

echo "🔧 Setting up development environment for pyMiceTracking..."

# Install development dependencies
echo "📦 Installing development dependencies..."
if command -v uv &> /dev/null; then
    echo "Using UV package manager..."
    uv sync --all-extras
elif command -v pip &> /dev/null; then
    echo "Using pip package manager..."
    pip install -e ".[dev]"
else
    echo "❌ No package manager found. Please install pip or uv first."
    exit 1
fi

# Install pre-commit hooks
echo "🔗 Installing pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "✅ Pre-commit hooks installed successfully!"
else
    echo "❌ pre-commit not found. Please install it first:"
    echo "   pip install pre-commit"
    echo "   or add it to your virtual environment"
fi

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Available commands:"
echo "  • black .              - Format all code"
echo "  • isort .              - Sort all imports" 
echo "  • flake8 src/ tests/   - Lint code"
echo "  • pre-commit run --all-files  - Run all pre-commit hooks"
echo ""
echo "Pre-commit hooks will now run automatically on every commit! 🚀"
