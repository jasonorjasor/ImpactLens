import subprocess

import pytest
from fastapi.testclient import TestClient

from benchmarks.usability import EXERCISE_URL, build_exercise, create_exercise_app


def test_exercise_uses_real_commits_and_source_evidence_without_running_fixture_code(tmp_path):
    exercise = build_exercise(tmp_path / "exercise")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text('<html><body><div id="root"></div></body></html>', encoding="utf-8")
    client = TestClient(create_exercise_app(exercise, frontend))

    response = client.post("/analyze", json=exercise.request)
    assert response.status_code == 200
    report = response.json()
    assert report["resolved_commits"] == {"base": exercise.base, "target": exercise.target}
    assert [item["id"] for item in report["changed_symbols"]] == ["pricing.py::shipping_fee"]
    assert report["evidence_paths"] == [{"source": "target", "symbols": [
        "pricing.py::shipping_fee", "routes.py::shipping", "tests/test_shipping.py::test_free_shipping",
    ]}]
    assert report["affected_routes"] == [{
        "symbol_id": "routes.py::shipping", "method": "GET", "path": "/api/checkout/shipping", "registration": "registered",
    }]
    assert report["related_tests"] == ["tests/test_shipping.py::test_free_shipping"]
    assert report["analysis_errors"] == report["analysis_warnings"] == []
    assert report.get("repository_url") is None
    assert [(site["path"], site["line"], site["code"]) for site in report["call_sites"]] == [
        ("routes.py", 8, "return {'fee': shipping_fee(subtotal)}"),
        ("tests/test_shipping.py", 4, "assert shipping(60) == {'fee': 0}"),
    ]
    assert not list(exercise.repository.rglob("__pycache__"))
    assert "Local review exercise" in client.get("/").text
    sheet = client.get("/exercise").text
    assert exercise.base in sheet and exercise.target in sheet and EXERCISE_URL in sheet
    assert "/api/checkout/shipping" not in sheet

    for field in ("repository", "base_commit", "target_commit"):
        invalid = {**exercise.request, field: "https://github.com/other/repo" if field == "repository" else "HEAD"}
        error = client.post("/analyze", json=invalid)
        assert error.status_code == 400
        assert "No GitHub fetch was attempted" in error.json()["detail"]
    assert client.post("/analyze", json={}).status_code == 422
    assert client.post("/analyze", json=exercise.request).json() == report


def test_exercise_is_reproducible_and_does_not_overwrite_files(tmp_path):
    first = build_exercise(tmp_path / "first")
    second = build_exercise(tmp_path / "second")
    assert first.request == second.request
    assert subprocess.run(
        ["git", "-C", str(first.repository), "diff", "--name-only", first.base, first.target],
        check=True, capture_output=True, text=True,
    ).stdout.strip() == "pricing.py"
    with pytest.raises(FileExistsError):
        build_exercise(first.repository.parent)
    assert (first.repository.parent / "comparison.json").is_file()
