import argparse
import json

from git_analyzer import analyze_change


def format_report(report):
    lines = [
        "ImpactLens",
        f"Commits: {report['base_commit']} -> {report['target_commit']}",
        "",
    ]

    changed = report["changed_symbols"]
    lines.append(f"Changed symbols ({len(changed)})")
    if changed:
        for symbol in changed:
            changed_lines = ", ".join(str(line) for line in symbol["changed_lines"])
            lines.append(f"- {symbol['id']} (lines: {changed_lines})")
    else:
        lines.append("- none")

    affected = report["affected_symbols"]
    lines.extend(["", f"Affected symbols ({len(affected)})"])
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
    if paths:
        lines.extend(f"- {' -> '.join(path)}" for path in paths)
    else:
        lines.append("- none")

    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Analyze the impact of a Python change between two Git commits."
    )
    parser.add_argument("repository", help="Path to a local Git repository")
    parser.add_argument("base_commit", help="Older commit to compare")
    parser.add_argument("target_commit", help="Newer commit to analyze")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON",
    )
    return parser


def main(arguments=None):
    parser = build_parser()
    args = parser.parse_args(arguments)
    report = analyze_change(args.repository, args.base_commit, args.target_commit)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
