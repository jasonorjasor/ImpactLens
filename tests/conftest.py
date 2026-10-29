"""Shared real-Git comparison fixture."""

import subprocess

import pytest


@pytest.fixture
def comparison(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()

    def git(*arguments):
        return subprocess.run(
            ["git", "-C", str(repository), *arguments], check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    git("init")
    git("config", "user.email", "impactlens@example.com")
    git("config", "user.name", "ImpactLens Tests")
    git("config", "commit.gpgsign", "false")

    def commit(sources):
        for path, source in sources.items():
            destination = repository / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source, encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "fixture")
        return git("rev-parse", "HEAD")

    return repository, commit
