# Contributing to MCP-Telecom

Thank you for your interest in contributing to MCP-Telecom! This project aims to be the definitive MCP server for network equipment, and we welcome contributions from the community.

## Getting Started

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Access to network equipment (or use mock devices for testing)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/Avinash-Amudala/MCP-Telecom.git
cd MCP-Telecom

# Create virtual environment and install dependencies
uv sync --all-extras

# Copy example config
cp devices.yaml.example devices.yaml

# Run tests
uv run pytest tests/ -v
```

## How to Contribute

### Adding a New Vendor

1. Add the vendor type to `src/mcp_telecom/models.py` → `VendorType` enum
2. Add command mappings in `src/mcp_telecom/vendors/mappings.py`
3. Add tests in `tests/test_vendors.py`
4. Update `devices.yaml.example` with an example config
5. Update the README

### Adding a New Tool

1. Add the tool function in the appropriate file under `src/mcp_telecom/tools/`
2. Register the tool in `src/mcp_telecom/server.py` with the `@mcp.tool()` decorator
3. Add relevant vendor commands in `vendors/mappings.py`
4. Add tests
5. Update README if it's a significant feature

### Adding Command Mappings

If a vendor supports additional commands:
1. Add the mapping in `src/mcp_telecom/vendors/mappings.py`
2. Add a test verifying the mapping

## Code Style

- We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Line length: 100 characters
- Type hints are required for all function signatures
- Docstrings are required for all public functions

```bash
# Check linting
uv run ruff check src/ tests/

# Auto-fix
uv run ruff check --fix src/ tests/
```

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_safety.py -v

# Run with coverage
uv run pytest tests/ --cov=mcp_telecom --cov-report=term-missing
```

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Make your changes with tests
3. Ensure all tests pass and linting is clean
4. Write a clear PR description explaining what and why
5. Submit the PR

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include device type, Python version, and error output for bug reports
- For feature requests, describe the use case

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
