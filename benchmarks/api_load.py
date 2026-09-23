"""Exercise the local API and sample memory used by it and its Git children."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait_for_server(url, process):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"API exited with status {process.returncode}")
        try:
            with urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.1)
    raise TimeoutError("API did not become ready within 20 seconds")


def _sample_memory(process, stop, peaks):
    while not stop.is_set():
        try:
            family = [process, *process.children(recursive=True)]
        except psutil.NoSuchProcess:
            return
        total = server = git = 0
        for member in family:
            try:
                rss = member.memory_info().rss
                total += rss
                if member.pid == process.pid:
                    server = rss
                elif member.name().lower().startswith("git"):
                    git += rss
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        peaks["tree"] = max(peaks["tree"], total)
        peaks["server"] = max(peaks["server"], server)
        peaks["git"] = max(peaks["git"], git)
        peaks["samples"] += 1
        stop.wait(0.02)


def _post(url, payload, start):
    start.wait(timeout=10)
    begun = time.perf_counter()
    request = Request(
        f"{url}/analyze",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            status = response.status
            body = json.load(response)
    except HTTPError as error:
        status = error.code
        body = json.load(error)

    result = {"status": status, "seconds": round(time.perf_counter() - begun, 3)}
    if status == 200:
        result.update({
            "changed_symbols": len(body["changed_symbols"]),
            "evidence_paths": len(body["evidence_paths"]),
            "analysis_errors": len(body["analysis_errors"]),
            "report_sha256": hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        })
    else:
        result["detail"] = body.get("detail")
    return result


def measure_api_load(repository, base_commit, target_commit, requests=1):
    if requests not in (1, 2, 3):
        raise ValueError("requests must be 1, 2, or 3")

    port = _available_port()
    url = f"http://127.0.0.1:{port}"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "error", "--no-access-log"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=flags,
    )
    stop = threading.Event()
    monitor = None
    try:
        _wait_for_server(url, server)
        peaks = {"tree": 0, "server": 0, "git": 0, "samples": 0}
        monitor = threading.Thread(
            target=_sample_memory,
            args=(psutil.Process(server.pid), stop, peaks),
            daemon=True,
        )
        monitor.start()
        payload = {
            "repository": repository,
            "base_commit": base_commit,
            "target_commit": target_commit,
        }
        start = threading.Barrier(requests)
        begun = time.perf_counter()
        with ThreadPoolExecutor(max_workers=requests) as pool:
            futures = [pool.submit(_post, url, payload, start) for _ in range(requests)]
            responses = [future.result() for future in futures]
        wall_seconds = round(time.perf_counter() - begun, 3)
        stop.set()
        monitor.join(timeout=2)

        statuses = sorted(response["status"] for response in responses)
        expected = [200] * min(requests, 2) + ([503] if requests == 3 else [])
        hashes = {response["report_sha256"] for response in responses if response["status"] == 200}
        if statuses != expected or len(hashes) != 1:
            raise RuntimeError(f"Unexpected API responses: {responses}")

        return {
            "repository": repository,
            "base_commit": base_commit,
            "target_commit": target_commit,
            "requests": requests,
            "wall_seconds": wall_seconds,
            "peak_tree_rss_bytes": peaks["tree"],
            "peak_server_rss_bytes": peaks["server"],
            "peak_git_rss_bytes": peaks["git"],
            "memory_samples": peaks["samples"],
            "responses": responses,
        }
    finally:
        stop.set()
        if monitor is not None:
            monitor.join(timeout=2)
        if server.poll() is None:
            server.terminate()
        try:
            server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate()


def main(arguments=None):
    parser = argparse.ArgumentParser(description="Measure local API concurrency and process-tree memory.")
    parser.add_argument("repository", help="Public GitHub URL")
    parser.add_argument("base_commit")
    parser.add_argument("target_commit")
    parser.add_argument("--requests", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args(arguments)
    result = measure_api_load(
        args.repository, args.base_commit, args.target_commit, args.requests
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
