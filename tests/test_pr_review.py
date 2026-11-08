import copy
import json
from contextlib import contextmanager

import pytest

from benchmarks.pr_review import check_report, load_cases, main
from git_analyzer import analyze_change


@pytest.fixture
def reviewed_report(comparison):
    repository, commit = comparison
    base = commit({
        "service.py": "def value():\n    return 1\n",
        "tests/test_value.py": "from service import value\ndef test_value():\n    assert value() == 1\n",
    })
    head = commit({"service.py": "def value():\n    return 2\n"})
    report = analyze_change(repository, base, head)
    case = {
        "base": base, "head": head,
        "expected": {
            "changed": ["service.py::value"],
            "direct_connections": [["service.py::value", "tests/test_value.py::test_value"]],
            "related_tests": ["tests/test_value.py::test_value"],
        },
    }
    return case, report


def test_required_findings_need_correct_snapshot_and_current_evidence(reviewed_report):
    case, report = reviewed_report
    assert check_report(case, report) == []
    wrong = copy.deepcopy(report)
    wrong["resolved_commits"]["target"] = case["base"]
    assert any("frozen comparison" in item for item in check_report(case, wrong))
    historical = copy.deepcopy(report)
    historical["evidence_paths"][0]["source"] = "base"
    assert any("Target connection missing" in item for item in check_report(case, historical))
    no_evidence = copy.deepcopy(report)
    no_evidence["call_sites"] = []
    assert any("source evidence missing" in item for item in check_report(case, no_evidence))


def test_empty_changed_and_rename_checks_do_not_pass_missing_findings(reviewed_report):
    case, report = reviewed_report
    missing = copy.deepcopy(case)
    missing["expected"]["changed"].append("missing.py::helper")
    missing["expected"]["renamed"] = [{"id": "service.py::value", "previous_id": "old.py::value"}]
    missing["expected"]["routes"] = [{"symbol_id": "service.py::value", "method": "GET", "path": "/value", "registration": "declared"}]
    missing["expected"]["related_tests"].append("tests/test_missing.py::test_missing")
    failures = check_report(missing, report)
    assert len(failures) == 4
    empty = {**case, "expected": {"empty_python_comparison": True}}
    assert check_report(empty, report)
    report["changed_symbols"] = []
    report["evidence_paths"] = []
    report["affected_symbols"] = []
    report["related_tests"] = []
    assert check_report(empty, report) == []
    report["historical_impact"]["related_tests"] = ["old.py::test_old"]
    assert any("historical impact" in item for item in check_report(empty, report))


def test_known_missing_relationships_are_notes_not_claimed_coverage(reviewed_report):
    case, report = reviewed_report
    case["expected"]["absent_related_tests"] = ["tests/test_value.py::test_value"]
    assert any("incorrectly listed" in item for item in check_report(case, report))
    cases = load_cases()
    assert len(cases) == 9 and len({item["id"] for item in cases}) == 9
    assert all(item["review_note"] for item in cases)
    assert len({item["repository"] for item in cases}) == 2


def test_saved_report_mode_labels_errors_and_refuses_wrong_comparison(reviewed_report, tmp_path, monkeypatch, capsys):
    case, report = reviewed_report
    case.update({"id": "test-case", "pull_request": "https://github.com/owner/repo/pull/1", "review_note": "Selected checks only."})
    monkeypatch.setattr("benchmarks.pr_review.load_cases", lambda: [case])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["--case", "test-case", "--saved-report", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "saved-report-check" and result["status"] == "required-checks-passed"
    report["resolved_commits"]["target"] = case["base"]
    path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["--case", "test-case", "--saved-report", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "missing-required-findings"
    path.write_text("{}", encoding="utf-8")
    assert main(["--case", "test-case", "--saved-report", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_fresh_mode_saves_real_analysis_and_never_treats_loading_failure_as_success(reviewed_report, comparison, tmp_path, monkeypatch, capsys):
    case, report = reviewed_report
    case.update({"id": "test-case", "repository": "https://github.com/owner/repo", "pull_request": "https://github.com/owner/repo/pull/1", "review_note": "Selected checks only."})
    monkeypatch.setattr("benchmarks.pr_review.load_cases", lambda: [case])
    destination = tmp_path / "fresh.json"
    assert main(["--case", "test-case", "--repository", str(comparison[0]), "--report", str(destination)]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "fresh-analysis"
    assert json.loads(destination.read_text(encoding="utf-8")) == report
    with pytest.raises(SystemExit) as error:
        main(["--case", "test-case", "--report", str(destination)])
    assert error.value.code == 2
    assert json.loads(destination.read_text(encoding="utf-8")) == report
    capsys.readouterr()

    @contextmanager
    def unavailable(*args):
        raise RuntimeError("Public repository could not be loaded")
        yield

    monkeypatch.setattr("benchmarks.pr_review.open_repository", unavailable)
    absent = tmp_path / "not-produced.json"
    assert main(["--case", "test-case", "--report", str(absent)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    assert not absent.exists()
