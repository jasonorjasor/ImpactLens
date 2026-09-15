from contextlib import contextmanager

import pytest
from fastapi import HTTPException

import api


def test_health_returns_ok():
    assert api.health() == {"status": "ok"}


def test_analyze_requires_a_github_url():
    request = api.AnalyzeRequest(
        repository="C:/local/repository",
        base_commit="old",
        target_commit="new",
    )

    with pytest.raises(HTTPException) as error:
        api.analyze_repository_change(request)

    assert error.value.status_code == 400


def test_analyze_uses_the_loader_and_analyzer(monkeypatch, tmp_path):
    calls = []

    @contextmanager
    def fake_loader(*args):
        calls.append(("load", args))
        yield tmp_path

    def fake_analyzer(*args):
        calls.append(("analyze", args))
        return {"result": "ok"}

    monkeypatch.setattr(api, "open_repository", fake_loader)
    monkeypatch.setattr(api, "analyze_change", fake_analyzer)
    request = api.AnalyzeRequest(
        repository="https://github.com/owner/repository",
        base_commit="old",
        target_commit="new",
    )

    assert api.analyze_repository_change(request) == {"result": "ok"}
    assert calls == [
        (
            "load",
            ("https://github.com/owner/repository", "old", "new"),
        ),
        ("analyze", (tmp_path, "old", "new")),
    ]
