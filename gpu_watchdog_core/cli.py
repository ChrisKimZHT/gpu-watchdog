from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from .diagnostics import print_samples
from .log import configure_logging, logger
from .watchdog import Watchdog


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    return config


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-dependency Linux resource watchdog for GPU training hosts")
    parser.add_argument("--config", help="Path to JSON config file")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--samples", action="store_true", help="Print current sampled metrics and exit")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    # Keep argv injectable so tests and library callers can exercise CLI behavior
    # without mutating sys.argv. Passing argv makes argparse ignore the real
    # command line; None preserves argparse's normal sys.argv[1:] path.
    args = parse_args(argv)
    config = load_config(args.config) if args.config else {}
    configure_logging(str(config.get("log_level", "INFO")))

    if args.samples:
        print_samples()
        return 0

    if not args.config:
        logger.error("--config is required unless --samples is used")
        return 2

    interval_seconds = float(config["interval_seconds"])
    watchdog = Watchdog(config)

    if args.once:
        watchdog.run_once()
    else:
        watchdog.run_forever(interval_seconds)
    return 0
