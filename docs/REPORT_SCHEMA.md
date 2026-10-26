# Report schema 2

The CLI's `--json` output and `POST /analyze` return the same analysis fields.
The API and public-GitHub CLI analyses also include `repository_url`, the normalized
HTTPS GitHub repository address. Local CLI analyses omit that optional address.

## Existing fields

`base_commit` and `target_commit` retain the requested revision labels; the target
is `WORKING_TREE` for saved local files. Existing `changed_symbols`,
`evidence_paths`, affected-symbol/route/test summaries, `historical_impact`, and
`analysis_errors` keep their meanings. Paths run from changed code toward callers.
They indicate possible dependencies, not runtime failures or tests that were run.

## Source evidence

- `schema_version`: integer `2`.
- `resolved_commits`: `base` and `target` contain full Git commit IDs. Revision
  labels are resolved before comparison and those IDs are used for analysis.
  `target` is `null` in working-tree mode; local files are not a frozen snapshot.
- `symbol_locations`: definitions involved in reported paths, plus changed
  functions even when isolated. Each entry has `source` (`base` or `target`),
  `id`, `path`, `qualname`, and inclusive `line_start` / `line_end`.
  Duplicate names can have multiple definition locations; consumers must not
  silently treat the first location as an unambiguous definition.
- `call_sites`: resolved direct calls that support edges in reported paths. Each
  entry has `source`, `caller_id`, `callee_id`, `path`, inclusive `line` /
  `line_end`, `column`, `expression`, `resolution`, `code`, and `code_truncated`.

Call-site direction is **caller → callee**, the reverse of the displayed impact
path direction. Sites are stored once per recorded call, rather than copied into
each path. Repeated calls remain separate, including calls on the same line.
`column` is the AST's zero-based UTF-8 byte offset. Line numbers are one-based.
`expression` is the source call target reconstructed by Python's AST tools,
before local `self` / `cls` normalization. It is not the full call with arguments.

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

## Compatibility

Schema 2 adds evidence fields to the earlier unversioned report. Existing path and
summary fields remain, but the complete JSON hash changes because new fields are
present. Compare the legacy fields separately when checking analysis equivalence.
The API validates the new shape; clients using strict schemas must update.
The web map still displays earlier reports, with an explicit source-evidence
unavailable message instead of fabricating locations.

Change detection currently focuses on functions and methods. Parsing classes does
not establish support for tracing class-attribute or module-level changes.
