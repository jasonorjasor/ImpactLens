# Benchmark snapshots

Run a comparison with `python -m benchmarks.measure REPOSITORY BASE_COMMIT TARGET_COMMIT`.
The script reports repository loading, analysis, and end-to-end time separately. Sizes include the Git checkout and `.git` directory. Each row below is one run on Windows with Python 3.14 on September 17, 2026; network and machine load can change the numbers.

| Repository | Base | Target | Loaded size | Load | Analysis | Total | Changed symbols | Evidence paths | Errors |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [ImpactLens](https://github.com/jasonorjasor/ImpactLens) | `d49b888e0f27b7a506f526148f573cd7f690e015` | `2b1ccbbb5779a50a7f1dc473d45c26215eaab1ad` | 227,135 B | 1.660 s | 6.161 s | 7.917 s | 7 | 3 | 0 |
| [Requests](https://github.com/psf/requests) | `5691f596134c2feb121e595c77a0178921fcce61` | `e511bc72777a94c45d004e010c597925092e1efe` | 11,445,473 B | 2.621 s | 10.001 s | 12.772 s | 2 | 7 | 0 |
| [pytest](https://github.com/pytest-dev/pytest) | `7d90c44cca8f2e37dc0ab3d9643a4672a8a3f7f9` | `6a0de9be56365e75ff30d75cee9654739ca95f97` | 25,811,249 B | 4.542 s | 24.619 s | 29.538 s | 2 | 0 | 0 |

These are cold, single-request observations, not throughput tests. They do not establish a safe deployment size limit or concurrent capacity.

## Batch-loading check

On September 18, profiling the Requests comparison showed 46 analyzer Git calls and about 10 seconds in committed-file loading, compared with about 1.6 seconds parsing files. We changed commit analysis to list Python blob IDs once and read them with one `git cat-file --batch` call. The same pinned comparisons then produced:

| Repository | Analysis before | Analysis after | Total after | Report check |
| --- | ---: | ---: | ---: | --- |
| ImpactLens | 6.161 s | 6.922 s | 8.968 s | Same counts; no baseline hash |
| Requests | 9.446 s | 7.955 s | 10.709 s | Full report hash unchanged |
| pytest | 23.013 s | 6.896 s | 12.235 s | Full report hash unchanged |

The Requests and pytest “before” runs were repeated on September 18 before the change. The ImpactLens “before” value is from September 17; its checkout size also changed as this repository grew. Another ImpactLens run after the change took 8.368 seconds in analysis, so this is not evidence of a small-repository speedup. Network, Git lazy fetching, and machine load vary between runs. The command now prints a SHA-256 hash of the complete JSON report to detect output changes, not just changes in result counts.

## Peak memory and overlapping analyses

Run `python -m benchmarks.capacity REPOSITORY BASE_COMMIT TARGET_COMMIT --concurrent 1`, then repeat with `--concurrent 2` in a fresh process. The two-run command starts both repository loads together and waits for both to finish loading before starting analysis. It reports each run's timing, result counts, and full report hash, plus wall time and the process's peak memory. Use the pinned commit pairs above.

One Windows/Python 3.14 run per setting on September 18, 2026 gave:

| Repository | Peak memory, one | Peak memory, two | Wall time, one | Wall time, two | Results per run | Report hash prefix |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| ImpactLens | 25.4 MiB | 26.4 MiB | 9.233 s | 9.417 s | 7 changed, 3 paths, 0 errors | `a18e17902cd4` |
| Requests | 38.5 MiB | 46.1 MiB | 12.482 s | 12.563 s | 2 changed, 7 paths, 0 errors | `67dac84aa64a` |
| pytest | 58.6 MiB | 76.1 MiB | 24.870 s | 19.242 s | 2 changed, 0 paths, 0 errors | `f818ed26e66e` |

Both runs in each pair matched the single-run report hash. Peak memory is the Python process's peak working set from process start; it excludes child Git processes, other server processes, and operating-system cache. These commands exercise the same loader and analyzer as the API, but they do not send HTTP requests or measure rejected third requests. Cloning and on-demand Git fetching affect wall time, so the shorter two-run pytest result is not a throughput claim. These samples do not justify raising the 100 MB repository limit or changing the two-analysis API limit. Streaming batch blob output remains an option if larger or repeated workloads show memory pressure.
