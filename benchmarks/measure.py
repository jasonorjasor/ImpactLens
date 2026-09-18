import argparse
import hashlib
import json
import time

from git_analyzer import analyze_change
from repository_loader import open_repository, repository_size_bytes


def measure(repository, base_commit, target_commit):
    started = time.perf_counter()
    with open_repository(repository, base_commit, target_commit) as loaded_repository:
        loaded = time.perf_counter()
        loaded_bytes = repository_size_bytes(loaded_repository)
        analysis_started = time.perf_counter()
        report = analyze_change(loaded_repository, base_commit, target_commit)
        analyzed = time.perf_counter()
        analyzed_bytes = repository_size_bytes(loaded_repository)
        report_sha256 = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    return {
        "repository": repository,
        "base_commit": base_commit,
        "target_commit": target_commit,
        "load_seconds": round(loaded - started, 3),
        "analysis_seconds": round(analyzed - analysis_started, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "loaded_bytes": loaded_bytes,
        "analyzed_bytes": analyzed_bytes,
        "changed_symbols": len(report["changed_symbols"]),
        "evidence_paths": len(report["evidence_paths"]),
        "analysis_errors": len(report["analysis_errors"]),
        "report_sha256": report_sha256,
    }


def main(arguments=None):
    parser = argparse.ArgumentParser(description="Measure one ImpactLens commit comparison.")
    parser.add_argument("repository", help="Local Git path or public GitHub URL")
    parser.add_argument("base_commit")
    parser.add_argument("target_commit")
    args = parser.parse_args(arguments)
    print(json.dumps(measure(args.repository, args.base_commit, args.target_commit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
