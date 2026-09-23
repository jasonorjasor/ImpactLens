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

## API and Git process check

Install the optional sampler with `python -m pip install -e ".[benchmark]"`. Run `python -m benchmarks.api_load REPOSITORY BASE_COMMIT TARGET_COMMIT --requests 1`, then repeat with `--requests 2` and `--requests 3` in fresh processes. Each command starts a local API server, sends requests together, samples its process and Git children, checks successful report hashes, and expects a 503 when a third request overlaps the two API slots.

One Windows/Python 3.14 run per setting on September 22, 2026 gave:

| Repository | Peak summed RSS, 1 / 2 / 3 requests | Wall time, 1 / 2 / 3 | HTTP results for 3 | API report hash prefix |
| --- | --- | --- | --- | --- |
| ImpactLens | 121.5 / 176.1 / 172.2 MiB | 8.556 / 8.861 / 8.777 s | 200, 200, 503 | `f663537c47d3` |
| Requests | 126.3 / 189.6 / 192.7 MiB | 10.909 / 11.244 / 11.701 s | 200, 200, 503 | `67dac84aa64a` |
| pytest | 131.0 / 192.6 / 197.2 MiB | 17.129 / 23.672 / 25.097 s | 200, 200, 503 | `64c9b4df15a2` |

Every 200 response in a repository's three settings had the same complete JSON hash and zero analysis errors. The rejected requests returned the API's busy message in 0.018–0.046 seconds. The sampler checks RSS about every 20 ms while requests run. Summing RSS can count shared memory more than once, and brief Git peaks can fall between samples; the result is an observed process-tree footprint, not an exact peak or unique-memory total. GitHub download speed and machine load affect wall times. These single runs support the existing two-slot behavior for these repositories but do not establish a safe 100 MB repository limit, a total request deadline, or capacity across server processes.

## Near-limit check

On September 23, 2026, the pinned [AutoGen](https://github.com/microsoft/autogen) pair `b0477309d2a0baf489aa256646e41e513ab3bfe8` → `8544314fa6cc9f906c3ec2395927f5404ffbb5eb` loaded at 98,437,059 bytes (93.9 MiB). Analysis grew its checkout to 98,446,098 bytes. It reported 5 changed symbols, 1 evidence path, and no errors; the complete CLI JSON hash was `f513c6f1679b5d34efb835bffbd1f9121b63a0a72ab39bf217dfdfdfad679105` before and after the final size check was added.

| Requests | Sampled peak summed RSS | Wall time | HTTP results |
| --- | ---: | ---: | --- |
| 1 | 227.5 MiB | 19.064 s | 200 |
| 2 | 393.2 MiB | 27.128 s | 200, 200 |
| 3 | 344.5 MiB | 32.865 s | 200, 200, 503 |

All successful API responses had the same complete JSON hash, `e4cd41e1f162f67e83db211203dc055381e4d995ac624f6ec4ab2ef89b800f01`. The adjacent documentation-only pair also completed at the same checkout size, with zero changed symbols. A pinned Django checkout was rejected after clone at 113,953,449 bytes, above the 104,857,600-byte limit. These are single runs on this Windows machine. The 3-request peak can be lower than the 2-request peak because the third request is rejected and sampled memory varies between runs. The size check after analysis catches a checkout that finishes too large, but it cannot bound bytes downloaded or disk used while Git is running. Keep one server worker until admission is coordinated across processes.

## Shared request deadline

The API now gives repository loading and analysis one 120-second budget. Each Git command uses the smaller of its own ceiling and the remaining request time; source parsing and graph traversal check between work items. The deadline returns 504 and releases the API slot. It is cooperative for Python work and does not interrupt a single AST parse or guarantee that spawned Git descendants stop at the exact deadline.

After this change, the pinned ImpactLens API comparison returned two identical 200 reports in 9.351 seconds of wall time. CLI runs of Requests and pytest kept their full report hashes (`67dac84aa64a` and `f818ed26e66e`), with totals of 11.382 and 26.515 seconds. The near-limit AutoGen API comparison returned the same report hash (`e4cd41e1f162`) in 18.953 seconds. These are individual runs on September 23, 2026, not evidence of a speed change.
