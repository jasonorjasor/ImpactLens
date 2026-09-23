"""Tests for the ImpactLens AST extraction."""

import pytest

from analyzer import analyze_sources, extract_calls, extract_functions, extract_symbols
from request_budget import RequestDeadlineExceeded, request_deadline


def test_analysis_stops_at_a_file_boundary_when_request_time_expires():
    with request_deadline(0):
        with pytest.raises(RequestDeadlineExceeded):
            analyze_sources({"example.py": b"def work():\n    return 1\n"})


def test_extracts_function_names_and_line_ranges():
    source = """
def greet(name):
    return name

def add(a, b):
    return a + b
"""

    result = extract_functions(source)

    assert result == [
        {"kind": "function", "name": "greet", "qualname": "greet", "line_start": 2, "line_end": 3},
        {"kind": "function", "name": "add", "qualname": "add", "line_start": 5, "line_end": 6},
    ]


def test_extracts_caller_and_callee():
    source = """
def login():
    return verify_user()
"""

    result = extract_calls(source)

    assert result == [
        {"caller": "login", "callee": "verify_user", "line": 3}
    ]


def test_tracks_class_methods_and_self_calls():
    source = """
class User:
    def login(self):
        return self.verify_user()

    def verify_user(self):
        return True
"""

    symbols = extract_symbols(source)
    calls = extract_calls(source)

    assert [symbol["qualname"] for symbol in symbols] == [
        "User",
        "User.login",
        "User.verify_user",
    ]
    assert calls == [
        {"caller": "User.login", "callee": "User.verify_user", "line": 4}
    ]
