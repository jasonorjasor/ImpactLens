import subprocess
import sys
import time

import psutil
import pytest

from git_process import GitDiskLimitExceeded, guard_repository, run_git_command
from repository_loader import repository_size_bytes


def test_active_disk_limit_stops_git_descendants(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    child_pid_file = tmp_path / "child-pid"
    writer = (
        "import pathlib, sys, time; "
        "path = pathlib.Path(sys.argv[1]); "
        "file = path.open('wb'); "
        "[(file.write(b'x' * 1024), file.flush(), time.sleep(0.03)) for _ in range(1000)]"
    )
    parent = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', sys.argv[3], sys.argv[1]]); "
        "pathlib.Path(sys.argv[2]).write_text(str(child.pid)); "
        "time.sleep(30)"
    )

    with guard_repository(repository, 4 * 1024, repository_size_bytes):
        with pytest.raises(GitDiskLimitExceeded, match="Repository is too large"):
            run_git_command(
                [sys.executable, "-c", parent, str(repository / "growth"), str(child_pid_file), writer],
                timeout=5,
            )

    child_pid = int(child_pid_file.read_text())
    for _ in range(20):
        if not psutil.pid_exists(child_pid):
            break
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pid)
    assert repository_size_bytes(repository) > 4 * 1024


def test_guard_does_not_change_local_commands(monkeypatch, tmp_path):
    observed = []

    def fake_run(*args, **kwargs):
        observed.append(kwargs["timeout"])
        return subprocess.CompletedProcess(args[0], 0, b"ok", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_git_command(["git", "version"], timeout=3)

    assert observed == [3]
    assert result.stdout == b"ok"


def test_guarded_timeout_stops_child_process(tmp_path):
    child_pid_file = tmp_path / "child-pid"
    parent = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); "
        "time.sleep(30)"
    )

    with guard_repository(tmp_path, 1000, repository_size_bytes):
        with pytest.raises(subprocess.TimeoutExpired):
            run_git_command(
                [sys.executable, "-c", parent, str(child_pid_file)],
                timeout=0.5,
            )

    child_pid = int(child_pid_file.read_text())
    for _ in range(20):
        if not psutil.pid_exists(child_pid):
            break
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pid)
