# Report schema 3

The CLI's `--json` output and `POST /analyze` return the same analysis fields.
The API and public-GitHub CLI analyses also include `repository_url`, the normalized
HTTPS GitHub repository address. Local CLI analyses omit that optional address.

## Existing fields

`base_commit` and `target_commit` retain the requested revision labels; the target
is `WORKING_TREE` for saved local files. Existing `changed_symbols`,
`evidence_paths`, affected-symbol/route/test summaries, `historical_impact`, and
`analysis_errors` keep their meanings. Paths run from changed code toward code
that may use it through a direct call or supported FastAPI dependency declaration.
They indicate possible dependencies, not runtime failures or tests that were run.

## Source evidence

- `schema_version`: integer `3`.
- `resolved_commits`: `base` and `target` contain full Git commit IDs. Revision
  labels are resolved before comparison and those IDs are used for analysis.
  `target` is `null` in working-tree mode; local files are not a frozen snapshot.
- `symbol_locations`: definitions involved in reported paths, plus changed
  functions even when isolated. Each entry has `source` (`base` or `target`),
  `id`, `path`, `qualname`, and inclusive `line_start` / `line_end`.
  Duplicate names can have multiple definition locations; consumers must not
  silently treat the first location as an unambiguous definition.
- `call_sites`: resolved source relationships that support edges in reported paths. Each
  entry has `source`, `caller_id`, `callee_id`, `path`, inclusive `line` /
  `line_end`, `column`, `expression`, `resolution`, `code`, `code_truncated`, and
  `relationship` (`call` or `fastapi_dependency`).

Call-site direction is **caller → callee**, the reverse of the displayed impact
path direction. Sites are stored once per recorded call, rather than copied into
each path. Repeated calls remain separate, including calls on the same line.
`column` is the AST's zero-based UTF-8 byte offset. Line numbers are one-based.
For `call`, `expression` is the source call target reconstructed by Python's AST
tools, before local `self` / `cls` normalization. For `fastapi_dependency`, it is
the reconstructed `Depends(...)` declaration. Its source range and preview point
to the declaration, not a fictional direct call to the supplied helper. The
caller/callee IDs retain the using-function/dependency direction in both cases.

`resolution` is `local` (a name matched within the file) or `import` (matched
through an imported name). These are resolution rules, not confidence scores or
proofs of runtime dispatch. Unresolved/ambiguous calls do not gain invented edges;
this list is not an inventory of every unsupported or unresolved call.

`code` is the trimmed first source line of the call, limited to 240 characters.
`code_truncated` indicates clipping. Multiline calls link to the full line range;
the inline preview does not reproduce every line. Consumers must display source
as text, never interpret it as HTML.

Deleted-code evidence uses base-version locations, call sites, and source links.
GitHub links use the normalized repository, full resolved commit ID, encoded
file path, and line anchors. Local working-tree target evidence has no immutable
GitHub link. No extra source-fetch API or persistent repository cache is required.

## FastAPI registration and limitations

Affected routes now include `registration`: `registered` when a named FastAPI app
and a supported registration are found, or `declared` for an unmounted APIRouter.
`declared` paths include a known router prefix but may be partial app addresses.
Registered paths combine literal include/router prefixes and the decorator path;
multiple direct mounts can produce multiple addresses for the same symbol.
This does not prove the app is deployed or that the registration executes.

`analysis_warnings` contains source-qualified `path`, one-based `line`, and
`message` entries for recognized unsupported FastAPI declarations or unresolved
dependencies. Warnings do not mean the whole file failed to parse: parse/source
errors remain in `analysis_errors`. Warnings are not an exhaustive inventory of
all unsupported Python/FastAPI behavior. A known route with a dynamic prefix/path
is omitted rather than presented as a complete address.

The initial subset handles simple module-level app/router assignments, direct
app includes, explicit function parameter Depends (default or inline Annotated),
and unique local/imported function names. Reassigned bindings are treated
conservatively. Nested includes, shared Annotated aliases, app factories,
conditional setup, class dependencies, Security, and app/router/decorator/include
dependencies remain unsupported. Import/execution ordering across modules and
runtime mutation are not modeled; registered means a static declaration match.

## Compatibility

Schema 2 added evidence to the earlier unversioned report. Schema 3 adds typed
relationships, route registration, and warnings, and uses import-aware FastAPI
recognition instead of treating any `.get(...)` decorator as a route. New
dependency paths and corrected addresses can intentionally change summary/path
contents, not just whole-report hashes. The API validates schema 3; strict clients
must update. The web map still reads schema 2 evidence as direct calls and shows
an evidence-unavailable message for earlier unversioned reports.

Change detection currently focuses on functions and methods. Parsing classes does
not establish support for tracing class-attribute or module-level changes.
