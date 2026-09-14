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

Compare the current files with `HEAD`:

```powershell
python cli.py PATH_TO_REPOSITORY HEAD --working-tree
```

Use `--json` for machine-readable output:

```powershell
python cli.py PATH_TO_REPOSITORY BASE_COMMIT TARGET_COMMIT --json
```

Human-readable output shows up to 20 impact paths by default. Use `--all-paths` to show the full list.

## Main files

- `analyzer.py` contains the Python parsing and dependency analysis.
- `git_analyzer.py` connects the analysis to Git commits.
- `cli.py` formats an impact report for the terminal or as JSON.
- `pyproject.toml` contains project tool configuration.
- `tests/` contains the tests.
- `examples/` contains small repositories used by the tests and lessons.

## Current limitations

ImpactLens analyzes Python source statically. It does not run the code, and it cannot always resolve dynamic calls, reflection, or code generated at runtime.
Working-tree mode includes tracked and untracked Python changes. Deleted symbols are reported, but their remaining callers may be unresolved because the deleted code is absent from the current snapshot.
Renames are detected from Git metadata or conservative file-content similarity; ambiguous cases may be reported as separate additions and deletions.

## Planned work

- build a FastAPI backend
- build a React interface
- support analysis of public GitHub repositories
