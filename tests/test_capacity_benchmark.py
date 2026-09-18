import threading

from benchmarks import capacity


def test_two_capacity_runs_overlap_and_keep_their_reports(monkeypatch):
    both_running = threading.Barrier(2)

    def fake_measure(*args):
        args[3].wait(timeout=5)
        both_running.wait(timeout=5)
        return {"report_sha256": "same-report", "analysis_errors": 0}

    monkeypatch.setattr(capacity, "measure", fake_measure)
    monkeypatch.setattr(capacity, "peak_process_memory_bytes", lambda: 123456)

    result = capacity.measure_capacity("repo", "base", "target", concurrent=2)

    assert result["concurrent"] == 2
    assert result["peak_process_memory_bytes"] == 123456
    assert [run["report_sha256"] for run in result["runs"]] == [
        "same-report", "same-report"
    ]
    assert result["wall_seconds"] >= 0
