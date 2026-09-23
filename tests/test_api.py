from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import subprocess
import threading
import time

import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient

import api
from git_analyzer import AnalysisTimeoutError
from repository_loader import RepositoryTimeoutError


client = TestClient(api.app)
request = {
    "repository": "https://github.com/owner/repository",
    "base_commit": "old",
    "target_commit": "new",
}


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("payload, status", [
    ({**request, "repository": "C:/local/repository"}, 400),
    ({**request, "base_commit": ""}, 422),
    ({"repository": request["repository"], "base_commit": "old"}, 422),
])
def test_analyze_rejects_invalid_requests(payload, status):
    assert client.post("/analyze", json=payload).status_code == status


def test_analyze_returns_a_validated_report(monkeypatch, tmp_path):
    calls = []

    @contextmanager
    def fake_loader(*args):
        calls.append(("load", args))
        yield tmp_path

    def fake_analyzer(*args):
        calls.append(("analyze", args))
        return {
            "base_commit": "old",
            "target_commit": "new",
            "changed_symbols": [{
                "id": "auth.py::verify_user", "path": "auth.py", "qualname": "verify_user",
                "line_start": 1, "line_end": 2, "changed_lines": [],
                "removed_lines": [1, 2], "change_type": "deleted",
                "impact_paths": [{
                    "source": "base",
                    "symbols": ["auth.py::verify_user", "services.py::login"],
                }],
            }],
            "affected_symbols": [], "affected_routes": [], "related_tests": [],
            "historical_impact": {
                "affected_symbols": ["services.py::login"],
                "affected_routes": [], "related_tests": [],
            },
            "evidence_paths": [{
                "source": "base",
                "symbols": ["auth.py::verify_user", "services.py::login"],
            }],
            "analysis_errors": [{
                "source": "target", "path": "broken.py", "error": "invalid syntax",
            }],
        }

    monkeypatch.setattr(api, "open_repository", fake_loader)
    monkeypatch.setattr(api, "analyze_change", fake_analyzer)

    response = client.post("/analyze", json=request)

    assert response.status_code == 200
    assert response.json()["changed_symbols"][0]["change_type"] == "deleted"
    assert response.json()["historical_impact"]["affected_symbols"] == ["services.py::login"]
    assert response.json()["analysis_errors"] == [{
        "source": "target", "path": "broken.py", "error": "invalid syntax",
    }]
    assert calls == [
        ("load", (request["repository"], "old", "new")),
        ("analyze", (tmp_path, "old", "new")),
    ]


def test_http_response_contains_real_analysis_and_parse_errors(monkeypatch, tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    git("init")
    git("config", "user.email", "impactlens@example.com")
    git("config", "user.name", "ImpactLens Tests")
    (repository / "auth.py").write_text(
        "def verify_user():\n    return True\n", encoding="utf-8"
    )
    (repository / "services.py").write_text(
        "from auth import verify_user\n\ndef login():\n    return verify_user()\n",
        encoding="utf-8",
    )
    git("add", "auth.py", "services.py")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repository / "auth.py").write_text(
        "def verify_user():\n    return False\n", encoding="utf-8"
    )
    (repository / "broken.py").write_text("def invalid(:\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "change verification")
    target = git("rev-parse", "HEAD")

    @contextmanager
    def fake_loader(*args):
        yield repository

    monkeypatch.setattr(api, "open_repository", fake_loader)
    response = client.post("/analyze", json={
        **request, "base_commit": base, "target_commit": target,
    })

    assert response.status_code == 200
    assert response.json()["changed_symbols"][0]["id"] == "auth.py::verify_user"
    assert response.json()["evidence_paths"][0]["source"] == "target"
    assert response.json()["analysis_errors"][0]["path"] == "broken.py"
    assert response.json()["analysis_errors"][0]["source"] == "target"


def test_analyze_returns_loader_error_as_http_error(monkeypatch):
    @contextmanager
    def fake_loader(*args):
        raise api.RepositoryLoadError("commit not found")
        yield

    monkeypatch.setattr(api, "open_repository", fake_loader)
    response = client.post("/analyze", json=request)

    assert response.status_code == 400
    assert response.json() == {"detail": "commit not found"}


def test_analyze_returns_post_analysis_size_error_and_releases_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(1))

    @contextmanager
    def growing_repository(*args):
        yield tmp_path
        raise api.RepositoryLoadError("Repository is too large")

    monkeypatch.setattr(api, "open_repository", growing_repository)
    monkeypatch.setattr(api, "analyze_change", lambda *args: empty_report())

    first = client.post("/analyze", json=request)
    second = client.post("/analyze", json=request)

    assert first.status_code == second.status_code == 400
    assert first.json() == second.json() == {"detail": "Repository is too large"}


