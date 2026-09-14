"""Tests for mapping Git changes to Python functions."""

import subprocess

from git_analyzer import (
    analyze_working_tree,
    changed_python_lines,
    changed_symbols,
)


def run_git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def test_maps_changed_lines_to_target_functions(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")

    source = repository / "auth.py"
    source.write_text(
        "def verify_user():\n    return True\n\n"
        "def unchanged():\n    return 1\n",
        encoding="utf-8",
    )
    run_git(repository, "add", "auth.py")
    run_git(repository, "commit", "-m", "base")
    base_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    source.write_text(
        "def verify_user():\n    return False\n\n"
        "def unchanged():\n    return 1\n",
        encoding="utf-8",
    )
    run_git(repository, "add", "auth.py")
    run_git(repository, "commit", "-m", "change auth behavior")
    target_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    assert changed_python_lines(repository, base_commit, target_commit) == {"auth.py": {2}}
    assert changed_symbols(repository, base_commit, target_commit) == [
        {
            "id": "auth.py::verify_user",
            "path": "auth.py",
            "qualname": "verify_user",
            "line_start": 1,
            "line_end": 2,
            "changed_lines": [2],
        }
    ]

    source.write_text(
        "def verify_user():\n    return 0\n\n"
        "def unchanged():\n    return 1\n",
        encoding="utf-8",
    )

    assert changed_python_lines(repository, target_commit) == {"auth.py": {2}}
    working_tree_report = analyze_working_tree(repository, target_commit)
    assert working_tree_report["target_commit"] == "WORKING_TREE"
    assert [symbol["id"] for symbol in working_tree_report["changed_symbols"]] == [
        "auth.py::verify_user"
    ]
