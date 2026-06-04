from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import normalize_config
from .diagnostics import print_samples
from .log import configure_logging, logger
from . import __version__
from .watchdog import Watchdog

DEFAULT_CONFIG_PATH = "config.json"
EMBEDDED_CONFIG = ""
ConfigSignature = Tuple[int, int]


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    return normalize_config(config)


def load_config_text(config_text: str) -> Dict[str, Any]:
    config = json.loads(config_text)
    return normalize_config(config)


@dataclass
class ConfigFileReloader:
    path: str
    signature: Optional[ConfigSignature] = None

    def load(self) -> Dict[str, Any]:
        config = load_config(self.path)
        self.signature = self._signature()
        return config

    def reload_if_changed(self) -> Optional[Dict[str, Any]]:
        try:
            signature = self._signature()
        except OSError as exc:
            logger.error("Config file %s is unavailable; keeping current config: %s", self.path, exc)
            return None

        if signature == self.signature:
            return None

        self.signature = signature
        try:
            config = load_config(self.path)
        except Exception:
            logger.exception("Failed to reload config file %s; keeping current config", self.path)
            return None

        configure_logging(config["log_level"])
        logger.info("Reloaded config file %s", self.path)
        return config

    def _signature(self) -> ConfigSignature:
        stat_result = os.stat(self.path)
        return stat_result.st_mtime_ns, stat_result.st_size


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
    embedded_config = EMBEDDED_CONFIG.strip()
    config_reloader: Optional[ConfigFileReloader] = None

    if args.config:  # if --config is provided, load it
        config_reloader = ConfigFileReloader(args.config)
        config = config_reloader.load()
    elif os.path.exists(DEFAULT_CONFIG_PATH):  # if default config file exists, load it
        config_reloader = ConfigFileReloader(DEFAULT_CONFIG_PATH)
        config = config_reloader.load()
    elif embedded_config:  # if EMBEDDED_CONFIG is set, load it as the last fallback
        config = load_config_text(embedded_config)
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
        watchdog.run_forever(config_reloader.reload_if_changed if config_reloader is not None else None)
    return 0
