import pytest

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
