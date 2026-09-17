from contextlib import contextmanager
import subprocess

import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient

import api


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


def test_analyze_rejects_a_malformed_analyzer_result(monkeypatch, tmp_path):
    @contextmanager
    def fake_loader(*args):
        yield tmp_path

    monkeypatch.setattr(api, "open_repository", fake_loader)
    monkeypatch.setattr(api, "analyze_change", lambda *args: {"result": "unknown shape"})

    with pytest.raises(ResponseValidationError):
        client.post("/analyze", json=request)