def test_analyze_rejects_a_malformed_analyzer_result(monkeypatch, tmp_path):
    @contextmanager
    def fake_loader(*args):
        yield tmp_path

    monkeypatch.setattr(api, "open_repository", fake_loader)
    monkeypatch.setattr(api, "analyze_change", lambda *args: {"result": "unknown shape"})

    with pytest.raises(ResponseValidationError):
        client.post("/analyze", json=request)


def empty_report():
    return {
        "base_commit": "old", "target_commit": "new", "changed_symbols": [],
        "affected_symbols": [], "affected_routes": [], "related_tests": [],
        "historical_impact": {
            "affected_symbols": [], "affected_routes": [], "related_tests": [],
        },
        "evidence_paths": [], "analysis_errors": [],
    }


def test_analyze_rejects_excess_concurrent_requests(monkeypatch, tmp_path):
    entered = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(1))

    @contextmanager
    def slow_loader(*args):
        entered.set()
        assert release.wait(5)
        yield tmp_path

    monkeypatch.setattr(api, "open_repository", slow_loader)
    monkeypatch.setattr(api, "analyze_change", lambda *args: empty_report())

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, "/analyze", json=request)
        assert entered.wait(5)
        try:
            busy = client.post("/analyze", json=request)
            assert busy.status_code == 503
            assert "busy" in busy.json()["detail"].lower()
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200


def test_two_analyses_run_while_a_third_is_rejected(monkeypatch, tmp_path):
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    active = 0
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(2))

    @contextmanager
    def slow_loader(*args):
        nonlocal active
        with lock:
            active += 1
            if active == 2:
                entered.set()
        assert release.wait(5)
        try:
            yield tmp_path
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(api, "open_repository", slow_loader)
    monkeypatch.setattr(api, "analyze_change", lambda *args: empty_report())

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, "/analyze", json=request)
        second = pool.submit(client.post, "/analyze", json=request)
        assert entered.wait(5)
        try:
            busy = client.post("/analyze", json=request)
            assert busy.status_code == 503
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
        assert second.result(timeout=5).status_code == 200


def test_analysis_timeout_returns_a_clear_response_and_releases_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(1))

    @contextmanager
    def fake_loader(*args):
        yield tmp_path

    monkeypatch.setattr(api, "open_repository", fake_loader)
    def timed_out(*args):
        raise AnalysisTimeoutError("Analysis Git command timed out")

    monkeypatch.setattr(api, "analyze_change", timed_out)
    response = client.post("/analyze", json=request)
    assert response.status_code == 504
    assert "timed out" in response.json()["detail"].lower()

    monkeypatch.setattr(api, "analyze_change", lambda *args: empty_report())
    assert client.post("/analyze", json=request).status_code == 200


def test_request_deadline_returns_504_and_releases_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "MAX_REQUEST_SECONDS", 0.05)
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(1))

    @contextmanager
    def fake_loader(*args):
        yield tmp_path

    def slow_analyzer(*args):
        time.sleep(0.1)
        return empty_report()

    monkeypatch.setattr(api, "open_repository", fake_loader)
    monkeypatch.setattr(api, "analyze_change", slow_analyzer)
    response = client.post("/analyze", json=request)
    assert response.status_code == 504
    assert "deadline" in response.json()["detail"].lower()

    monkeypatch.setattr(api, "analyze_change", lambda *args: empty_report())
    assert client.post("/analyze", json=request).status_code == 200


def test_repository_timeout_returns_gateway_timeout(monkeypatch):
    @contextmanager
    def slow_loader(*args):
        raise RepositoryTimeoutError("Git operation timed out")
        yield

    monkeypatch.setattr(api, "open_repository", slow_loader)
    response = client.post("/analyze", json=request)

    assert response.status_code == 504
    assert response.json() == {"detail": "Git operation timed out"}
