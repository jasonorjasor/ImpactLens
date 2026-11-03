"""Share an API request deadline across repository loading and analysis."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time


_current_deadline = ContextVar("impactlens_request_deadline", default=None)


class RequestDeadlineExceeded(RuntimeError):
    pass


class AnalysisLimitExceeded(RuntimeError):
    def __init__(self, resource, limit):
        self.resource = resource
        self.limit = limit
        super().__init__(
            f"Connection tracing exceeded its {resource} limit ({limit}). "
            "No complete report was produced. Review the diff manually or choose a smaller comparison."
        )


@dataclass
class TraversalBudget:
    max_steps: int = 50_000
    max_paths: int = 2_000
    max_depth: int = 512
    max_path_symbols: int = 100_000
    steps: int = field(default=0, init=False)
    paths: int = field(default=0, init=False)
    path_symbols: int = field(default=0, init=False)

    def __post_init__(self):
        limits = (self.max_steps, self.max_paths, self.max_depth, self.max_path_symbols)
        if any(type(limit) is not int or limit < 1 for limit in limits):
            raise ValueError("Traversal limits must be positive integers")

    def consume_step(self):
        if self.steps >= self.max_steps:
            raise AnalysisLimitExceeded("tracing steps", self.max_steps)
        self.steps += 1

    def check_depth(self, length):
        if length > self.max_depth:
            raise AnalysisLimitExceeded("steps in a single path", self.max_depth)

    def record_path(self, length):
        if self.paths >= self.max_paths:
            raise AnalysisLimitExceeded("connection paths", self.max_paths)
        if self.path_symbols + length > self.max_path_symbols:
            raise AnalysisLimitExceeded("stored path steps", self.max_path_symbols)
        self.paths += 1
        self.path_symbols += length


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
