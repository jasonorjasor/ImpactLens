import subprocess

import pytest

import repository_loader
from repository_loader import (
    RepositoryLoadError,
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
        raise RepositoryLoadError("Git operation timed out") from subprocess.TimeoutExpired("git", 120)

    monkeypatch.setattr(repository_loader, "_run_command", timeout)

    with pytest.raises(RepositoryLoadError, match="Git operation timed out"):
        repository_loader._ensure_commit(tmp_path, "missing")
