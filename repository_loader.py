import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


MAX_REPOSITORY_BYTES = 100 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 120
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class RepositoryLoadError(RuntimeError):
    pass


def normalize_github_url(value):
    parsed = urlparse(str(value))
    if parsed.scheme.lower() != "https" or parsed.netloc.lower() != "github.com":
        raise RepositoryLoadError("Only public HTTPS GitHub URLs are supported")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise RepositoryLoadError("GitHub URLs cannot include credentials or parameters")

    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise RepositoryLoadError("GitHub URL must have the form owner/repository")

    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        raise RepositoryLoadError("GitHub URL must include an owner and repository")
    if not NAME_PATTERN.fullmatch(owner) or not NAME_PATTERN.fullmatch(repository):
        raise RepositoryLoadError("GitHub URL contains an invalid owner or repository")

    return f"https://github.com/{owner}/{repository}.git"


def is_github_url(value):
    parsed = urlparse(str(value))
    return bool(parsed.scheme and parsed.netloc) and parsed.scheme.lower() == "https" and parsed.netloc.lower() == "github.com"


def _execute_command(arguments):
    try:
        result = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise RepositoryLoadError("Git is required to load a repository") from error
    except subprocess.TimeoutExpired as error:
        raise RepositoryLoadError("Git operation timed out") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "Git operation failed"
        raise RepositoryLoadError(message) from error
    return result.stdout


def _run_command(arguments):
    try:
        return _execute_command(arguments)
    except RepositoryLoadError as error:
        is_network_operation = "clone" in arguments or "fetch" in arguments
        if is_network_operation and "schannel" in str(error).lower():
            return _execute_command(
                ["git", "-c", "http.sslBackend=openssl", *arguments[1:]]
            )
        raise


def _commit_exists(repository, commit):
    if not commit or commit.startswith("-"):
        return False
    try:
        _run_command(
            [
                "git",
                "-C",
                str(repository),
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{commit}^{{commit}}",
            ]
        )
    except RepositoryLoadError:
        return False
    return True


def _ensure_commit(repository, commit):
    if _commit_exists(repository, commit):
        return
    if not commit or commit.startswith("-"):
        raise RepositoryLoadError(f"Invalid commit reference: {commit}")
    _run_command(
        [
            "git",
            "-C",
            str(repository),
            "fetch",
            "--no-tags",
            "origin",
            commit,
        ]
    )
    if not _commit_exists(repository, commit):
        raise RepositoryLoadError(f"Commit not found: {commit}")


def repository_size_bytes(repository):
    total = 0
    for path in Path(repository).rglob("*"):
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


@contextmanager
def open_repository(location, base_commit=None, target_commit=None, max_bytes=MAX_REPOSITORY_BYTES):
    location = str(location)
    parsed = urlparse(location)
    is_url = bool(parsed.scheme and parsed.netloc)

    if not is_url:
        yield Path(location).resolve()
        return

    repository_url = normalize_github_url(location)
    if target_commit is None:
        raise RepositoryLoadError("Working-tree mode requires a local repository path")

    with tempfile.TemporaryDirectory(prefix="impactlens-") as temporary_directory:
        repository = Path(temporary_directory) / "repository"
        _run_command(
            [
                "git",
                "clone",
                "--no-tags",
                "--filter=blob:none",
                repository_url,
                str(repository),
            ]
        )
        _run_command(
            [
                "git",
                "-C",
                str(repository),
                "config",
                "http.sslBackend",
                "openssl",
            ]
        )
        _ensure_commit(repository, base_commit)
        _ensure_commit(repository, target_commit)

        size = repository_size_bytes(repository)
        if size > max_bytes:
            raise RepositoryLoadError(
                f"Repository is too large: {size} bytes exceeds the {max_bytes}-byte limit"
            )

        yield repository
