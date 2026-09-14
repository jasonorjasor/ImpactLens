# ImpactLens

ImpactLens analyzes Python code changes and shows what may be affected.

It currently:

- finds Python functions and classes
- tracks function calls across files
- resolves many local and imported calls
- maps changed lines between two Git commits
- identifies affected FastAPI routes and pytest tests
- shows dependency paths from changed code to callers

## Run the tests

From the project folder:

```powershell
python -m pytest -q
```

## Run an analysis

The CLI compares two commits in a local Git repository:

```powershell
python cli.py PATH_TO_REPOSITORY BASE_COMMIT TARGET_COMMIT
```

Use `--json` for machine-readable output:

```powershell
python cli.py PATH_TO_REPOSITORY BASE_COMMIT TARGET_COMMIT --json
```

## Main files

- `analyzer.py` contains the Python parsing and dependency analysis.
- `git_analyzer.py` connects the analysis to Git commits.
- `cli.py` formats an impact report for the terminal or as JSON.
- `pyproject.toml` contains project tool configuration.
- `tests/` contains the tests.
- `examples/` contains small repositories used by the tests and lessons.

## Current limitations

ImpactLens analyzes Python source statically. It does not run the code, and it cannot always resolve dynamic calls, reflection, or code generated at runtime.

## Planned work

- build a FastAPI backend
- build a React interface
- support analysis of public GitHub repositories
