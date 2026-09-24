import pytest
from fastapi.testclient import TestClient

from web import create_app


def test_production_app_serves_frontend_and_api(tmp_path):
    (tmp_path / "index.html").write_text("<h1>ImpactLens</h1>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ready')", encoding="utf-8")

    client = TestClient(create_app(tmp_path))

    assert "ImpactLens" in client.get("/").text
    assert "ready" in client.get("/assets/app.js").text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/analyze", json={}).status_code == 422
    assert client.get("/docs").status_code == 200


def test_production_app_requires_a_frontend_build(tmp_path):
    with pytest.raises(RuntimeError, match="Frontend build is missing"):
        create_app(tmp_path)
