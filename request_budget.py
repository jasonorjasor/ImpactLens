"""Share an API request deadline across repository loading and analysis."""

from contextlib import contextmanager
from contextvars import ContextVar
import time


_current_deadline = ContextVar("impactlens_request_deadline", default=None)


class RequestDeadlineExceeded(RuntimeError):
    pass


@contextmanager
def request_deadline(seconds):
    token = _current_deadline.set((time.monotonic() + seconds, seconds))
    try:
        yield
    finally:
        _current_deadline.reset(token)


def check_deadline():
    limit = _current_deadline.get()
    if limit is not None and time.monotonic() >= limit[0]:
        raise RequestDeadlineExceeded(
            f"Analysis request exceeded the {limit[1]}-second deadline"
        )


def command_timeout(default_seconds):
    check_deadline()
    limit = _current_deadline.get()
    if limit is None:
        return default_seconds
    return min(default_seconds, max(0.001, limit[0] - time.monotonic()))
