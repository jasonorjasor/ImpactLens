import pytest

import git_analyzer
from cli import format_report


@pytest.mark.parametrize("deleted", [False, True])
def test_source_evidence_preserves_repeated_import_calls_and_snapshot(comparison, deleted):
    repository, commit = comparison
    caller = "from service import calculate as compute\n\ndef run():\n    return compute() + compute()\n"
    base = commit({"service.py": "def calculate():\n    return 1\n", "caller.py": caller})
    target = commit({"service.py": "" if deleted else "def calculate():\n    return 2\n"})
    report = git_analyzer.analyze_change(repository, base, target)
    source = "base" if deleted else "target"
    assert report["resolved_commits"] == {"base": base, "target": target}
    assert report["schema_version"] == 3
    sites = report["call_sites"]
    assert len(sites) == 2
    assert {site["column"] for site in sites} == {11, 23}
    for site in sites:
        assert site["source"] == source
        assert site["caller_id"] == "caller.py::run"
        assert site["callee_id"] == "service.py::calculate"
        assert site["resolution"] == "import"
        assert site["expression"] == "compute"
        assert site["line"] == site["line_end"] == 4
        assert site["code"] == caller.splitlines()[3].strip()
    assert {item["id"] for item in report["symbol_locations"]} == {"caller.py::run", "service.py::calculate"}
    assert all(item["source"] == source for item in report["symbol_locations"])
    assert "caller.py:4" in format_report(report)
    assert (base if deleted else target) in format_report(report)


def test_unresolved_calls_do_not_gain_invented_source_evidence(comparison):
    repository, commit = comparison
    base = commit({"service.py": "def calculate():\n    return 1\n", "caller.py": "import service\n\ndef run():\n    return getattr(service, 'calculate')()\n"})
    target = commit({"service.py": "def calculate():\n    return 2\n"})
    report = git_analyzer.analyze_change(repository, base, target)
    assert report["evidence_paths"] == report["call_sites"] == []
    assert [item["id"] for item in report["symbol_locations"]] == ["service.py::calculate"]


def test_class_attribute_change_is_outside_function_detection(comparison):
    repository, commit = comparison
    base = commit({"settings.py": "class Settings:\n    timeout = 10\n"})
    target = commit({"settings.py": "class Settings:\n    timeout = 20\n"})
    report = git_analyzer.analyze_change(repository, base, target)
    assert report["changed_symbols"] == report["evidence_paths"] == report["call_sites"] == []
    assert report["analysis_errors"] == []


def test_duplicate_definitions_keep_all_locations_without_inventing_call_sites(comparison):
    repository, commit = comparison
    source = "def work():\n    return 1\n\ndef work():\n    return 2\n\ndef run():\n    return work()\n"
    base = commit({"service.py": source})
    target = commit({"service.py": source.replace("return 2", "return 3")})
    report = git_analyzer.analyze_change(repository, base, target)
    assert report["call_sites"] == []
    assert [item["line_start"] for item in report["symbol_locations"]] == [1, 4]


def test_working_tree_evidence_never_claims_a_target_commit(comparison):
    repository, commit = comparison
    base = commit({"service.py": "def calculate():\n    return 1\n\ndef run():\n    return calculate()\n"})
    (repository / "service.py").write_text("def calculate():\n    return 2\n\ndef run():\n    return calculate()\n", encoding="utf-8")
    report = git_analyzer.analyze_working_tree(repository)
    assert report["resolved_commits"] == {"base": base, "target": None}
    assert report["call_sites"][0]["resolution"] == "local"
    assert "WORKING_TREE" in format_report(report)


def test_commit_labels_are_frozen_before_analysis(comparison, monkeypatch):
    repository, commit = comparison
    base = commit({"service.py": "def calculate():\n    return 1\n"})
    target = commit({"service.py": "def calculate():\n    return 2\n"})
    original = git_analyzer.changed_symbols

    def move_head(*args):
        commit({"service.py": "def unrelated():\n    return 3\n"})
        return original(*args)

    monkeypatch.setattr(git_analyzer, "changed_symbols", move_head)
    report = git_analyzer.analyze_change(repository, "HEAD~1", "HEAD")
    assert report["resolved_commits"] == {"base": base, "target": target}
    assert [symbol["id"] for symbol in report["changed_symbols"]] == ["service.py::calculate"]
    assert report["changed_symbols"][0].get("change_type") != "deleted"


def test_multiline_and_cycle_call_sites_keep_their_original_locations(comparison):
    repository, commit = comparison
    before = "def first():\n    return second(\n    )\n\ndef second():\n    return first()\n"
    base = commit({"cycle.py": before})
    target = commit({"cycle.py": before.replace("return second(", "return 1 + second(")})
    report = git_analyzer.analyze_change(repository, base, target)
    assert len(report["call_sites"]) == 2
    multiline = next(site for site in report["call_sites"] if site["caller_id"] == "cycle.py::first")
    assert (multiline["line"], multiline["line_end"]) == (2, 3)
    assert report["evidence_paths"][0]["symbols"][-1].endswith(" (cycle)")
