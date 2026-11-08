"""Repeat selected checks on frozen real PR comparisons, without running their code."""

import argparse
import json
import time
from pathlib import Path

from api import AnalyzeResponse
from git_analyzer import analyze_change
from repository_loader import open_repository
from request_budget import request_deadline


CASE_FILE = Path(__file__).with_name("pr_cases.json")


def load_cases():
    return json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]


def check_report(case, report):
    AnalyzeResponse.model_validate(report)
    expected = case["expected"]
    missing = []
    if report["resolved_commits"] != {"base": case["base"], "target": case["head"]}:
        missing.append("The report does not describe the frozen comparison.")
    if report["analysis_errors"]:
        missing.append("Some Python files could not be analyzed.")
    changed = {item["id"]: item for item in report["changed_symbols"]}
    for identifier in expected.get("changed", []):
        if identifier not in changed:
            missing.append(f"Changed symbol missing: {identifier}")
    for rename in expected.get("renamed", []):
        symbol = changed.get(rename["id"], {})
        if symbol.get("change_type") != "renamed" or symbol.get("previous_id") != rename["previous_id"]:
            missing.append(f"Rename identity missing: {rename['id']}")
    for route in expected.get("routes", []):
        if route not in report["affected_routes"]:
            missing.append(f"Route declaration differs: {route['method']} {route['path']}")
    for identifier in expected.get("related_tests", []):
        if identifier not in report["related_tests"]:
            missing.append(f"Related test missing: {identifier}")
    for identifier in expected.get("absent_related_tests", []):
        if identifier in report["related_tests"]:
            missing.append(f"Old-path test incorrectly listed as current: {identifier}")
    edges = {
        (callee.removesuffix(" (cycle)"), caller.removesuffix(" (cycle)"))
        for path in report["evidence_paths"] if path["source"] == "target"
        for callee, caller in zip(path["symbols"], path["symbols"][1:])
    }
    evidence_edges = {
        (site["callee_id"], site["caller_id"])
        for site in report["call_sites"] if site["source"] == "target"
    }
    for connection in expected.get("direct_connections", []):
        if tuple(connection) not in edges:
            missing.append(f"Target connection missing: {' -> '.join(connection)}")
        elif tuple(connection) not in evidence_edges:
            missing.append(f"Target source evidence missing: {' -> '.join(connection)}")
    if expected.get("empty_python_comparison"):
        if any(report[key] for key in ("changed_symbols", "evidence_paths", "affected_symbols", "affected_routes", "related_tests")):
            missing.append("Non-Python-only comparison unexpectedly has Python change results.")
        if any(report["historical_impact"].values()):
            missing.append("Non-Python-only comparison unexpectedly has historical impact.")
    return missing


def main(arguments=None):
    cases = {case["id"]: case for case in load_cases()}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=cases)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--repository", help="Existing local checkout containing the frozen commits; default loads the public repository")
    source.add_argument("--saved-report", type=Path, help="Check an existing JSON report without loading Git or doing a fresh analysis")
    parser.add_argument("--report", type=Path, help="Save fresh report JSON to a new file")
    args = parser.parse_args(arguments)
    if args.saved_report and args.report:
        parser.error("--report is only for a fresh analysis")
    if args.report and args.report.exists():
        parser.error("Choose a new report file; existing files are never overwritten")
    case = cases[args.case]
    started = time.perf_counter()
    try:
        if args.saved_report:
            report = json.loads(args.saved_report.read_text(encoding="utf-8"))
        else:
            with request_deadline(120):
                with open_repository(args.repository or case["repository"], case["base"], case["head"]) as repository:
                    report = analyze_change(repository, case["base"], case["head"])
        missing = check_report(case, report)
        if args.report:
            with args.report.open("x", encoding="utf-8") as destination:
                json.dump(report, destination, indent=2)
                destination.write("\n")
        result = {
            "case": case["id"], "pull_request": case["pull_request"],
            "mode": "saved-report-check" if args.saved_report else "fresh-analysis",
            "status": "missing-required-findings" if missing else "required-checks-passed",
            "missing": missing, "changed_symbols": len(report["changed_symbols"]),
            "paths": len(report["evidence_paths"]), "related_tests": len(report["related_tests"]),
            "warnings": len(report["analysis_warnings"]),
            "seconds": round(time.perf_counter() - started, 3),
            "review_note": case["review_note"],
            "scope": "Selected checks only. Extra findings and known missed relationships require review; this is not an accuracy score.",
        }
    except (RuntimeError, ValueError, OSError) as error:
        result = {"case": case["id"], "status": "error", "error": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "required-checks-passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
