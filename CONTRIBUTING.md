# Contributing to Ladder

Thank you for your interest in contributing! Ladder is a community-driven project and every contribution helps.

## How to Contribute

### Reporting Bugs

1. Check if the issue already exists
2. Open a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version, config)
   - Relevant logs (redact API keys!)

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the feature and its use case
3. Explain how it fits the Ponytail philosophy (minimal, lazy)

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests if applicable
5. Update documentation
6. Submit a pull request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/brain-loader-v5.git
cd brain-loader-v5

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install in development mode
pip install -e .
pip install -r requirements_local.txt  # Optional: for local MLX testing

# Run tests
pytest
```

## Code Style

- Follow PEP 8
- Use type hints
- Add docstrings to public functions
- Keep functions small and focused (Ponytail philosophy)
- Use Trio patterns, not asyncio

## Provider Contributions

To add a new LLM provider:

1. Create `core/providers/your_provider.py`
2. Inherit from `BaseProvider`
3. Implement `_execute()` method
4. Add to `UniversalRouter._init_providers()`
5. Add configuration example to `config.yaml`
6. Update README

## Commit Messages

Use conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Test changes
- `chore:` Maintenance

## Questions?

Open a Discussion or reach out via the Telegram community.
