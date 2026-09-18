"""Tests for complete Git-based impact analysis."""

import subprocess

import pytest

from git_analyzer import analyze_change


def run_git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def test_uses_declared_python_encoding_for_commits_and_working_tree(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")

    source = repository / "legacy.py"
    source.write_bytes(b"# coding: latin-1\ndef caf\xe9():\n    return 1\n")
    run_git(repository, "add", "legacy.py")
    run_git(repository, "commit", "-m", "base")
    base = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    source.write_bytes(b"# coding: latin-1\ndef caf\xe9():\n    return 2\n")
    run_git(repository, "add", "legacy.py")
    run_git(repository, "commit", "-m", "change")
    target = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    committed = analyze_change(repository, base, target)
    assert [symbol["id"] for symbol in committed["changed_symbols"]] == ["legacy.py::caf\u00e9"]
    assert committed["analysis_errors"] == []

    source.write_bytes(b"# coding: latin-1\ndef caf\xe9():\n    return 3\n")
    working = analyze_change(repository, target)
    assert [symbol["id"] for symbol in working["changed_symbols"]] == ["legacy.py::caf\u00e9"]
    assert working["analysis_errors"] == []


def test_builds_impact_report_from_two_commits(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")

    (repository / "auth.py").write_text(
        "def verify_user():\n    return True\n", encoding="utf-8"
    )
    (repository / "services.py").write_text(
        "from auth import verify_user\n\n"
        "def login():\n    return verify_user()\n",
        encoding="utf-8",
    )
    (repository / "routes.py").write_text(
        "from services import login\n"
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.post(\"/api/login\")\n"
        "def login_route():\n"
        "    return login()\n",
        encoding="utf-8",
    )
    (repository / "tests").mkdir()
    (repository / "tests" / "test_login.py").write_text(
        "from routes import login_route\n\n"
        "def test_login_route():\n    return login_route()\n",
        encoding="utf-8",
    )
    run_git(repository, "add", ".")
    run_git(repository, "commit", "-m", "base")
    base_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    (repository / "auth.py").write_text(
        "def verify_user():\n    return False\n", encoding="utf-8"
    )
    run_git(repository, "add", "auth.py")
    run_git(repository, "commit", "-m", "change verification")
    target_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    report = analyze_change(repository, base_commit, target_commit)

    assert [symbol["id"] for symbol in report["changed_symbols"]] == [
        "auth.py::verify_user"
    ]
    assert report["affected_symbols"] == [
        "services.py::login",
        "routes.py::login_route",
        "tests/test_login.py::test_login_route",
    ]
    assert report["evidence_paths"] == [
        {"source": "target", "symbols": [
            "auth.py::verify_user",
            "services.py::login",
            "routes.py::login_route",
            "tests/test_login.py::test_login_route",
        ]}
    ]
    assert report["affected_routes"] == [
        {
            "symbol_id": "routes.py::login_route",
            "method": "POST",
            "path": "/api/login",
        }
    ]
    assert report["related_tests"] == ["tests/test_login.py::test_login_route"]
    assert report["historical_impact"] == {
        "affected_symbols": [], "affected_routes": [], "related_tests": [],
    }


@pytest.fixture
def deletion_repository(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")
    sources = {
        "auth.py": "def verify_user():\n    return True\n\ndef keep():\n    return 1\n",
        "services.py": "from auth import verify_user\n\ndef login():\n    return verify_user()\n",
        "routes.py": (
            "from services import login\nfrom fastapi import APIRouter\n"
            "router = APIRouter()\n@router.post('/login')\n"
            "def login_route():\n    return login()\n"
        ),
        "tests/test_login.py": (
            "from routes import login_route\n"
            "def test_login():\n    return login_route()\n"
        ),
    }
    for path, source in sources.items():
        destination = repository / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    run_git(repository, "add", ".")
    run_git(repository, "commit", "-m", "base")
    return repository, run_git(repository, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.parametrize("mode", ["commits", "working_tree", "staged"])
@pytest.mark.parametrize("deletion", ["function", "empty_file", "file"])
def test_deleted_functions_use_historical_dependencies(deletion_repository, mode, deletion):
    repository, base = deletion_repository
    if deletion == "file":
        (repository / "auth.py").unlink()
    else:
        source = "def keep():\n    return 1\n" if deletion == "function" else ""
        (repository / "auth.py").write_text(source, encoding="utf-8")
    target = None
    if mode in {"commits", "staged"}:
        run_git(repository, "add", "-A")
    if mode == "commits":
        run_git(repository, "commit", "-m", "delete authentication")
        target = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    report = analyze_change(repository, base, target)

    symbols = {symbol["id"]: symbol for symbol in report["changed_symbols"]}
    assert len(symbols) == len(report["changed_symbols"])
    expected_ids = {"auth.py::verify_user"}
    if deletion != "function":
        expected_ids.add("auth.py::keep")
    assert set(symbols) == expected_ids
    removed = symbols["auth.py::verify_user"]
    assert removed["change_type"] == "deleted"
    assert removed["changed_lines"] == []
    assert removed["removed_lines"] == [1, 2]
    assert (removed["line_start"], removed["line_end"]) == (1, 2)
    evidence = {
        "source": "base",
        "symbols": [
            "auth.py::verify_user", "services.py::login",
            "routes.py::login_route", "tests/test_login.py::test_login",
        ],
    }
    assert removed["impact_paths"] == [evidence]
    assert evidence in report["evidence_paths"]
    assert all(path["source"] == "base" for path in report["evidence_paths"])
    assert report["affected_symbols"] == []
    assert report["affected_routes"] == []
    assert report["related_tests"] == []
    assert report["historical_impact"] == {
        "affected_symbols": evidence["symbols"][1:],
        "affected_routes": [{
            "symbol_id": "routes.py::login_route", "method": "POST", "path": "/login",
        }],
        "related_tests": ["tests/test_login.py::test_login"],
    }


def test_current_and_historical_paths_stay_separate(deletion_repository):
    repository, base = deletion_repository
    (repository / "auth.py").unlink()
    (repository / "services.py").write_text(
        "def login():\n    return False\n", encoding="utf-8"
    )
    (repository / "routes.py").write_text(
        "from services import login\nfrom fastapi import APIRouter\n"
        "router = APIRouter()\n@router.post('/new-login')\n"
        "def login_route():\n    return login()\n", encoding="utf-8"
    )
    run_git(repository, "add", "-A")
    run_git(repository, "commit", "-m", "replace authentication")
    target = run_git(repository, "rev-parse", "HEAD").stdout.strip()
    report = analyze_change(repository, base, target)

    assert {path["source"] for path in report["evidence_paths"]} == {"base", "target"}
    assert report["affected_routes"][0]["path"] == "/new-login"
    assert report["historical_impact"]["affected_routes"][0]["path"] == "/login"
    for path in report["evidence_paths"]:
        if path["source"] == "target":
            assert "auth.py::verify_user" not in path["symbols"]


def test_deleted_routes_and_tests_are_only_historical(deletion_repository):
    repository, base = deletion_repository
    for path in ["auth.py", "routes.py", "tests/test_login.py"]:
        (repository / path).unlink()
    report = analyze_change(repository, base)

    assert report["affected_routes"] == []
    assert report["related_tests"] == []
    assert report["historical_impact"]["affected_routes"][0]["path"] == "/login"
    assert report["historical_impact"]["related_tests"] == ["tests/test_login.py::test_login"]


def test_reports_parse_errors_from_both_versions(deletion_repository):
    repository, base = deletion_repository
    (repository / "broken.py").write_text("def unfinished(:\n", encoding="utf-8")
    run_git(repository, "add", "broken.py")
    run_git(repository, "commit", "-m", "add broken file")
    base = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    (repository / "auth.py").unlink()
    (repository / "new_broken.py").write_text("def also_unfinished(:\n", encoding="utf-8")
    run_git(repository, "add", "-A")
    run_git(repository, "commit", "-m", "delete auth and add invalid file")
    target = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    report = analyze_change(repository, base, target)

    assert {symbol["id"] for symbol in report["changed_symbols"]} == {
        "auth.py::verify_user", "auth.py::keep",
    }
    assert {(item["source"], item["path"]) for item in report["analysis_errors"]} == {
        ("base", "broken.py"),
        ("target", "broken.py"),
        ("target", "new_broken.py"),
    }
    assert all(item["error"] for item in report["analysis_errors"])


def test_changed_function_without_callers_has_no_impact_path(deletion_repository):
    repository, base = deletion_repository
    (repository / "auth.py").write_text(
        "def verify_user():\n    return True\n\ndef keep():\n    return 2\n",
        encoding="utf-8",
    )

    report = analyze_change(repository, base)

    assert [symbol["id"] for symbol in report["changed_symbols"]] == ["auth.py::keep"]
    assert report["changed_symbols"][0]["impact_paths"] == []
    assert report["evidence_paths"] == []
    assert report["affected_symbols"] == []


def test_deleted_route_without_callers_is_still_historical(deletion_repository):
    repository, _ = deletion_repository
    route = repository / "isolated.py"
    route.write_text(
        "@router.get('/isolated')\ndef isolated():\n    return True\n",
        encoding="utf-8",
    )
    run_git(repository, "add", "isolated.py")
    run_git(repository, "commit", "-m", "add isolated route")
    base = run_git(repository, "rev-parse", "HEAD").stdout.strip()
    route.unlink()

    report = analyze_change(repository, base)

    assert report["changed_symbols"][0]["id"] == "isolated.py::isolated"
    assert report["changed_symbols"][0]["impact_paths"] == []
    assert report["evidence_paths"] == []
    assert report["historical_impact"]["affected_routes"] == [{
        "symbol_id": "isolated.py::isolated", "method": "GET", "path": "/isolated",
    }]
