"""Tests for the ImpactLens reverse-call traversal."""

import random

import pytest

from analyzer import build_reverse_graph, find_affected_functions, find_impact_paths
from request_budget import AnalysisLimitExceeded, RequestDeadlineExceeded, TraversalBudget, request_deadline


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


def test_repeated_source_calls_are_one_graph_connection_in_first_seen_order():
    calls = [{"caller": "middle", "callee": "root"}] * 30 + [{"caller": "outer", "callee": "middle"}] * 30
    graph = build_reverse_graph(calls)
    assert graph == {"root": ["middle"], "middle": ["outer"]}
    assert find_impact_paths("root", graph) == [["root", "middle", "outer"]]
    assert len(calls) == 60


def test_preserves_depth_first_order_reconvergence_and_cycle_closures():
    graph = {"root": ["left", "right"], "left": ["shared", "leaf"], "right": ["shared"], "shared": ["root"]}
    assert find_impact_paths("root", graph) == [
        ["root", "left", "shared", "root (cycle)"],
        ["root", "left", "leaf"],
        ["root", "right", "shared", "root (cycle)"],
    ]


def test_iterative_walk_can_handle_a_deep_chain_and_default_limit_is_readable():
    graph = {str(index): [str(index + 1)] for index in range(1200)}
    assert find_impact_paths("0", graph, TraversalBudget(max_depth=1300)) == [[str(index) for index in range(1201)]]
    with pytest.raises(AnalysisLimitExceeded, match="No complete report was produced") as caught:
        find_impact_paths("0", graph)
    assert caught.value.resource == "steps in a single path"
    assert caught.value.limit == 512


@pytest.mark.parametrize("limits, resource", [
    ({"max_steps": 3}, "tracing steps"),
    ({"max_paths": 1}, "connection paths"),
    ({"max_depth": 2}, "steps in a single path"),
    ({"max_path_symbols": 5}, "stored path steps"),
])
def test_each_budget_stops_before_returning_a_partial_result(limits, resource):
    budget = TraversalBudget(**limits)
    graph = {"root": ["middle"], "middle": ["first", "second"]}
    with pytest.raises(AnalysisLimitExceeded) as caught:
        find_impact_paths("root", graph, budget)
    assert caught.value.resource == resource
    assert budget.steps <= budget.max_steps
    assert budget.paths <= budget.max_paths
    assert budget.path_symbols <= budget.max_path_symbols


def test_exact_boundaries_succeed_and_cycle_markers_count_toward_path_length():
    budget = TraversalBudget(max_steps=4, max_paths=2, max_depth=3, max_path_symbols=6)
    assert find_impact_paths("root", {"root": ["middle"], "middle": ["first", "second"]}, budget) == [
        ["root", "middle", "first"], ["root", "middle", "second"],
    ]
    with pytest.raises(AnalysisLimitExceeded, match="steps in a single path"):
        find_impact_paths("root", {"root": ["middle"], "middle": ["root"]}, TraversalBudget(max_depth=2))


def test_shared_budget_covers_multiple_changed_roots_and_a_new_analysis_starts_fresh():
    graph = {"one": ["caller"], "two": ["other"]}
    budget = TraversalBudget(max_paths=1)
    assert find_impact_paths("one", graph, budget) == [["one", "caller"]]
    with pytest.raises(AnalysisLimitExceeded, match="connection paths"):
        find_impact_paths("two", graph, budget)
    assert find_impact_paths("two", graph, TraversalBudget(max_paths=1)) == [["two", "other"]]


def test_no_caller_root_does_not_spend_a_reported_path_slot_and_deadlines_still_apply():
    budget = TraversalBudget(max_paths=1)
    assert find_impact_paths("alone", {}, budget) == [["alone"]]
    assert budget.paths == budget.path_symbols == 0
    with request_deadline(0), pytest.raises(RequestDeadlineExceeded):
        find_impact_paths("alone", {}, budget)


def test_reconverging_graph_stops_at_the_default_output_budget():
    graph = {"root": ["a0", "b0"]}
    for index in range(13):
        for letter in ("a", "b"):
            graph[f"{letter}{index}"] = [f"a{index + 1}", f"b{index + 1}"]
    budget = TraversalBudget()
    with pytest.raises(AnalysisLimitExceeded, match="connection paths"):
        find_impact_paths("root", graph, budget)
    assert budget.paths == 2000


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_budget_configuration_requires_positive_integers(limit):
    with pytest.raises(ValueError, match="positive integers"):
        TraversalBudget(max_steps=limit)


def test_small_graphs_match_an_independent_recursive_reference():
    def reference(node, graph, path):
        callers = graph.get(node, [])
        if not callers:
            return [path]
        result = []
        for caller in callers:
            result.extend([path + [f"{caller} (cycle)"]] if caller in path
                          else reference(caller, graph, path + [caller]))
        return result

    rng = random.Random(20261103)
    for _ in range(60):
        graph = {node: [caller for caller in range(5) if rng.random() < 0.35] for node in range(5)}
        assert find_impact_paths(0, graph) == reference(0, graph, [0])


def test_wide_neighbor_iterator_is_not_materialized_before_the_limit():
    inspected = []

    def neighbors():
        for index in range(1_000_000):
            inspected.append(index)
            yield str(index)

    with pytest.raises(AnalysisLimitExceeded, match="connection paths"):
        find_impact_paths("root", {"root": neighbors()}, TraversalBudget(max_paths=2))
    assert inspected == [0, 1, 2]
