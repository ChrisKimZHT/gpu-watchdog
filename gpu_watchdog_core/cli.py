from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from .constants import DEFAULT_INTERVAL_SECONDS
from .sampler import ResourceSampler
from .utils import pct
from .watchdog import Watchdog


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    return config


def print_samples() -> None:
    print("CPU pressure:")
    try:
        print(json.dumps(ResourceSampler.cpu_pressure(), indent=2, sort_keys=True))
    except Exception as exc:
        print(f"  unavailable: {exc}")

    print("Memory:")
    try:
        print(f"  used_percent={pct(ResourceSampler.memory_used_percent())}")
    except Exception as exc:
        print(f"  unavailable: {exc}")

    print("Disks:")
    for mount_point in ("/",):
        try:
            print(f"  {mount_point} used_percent={pct(ResourceSampler.disk_used_percent(mount_point))}")
        except Exception as exc:
            print(f"  {mount_point} unavailable: {exc}")

    print("GPUs:")
    try:
        for gpu in ResourceSampler.gpus():
            print(
                f"  id={gpu.id} uuid={gpu.uuid} "
                f"compute={pct(float(gpu.gpu_util))} memory={pct(float(gpu.mem_util))}"
            )
    except Exception as exc:
        print(f"  unavailable: {exc}")

    print("GPU processes:")
    try:
        for proc in ResourceSampler.gpu_processes():
            print(f"  pid={proc.pid} gpu_id={proc.gpu_id} name={proc.process_name} used_memory={proc.used_memory}MB")
    except Exception as exc:
        print(f"  unavailable: {exc}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-dependency Linux resource watchdog for GPU training hosts")
    parser.add_argument("--config", help="Path to JSON config file")
    parser.add_argument("--interval", type=float, help="Override interval_seconds from config")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--samples", action="store_true", help="Print current sampled metrics and exit")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.samples:
        print_samples()
        return 0

    if not args.config:
        print("--config is required unless --samples is used", file=sys.stderr)
        return 2

    config = load_config(args.config)
    interval_seconds = float(args.interval or config.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
    watchdog = Watchdog(config)

    if args.once:
        watchdog.run_once()
    else:
        watchdog.run_forever(interval_seconds)
    return 0
