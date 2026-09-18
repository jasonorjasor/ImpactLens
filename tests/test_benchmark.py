from contextlib import contextmanager
import hashlib
import json

from benchmarks import measure as benchmark


def test_measure_reports_load_analysis_and_repository_size(monkeypatch, tmp_path):
    times = iter([0.0, 2.0, 2.1, 5.1, 5.3])
    sizes = iter([100, 120])

    @contextmanager
    def fake_loader(*args):
        yield tmp_path

    monkeypatch.setattr(benchmark, "open_repository", fake_loader)
    monkeypatch.setattr(benchmark, "repository_size_bytes", lambda _: next(sizes))
    monkeypatch.setattr(benchmark, "analyze_change", lambda *args: {
        "changed_symbols": [{"id": "core.py::work"}],
        "evidence_paths": [],
        "analysis_errors": [],
    })
    monkeypatch.setattr(benchmark.time, "perf_counter", lambda: next(times))

    result = benchmark.measure("repo", "base", "target")

    assert result == {
        "repository": "repo",
        "base_commit": "base",
        "target_commit": "target",
        "load_seconds": 2.0,
        "analysis_seconds": 3.0,
        "total_seconds": 5.3,
        "loaded_bytes": 100,
        "analyzed_bytes": 120,
        "changed_symbols": 1,
        "evidence_paths": 0,
        "analysis_errors": 0,
        "report_sha256": hashlib.sha256(
            json.dumps(
                {
                    "changed_symbols": [{"id": "core.py::work"}],
                    "evidence_paths": [],
                    "analysis_errors": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
