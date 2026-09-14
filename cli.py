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
            detail = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- {symbol['id']}{detail}")
    else:
        lines.append("- none")

    related_tests = set(report["related_tests"])
    affected = [
        symbol
        for symbol in report["affected_symbols"]
        if symbol not in related_tests and not is_test_identifier(symbol)
    ]
    lines.extend(["", f"Affected code symbols ({len(affected)})"])
    lines.extend(f"- {symbol}" for symbol in affected or ["none"])

    routes = report["affected_routes"]
    lines.extend(["", f"Affected routes ({len(routes)})"])
    if routes:
        lines.extend(
            f"- {route['method']} {route['path']} ({route['symbol_id']})"
            for route in routes
        )
    else:
        lines.append("- none")

    tests = report["related_tests"]
    lines.extend(["", f"Related tests ({len(tests)})"])
    lines.extend(f"- {test}" for test in tests or ["none"])

    paths = report["evidence_paths"]
    lines.extend(["", f"Impact paths ({len(paths)})"])
    visible_paths = paths if max_paths is None else paths[:max_paths]
    if visible_paths:
        lines.extend(f"- {' -> '.join(path)}" for path in visible_paths)
    else:
        lines.append("- none")
    if len(visible_paths) < len(paths):
        remaining = len(paths) - len(visible_paths)
        lines.append(f"- {remaining} more paths (use --all-paths)")

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
