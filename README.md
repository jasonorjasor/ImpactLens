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

Deleted functions are matched against the base version, including when a whole file is removed.
Their former callers, routes, and tests appear as historical results. Those dependencies may no longer exist in the target version.

In JSON reports, `evidence_paths` and each function's `impact_paths` contain objects with `source` (`base` or `target`) and a `symbols` list.
The top-level affected symbols, routes, and tests use target-version evidence. `historical_impact` contains the same three lists using base-version evidence.
`changed_lines` refers to the target version; `removed_lines` refers to the base version. Deleted functions' start and end lines refer to the base version.
If a Python file cannot be parsed, `analysis_errors` names the file and version. The report may be incomplete.

## Run the API

Start the development server:

```powershell
python -m uvicorn api:app --reload
```

The API provides `GET /health` and `POST /analyze`. FastAPI's interactive documentation is available at `http://127.0.0.1:8000/docs`.
`POST /analyze` validates its response against the report model before returning JSON. Invalid requests return 422; repository loading errors return 400.

## Run the frontend

Start the API first, then in a second terminal:

```powershell
cd frontend
npm install --cache .npm-cache
npm run dev
```

Open the local URL printed by Vite. The frontend sends analysis requests to the API through the development proxy.

## Main files

- `analyzer.py` contains the Python parsing and dependency analysis.
- `git_analyzer.py` connects the analysis to Git commits.
- `cli.py` formats an impact report for the terminal or as JSON.
- `repository_loader.py` validates and temporarily clones public GitHub repositories.
- `api.py` exposes the analyzer through FastAPI.
- `frontend/` contains the React interface.
- `pyproject.toml` contains project tool configuration.
- `tests/` contains the tests.
- `examples/` contains small repositories used by the tests and lessons.

## Current limitations

ImpactLens analyzes Python source statically. It does not run the code, and it cannot always resolve dynamic calls, reflection, or code generated at runtime.
Working-tree mode includes tracked and untracked Python changes saved to disk. Unsaved editor changes are not included.
Renames are detected from Git metadata or conservative file-content similarity; ambiguous cases may be reported as separate additions and deletions.
Public GitHub repositories are limited to HTTPS URLs and a 100 MB cloned-repository size limit.
