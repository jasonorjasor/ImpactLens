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

## Main files

- `analyzer.py` contains the Python parsing and dependency analysis.
- `git_analyzer.py` connects the analysis to Git commits.
- `test_*.py` contains the tests.
- `example_repo/` and `relative_repo/` contain small examples used by the tests.

## Current limitations

ImpactLens analyzes Python source statically. It does not run the code, and it cannot always resolve dynamic calls, reflection, or code generated at runtime.

## Planned work

- add a clearer command-line report
- build a FastAPI backend
- build a React interface
- support analysis of public GitHub repositories
