import argparse
import json
from pathlib import Path

from git_analyzer import analyze_change, analyze_working_tree
from repository_loader import RepositoryLoadError, is_github_url, open_repository


def is_test_identifier(identifier):
    relative_path = identifier.split("::", 1)[0]
    path = Path(relative_path)
    return (
        "tests" in path.parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def format_impact_sections(report, historical=False):
    related_tests = set(report["related_tests"])
    affected = [
        symbol for symbol in report["affected_symbols"]
        if symbol not in related_tests and not is_test_identifier(symbol)
    ]
    code_title = "Historical callers" if historical else "Affected code symbols"
    lines = ["", f"{code_title} ({len(affected)})"]
    lines.extend(f"- {symbol}" for symbol in affected or ["none"])

    routes = report["affected_routes"]
    route_title = "Historical routes" if historical else "Affected routes"
    lines.extend(["", f"{route_title} ({len(routes)})"])
    if routes:
        lines.extend(
            f"- {route['method']} {route['path']} ({route['symbol_id']})"
            for route in routes
        )
    else:
        lines.append("- none")

    tests = report["related_tests"]
    test_title = "Historical related tests" if historical else "Related tests"
    lines.extend(["", f"{test_title} ({len(tests)})"])
    lines.extend(f"- {test}" for test in tests or ["none"])
    return lines


def format_report(report, max_paths=20):
    lines = [
        "ImpactLens",
        f"Comparison: {report['base_commit']} -> {report['target_commit']}",
        "",
    ]

    changed = report["changed_symbols"]
    lines.append(f"Changed symbols ({len(changed)})")
    if changed:
        for symbol in changed:
            details = []
            if symbol.get("change_type"):
                details.append(symbol["change_type"])
            if symbol.get("previous_id"):
                details.append(f"from {symbol['previous_id']}")
            if symbol["changed_lines"]:
                changed_lines = ", ".join(
                    str(line) for line in symbol["changed_lines"]
                )
                details.append(f"lines: {changed_lines}")
            if symbol.get("removed_lines"):
                removed_lines = ", ".join(str(line) for line in symbol["removed_lines"])
                details.append(f"removed lines (base): {removed_lines}")
            detail = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- {symbol['id']}{detail}")
    else:
        lines.append("- none")

    lines.extend(["Results from the target version:"])
    lines.extend(format_impact_sections(report))
    paths = report["evidence_paths"]
    if any(path["source"] == "base" for path in paths):
        lines.extend(["", "Historical results come from the base version; they may no longer exist or depend on the deleted code."])
        lines.extend(format_impact_sections(report["historical_impact"], historical=True))
    lines.extend(["", f"Impact paths ({len(paths)})"])
    visible_paths = paths if max_paths is None else paths[:max_paths]
    if visible_paths:
        for path in visible_paths:
            label = "base, historical" if path["source"] == "base" else "target"
            lines.append(f"- [{label}] {' -> '.join(path['symbols'])}")
    else:
        lines.append("- none")
    if len(visible_paths) < len(paths):
        remaining = len(paths) - len(visible_paths)
        lines.append(f"- {remaining} more paths (use --all-paths)")

    errors = report["analysis_errors"]
    if errors:
        lines.extend(["", f"Files not analyzed ({len(errors)})"])
        lines.extend(
            f"- [{item['source']}] {item['path']}: {item['error']}"
            for item in errors
        )
        lines.append("Results may be incomplete.")

    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Analyze the impact of a Python change between two commits or against the working tree."
    )
    parser.add_argument(
        "repository",
        help="Path to a local Git repository or a public GitHub URL",
    )
    parser.add_argument("base_commit", help="Older commit to compare")
    parser.add_argument(
        "target_commit",
        nargs="?",
        help="Newer commit to analyze",
    )
    parser.add_argument(
        "--working-tree",
        action="store_true",
        help="Compare the current files against the base commit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON",
    )
    parser.add_argument(
        "--all-paths",
        action="store_true",
        help="Print every impact path in human-readable output",
    )
    return parser


def main(arguments=None):
    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        if args.working_tree:
            if args.target_commit is not None:
                parser.error("target_commit cannot be used with --working-tree")
            with open_repository(args.repository) as repository:
                report = analyze_working_tree(repository, args.base_commit)
        else:
            if args.target_commit is None:
                parser.error("target_commit is required unless --working-tree is used")
            if is_github_url(args.repository):
                with open_repository(
                    args.repository,
                    args.base_commit,
                    args.target_commit,
                ) as repository:
                    report = analyze_change(
                        repository,
                        args.base_commit,
                        args.target_commit,
                    )
            else:
                with open_repository(args.repository) as repository:
                    report = analyze_change(
                        repository,
                        args.base_commit,
                        args.target_commit,
                    )
    except RepositoryLoadError as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        max_paths = None if args.all_paths else 20
        print(format_report(report, max_paths=max_paths))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
