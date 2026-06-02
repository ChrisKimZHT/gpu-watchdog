from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from .constants import DEFAULT_INTERVAL_SECONDS
from .log import configure_logging, logger
from .sampler import ResourceSampler
from .utils import mib, pct, usage_text
from .watchdog import Watchdog


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    return config


def print_samples() -> None:
    logger.info("CPU pressure:")
    try:
        logger.info("\n%s", json.dumps(ResourceSampler.cpu_pressure(), indent=2, sort_keys=True))
    except Exception as exc:
        logger.info("  unavailable: %s", exc)

    logger.info("Memory:")
    try:
        logger.info("  %s", usage_text(ResourceSampler.memory_usage()))
    except Exception as exc:
        logger.info("  unavailable: %s", exc)

    logger.info("Disks:")
    for mount_point in ("/",):
        try:
            logger.info("  %s %s", mount_point, usage_text(ResourceSampler.disk_usage(mount_point)))
        except Exception as exc:
            logger.info("  %s unavailable: %s", mount_point, exc)

    logger.info("GPUs:")
    try:
        for gpu in ResourceSampler.gpus():
            logger.info(
                "  id=%s uuid=%s compute=%s memory=%s / %s (%s)",
                gpu.id,
                gpu.uuid,
                pct(float(gpu.gpu_util)),
                mib(float(gpu.mem_used)),
                mib(float(gpu.mem_total)),
                pct(float(gpu.mem_util)),
            )
    except Exception as exc:
        logger.info("  unavailable: %s", exc)

    logger.info("GPU processes:")
    try:
        for proc in ResourceSampler.gpu_processes():
            logger.info(
                "  pid=%s gpu_id=%s name=%s used_memory=%sMB",
                proc.pid,
                proc.gpu_id,
                proc.process_name,
                proc.used_memory,
            )
    except Exception as exc:
        logger.info("  unavailable: %s", exc)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-dependency Linux resource watchdog for GPU training hosts")
    parser.add_argument("--config", help="Path to JSON config file")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--samples", action="store_true", help="Print current sampled metrics and exit")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config) if args.config else {}
    configure_logging(str(config.get("log_level", "INFO")))

    if args.samples:
        print_samples()
        return 0

    if not args.config:
        logger.error("--config is required unless --samples is used")
        return 2

    interval_seconds = float(config.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
    watchdog = Watchdog(config)

    if args.once:
        watchdog.run_once()
    else:
        watchdog.run_forever(interval_seconds)
    return 0
