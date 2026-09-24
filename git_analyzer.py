"""Git-based change analysis for ImpactLens."""

import difflib
import re
import subprocess
from pathlib import Path

from git_process import GitDiskLimitExceeded, run_git_command
from repository_loader import RepositoryLoadError
from analyzer import (
    analyze_sources,
    analyze_repository,
    build_reverse_graph,
    decode_python_source,
    extract_symbols,
    find_impact_paths,
)
from request_budget import check_deadline, command_timeout


GIT_TIMEOUT_SECONDS = 60


class AnalysisTimeoutError(RuntimeError):
    pass


def run_git(repository, *arguments, binary=False, input_data=None):
    try:
        result = run_git_command(
            ["git", "-C", str(repository), *arguments],
            input_data=input_data,
            timeout=command_timeout(GIT_TIMEOUT_SECONDS),
        )
    except GitDiskLimitExceeded as error:
        raise RepositoryLoadError(str(error)) from error
    except subprocess.TimeoutExpired as error:
        check_deadline()
        raise AnalysisTimeoutError("Analysis Git command timed out") from error
    except subprocess.CalledProcessError:
        check_deadline()
        raise
    check_deadline()
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="surrogateescape")


def untracked_python_files(repository):
    output = run_git(
        repository,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "*.py",
    )
    return {path for path in output.splitlines() if path}


def python_file_changes(repository, base_commit, target_commit=None):
    arguments = ["diff", "--name-status", "--find-renames", base_commit]
    if target_commit is not None:
        arguments.append(target_commit)
    output = run_git(repository, *arguments, "--", "*.py")
    deleted = set()
    renamed = {}

    for line in output.splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            renamed[parts[2]] = parts[1]
        elif status == "D" and len(parts) >= 2:
            deleted.add(parts[1])

    return deleted, renamed


def detect_untracked_renames(repository, base_commit, deleted, untracked):
    candidates = []
    for new_path in sorted(untracked):
        try:
            new_source = (Path(repository) / new_path).read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            continue

        for old_path in sorted(deleted):
            try:
                old_source = run_git(repository, "show", f"{base_commit}:{old_path}", binary=True)
                old_source = old_source.replace(b"\r\n", b"\n")
            except subprocess.CalledProcessError:
                continue

            similarity = difflib.SequenceMatcher(
                None,
                old_source,
                new_source,
            ).ratio()
            if similarity >= 0.8:
                candidates.append((similarity, old_path, new_path))

    renames = {}
    used_old_paths = set()
    used_new_paths = set()
    for _, old_path, new_path in sorted(candidates, reverse=True):
        if old_path in used_old_paths or new_path in used_new_paths:
            continue
        renames[new_path] = old_path
        used_old_paths.add(old_path)
        used_new_paths.add(new_path)

    return renames


def changed_python_line_ranges(repository, base_commit, target_commit=None):
    arguments = ["diff", "--unified=0", "--no-renames", base_commit]
    if target_commit is not None:
        arguments.append(target_commit)
    arguments.extend(["--", "*.py"])
    diff = run_git(repository, *arguments)
    changed = {}
    current_path = None
    old_line = None
    new_line = None
    pattern = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

    for line in diff.splitlines():
        check_deadline()
        if line.startswith("diff --git "):
            current_path = None
            old_line = None
            new_line = None
        elif old_line is None and line.startswith("--- a/"):
            current_path = line[6:]
        elif old_line is None and line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("@@"):
            match = pattern.match(line)
            if match:
                old_line = int(match.group(1))
                new_line = int(match.group(2))
                changed.setdefault(
                    current_path,
                    {"added_lines": set(), "removed_lines": set()},
                )
        elif current_path and new_line is not None:
            if line.startswith("+"):
                changed[current_path]["added_lines"].add(new_line)
                new_line += 1
            elif line.startswith("-"):
                changed[current_path]["removed_lines"].add(old_line)
                old_line += 1
            elif line.startswith(" "):
                old_line += 1
                new_line += 1

    if target_commit is None:
        for path in untracked_python_files(repository):
            try:
                source = (Path(repository) / path).read_bytes()
            except OSError:
                continue
            line_count = len(source.splitlines())
            if line_count:
                changed.setdefault(
                    path,
                    {"added_lines": set(), "removed_lines": set()},
                )["added_lines"].update(range(1, line_count + 1))

    return {path: ranges for path, ranges in changed.items() if path}


