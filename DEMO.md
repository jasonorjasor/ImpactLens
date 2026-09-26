# Demo cases

## Three-minute walkthrough

1. Explain the problem: a changed Python function may affect callers in other files.
2. Run case 1. Point to a changed function, then follow one evidence path to a test. Say: "This shows a possible dependency; it does not prove that the test will fail."
3. Run case 2. Explain that deleted code is absent from the new version, so its former callers are found in the old version and labeled historical.
4. Run case 3. Explain that a documentation-only change correctly produces no Python symbol impact. An empty report still does not guarantee that every kind of change is safe.
5. Finish with one limitation: dynamic Python behavior can escape source-level call resolution. Use the report to guide review and test selection, then run the actual tests.

For a recording, use the local app and these same commit pairs. Hosting is optional for this walkthrough.

These commit pairs are from this repository. Enter `https://github.com/jasonorjasor/ImpactLens` as the repository in the web app, then paste a base and target commit below. The README has instructions for starting the API and frontend.

You can also run a pair in the terminal:

```powershell
python cli.py https://github.com/jasonorjasor/ImpactLens BASE_COMMIT TARGET_COMMIT
```

## 1. Changed code with callers (start here)

Base: `d49b888e0f27b7a506f526148f573cd7f690e015`

Target: `2b1ccbbb5779a50a7f1dc473d45c26215eaab1ad`

The current report finds 7 changed functions, 2 directly changed routes, and 3 caller paths. One path connects `api.py::health` to `tests/test_api.py::test_health_returns_ok`. This is the clearest first demo.

## 2. Deleted function with historical impact

Base: `fe5ef3f54e317f6a6f9f87e1179724b670d82699`

Target: `d1cf88896bb7b5a440194e3c57470edf8e3cf651`

Look for the deleted `git_analyzer.py::working_tree_file_changes` function. Its callers are shown from the base version, including a path to the historical `POST /analyze` route. The report is larger, so focus on the historical labels rather than reading every path.

## 3. Documentation-only change

Base: `90c2aa7b79ab746479ca2bd3f556efe796bcb3c0`

Target: `2045fb5184543f52ef3ccb349b5a49a951524dfc`

This change only adds the README. The report should have no changed functions or caller paths. An empty result is correct here.

These are examples, not accuracy benchmarks. ImpactLens performs static analysis and can miss dynamic calls or report possible impacts that do not fail at runtime.

All three public commit pairs were rechecked on September 26, 2026 with zero analysis errors. Case 1 returned 7 changed symbols and 3 evidence paths; case 2 included the deleted function and the historical `POST /analyze` route; case 3 returned no changed symbols or evidence paths.
