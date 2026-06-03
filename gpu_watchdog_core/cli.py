from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import normalize_config
from .diagnostics import print_samples
from .log import configure_logging, logger
from . import __version__
from .watchdog import Watchdog

DEFAULT_CONFIG_PATH = Path("config.json")
EMBEDDED_CONFIG = ""


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    return normalize_config(config)


def load_config_text(config_text: str) -> Dict[str, Any]:
    config = json.loads(config_text)
    return normalize_config(config)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-dependency Linux resource watchdog for GPU training hosts")
    parser.add_argument("--version", action="version", version=f"gpu-watchdog {__version__} (https://github.com/ChrisKimZHT/gpu-watchdog)")
    parser.add_argument("--config", help="Path to JSON config file")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--samples", action="store_true", help="Print current sampled metrics and exit")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    # Keep argv injectable so tests and library callers can exercise CLI behavior
    # without mutating sys.argv. Passing argv makes argparse ignore the real
    # command line; None preserves argparse's normal sys.argv[1:] path.
    args = parse_args(argv)
    config_path = args.config
    embedded_config = EMBEDDED_CONFIG.strip()

    if config_path:  # if --config is provided, load it
        config = load_config(config_path)
    elif embedded_config:  # if EMBEDDED_CONFIG is set, load it
        config = load_config_text(embedded_config)
    elif DEFAULT_CONFIG_PATH.exists():  # if default config file exists, load it
        config_path = str(DEFAULT_CONFIG_PATH)
        config = load_config(config_path)
    else:  # if no config is found, config is empty and will trigger an error later
        config = {}

    configure_logging(config["log_level"] if config else "INFO")

    if args.samples:
        print_samples()
        return 0

    if not config:
        logger.error("--config is required unless ./config.json exists")
        return 2

    watchdog = Watchdog(config)

    if args.once:
        watchdog.run_once()
    else:
        watchdog.run_forever(config["interval_seconds"])
    return 0
