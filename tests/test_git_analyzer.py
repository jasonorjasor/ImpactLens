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
            "removed_lines": [2],
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


def test_maps_removed_lines_to_the_function_that_lost_them(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")

    source = repository / "auth.py"
    source.write_text(
        "def verify_user():\n    load_user()\n    return True\n",
        encoding="utf-8",
    )
    run_git(repository, "add", "auth.py")
    run_git(repository, "commit", "-m", "base")
    base_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    source.write_text(
        "def verify_user():\n    return True\n",
        encoding="utf-8",
    )
    assert changed_symbols(repository, base_commit) == [
        {
            "id": "auth.py::verify_user",
            "path": "auth.py",
            "qualname": "verify_user",
            "line_start": 1,
            "line_end": 2,
            "changed_lines": [],
            "removed_lines": [2],
        }
    ]
    run_git(repository, "add", "auth.py")
    run_git(repository, "commit", "-m", "remove user loading")
    target_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    assert changed_symbols(repository, base_commit, target_commit) == [
        {
            "id": "auth.py::verify_user",
            "path": "auth.py",
            "qualname": "verify_user",
            "line_start": 1,
            "line_end": 2,
            "changed_lines": [],
            "removed_lines": [2],
        }
    ]


def test_detects_untracked_deleted_and_renamed_working_tree_files(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")

    (repository / "old.py").write_text(
        "def old_function():\n    return True\n", encoding="utf-8"
    )
    (repository / "deleted.py").write_text(
        "def removed_function():\n    return True\n", encoding="utf-8"
    )
    run_git(repository, "add", ".")
    run_git(repository, "commit", "-m", "base")
    base_commit = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    (repository / "old.py").rename(repository / "renamed.py")
    (repository / "deleted.py").unlink()
    (repository / "new.py").write_text(
        "def new_function():\n"
        "    first = 1\n"
        "    second = 2\n"
        "    third = 3\n"
        "    fourth = 4\n"
        "    return first + second + third + fourth\n",
        encoding="utf-8",
    )

    symbols = changed_symbols(repository, base_commit)
    symbols_by_id = {symbol["id"]: symbol for symbol in symbols}

    assert symbols_by_id["renamed.py::old_function"]["change_type"] == "renamed"
    assert symbols_by_id["renamed.py::old_function"]["previous_id"] == (
        "old.py::old_function"
    )
    assert symbols_by_id["new.py::new_function"]["change_type"] == "added"
    assert symbols_by_id["deleted.py::removed_function"]["change_type"] == "deleted"


def test_marks_new_functions_added_in_commit_and_working_tree(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")
    (repository / "core.py").write_text(
        "def existing():\n    return True\n", encoding="utf-8"
    )
    run_git(repository, "add", ".")
    run_git(repository, "commit", "-m", "base")
    base = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    (repository / "core.py").write_text(
        "def existing():\n    return False\n\ndef added_here():\n    return 1\n",
        encoding="utf-8",
    )
    (repository / "new.py").write_text(
        "def added_file():\n    return 2\n", encoding="utf-8"
    )
    working = {symbol["id"]: symbol for symbol in changed_symbols(repository, base)}
    assert working["core.py::existing"].get("change_type") is None
    assert working["core.py::added_here"]["change_type"] == "added"
    assert working["new.py::added_file"]["change_type"] == "added"

    run_git(repository, "add", ".")
    run_git(repository, "commit", "-m", "add functions")
    target = run_git(repository, "rev-parse", "HEAD").stdout.strip()
    committed = {symbol["id"]: symbol for symbol in changed_symbols(repository, base, target)}
    assert {name: symbol.get("change_type") for name, symbol in committed.items()} == {
        "core.py::existing": None,
        "core.py::added_here": "added",
        "new.py::added_file": "added",
    }


def test_renamed_file_preserves_old_function_and_marks_new_one_added(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    run_git(repository, "init")
    run_git(repository, "config", "user.email", "impactlens@example.com")
    run_git(repository, "config", "user.name", "ImpactLens Tests")
    old_source = (
        "def existing():\n"
        + "".join(f"    value_{index} = {index}\n" for index in range(12))
        + "    return value_11\n"
    )
    (repository / "old.py").write_text(old_source, encoding="utf-8")
    run_git(repository, "add", ".")
    run_git(repository, "commit", "-m", "base")
    base = run_git(repository, "rev-parse", "HEAD").stdout.strip()

    (repository / "old.py").rename(repository / "renamed.py")
    (repository / "renamed.py").write_text(
        old_source + "\ndef fresh():\n    return 2\n", encoding="utf-8"
    )
    working = {symbol["id"]: symbol for symbol in changed_symbols(repository, base)}
    assert working["renamed.py::existing"]["change_type"] == "renamed"
    assert working["renamed.py::fresh"]["change_type"] == "added"
    assert "previous_id" not in working["renamed.py::fresh"]

    run_git(repository, "add", "-A")
    run_git(repository, "commit", "-m", "rename and add")
    target = run_git(repository, "rev-parse", "HEAD").stdout.strip()
    committed = {symbol["id"]: symbol for symbol in changed_symbols(repository, base, target)}
    assert committed["renamed.py::existing"]["change_type"] == "renamed"
    assert committed["renamed.py::fresh"]["change_type"] == "added"
