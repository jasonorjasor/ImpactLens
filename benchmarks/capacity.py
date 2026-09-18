"""Measure process memory and overlapping commit comparisons."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import sys
import threading
import time

from benchmarks.measure import measure


def peak_process_memory_bytes():
    if sys.platform == "win32":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_fault_count", wintypes.DWORD),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_nonpaged_pool_usage", ctypes.c_size_t),
                ("quota_nonpaged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return counters.peak_working_set_size

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def measure_capacity(repository, base_commit, target_commit, concurrent=1):
    if concurrent not in (1, 2):
        raise ValueError("concurrent must be 1 or 2, matching the API limit")

    start_barrier = threading.Barrier(concurrent)
    analysis_barrier = threading.Barrier(concurrent) if concurrent == 2 else None

    def run_one():
        start_barrier.wait()
        try:
            return measure(repository, base_commit, target_commit, analysis_barrier)
        except Exception:
            if analysis_barrier is not None:
                analysis_barrier.abort()
            raise

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futures = [pool.submit(run_one) for _ in range(concurrent)]
        results = [future.result() for future in futures]

    return {
        "concurrent": concurrent,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "peak_process_memory_bytes": peak_process_memory_bytes(),
        "runs": results,
    }


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Measure one or two overlapping ImpactLens analyses."
    )
    parser.add_argument("repository", help="Local Git path or public GitHub URL")
    parser.add_argument("base_commit")
    parser.add_argument("target_commit")
    parser.add_argument("--concurrent", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(arguments)
    result = measure_capacity(
        args.repository, args.base_commit, args.target_commit, args.concurrent
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
