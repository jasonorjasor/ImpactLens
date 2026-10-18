"""Git read failures must not become empty reports or unreadable HTTP errors."""

from pathlib import Path
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

import api
import cli
import git_analyzer
import repository_loader
from request_budget import RequestDeadlineExceeded


@pytest.fixture
def comparison(tmp_path):
    repository = tmp_path / "source"
    repository.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    git("init")
    git("config", "user.email", "impactlens@example.com")
    git("config", "user.name", "ImpactLens Tests")
    (repository / "core.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (repository / "caller.py").write_text(
        "from core import value\n\ndef use_value():\n    return value()\n", encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repository / "core.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "change")
    return repository, base, git("rev-parse", "HEAD")


@pytest.mark.parametrize("stderr", [
    b"fatal: cannot read C:/private/checkout\n\xff\x1b[31m diagnostic\x00",
    None,
    "fatal: cannot read C:/private/checkout\r\n" + "x" * 5000,
])
def test_api_git_failure_is_readable_cleans_up_and_allows_recovery(
    monkeypatch, comparison, caplog, stderr,
):
    repository, base, target = comparison
    clones = []
    original_command = repository_loader._run_command
    original_read = git_analyzer.run_git_command
    failed = False

    def clone_local(arguments):
        if arguments[1] == "clone":
            clones.append(Path(arguments[-1]))
            arguments = [*arguments[:-2], str(repository), arguments[-1]]
        return original_command(arguments)

    def fail_one_batch(arguments, **options):
        nonlocal failed
        if arguments[3] == "cat-file" and not failed:
            failed = True
            raise subprocess.CalledProcessError(128, arguments, stderr=stderr)
        return original_read(arguments, **options)

    monkeypatch.setattr(repository_loader, "_run_command", clone_local)
    monkeypatch.setattr(git_analyzer, "run_git_command", fail_one_batch)
    monkeypatch.setattr(api, "analysis_slots", threading.BoundedSemaphore(1))
    client = TestClient(api.app, raise_server_exceptions=False)
    payload = {
        "repository": "https://github.com/owner/repository",
        "base_commit": base, "target_commit": target,
    }
    response = client.post("/analyze", json=payload)
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "detail": "Git could not read the repository during analysis. "
                  "Try again. If it keeps failing, report the problem.",
    }
    assert "private" not in response.text
    assert "fatal:" not in response.text
    assert len(clones) == 1
    assert not clones[0].parent.exists()
    records = [record for record in caplog.records if record.name == "api"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "operation=cat-file" in message
    assert "exit_code=128" in message
    assert "stderr=" in message
    assert len(message) < 2200
    assert not any(character in message for character in "\r\n\x00\x1b")

    recovered = client.post("/analyze", json=payload)
    assert recovered.status_code == 200
    assert recovered.json()["evidence_paths"] == [{
        "source": "target", "symbols": ["core.py::value", "caller.py::use_value"],
    }]
    assert len(clones) == 2
    assert all(not path.parent.exists() for path in clones)


@pytest.mark.parametrize("version", ["base", "target"])
def test_changed_file_read_failure_is_not_treated_as_absent(monkeypatch, comparison, version):
    repository, base, target = comparison
    original_read = git_analyzer.run_git_command
    commit = base if version == "base" else target

    def fail_show(arguments, **options):
        if arguments[3:] == ["show", f"{commit}:core.py"]:
            raise subprocess.CalledProcessError(128, arguments, stderr=b"fatal: read failed")
        return original_read(arguments, **options)

    monkeypatch.setattr(git_analyzer, "run_git_command", fail_show)
    with pytest.raises(git_analyzer.AnalysisGitError):
        git_analyzer.changed_symbols(repository, base, target)


def test_rename_read_failure_is_not_skipped(monkeypatch, comparison):
    repository, base, _ = comparison
    (repository / "core.py").rename(repository / "renamed.py")
    original_read = git_analyzer.run_git_command

    def fail_show(arguments, **options):
        if arguments[3:] == ["show", f"{base}:core.py"]:
            raise subprocess.CalledProcessError(128, arguments, stderr=b"fatal: read failed")
        return original_read(arguments, **options)

    monkeypatch.setattr(git_analyzer, "run_git_command", fail_show)
    with pytest.raises(git_analyzer.AnalysisGitError):
        git_analyzer.changed_symbols(repository, base)


def test_missing_git_has_a_specific_message(monkeypatch, tmp_path):
    def missing(*args, **options):
        raise FileNotFoundError("git executable missing")

    monkeypatch.setattr(git_analyzer, "run_git_command", missing)
    with pytest.raises(git_analyzer.AnalysisGitError, match="Git is required"):
        git_analyzer.run_git(tmp_path, "ls-tree", "HEAD")


def test_deadline_takes_precedence_over_a_git_failure(monkeypatch, tmp_path):
    def failed(arguments, **options):
        raise subprocess.CalledProcessError(128, arguments)

    def expired():
        raise RequestDeadlineExceeded("deadline expired")

    monkeypatch.setattr(git_analyzer, "run_git_command", failed)
    monkeypatch.setattr(git_analyzer, "check_deadline", expired)
    with pytest.raises(RequestDeadlineExceeded):
        git_analyzer.run_git(tmp_path, "cat-file", "--batch")


def test_cli_git_failure_does_not_print_a_report_or_traceback(monkeypatch, comparison, capsys):
    repository, base, target = comparison
    original_read = git_analyzer.run_git_command

    def fail_batch(arguments, **options):
        if arguments[3] == "cat-file":
            raise subprocess.CalledProcessError(128, arguments, stderr=b"fatal: private path")
        return original_read(arguments, **options)

    monkeypatch.setattr(git_analyzer, "run_git_command", fail_batch)
    with pytest.raises(SystemExit) as raised:
        cli.main([str(repository), base, target, "--json"])
    assert raised.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Git could not read the repository" in output.err
    assert "fatal:" not in output.err
    assert "Traceback" not in output.err
