#!/usr/bin/env python3
"""Allocate and hold host memory for watchdog testing."""

from __future__ import annotations

import argparse
import re
import time


SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b?|[kmgt])?\s*$", re.IGNORECASE)
UNITS = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "mib": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "gib": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
    "tib": 1024**4,
}


def parse_size(value: str) -> int:
    match = SIZE_RE.match(value)
    if not match:
        raise argparse.ArgumentTypeError("size must look like 512M, 2G, or 1048576")
    amount = float(match.group(1))
    unit = (match.group(2) or "").lower()
    size = int(amount * UNITS[unit])
    if size <= 0:
        raise argparse.ArgumentTypeError("size must be positive")
    return size


def percent(value: str) -> float:
    parsed = float(value)
    if parsed <= 0 or parsed >= 100:
        raise argparse.ArgumentTypeError("percent must be > 0 and < 100")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def available_memory_bytes() -> int:
    with open("/proc/meminfo", "r", encoding="utf-8") as meminfo:
        for line in meminfo:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("could not read MemAvailable from /proc/meminfo")


def main() -> int:
    parser = argparse.ArgumentParser(description="Allocate and hold host memory.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--memory-size",
        "--size",
        dest="memory_size",
        type=parse_size,
        help="memory to allocate, e.g. 512M or 4G",
    )
    group.add_argument(
        "--memory-percent",
        "--percent",
        dest="memory_percent",
        type=percent,
        help="percent of currently available host memory to allocate",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=non_negative_float,
        default=0.0,
        help="seconds to hold memory; 0 means until Ctrl-C, default: 0",
    )
    parser.add_argument(
        "--chunk-size",
        type=parse_size,
        default=parse_size("64M"),
        help="allocation chunk size, default: 64M",
    )
    args = parser.parse_args()

    if args.memory_size is None and args.memory_percent is None:
        parser.error("choose memory to allocate: --size or --percent")

    available_bytes = available_memory_bytes()
    target_bytes = args.memory_size
    if target_bytes is None:
        target_bytes = int(available_bytes * args.memory_percent / 100)
    if target_bytes >= available_bytes:
        raise RuntimeError(
            f"requested {target_bytes} byte(s), but only {available_bytes} byte(s) are available"
        )

    chunks: list[bytearray] = []
    remaining = target_bytes
    print(
        f"Allocating {target_bytes} byte(s) of host memory; "
        f"{available_bytes} byte(s) currently available."
    )
    while remaining > 0:
        chunk_len = min(remaining, args.chunk_size)
        chunk = bytearray(chunk_len)
        chunk[::4096] = b"\x01" * ((chunk_len + 4095) // 4096)
        chunks.append(chunk)
        remaining -= chunk_len

    print("Memory allocated. Press Ctrl-C to release.")
    try:
        if args.duration == 0:
            while True:
                time.sleep(1)
        else:
            time.sleep(args.duration)
    except KeyboardInterrupt:
        print("Releasing memory...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
