"""Reviewed FastAPI relationships, without importing the fixture applications."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import api
from analyzer import analyze_sources
from cli import format_report
from git_analyzer import analyze_change


@pytest.mark.parametrize("parameter", [
    "user=Depends(get_user)",
    "user=Depends(dependency=get_user, use_cache=False)",
    "user: Annotated[str, Depends(get_user)]",
    "*, user: Annotated[str, Depends(get_user)]",
])
@pytest.mark.parametrize("deleted", [False, True])
def test_dependency_change_reaches_registered_route_and_test(comparison, parameter, deleted, monkeypatch):
    repository, commit = comparison
    routes = (
        "from typing import Annotated\n"
        "from fastapi import APIRouter, Depends\n"
        "from auth import get_user\n"
        "router = APIRouter(prefix='/users')\n"
        "@router.get('/me')\n"
        f"def me({parameter}):\n    return user\n"
    )
    base = commit({
        "auth.py": "def get_user():\n    return 'before'\n",
        "routes.py": routes,
        "main.py": "from fastapi import FastAPI\nfrom routes import router\napp = FastAPI()\napp.include_router(router, prefix='/api')\n",
        "tests/test_routes.py": "from routes import me\ndef test_me():\n    return me()\n",
    })
    target = commit({"auth.py": "" if deleted else "def get_user():\n    return 'after'\n"})
    report = analyze_change(repository, base, target)
    source = "base" if deleted else "target"
    summary = report["historical_impact"] if deleted else report
    assert report["analysis_errors"] == []
    assert report["evidence_paths"] == [{"source": source, "symbols": ["auth.py::get_user", "routes.py::me", "tests/test_routes.py::test_me"]}]
    assert summary["affected_routes"] == [{"symbol_id": "routes.py::me", "method": "GET", "path": "/api/users/me", "registration": "registered"}]
    assert summary["related_tests"] == ["tests/test_routes.py::test_me"]
    site = next(site for site in report["call_sites"] if site["relationship"] == "fastapi_dependency")
    assert site["source"] == source
    assert (site["caller_id"], site["callee_id"]) == ("routes.py::me", "auth.py::get_user")
    assert site["path"] == "routes.py" and site["line"] == site["line_end"] == 6
    assert site["expression"].startswith("Depends(")
    assert site["code"] == f"def me({parameter}):"
    assert site["resolution"] == "import"
    assert "depends on (FastAPI Depends)" in format_report(report)
    if not deleted:
        assert report["analysis_warnings"] == []
    else:
        assert report["affected_routes"] == []
        assert any(item["source"] == "target" and "get_user" in item["message"] for item in report["analysis_warnings"])

    @contextmanager
    def loader(*args):
        yield repository

    monkeypatch.setattr(api, "open_repository", loader)
    response = TestClient(api.app).post("/analyze", json={"repository": "https://github.com/owner/repo", "base_commit": base, "target_commit": target})
    assert response.status_code == 200
    assert response.json()["call_sites"] == report["call_sites"]
    assert response.json()["analysis_warnings"] == report["analysis_warnings"]


def test_aliases_relative_imports_and_multiple_mounts():
    report = analyze_sources({
        "app/auth.py": "def user():\n    return 1\n",
        "app/routes.py": "import fastapi as f\nfrom .auth import user as get_user\nr = f.APIRouter(prefix='/users')\n@r.get(path='/me')\ndef me(user=f.Depends(get_user)):\n    return user\n",
        "app/__init__.py": "from fastapi import FastAPI as API\nfrom . import routes as endpoints\napp = API()\napp.include_router(endpoints.r, prefix='/v1')\napp.include_router(endpoints.r, prefix='/v2')\n",
    })
    routes = next(file for file in report["files"] if file["path"] == "app/routes.py")
    assert [route["path"] for route in routes["routes"]] == ["/v1/users/me", "/v2/users/me"]
    assert all(route["registration"] == "registered" for route in routes["routes"])
    dependency = next(call for call in routes["calls"] if call.get("relationship"))
    assert dependency["callee_id"] == "app/auth.py::user"
    assert report["warnings"] == []


def test_subdependencies_are_framework_edges_with_actual_declarations():
    report = analyze_sources({"app.py": "from fastapi import FastAPI, Depends as D\napp = FastAPI()\ndef token():\n    return 1\ndef user(token=D(token)):\n    return token\n@app.get('/me')\ndef me(user=D(user)):\n    return user\n"})
    dependencies = [call for call in report["files"][0]["calls"] if call.get("relationship")]
    assert [(call["caller_id"], call["callee_id"], call["line"]) for call in dependencies] == [
        ("app.py::user", "app.py::token", 5), ("app.py::me", "app.py::user", 8),
    ]
    assert report["warnings"] == []


def test_function_local_bindings_do_not_reassign_module_framework_names():
    report = analyze_sources({"app.py": "import fastapi as f\napp = f.FastAPI()\ndef helper():\n    f = 'local'\n    app = 'local'\n    return f + app\ndef user():\n    return 1\n@app.get('/me')\ndef me(user=f.Depends(user)):\n    return user\n"})
    file = report["files"][0]
    assert file["routes"][0]["path"] == "/me"
    assert next(call for call in file["calls"] if call.get("relationship"))["callee_id"] == "app.py::user"
    assert report["warnings"] == []


@pytest.mark.parametrize("declarations", [
    "class Store:\n    def get(self, path):\n        return lambda fn: fn\napp = Store()\n",
    "from fastapi import FastAPI\nFastAPI = object\napp = FastAPI()\n",
    "from fastapi import FastAPI\napp = FastAPI()\napp = object()\n",
])
def test_lookalike_or_reassigned_objects_are_not_fastapi_routes(declarations):
    result = analyze_sources({"app.py": declarations + "@app.get('/fake')\ndef endpoint():\n    return 1\n"})
    assert result["files"][0]["routes"] == []


@pytest.mark.parametrize("suffix", [
    "get_user = object()\n",
    "def get_user():\n    return 2\n",
    "Depends = lambda item: item\n",
])
def test_reassigned_dependency_names_do_not_gain_framework_edges(suffix):
    result = analyze_sources({"app.py": "from fastapi import Depends\ndef get_user():\n    return 1\n" + suffix + "def me(user=Depends(get_user)):\n    return user\n"})
    assert not any(call["callee_id"] for call in result["files"][0]["calls"] if call.get("relationship"))


@pytest.mark.parametrize("setup, expected_warning", [
    ("router = APIRouter(prefix=PREFIX)\napp.include_router(router)\n", "prefix"),
    ("router = APIRouter()\napp.include_router(router, prefix=PREFIX)\n", "configuration"),
    ("router = APIRouter()\nparent = APIRouter(prefix='/api')\nparent.include_router(router)\napp.include_router(parent)\n", "Nested"),
    ("router = APIRouter()\ndef register():\n    app.include_router(router)\n", "configuration"),
])
def test_unknown_registration_does_not_invent_complete_addresses(setup, expected_warning):
    result = analyze_sources({"app.py": "from fastapi import APIRouter, FastAPI\napp = FastAPI()\n" + setup + "@router.get('/me')\ndef me():\n    return 1\n"})
    assert result["files"][0]["routes"] == []
    assert any(expected_warning in warning["message"] for warning in result["warnings"])


def test_unmounted_router_is_a_declaration_and_late_route_is_not_registered():
    unmounted = analyze_sources({"app.py": "from fastapi import APIRouter\nrouter = APIRouter(prefix='/users')\n@router.get('/me')\ndef me():\n    return 1\n"})
    assert unmounted["files"][0]["routes"][0]["registration"] == "declared"
    assert unmounted["files"][0]["routes"][0]["path"] == "/users/me"
    late = analyze_sources({"app.py": "from fastapi import APIRouter, FastAPI\napp = FastAPI()\nrouter = APIRouter()\napp.include_router(router)\n@router.get('/late')\ndef late():\n    return 1\n"})
    assert late["files"][0]["routes"] == []
    assert any("after include_router" in item["message"] for item in late["warnings"])


@pytest.mark.parametrize("parameter, extra", [
    ("user=Depends()", ""),
    ("user=Depends(factory())", ""),
    ("user=Depends(User)", "class User:\n    pass\n"),
    ("user: UserDep", "UserDep = Annotated[str, Depends(get_user)]\n"),
])
def test_unsupported_dependencies_have_limitations(parameter, extra):
    result = analyze_sources({"app.py": "from fastapi import Depends\nfrom typing import Annotated\ndef get_user():\n    return 1\n" + extra + f"def me({parameter}):\n    return user\n"})
    assert not any(call["callee_id"] for call in result["files"][0]["calls"] if call.get("relationship"))
    assert result["warnings"]


def test_framework_warnings_are_separate_from_parse_errors():
    result = analyze_sources({"app.py": "from fastapi import FastAPI\napp = FastAPI(dependencies=deps)\n", "broken.py": "def invalid(:\n"})
    assert len(result["errors"]) == 1 and result["errors"][0]["path"] == "broken.py"
    assert any(item["path"] == "app.py" and item["line"] == 2 for item in result["warnings"])


def test_decorator_dependency_warning_requires_a_framework_owner():
    result = analyze_sources({
        "real.py": "from fastapi import FastAPI, Depends\napp = FastAPI()\ndef user():\n    return 1\n@app.get('/me', dependencies=[Depends(user)])\ndef me():\n    return 1\n",
        "other.py": "@store.get('/item', dependencies=items)\ndef item():\n    return 1\n",
    })
    assert any("Decorator-level" in item["message"] for item in result["warnings"])
    assert not any(item["path"] == "other.py" for item in result["warnings"])
