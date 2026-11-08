# Real-PR review casebook

On November 8, 2026, we inspected nine merged pull requests from two Python/FastAPI
projects and ran ImpactLens on their frozen Git comparisons. This checks selected
real behavior and exposes limitations. It is not an accuracy percentage, an
independent user study, or evidence that the tool improves review speed.

## Repeat a case

From the repository folder, with the project installed:

```powershell
python -m benchmarks.pr_review --case users-jwt-1369
```

This loads the public repository through the normal loader, with its checkout-size
guard and a shared 120-second loading/analysis deadline. It never imports or runs
the reviewed project's application or tests. A size/deadline/network failure is
an error, not an empty successful report. Public replay can depend on GitHub and
availability of the frozen commits.

For an existing local Git checkout containing the commits:

```powershell
python -m benchmarks.pr_review --case users-jwt-1369 --repository PATH_TO_CHECKOUT --report PATH_TO_NEW_REPORT.json
```

`--report` saves full analysis JSON and refuses an existing output file. Local
checkouts use the analyzer deadline but not the public checkout-size guard.

To check saved JSON without Git loading or a fresh analysis:

```powershell
python -m benchmarks.pr_review --case users-jwt-1369 --saved-report PATH_TO_REPORT.json
```

The output distinguishes a saved-report check from fresh analysis. Exit 0 means
the selected required findings were present, not that every finding is correct or
every effect was found. Exit 1 indicates an error or missing required findings.
Ordinary pytest runs exercise the checker offline; they do not fetch these projects.

Full commit IDs, PR links, required checks, and case IDs are in
[pr_cases.json](pr_cases.json). Each analysis compares `base` (the verified merge
base) with `head`; `base_tip` preserves the PR base snapshot used to find it. In
this selected sample all nine base tips equal their merge bases. This therefore
does not test diverged-base PR resolution. It is not yet a general PR-URL input feature.

## Observations

Counts below are from full local-Git analysis, not extracted snippets or fixture
reconstructions. Paths run from changed code toward possible callers. Related
tests include directly edited tests as well as tests reached through connections.

| PR / case | Changed functions | Paths | Related tests | What the source review established |
| --- | ---: | ---: | ---: | --- |
| [Template #1396](https://github.com/fastapi/full-stack-fastapi-template/pull/1396) — `template-users-1396` | 6 | 0 | 4 | Finds the changed user lookup and edited tests. Reports GET `/users/{user_id}` as a router declaration. No HTTP-client-to-endpoint path. A renamed test function is represented as an addition/deletion, rather than inferred as a function rename. |
| [Template #1440](https://github.com/fastapi/full-stack-fastapi-template/pull/1440) — `template-reset-1440` | 1 | 0 | 0 | Finds reset-password and its declared route, but misses relevant unchanged HTTP tests. An empty test list does not mean no tests exist. |
| [Template #1543](https://github.com/fastapi/full-stack-fastapi-template/pull/1543) — `template-permissions-1543` | 6 | 0 | 3 | Finds three permission checks and the edited status-code tests. Listing those edited tests adds less context than finding unchanged dependencies. |
| [Template #1862](https://github.com/fastapi/full-stack-fastapi-template/pull/1862) — `template-move-1862` | 66 | 2 | 55 | File moves retain old/new symbol identities and current test paths. Counts include relocated functions with unchanged bodies, not 66 behavioral edits. Two helper connections are supported by source calls. |
| [Template #2392](https://github.com/fastapi/full-stack-fastapi-template/pull/2392) — `template-compose-2392` | 0 | 0 | 0 | Only Compose database-volume/environment settings change. Correctly empty Python-function output says nothing about operational safety. |
| [Users #1552](https://github.com/fastapi-users/fastapi-users/pull/1552) — `users-cookie-1552` | 1 | 0 | 0 | Finds the changed OAuth wrapper method. Class-instance/factory wiring yields no useful downstream route/test suggestions in this case. |
| [Users #1485](https://github.com/fastapi-users/fastapi-users/pull/1485) — `users-oauth-1485` | 8 | 3 | 4 | Finds nested callbacks, containing factories, added tests, and three factory callers. Does not recover registered app addresses or HTTP coverage; enum-attribute edits fall outside function detection. |
| [Users #1564](https://github.com/fastapi-users/fastapi-users/pull/1564) — `users-docs-1564` | 0 | 0 | 0 | Documentation-link-only edit correctly has no changed Python functions. |
| [Users #1369](https://github.com/fastapi-users/fastapi-users/pull/1369) — `users-jwt-1369` | 1 | 18 | 10 | A shared JWT helper change reaches unchanged callers and tests. All eight independently identified direct callers appear; additional paths follow actual calls to the state-token helper. This is the clearest example of context beyond the diff. |

All nine runs returned schema-3 reports with zero parse/source errors. They still
had framework warnings: 23 for most template cases, 46 for #1396 (base and target),
and 99 for the users cases. Warnings cover each analyzed snapshot, not only the
changed code. Zero parse errors is not complete framework analysis. No full
registered app routes were established in this sample; template addresses were
labeled declarations and users' factory-built routes were omitted with warnings.

## How the review was performed

We selected eight PRs by inspecting their patches and frozen source, and wrote
scoped expectations before generating reports. After the first five template
results, we added #1369 to test a shared helper rather than only edited endpoints.
Its eight direct-call expectations were also recorded before analyzing it. This
deliberate selection limits what can be generalized from the sample.

Reviewed the complete returned paths, not just the counts. Checked all 25 returned
call-site previews/ranges against frozen Git source, and all 110 returned
definition locations against independently parsed Python scopes. This verifies
source correspondence, not runtime dispatch or the absence of missing effects.
The source audit and full raw reports are retained privately. Factory edges in
#1485 were inspected after the first report and retained as regression checks;
they were not independently predicted findings.

A separate fresh public-loader replay of #1369 also produced the identical complete
report (SHA-256 `ad10f0ddf9fdf930ae61681129fd0a3515c23effd187ccc9b0b15e8a8e1f3097`).
This checks that the local case was not dependent on a special source loader; it
does not establish general public-repository capacity or performance.

The automated checker validates report schema and exact snapshot IDs, requires
selected changed symbols, rename identities, route declarations, and tests, and
checks selected target edges have source evidence. It checks Python-only emptiness
for the docs/Compose cases. It does not automatically label every extra suggestion
as correct or reject a future improvement that discovers a previously missed test.

## Consequences for product work

- Direct imported helpers can produce useful context outside edited files, as in
  #1369. This is source-level guidance, not proof that ten tests will fail.
- HTTP tests, fixture injection, runtime instances, shared dependency aliases,
  nested routers, and settings-based registration limit coverage in real projects.
  A router declaration must not be presented as a verified deployed address.
- The template's `app.*` imports live below `backend/`. The analyzer does not
  configure that source root. Avoid guessing roots by stripping arbitrary path
  prefixes; explicit project-root support needs its own design and cases.
- File rename identity works here, but a moved/import-only function can still add
  visual noise. Changed-function counts are not risk or semantic-change scores.
- Keep current empty-result and incomplete-analysis explanations. Configuration,
  class attributes, and unreported connections still require normal review.

Next: make these frozen comparisons convenient through correctly resolved PR
input, while prioritizing accuracy work from concrete gaps. A compact changed-code
diff and portable reports remain later workflow improvements. Human reviewers must
still establish whether the findings change their actions or warrant repeat use.