def changed_python_lines(repository, base_commit, target_commit=None):
    return {
        path: ranges["added_lines"]
        for path, ranges in changed_python_line_ranges(
            repository, base_commit, target_commit
        ).items()
    }


def changed_symbols(repository, base_commit, target_commit=None):
    repository = Path(repository).resolve()
    changed_ranges = changed_python_line_ranges(repository, base_commit, target_commit)
    symbols = []
    untracked = untracked_python_files(repository) if target_commit is None else set()
    deleted, renamed = python_file_changes(repository, base_commit, target_commit)
    if target_commit is None:
        renamed.update(
            detect_untracked_renames(repository, base_commit, deleted, untracked)
        )
    renamed_sources = set(renamed.values())

    for path, ranges in changed_ranges.items():
        check_deadline()
        if path in renamed_sources:
            continue
        added_lines = ranges["added_lines"]
        removed_lines = ranges["removed_lines"]
        try:
            if path in deleted:
                source = b""
            elif target_commit is None:
                source = (repository / path).read_bytes()
            else:
                source = run_git(repository, "show", f"{target_commit}:{path}", binary=True)
        except (OSError, subprocess.CalledProcessError):
            continue

        try:
            current_symbols = {
                symbol["qualname"]: symbol
                for symbol in extract_symbols(decode_python_source(source))
                if symbol["kind"] in {"function", "async_function"}
            }
        except (SyntaxError, UnicodeDecodeError):
            continue

        previous_path = renamed.get(path, path)
        try:
            old_source = run_git(repository, "show", f"{base_commit}:{previous_path}", binary=True)
        except subprocess.CalledProcessError:
            old_source = b""
        try:
            old_symbols = {
                symbol["qualname"]: symbol
                for symbol in extract_symbols(decode_python_source(old_source))
                if symbol["kind"] in {"function", "async_function"}
            }
        except (SyntaxError, UnicodeDecodeError):
            old_symbols = None

        matched_symbols = {}
        for symbol in current_symbols.values():
            affected_lines = [
                line
                for line in sorted(added_lines)
                if symbol["line_start"] <= line <= symbol["line_end"]
            ]
            if affected_lines:
                matched_symbols[symbol["qualname"]] = {
                    **symbol,
                    "changed_lines": affected_lines,
                }

        if removed_lines and old_symbols is not None:
            for symbol in old_symbols.values():
                removed = [
                    line
                    for line in sorted(removed_lines)
                    if symbol["line_start"] <= line <= symbol["line_end"]
                ]
                if not removed:
                    continue
                current = current_symbols.get(symbol["qualname"])
                matched_symbols.setdefault(
                    symbol["qualname"],
                    {
                        **(current or symbol),
                        "changed_lines": [],
                    },
                )["removed_lines"] = removed

        for symbol in matched_symbols.values():
            symbol_id = f"{path}::{symbol['qualname']}"
            changed_symbol = {
                "id": symbol_id,
                "path": path,
                "qualname": symbol["qualname"],
                "line_start": symbol["line_start"],
                "line_end": symbol["line_end"],
                "changed_lines": symbol["changed_lines"],
            }
            if "removed_lines" in symbol:
                changed_symbol["removed_lines"] = symbol["removed_lines"]
            if symbol["qualname"] not in current_symbols:
                changed_symbol["change_type"] = "deleted"
            elif path in renamed and old_symbols is not None and symbol["qualname"] in old_symbols:
                changed_symbol["change_type"] = "renamed"
                changed_symbol["previous_id"] = (
                    f"{renamed[path]}::{symbol['qualname']}"
                )
            elif old_symbols is not None and symbol["qualname"] not in old_symbols:
                changed_symbol["change_type"] = "added"
            symbols.append(changed_symbol)

    return symbols


