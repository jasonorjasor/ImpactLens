"""Tests for the ImpactLens reverse-call traversal."""

from analyzer import find_affected_functions, find_impact_paths


def test_finds_direct_caller():
    graph = {
        "verify_user": ["login"],
    }

    result = find_affected_functions("verify_user", graph)

    assert result == ["login"]


def test_finds_recursive_callers():
    graph = {
        "verify_user": ["login"],
        "login": ["login_route"],
    }

    result = find_impact_paths("verify_user", graph)

    assert result == [["verify_user", "login", "login_route"]]


def test_ignores_unrelated_functions():
    graph = {
        "verify_user": ["login"],
        "unrelated_function": ["unrelated_route"],
    }

    result = find_affected_functions("verify_user", graph)

    assert result == ["login"]


def test_handles_circular_dependencies():
    graph = {
        "function_a": ["function_b"],
        "function_b": ["function_a"],
    }

    result = find_impact_paths("function_a", graph)

    assert result == [["function_a", "function_b", "function_a (cycle)"]]
