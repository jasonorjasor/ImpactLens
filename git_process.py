"""Run Git while watching the disk used by a temporary public checkout."""

import subprocess
import threading
from contextlib import contextmanager
from contextvars import ContextVar

import psutil


_repository_guard = ContextVar("impactlens_repository_guard", default=None)
POLL_SECONDS = 0.1


class GitDiskLimitExceeded(RuntimeError):
    pass


@contextmanager
def guard_repository(repository, max_bytes, size_function):
    token = _repository_guard.set((repository, max_bytes, size_function))
    try:
        yield
    finally:
        _repository_guard.reset(token)


def _stop_process_tree(process):
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []
    for child in reversed(descendants):
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def run_git_command(arguments, *, timeout, text=False, input_data=None):
    guard = _repository_guard.get()
    if guard is None:
        return subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=text,
            input=input_data,
            timeout=timeout,
        )

    repository, max_bytes, size_function = guard
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.PIPE if input_data is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    finished = threading.Event()
    exceeded = []
    watch_errors = []

    def watch_size():
        while not finished.wait(POLL_SECONDS):
            try:
                size = size_function(repository)
            except Exception as error:
                watch_errors.append(error)
                _stop_process_tree(process)
                return
            if size > max_bytes:
                exceeded.append(size)
                _stop_process_tree(process)
                return

    watcher = threading.Thread(target=watch_size, daemon=True)
    watcher.start()
    try:
        stdout, stderr = process.communicate(input=input_data, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process_tree(process)
        process.communicate()
        raise
    finally:
        finished.set()
        watcher.join()

    if exceeded:
        raise GitDiskLimitExceeded(
            f"Repository is too large: {exceeded[0]} bytes exceeds the {max_bytes}-byte limit"
        )
    if watch_errors:
        raise watch_errors[0]
    result = subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
    result.check_returncode()
    return result
