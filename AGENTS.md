# ImpactLens working agreement

- Help the project owner learn while building. Before a meaningful change, explain its purpose and why it is the next step. Afterward, explain what changed, how it works, verification, tradeoffs, and the next logical step.
- Make scoped changes backed by evidence. Inspect existing behavior and tests first; do not optimize or expand the product based on guesses.
- Keep code comments rare, short, and necessary. Keep the public README plain and concise.
- Treat impact paths as possible effects of a code change, not proof of a runtime failure.
- Keep private decision notes outside the public repository. If the local private decision log is available, update it with the choice, reason, alternative, and limitation; never stage or push it.
- Run relevant Python and frontend tests after changes. For performance work, compare pinned cases in `benchmarks/README.md` and verify report contents as well as time.
- Tell the project owner when a coherent commit is appropriate. Do not assume that project organization or a new chat transfers permission to publish changes.
