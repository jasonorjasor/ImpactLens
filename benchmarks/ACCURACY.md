# Hand-reviewed accuracy cases

Run `python -m pytest tests/test_review_cases.py -q -rx` from the repository.
The fixtures create local Git commits and call the complete commit analyzer.
They read source without importing or executing fixture code.

The expectations come from reading four small programs. Each comparison changes
only `service.py::calculate`, either returning 2 instead of 1 or removing it.
The caller and test are unchanged. Paths below run from the changed function
through `caller.py::run` to `tests/test_run.py::test_run`.

| Case | Expected from manual review | Observed September 26, 2026 |
| --- | --- | --- |
| Aliased import | `from service import calculate as compute` connects the function to `run`, then its test, in the target version. | Exact expected path and related test; no extra paths. |
| Ambiguous wildcard imports | `from service import *` followed by `from other import *` makes `calculate` refer to the other function in this fixture. Changing the first function should not invent a caller path. | Changed function reported; no caller paths. This demonstrates conservative behavior, not general wildcard resolution. |
| Deleted function | The target has no function to follow. The base version contains the former caller and test path. | Exact expected base path and historical related test; no target callers. |
| Dynamic dispatch | `getattr(service, 'calculate')()` calls the changed function, then reaches the test through `run`. | Changed function reported, but the expected target path is missed. |

All four comparisons identify the expected changed symbol with no parse errors.
The first three match the reviewed paths. The dynamic case is an explicit
expected failure (`xfail`), not a successful dependency detection. The test checks
changed symbols and parse errors before accepting that specific missing-path
result as the known limitation. If the analyzer later finds the full expected
path, the case can pass normally.

These synthetic examples are small, selected, and reviewed by the project
maintainer. They do not measure general precision or recall. A larger independent
corpus would be needed for those claims. An empty report is especially unsuitable
as a safety guarantee for runtime-selected calls.
