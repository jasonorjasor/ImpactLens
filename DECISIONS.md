# ImpactLens decisions

This is the running record of what we chose and why. Earlier entries are reconstructed from the code and commit history; new decisions are recorded as we make them. It is not a claim that every alternative was tested.

## What the project is for

ImpactLens helps a developer review a Python code change by showing changed functions, possible callers, affected FastAPI routes, and related pytest tests. It provides evidence paths, not a guarantee that code will fail. The main workflow compares two commits; comparing saved working-tree files with `HEAD` is an optional second workflow.

## Decisions so far (retrospective)

1. **Start with Python and static analysis.** Python's built-in `ast` module gives us functions, classes, calls, and line numbers without running somebody else's code. The cost is that dynamic dispatch, reflection, and generated code may be missed. We kept the first version focused instead of promising many languages.
2. **Track calls and use stable symbol IDs.** IDs such as `path.py::Class.method` distinguish same-named functions in different files or classes. Caller-to-callee edges let us traverse from a changed function to its callers. Names and imports can still be ambiguous, so resolution should be conservative.
3. **Use import-aware resolution.** Matching a call by its short name alone can connect unrelated functions and create false positives. Imports provide more context without requiring a full Python runtime or type checker.
4. **Make two Git commits the main comparison.** Git provides a reproducible base and target. Map changed lines to functions, then analyze callers in the relevant version. A Git diff alone says what changed, but not what calls it.
5. **Also support saved working-tree changes against `HEAD`.** This lets a developer inspect work before committing. It includes tracked and untracked Python files saved to disk, but not unsaved editor buffers. We kept commit comparison as the main public web workflow because it is easier to reproduce from a repository URL.
6. **Report routes and tests as useful endpoints.** FastAPI routes and pytest tests are more actionable than a raw list of functions. They are still possible impacts from static calls, not proof that a route or test is broken.
7. **Keep evidence in JSON and make the CLI readable.** JSON serves the API and other tools; terminal output helps a person inspect an analysis. Paths show how a changed function reaches a caller. The CLI limits displayed paths by default so large reports remain readable; the full list is available on request.
8. **Build the web app with FastAPI and React.** FastAPI exposes the Python analyzer with a validated response model. React renders the report and form without moving analysis logic into the browser. This adds a frontend build, but keeps one analysis implementation.
9. **Accept public GitHub URLs through a temporary clone.** A user can try the web app without a local checkout. Restricting URLs and repository size reduces the risk and cost of processing arbitrary repositories. Private repositories are outside the current scope.
10. **Separate deletion impacts from current impacts.** Deleted functions must be analyzed in the base version because they are absent from the target. Their former callers, routes, and tests are labeled historical so we do not imply they still exist.
11. **Show parse failures instead of silently claiming a complete report.** Invalid Python files can leave gaps in analysis. We return file/version errors and validate API reports so callers can distinguish incomplete results from a clean result.
12. **Clarify the report before adding more analysis.** New functions are labeled `added` by comparing old and new symbols. A path needs at least one caller; an isolated changed function remains in Changed functions. Directly changed routes and tests are distinguished from reached ones, and tests are not listed twice. This makes the current evidence easier to interpret without changing the core graph.

## Later decisions

13. **Keep this file in the repository.** It stays beside the code, can be reviewed in GitHub, and can be updated in the same commit as a change. We will record the choice, reason, meaningful alternative, and limitation when we implement something new.
14. **Add a focused frontend report test with Node's built-in test runner.** The Python suite checks analysis and API behavior but cannot catch a misleading browser label or count. A server-rendered component test checks those report rules without adding a test framework dependency. It does not replace a future browser interaction test.
15. **Translate expected loading failures into useful messages.** A real browser run against this public repository succeeded, but an invalid commit exposed raw Git text and an unavailable API exposed a JSON parsing error. The loader now keeps the original Git error as a cause but returns a short explanation for clone/fetch failures. The frontend handles connection and non-JSON responses separately. This loses some low-level detail in the UI; preserving it in the exception chain keeps debugging possible without showing temporary paths to users.
16. **Check repository size after each download stage.** We used to check only after cloning and both commit fetches. Checking after the initial clone and each fetch stops work sooner when the repository has grown past 100 MB. Repeated scans add a little overhead; they are not a hard cap during a clone or on-demand blob fetch.
17. **Bound Git command time and concurrent API work.** Git commands in the analyzer now have a 60-second timeout, alongside the loader's existing 120-second per-command timeout. The API admits two analyses at a time per process and returns 503 when both slots are in use; timeouts return 504. This is a conservative starting limit, not a measured capacity figure. A fixed per-command timeout and per-process semaphore do not enforce a total request deadline or a limit shared across multiple server processes.

## Next checkpoints

1. Before public deployment, measure realistic repository sizes and request times, then decide whether we need a hard download cap, a total request deadline, or cross-process admission control.
2. Prepare a repeatable demo input and practice explaining the analysis and its limitations.
3. If browser interactions grow, add an automated browser test. Component and request tests protect current behavior, but they do not automate every click-through scenario.

We should revisit a decision when a real example or test shows it is not serving the project. The point of this file is to explain choices, not defend them forever.
