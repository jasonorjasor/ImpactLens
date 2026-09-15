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

The CLI compares two commits in a local Git repository or a public GitHub repository:

```powershell
python cli.py PATH_TO_REPOSITORY BASE_COMMIT TARGET_COMMIT
```

For a public GitHub repository:

```powershell
python cli.py https://github.com/OWNER/REPOSITORY BASE_COMMIT TARGET_COMMIT
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

## Run the API

Start the development server:

```powershell
python -m uvicorn api:app --reload
```

The API provides `GET /health` and `POST /analyze`. FastAPI's interactive documentation is available at `http://127.0.0.1:8000/docs`.

## Main files

- `analyzer.py` contains the Python parsing and dependency analysis.
- `git_analyzer.py` connects the analysis to Git commits.
- `cli.py` formats an impact report for the terminal or as JSON.
- `repository_loader.py` validates and temporarily clones public GitHub repositories.
- `api.py` exposes the analyzer through FastAPI.
- `pyproject.toml` contains project tool configuration.
- `tests/` contains the tests.
- `examples/` contains small repositories used by the tests and lessons.

## Current limitations

ImpactLens analyzes Python source statically. It does not run the code, and it cannot always resolve dynamic calls, reflection, or code generated at runtime.
Working-tree mode includes tracked and untracked Python changes. Deleted symbols are reported, but their remaining callers may be unresolved because the deleted code is absent from the current snapshot.
Renames are detected from Git metadata or conservative file-content similarity; ambiguous cases may be reported as separate additions and deletions.
Public GitHub repositories are limited to HTTPS URLs and a 100 MB cloned-repository size limit.

## Planned work

- build a React interface