def analyze_commit(repository, commit=None):
    if commit is None:
        return analyze_repository(repository)

    listing = run_git(repository, "ls-tree", "-r", "-z", commit, "--", binary=True)
    entries = []
    for record in listing.split(b"\0"):
        check_deadline()
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _, kind, object_id = metadata.split(b" ")
        if kind == b"blob" and raw_path.endswith(b".py"):
            entries.append((raw_path.decode("utf-8", errors="surrogateescape"), object_id))

    if not entries:
        return analyze_sources({})

    output = run_git(
        repository,
        "cat-file",
        "--batch",
        binary=True,
        input_data=b"\n".join(object_id for _, object_id in entries) + b"\n",
    )
    sources = {}
    offset = 0
    for path, object_id in entries:
        check_deadline()
        line_end = output.find(b"\n", offset)
        if line_end < 0:
            raise ValueError("Git returned an incomplete blob header")
        header = output[offset:line_end].split(b" ")
        if len(header) != 3 or header[:2] != [object_id, b"blob"]:
            raise ValueError("Git returned an unexpected blob header")
        size = int(header[2])
        start = line_end + 1
        end = start + size
        if output[end:end + 1] != b"\n":
            raise ValueError("Git returned an incomplete blob")
        sources[path] = output[start:end]
        offset = end + 1

    if offset != len(output):
        raise ValueError("Git returned extra blob data")
    return analyze_sources(sources)


def summarize_impact(report, changed_ids, affected_symbols):
    impacted_ids = set(changed_ids) | set(affected_symbols)
    affected_routes = [
        {
            "symbol_id": route["id"],
            "method": route["method"],
            "path": route["path"],
        }
        for file in report["files"]
        for route in file["routes"]
        if route["id"] in impacted_ids
    ]
    related_tests = [
        test["id"]
        for file in report["files"]
        for test in file["tests"]
        if test["id"] in impacted_ids
    ]

    return {
        "affected_symbols": affected_symbols,
        "affected_routes": affected_routes,
        "related_tests": related_tests,
    }


def analyze_change(repository, base_commit, target_commit=None):
    changed = changed_symbols(repository, base_commit, target_commit)
    reports = {"target": analyze_commit(repository, target_commit)}
    if any(symbol.get("change_type") == "deleted" for symbol in changed):
        reports["base"] = analyze_commit(repository, base_commit)
    graphs = {
        source: build_reverse_graph([
            call for file in report["files"] for call in file["calls"]
        ])
        for source, report in reports.items()
    }
    evidence_paths = []
    affected = {"base": [], "target": []}
    changed_ids = {"base": [], "target": []}

    for symbol in changed:
        check_deadline()
        source = "base" if symbol.get("change_type") == "deleted" else "target"
        changed_ids[source].append(symbol["id"])
        paths = [
            path for path in find_impact_paths(symbol["id"], graphs[source])
            if len(path) > 1
        ]
        symbol["impact_paths"] = [
            {"source": source, "symbols": path} for path in paths
        ]
        for evidence in symbol["impact_paths"]:
            if evidence not in evidence_paths:
                evidence_paths.append(evidence)
            for identifier in evidence["symbols"][1:]:
                if identifier not in affected[source]:
                    affected[source].append(identifier)

    return {
        "base_commit": base_commit,
        "target_commit": target_commit or "WORKING_TREE",
        "changed_symbols": changed,
        "evidence_paths": evidence_paths,
        **summarize_impact(reports["target"], changed_ids["target"], affected["target"]),
        "historical_impact": summarize_impact(
            reports.get("base", {"files": []}), changed_ids["base"], affected["base"]
        ),
        "analysis_errors": [
            {"source": source, **error}
            for source, report in reports.items()
            for error in report["errors"]
        ],
    }


def analyze_working_tree(repository, base_commit="HEAD"):
    return analyze_change(repository, base_commit, None)
