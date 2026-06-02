#!/usr/bin/env python3
"""Burn CPU cores for watchdog testing."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import time


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def burn(stop_at: float | None) -> None:
    x = 0x12345678
    while stop_at is None or time.monotonic() < stop_at:
        x = ((x * 1103515245 + 12345) & 0x7FFFFFFF) ^ (x >> 7)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fully occupy CPU cores.")
    parser.add_argument(
        "-w",
        "--workers",
        type=positive_int,
        default=os.cpu_count() or 1,
        help="number of CPU worker processes, default: all logical CPUs",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=non_negative_float,
        default=0.0,
        help="seconds to run; 0 means until Ctrl-C, default: 0",
    )
    args = parser.parse_args()

    stop_at = None if args.duration == 0 else time.monotonic() + args.duration
    processes = [mp.Process(target=burn, args=(stop_at,)) for _ in range(args.workers)]

    print(f"Starting {len(processes)} CPU worker(s). Press Ctrl-C to stop.")
    for process in processes:
        process.start()

    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        print("Stopping CPU workers...")
        for process in processes:
            process.terminate()
        for process in processes:
            process.join()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
