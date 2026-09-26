import subprocess

import pytest

import repository_loader
from request_budget import RequestDeadlineExceeded, request_deadline
from repository_loader import (
    RepositoryLoadError,
    RepositoryTimeoutError,
    is_github_url,
    normalize_github_url,
    open_repository,
)


@pytest.mark.parametrize(
    ("url", "normalized"),
    [
        (
            "https://github.com/jasonorjasor/ImpactLens",
            "https://github.com/jasonorjasor/ImpactLens.git",
        ),
        (
            "https://github.com/owner/repository.git/",
            "https://github.com/owner/repository.git",
        ),
    ],
)
def test_normalizes_public_github_urls(url, normalized):
    assert normalize_github_url(url) == normalized
    assert is_github_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repository",
        "https://gitlab.com/owner/repository",
        "https://github.com/owner/repository/issues",
        "https://user:password@github.com/owner/repository",
        "https://github.com/owner/repository?download=1",
    ],
)
def test_rejects_unsupported_github_urls(url):
    with pytest.raises(RepositoryLoadError):
        normalize_github_url(url)


def test_local_repository_paths_are_not_cloned(tmp_path):
    with open_repository(tmp_path) as repository:
        assert repository == tmp_path.resolve()


def test_working_tree_mode_requires_a_local_repository():
    with pytest.raises(RepositoryLoadError, match="local repository path"):
        with open_repository(
            "https://github.com/owner/repository",
            "HEAD",
        ):
            pass


def test_clone_failure_has_a_user_facing_message(monkeypatch):
    def fail_clone(arguments):
        cause = subprocess.CalledProcessError(
            128, arguments, stderr="fatal: C:/Temp/impactlens-random/repository is unavailable"
        )
        raise RepositoryLoadError(cause.stderr) from cause

    monkeypatch.setattr(repository_loader, "_run_command", fail_clone)

    with pytest.raises(RepositoryLoadError, match="Could not access this public GitHub repository") as error:
        with open_repository("https://github.com/owner/repository", "base", "target"):
            pass
    assert "C:/Temp" not in str(error.value)


def test_fetch_failure_identifies_the_commit_without_git_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(repository_loader, "_commit_exists", lambda *_: False)

    def fail_fetch(arguments):
        cause = subprocess.CalledProcessError(
            128, arguments, stderr="fatal: couldn't find remote ref missing"
        )
        raise RepositoryLoadError(cause.stderr) from cause

    monkeypatch.setattr(repository_loader, "_run_command", fail_fetch)

    with pytest.raises(RepositoryLoadError, match="Could not find or fetch commit 'missing'") as error:
        repository_loader._ensure_commit(tmp_path, "missing")
    assert "fatal:" not in str(error.value)


def test_fetch_timeout_keeps_its_specific_message(monkeypatch, tmp_path):
    monkeypatch.setattr(repository_loader, "_commit_exists", lambda *_: False)

    def timeout(_):
        raise RepositoryTimeoutError("Git operation timed out") from subprocess.TimeoutExpired("git", 120)

    monkeypatch.setattr(repository_loader, "_run_command", timeout)

    with pytest.raises(RepositoryLoadError, match="Git operation timed out"):
        repository_loader._ensure_commit(tmp_path, "missing")


@pytest.mark.parametrize("failure", [
    RepositoryTimeoutError("Git operation timed out"),
    RepositoryLoadError("Repository is too large"),
    RepositoryLoadError("Git is required"),
    RequestDeadlineExceeded("request deadline"),
])
def test_commit_check_failure_does_not_attempt_fetch(monkeypatch, tmp_path, failure):
    commands = []

    def fail(arguments):
        commands.append(arguments)
        raise failure

    monkeypatch.setattr(repository_loader, "_run_command", fail)
    with pytest.raises(type(failure)) as raised:
        repository_loader._ensure_commit(tmp_path, "commit")
    assert raised.value is failure
    assert len(commands) == 1
    assert "fetch" not in commands[0]


def test_missing_commit_is_fetched_then_verified(monkeypatch, tmp_path):
    commands = []

    def run(arguments):
        commands.append(arguments)
        if len(commands) == 1:
            cause = subprocess.CalledProcessError(1, arguments, stderr="")
            raise RepositoryLoadError("Git operation failed") from cause
        return "commit"

    monkeypatch.setattr(repository_loader, "_run_command", run)
    repository_loader._ensure_commit(tmp_path, "commit")
    assert [command[3] for command in commands] == ["rev-parse", "fetch", "rev-parse"]


def test_git_operational_error_is_not_a_missing_commit(monkeypatch, tmp_path):
    def fail(arguments):
        cause = subprocess.CalledProcessError(128, arguments, stderr="not a repository")
        raise RepositoryLoadError(cause.stderr) from cause

    monkeypatch.setattr(repository_loader, "_run_command", fail)
    with pytest.raises(RepositoryLoadError, match="not a repository"):
        repository_loader._commit_exists(tmp_path, "commit")


def test_rejects_oversized_clone_before_fetch(monkeypatch):
    commands = []
    monkeypatch.setattr(repository_loader, "_run_command", lambda arguments: commands.append(arguments))
    monkeypatch.setattr(
        repository_loader,
        "repository_size_bytes",
        lambda _: repository_loader.MAX_REPOSITORY_BYTES + 1,
    )

    with pytest.raises(RepositoryLoadError, match="Repository is too large"):
        with open_repository("https://github.com/owner/repository", "base", "target"):
            pass

    assert not any("fetch" in command for command in commands)


def test_rejects_repository_after_first_commit_fetch(monkeypatch):
    commands = []
    fetched = set()

    def run(arguments):
        commands.append(arguments)
        if "fetch" in arguments:
            fetched.add(arguments[-1])

    monkeypatch.setattr(repository_loader, "_run_command", run)
    monkeypatch.setattr(repository_loader, "_commit_exists", lambda _, commit: commit in fetched)
    monkeypatch.setattr(
        repository_loader,
        "repository_size_bytes",
        lambda _: repository_loader.MAX_REPOSITORY_BYTES + 1 if fetched else 0,
    )

    with pytest.raises(RepositoryLoadError, match="Repository is too large"):
        with open_repository("https://github.com/owner/repository", "base", "target"):
            pass

    assert [command[-1] for command in commands if "fetch" in command] == ["base"]


def test_rejects_repository_that_grows_during_analysis(monkeypatch):
    sizes = iter([0, 0, 0, repository_loader.MAX_REPOSITORY_BYTES + 1])
    monkeypatch.setattr(repository_loader, "_run_command", lambda arguments: None)
    monkeypatch.setattr(repository_loader, "_commit_exists", lambda *_: True)
    monkeypatch.setattr(repository_loader, "repository_size_bytes", lambda _: next(sizes))

    with pytest.raises(RepositoryLoadError, match="Repository is too large"):
        with open_repository("https://github.com/owner/repository", "base", "target"):
            pass


def test_git_command_uses_remaining_request_time(monkeypatch):
    seen = []

    def fake_run(*args, **kwargs):
        seen.append(kwargs["timeout"])
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(repository_loader.subprocess, "run", fake_run)
    with request_deadline(1):
        repository_loader._execute_command(["git", "version"])

    assert len(seen) == 1
    assert 0 < seen[0] <= 1
