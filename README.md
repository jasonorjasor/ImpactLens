# ImpactLens

ImpactLens analyzes Python code changes and shows what may be affected.

Watch the [one-minute demo](https://youtu.be/YPQ5ZJKiNow) for a code change, a deleted function, and a documentation-only comparison.

For a repeatable walkthrough, see [DEMO.md](DEMO.md).
For small hand-reviewed examples and a known missed dependency, see [benchmarks/ACCURACY.md](benchmarks/ACCURACY.md).
For the proposed Docker deployment and host checks, see [DEPLOYMENT.md](DEPLOYMENT.md).

It currently:

- finds Python functions and classes
- tracks function calls across files
- resolves many local and imported calls
- maps changed lines between two Git commits
- identifies affected FastAPI routes and pytest tests
- shows dependency paths from changed code to callers

## Limitations

ImpactLens reads Python source without executing it. A reported path is a possible dependency, not proof of a failure. An empty report does not prove a change is safe.

Dynamic calls such as `getattr`, runtime-selected callbacks, monkey-patching, and generated code can be missed. Import and method resolution uses source-level rules rather than a full type system, so ambiguous calls may be unresolved or matched imperfectly. The analyzer does not run tests or analyze JavaScript, configuration, database changes, or external services. Parse errors are included in the report and indicate incomplete analysis.

Working-tree mode reads saved files, not unsaved editor changes. Rename detection uses Git metadata or conservative file similarity; ambiguous cases may appear as an addition and deletion.

## Install locally

Install Git, Python, and Node.js. Python 3.14 and Node.js 22 are the verified container runtimes; the package requires Python 3.11 or newer, but older Python versions have not been checked in CI.

Clone the repository, then run from its folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[test]"
```

Use `.\.venv\Scripts\python.exe` in place of `python` in the commands below, or activate the environment first. On Linux/macOS, use `.venv/bin/python`. Run the web app from the repository folder so it can find the built frontend.

Install frontend dependencies once from `frontend/` with `npm ci --cache .npm-cache`.

## Run the tests

From the project folder:

```powershell
python -m pytest -q
```

For frontend report tests, run `npm test` from `frontend/`.

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
New functions are labeled `added`, including when they are added to an existing file.
An impact path connects changed code to a caller. A changed function with no callers still appears under changed symbols, but has no impact path.
Directly changed routes and tests are distinguished from code reached through calls.

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
The API runs at most two analyses at once per process; extra requests return 503. Each analysis request has a 120-second deadline. Git loading commands have a 120-second ceiling and Git commands during analysis have a 60-second ceiling; each also uses the remaining request time. Timeouts return 504. Python analysis checks the deadline between files and graph work, so a single long operation can finish before the deadline is noticed.
For public GitHub repositories, the temporary checkout is sampled while Git runs and Git's process tree is stopped if it exceeds 100 MiB. Size is also checked after cloning, after each commit fetch, and after analysis. Sampling can overshoot the limit between checks; this is a disk-use guard, not a network download cap.
For a server without development reload, use one worker: `python -m uvicorn api:app --workers 1`. Each additional worker would have its own two-analysis limit; deployment capacity and shared admission control have not been established.

## Run the frontend

Start the API first, then in a second terminal:

```powershell
cd frontend
npm ci --cache .npm-cache
npm run dev
```

Open the local URL printed by Vite. The frontend sends analysis requests to the API through the development proxy.

To preview the built app with one server, build the frontend with `npm run build`, then run `python -m uvicorn web:create_app --factory --workers 1` from the project folder. Open `http://127.0.0.1:8000`. The built frontend and API share the same address; this command reports a clear error if the frontend has not been built. Keep one worker until a deployment host and shared capacity limit are chosen.

## Main files

- `analyzer.py` contains the Python parsing and dependency analysis.
- `git_analyzer.py` connects the analysis to Git commits.
- `cli.py` formats an impact report for the terminal or as JSON.
- `repository_loader.py` validates and temporarily clones public GitHub repositories.
- `api.py` exposes the analyzer through FastAPI.
- `web.py` serves a built frontend alongside the API.
- `frontend/` contains the React interface.
- `pyproject.toml` contains project tool configuration.
- `tests/` contains the tests.
- `examples/` contains small repositories used by the tests and lessons.
