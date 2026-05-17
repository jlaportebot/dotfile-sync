# Contributing to dotfile-sync

Thank you for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/jlaportebot/dotfile-sync.git
cd dotfile-sync

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=dotfile_sync

# Run a single test file
python -m pytest tests/test_core.py -v
```

## Linting

```bash
# Check for issues
ruff check dotfile_sync/ tests/

# Auto-fix issues
ruff check --fix dotfile_sync/ tests/
```

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add new feature`
- `fix: resolve bug in backup`
- `docs: update README`
- `test: add tests for restore`
- `refactor: simplify manifest handling`
- `chore: update dependencies`

## Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with proper tests
4. Ensure all tests pass and linting is clean
5. Push your branch and open a Pull Request
6. Describe your changes clearly in the PR description

## Code Style

- Python 3.9+ compatible
- Line length: 100 characters
- Use type hints for all function signatures
- Write docstrings for all public functions and classes
