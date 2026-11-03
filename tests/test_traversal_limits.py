from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import api
import cli
import git_analyzer
import repository_loader
from request_budget import AnalysisLimitExceeded, TraversalBudget


def branching_comparison(comparison):
    repository, commit = comparison
    base = commit({"service.py": "def work():\n    return 1\n\ndef first():\n    return work()\n\ndef second():\n    return work()\n"})
    target = commit({"service.py": "def work():\n    return 2\n\ndef first():\n    return work()\n\ndef second():\n    return work()\n"})
    return repository, base, target


def test_api_rejects_oversized_tracing_and_releases_its_slot_for_the_next_request(comparison, monkeypatch):
    repository, base, target = branching_comparison(comparison)
    closed = []

    @contextmanager
    def loader(*args):
        try:
            yield repository
        finally:
            closed.append(True)

    monkeypatch.setattr(api, "open_repository", loader)
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(git_analyzer, "TraversalBudget", lambda: TraversalBudget(max_paths=1))
    client = TestClient(api.app)
    payload = {"repository": "https://github.com/owner/repo", "base_commit": base, "target_commit": target}
    response = client.post("/analyze", json=payload)
    assert response.status_code == 422
    assert "No complete report was produced" in response.json()["detail"]
    assert "evidence_paths" not in response.json()
    assert closed == [True]
    monkeypatch.setattr(git_analyzer, "TraversalBudget", lambda: TraversalBudget(max_paths=2))
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    assert len(response.json()["evidence_paths"]) == 2
    assert closed == [True, True]


def test_cli_limit_error_has_no_partial_json(comparison, monkeypatch, capsys):
    repository, base, target = branching_comparison(comparison)
    monkeypatch.setattr(git_analyzer, "TraversalBudget", lambda: TraversalBudget(max_paths=1))
    with pytest.raises(SystemExit) as caught:
        cli.main([str(repository), base, target, "--json", "--all-paths"])
    output = capsys.readouterr()
    assert caught.value.code == 2
    assert output.out == ""
    assert "No complete report was produced" in output.err


def test_changed_and_deleted_symbols_share_one_comparison_budget(comparison, monkeypatch):
    repository, commit = comparison
    base = commit({"service.py": "def old():\n    return 1\n\ndef new():\n    return 1\n\ndef old_caller():\n    return old()\n\ndef new_caller():\n    return new()\n"})
    target = commit({"service.py": "def new():\n    return 2\n\ndef old_caller():\n    return old()\n\ndef new_caller():\n    return new()\n"})
    monkeypatch.setattr(git_analyzer, "TraversalBudget", lambda: TraversalBudget(max_paths=1))
    with pytest.raises(AnalysisLimitExceeded, match="connection paths"):
        git_analyzer.analyze_change(repository, base, target)
    monkeypatch.setattr(git_analyzer, "TraversalBudget", lambda: TraversalBudget(max_paths=2))
    report = git_analyzer.analyze_change(repository, base, target)
    assert {path["source"] for path in report["evidence_paths"]} == {"base", "target"}


def test_overlapping_comparisons_have_independent_budgets(comparison, monkeypatch):
    repository, base, target = branching_comparison(comparison)
    monkeypatch.setattr(git_analyzer, "TraversalBudget", lambda: TraversalBudget(max_paths=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: git_analyzer.analyze_change(repository, base, target), range(2)))
    assert reports[0] == reports[1]
    assert len(reports[0]["evidence_paths"]) == 2


def test_public_checkout_cleanup_preserves_the_limit_error(tmp_path, monkeypatch):
    def command(arguments):
        if "clone" in arguments:
            Path(arguments[-1]).mkdir()

    monkeypatch.setattr(repository_loader, "tempfile", SimpleNamespace(
        TemporaryDirectory=lambda **kwargs: TemporaryDirectory(dir=tmp_path, **kwargs),
    ))
    monkeypatch.setattr(repository_loader, "_run_command", command)
    monkeypatch.setattr(repository_loader, "_commit_exists", lambda *_: True)
    failure = AnalysisLimitExceeded("connection paths", 1)
    with pytest.raises(AnalysisLimitExceeded) as caught:
        with repository_loader.open_repository("https://github.com/owner/repo", "base", "target") as repository:
            checkout_root = repository.parent.resolve()
            assert checkout_root.is_relative_to(tmp_path.resolve())
            assert repository.is_dir()
            raise failure
    assert caught.value is failure
    assert not checkout_root.exists()
