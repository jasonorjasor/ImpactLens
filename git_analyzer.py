"""Git-based change analysis for ImpactLens."""

import re
import subprocess
from pathlib import Path

from analyzer import (
    analyze_sources,
    build_reverse_graph,
    extract_symbols,
    find_impact_paths,
)


def run_git(repository, *arguments):
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def changed_python_lines(repository, base_commit, target_commit):
    diff = run_git(
        repository,
        "diff",
        "--unified=0",
        "--no-renames",
        base_commit,
        target_commit,
        "--",
        "*.py",
    )
    changed = {}
    current_path = None
    new_line = None
    pattern = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("@@"):
            match = pattern.match(line)
            if match:
                new_line = int(match.group(1))
                changed.setdefault(current_path, set())
        elif current_path and new_line is not None:
            if line.startswith("+") and not line.startswith("+++"):
                changed[current_path].add(new_line)
                new_line += 1
            elif line.startswith(" "):
                new_line += 1

    return {path: lines for path, lines in changed.items() if path}


def changed_symbols(repository, base_commit, target_commit):
    repository = Path(repository).resolve()
    changed_lines = changed_python_lines(repository, base_commit, target_commit)
    symbols = []

    for path, lines in changed_lines.items():
        try:
            source = run_git(repository, "show", f"{target_commit}:{path}")
        except subprocess.CalledProcessError:
            continue

        for symbol in extract_symbols(source):
            if symbol["kind"] not in {"function", "async_function"}:
                continue
            symbol_id = f"{path}::{symbol['qualname']}"
            affected_lines = [
                line
                for line in sorted(lines)
                if symbol["line_start"] <= line <= symbol["line_end"]
            ]
            if affected_lines:
                symbols.append(
                    {
                        "id": symbol_id,
                        "path": path,
                        "qualname": symbol["qualname"],
                        "line_start": symbol["line_start"],
                        "line_end": symbol["line_end"],
                        "changed_lines": affected_lines,
                    }
                )

    return symbols


def analyze_commit(repository, commit):
    paths = run_git(repository, "ls-tree", "-r", "--name-only", commit, "--")
    sources = {
        path: run_git(repository, "show", f"{commit}:{path}")
        for path in paths.splitlines()
        if path.endswith(".py")
    }
    return analyze_sources(sources)


def analyze_change(repository, base_commit, target_commit):
    changed = changed_symbols(repository, base_commit, target_commit)
    target_report = analyze_commit(repository, target_commit)
    calls = [call for file in target_report["files"] for call in file["calls"]]
    graph = build_reverse_graph(calls)
    evidence_paths = []
    affected_symbols = []

    for symbol in changed:
        paths = find_impact_paths(symbol["id"], graph)
        symbol["impact_paths"] = paths
        for path in paths:
            if path not in evidence_paths:
                evidence_paths.append(path)
            for identifier in path[1:]:
                if identifier not in affected_symbols:
                    affected_symbols.append(identifier)

    return {
        "base_commit": base_commit,
        "target_commit": target_commit,
        "changed_symbols": changed,
        "affected_symbols": affected_symbols,
        "evidence_paths": evidence_paths,
    }
