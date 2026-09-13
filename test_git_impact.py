"""Tests for complete Git-based impact analysis."""

import subprocess

from git_analyzer import analyze_change


def run_git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


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
        "from services import login\n\n"
        "def login_route():\n    return login()\n",
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
    ]
    assert report["evidence_paths"] == [
        [
            "auth.py::verify_user",
            "services.py::login",
            "routes.py::login_route",
        ]
    ]
