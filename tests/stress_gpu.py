#!/usr/bin/env python3
"""Burn compute and/or allocate memory on a selected CUDA GPU."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fully occupy CUDA GPU compute, memory, or both."
    )
    parser.add_argument("--gpu", type=int, default=0, help="CUDA GPU index, default: 0")
    parser.add_argument(
        "--compute",
        action="store_true",
        help="run repeated matrix multiplication to occupy GPU compute",
    )
    parser.add_argument(
        "--matrix-size",
        type=positive_int,
        default=8192,
        help="square matrix size used for repeated matmul, default: 8192",
    )
    memory_group = parser.add_mutually_exclusive_group()
    memory_group.add_argument(
        "--memory-size",
        "--size",
        dest="memory_size",
        type=parse_size,
        help="GPU memory to allocate, e.g. 4G",
    )
    memory_group.add_argument(
        "--memory-percent",
        "--percent",
        dest="memory_percent",
        type=percent,
        help="percent of currently free GPU memory to allocate",
    )
    parser.add_argument(
        "--memory-chunk-size",
        "--chunk-size",
        dest="memory_chunk_size",
        type=parse_size,
        default=parse_size("256M"),
        help="GPU memory allocation chunk size, default: 256M",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=non_negative_float,
        default=0.0,
        help="seconds to run; 0 means until Ctrl-C, default: 0",
    )
    args = parser.parse_args()
    if not args.compute and args.memory_size is None and args.memory_percent is None:
        parser.error("choose at least one load target: --compute, --size, or --percent")
    return args


def create_compute_tensors(torch, device, matrix_size: int):
    a = torch.randn((matrix_size, matrix_size), device=device, dtype=torch.float32)
    b = torch.randn((matrix_size, matrix_size), device=device, dtype=torch.float32)
    return a, b


def allocate_gpu_memory(torch, device, gpu: int, target_bytes: int, chunk_size: int) -> list:
    free_bytes, total_bytes = torch.cuda.mem_get_info(device)
    if target_bytes >= free_bytes:
        raise RuntimeError(
            f"requested {target_bytes} byte(s), but only {free_bytes} byte(s) are free on GPU {gpu}"
        )

    tensors = []
    remaining = target_bytes
    print(
        f"Allocating {target_bytes} byte(s) on GPU {gpu}; "
        f"{free_bytes} of {total_bytes} byte(s) currently free."
    )
    while remaining > 0:
        elements = min(remaining, chunk_size)
        tensors.append(torch.empty((elements,), dtype=torch.uint8, device=device))
        remaining -= elements

    torch.cuda.synchronize(device)
    return tensors


def main() -> int:
    args = parse_args()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Install a CUDA-enabled PyTorch build.")

    device = torch.device(f"cuda:{args.gpu}")
    torch.cuda.set_device(device)

    compute_enabled = args.compute
    memory_enabled = args.memory_size is not None or args.memory_percent is not None

    compute_tensors = None
    if compute_enabled:
        compute_tensors = create_compute_tensors(torch, device, args.matrix_size)

    memory_tensors = []
    if memory_enabled:
        free_bytes, _ = torch.cuda.mem_get_info(device)
        target_bytes = args.memory_size
        if target_bytes is None:
            target_bytes = int(free_bytes * args.memory_percent / 100)
        memory_tensors = allocate_gpu_memory(
            torch,
            device,
            args.gpu,
            target_bytes,
            args.memory_chunk_size,
        )

    stop_at = None if args.duration == 0 else time.monotonic() + args.duration
    load_name = "+".join(
        name
        for name, enabled in (("compute", compute_enabled), ("memory", memory_enabled))
        if enabled
    )
    print(f"Running GPU {args.gpu} {load_name} load. Press Ctrl-C to stop.")
    try:
        if compute_enabled:
            a, b = compute_tensors
            with torch.no_grad():
                while stop_at is None or time.monotonic() < stop_at:
                    a = torch.matmul(a, b)
                    a.relu_()
                    torch.cuda.synchronize(device)
        else:
            while stop_at is None or time.monotonic() < stop_at:
                time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping GPU load...")

    # Keep references alive until the load is done.
    del memory_tensors
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
