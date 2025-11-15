# Agent Guidelines for wxvx

## Build/Test Commands
- **Format code**: `make format` or `./format` (runs ruff format, import sorting, docformatter, JSON formatting)
- **Lint**: `make lint` or `recipe/run_test.sh lint` (uses ruff)
- **Type check**: `make typecheck` or `recipe/run_test.sh typecheck` (uses mypy)
- **All tests**: `make test` or `recipe/run_test.sh` (lint + typecheck + unittest + CLI)
- **Unit tests only**: `make unittest` or `recipe/run_test.sh unittest` (pytest with coverage, 4 parallel workers)
- **Single test**: `pytest -n 4 src/wxvx/tests/test_<name>.py::<test_function>` from project root

## Code Style
- **Imports**: Use `from __future__ import annotations` at top; stdlib → third-party → local; sort with ruff (isort)
- **Formatting**: Use ruff format (automatically handles line length, indentation, quotes)
- **Types**: Use type hints everywhere; run mypy for verification; use `TYPE_CHECKING` for circular imports
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants/Enums
- **Errors**: Raise `WXVXError` for domain errors; log tracebacks at debug level; use descriptive error messages
- **Docstrings**: Format with docformatter; use triple-quoted strings for module/class/function docs
- **Comments**: Use `# Public` and `# Private` sections to separate interface from implementation
- **Resources**: Access package resources via `wxvx.util.resource()` or `resource_path()`
- **Logging**: Use Python logging module; avoid print statements
- **Testing**: Use pytest; mock with `unittest.mock`; organize tests in `src/wxvx/tests/`
