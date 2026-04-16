# Agent Guidelines for wxvx

## General

- Access package resources via `wxvx.util.resource()` or `resource_path()`.
- Raise `WXVXError` for domain errors; log tracebacks at debug level; use descriptive error messages.
- Keep module ownership aligned with the current layout:
- `wxvx.config` owns config models and config validation helpers.
- `wxvx.variables` owns `VarMeta` and dataset/variable manipulation logic.
- `wxvx.workflow` owns workflow-only protocols/enums such as `Named` and `Source`.
- `wxvx.util` owns shared enums/utilities such as `DataFormat`, `ToGridVal`, `TruthType`, resource helpers, and generic helpers.
- Use Python's `logging` module; avoid print statements.
- Use `snake_case` names for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants/Enums.
- Use type hints in all Python code; run `make typecheck` for verification; use `TYPE_CHECKING` for circular imports.
- Follow observed patterns in the codebase.
- Do not `git commit` anything unless instructed to do so.
- Always ask the developer questions if you have doubts.
- Treat assertions used after schema validation as internal invariants; user-facing validation errors should raise `WXVXError` instead.

## Formatting

- Use `make format` to enforce project rules for import order and general style.
- Format `.json` and `.jsonschema` documents by running `make format` (which calls `jq`).
- Format code by running `make format` (which calls `ruff`) before running tests.
- Format docstrings by running `make format` (which calls `docformatter`); use triple-quoted strings for module/class/function docs.
- Use lexicographical ordering for functions in modules, methods in classes, keys in dictionaries, etc. Unless there's a good reason to do otherwise: alphabetize.

## Testing

- Organize unit tests under `src/wxvx/tests/`; mock with `unittest.mock`.
- In general, iterate by 1. editing code, 2. running `make format && make test`, and 3. fixing any reported errors.
- If `make test` reports errors, one of the more specific commands `make lint`, `make typecheck`, or `make unittest` can be run to validate fixes after linting, typechecking, or unit testing, respectively, have failed.
- Feel free to consult `src/pyproject.toml`, the top-level `Makefile`, and `recipe/run_test.sh` to see how the project configures and calls code quality tools, and then make direct calls to those tools yourself using the same settings.
