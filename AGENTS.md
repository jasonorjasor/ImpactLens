# ImpactLens working agreement

- Help the project owner learn while building. Before a meaningful change, explain its purpose and why it is the next step. Afterward, explain what changed, how it works, verification, tradeoffs, and the next logical step.
- Make scoped changes backed by evidence. Inspect existing behavior and tests first; do not optimize or expand the product based on guesses.
- Keep code comments rare, short, and necessary. Keep the public README plain and concise.
- Treat impact paths as possible effects of a code change, not proof of a runtime failure.
- Record each meaningful decision in the Decision log below: the choice, reason, alternative, limitation, and evidence. Keep anything private (interview notes, personal plans) outside the repository; this file is public.
- Run relevant Python and frontend tests after changes. For performance work, compare pinned cases in `benchmarks/README.md` and verify report contents as well as time.
- Tell the project owner when a coherent commit is appropriate. Do not assume that project organization or a new chat transfers permission to publish changes.

## Change workflow

1. Reproduce the gap with a small failing test before changing analyzer behavior. Add a guard test for the nearest case that must stay unresolved.
2. Make the smallest change that passes it.
3. Run `python -m pytest -q`, and `npm test` in `frontend/` when the frontend or report shape changes.
4. For analyzer changes, run every case in `benchmarks/pr_cases.json` before and after the change and compare changed symbols, paths, related tests, and call sites. Local checkouts need pull-request refs: `git fetch origin '+refs/pull/*/head:refs/remotes/pr/*'`.
5. Add a Decision log entry, then tell the project owner the change is ready to commit.

## Known environment notes

- Source is parsed with the running interpreter's grammar. Python 3.14 accepts `except A, B:` and older versions do not, so `template-compose-2392` reports a parse error (and fails its required check) below 3.14. Compare benchmark results on the same Python version.
- `tests/test_git_process.py` checks that stopped processes no longer exist. Where PID 1 does not reap orphans (some sandboxes), they remain as zombies and two tests fail. The Docker image uses `tini`, so CI is unaffected.

## Decision log

### 2026-11-23: Resolve calls through `from package import module`

- Choice: in `_resolve_files`, a two-part call such as `services.create_user()` whose first part came from `from pkg import services` (including relative and aliased forms) now looks for `create_user` in module `pkg.services`.
- Reason: a common import style produced no connection at all. A minimal repro reported zero affected symbols and tests.
- Alternative: general dotted-call resolution (`a.b.c.func()`) in the same change. Deferred to keep this change small and easy to verify.
- Limitation: matches only when that module exists in the analyzed snapshot. Imported classes (`Service.create()`) stay unresolved; a guard test covers this.
- Evidence: new tests in `tests/test_repository.py`. The nine real-PR cases are unchanged (before = after) because the template repository keeps code under `backend/app` while importing `app.*`, so module names do not match. Analyzing `backend/` directly as the root, resolved calls rose from 124 to 169 of 793, including 44 `crud.*` calls.

### 2026-11-24: Do not guess a submodule when Python would not load it (review follow-up)

- Choice: before treating `from pkg import X` as submodule `pkg.X`, check the package. If `pkg/__init__.py` binds `X` itself (class, function, assignment, or another import), Python uses that binding, so the call stays unresolved. It still resolves when the initializer re-exports the same submodule (`from . import X`). A plain module `pkg.py` has no submodules, so it never matches. Separately, relative imports inside `__init__.py` now resolve from the package itself, not its parent.
- Reason: an independent review found two wrong links: a package class shadowed by a same-named `pkg/X.py` file, and `from . import services` in `pkg/__init__.py` resolving to a top-level `services.py`. A wrong link sends a reviewer to unrelated code, which is worse than no link. The initializer bug predates the submodule change and also affected `from .services import name`.
- Alternative: mark these calls `ambiguous`. Not chosen, because Python's precedence is defined here; the unresolved case is a call to an attribute of a package binding that the analyzer does not follow.
- Limitation: package bindings are read from source only. A later `import pkg.X` elsewhere replaces the attribute at runtime and is not modeled. If `pkg/__init__.py` fails to parse, the package is treated like a namespace package, and the report already lists the parse error.
- Evidence: three regression tests in `tests/test_repository.py` (export precedence, re-export still resolves, initializer stays inside its package). The nine real-PR cases still match previous results, and analyzing template `backend/` as root still resolves 169 of 793 calls.

### 2026-11-24: Follow a package re-export only when its module-level binding is clear (second review)

- Choice: record every module-level binding in each file (definitions, assignments, deletions, and imports, including inside `if`/`try`, but not inside functions or classes). `from pkg import X` follows submodule `pkg.X` only when `pkg/__init__.py` does not bind `X`, or when every binding of `X` there is an import of that same submodule.
- Reason: the first fix read imports from anywhere in the initializer and ignored later assignments. A second review reproduced wrong links for `from . import services` followed by `services = ...`, and for a re-export that appears only inside a function.
- Alternative: replay statements in order to find the final binding. Not chosen; control flow such as `try`/`if` makes the final value uncertain, and refusing mixed bindings is simpler and errs toward no link.
- Limitation: any non-import binding of the name (for example, a fallback `services = None` in `except ImportError`) leaves the call unresolved even when the import usually succeeds.
- Evidence: two regression tests in `tests/test_repository.py`. The nine real-PR cases still match previous results, and analyzing template `backend/` as root still resolves 169 of 793 calls.

## Next steps

1. Import roots: detect or accept a source root (for example `backend/`) so `app.*` imports match. The probe above shows this unlocks the submodule fix on real code.
2. Dotted module calls (`pkg.services.func()` after `import pkg.services`).
3. Inherited `self.method()` lookups through base classes.
4. Simple local instance types (`x = Cls(); x.method()`).
