# Frontend checks

Run `npm test` and `npm run build` from the frontend folder.

For manual map checks, start `npm run dev` and open `/tests/map-preview.html` at the local address printed by Vite. These artificial fixtures cover isolated changes, cycles, incomplete analysis, branching, alternative paths, and a long path. They do not measure real-repository accuracy. The production build does not include this development page.

Check selection, alternative paths, expansion/reset, Map/Report switching, keyboard focus, and a narrow viewport. Verify that incomplete-analysis notices survive both views and that hidden items are disclosed. Use the real comparisons in the repository's `DEMO.md` for the ordinary, deletion, and documentation-only workflows.
