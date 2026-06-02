from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List

from .log import logger, notification_logger


class Notifier:
    def notify(self, title: str, body: str, level: str, kind: str) -> None:
        raise NotImplementedError


class LoggerNotifier(Notifier):
    def notify(self, title: str, body: str, level: str, kind: str) -> None:
        notification_logger.info("%s level=%s %s: %s", kind.upper(), level, title, body)


class BarkNotifier(Notifier):
    """Bark notifier with user-facing options passed through."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.server = str(config.get("server", "https://api.day.app")).rstrip("/")
        self.device_key = str(config.get("device_key", "")).strip()
        self.timeout_seconds = float(config.get("timeout_seconds", 10))
        self.options = {
            key: value
            for key, value in config.items()
            if key in {"isArchive", "icon", "group", "level"} and value is not None
        }
        if not self.device_key:
            raise ValueError("notifiers.bark.device_key is required when Bark is enabled")

    def notify(self, title: str, body: str, level: str, kind: str) -> None:
        params = dict(self.options)
        params["level"] = "critical" if kind == "alert" else level

        path = "/".join(
            urllib.parse.quote(part, safe="")
            for part in (self.device_key, title, body)
        )
        url = f"{self.server}/{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            resp.read()


class NotificationHub:
    def __init__(self, notifiers: Iterable[Notifier]) -> None:
        self.notifiers = list(notifiers) or [LoggerNotifier()]

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "NotificationHub":
        notifiers: List[Notifier] = []
        notifier_config = config.get("notifiers", {})

        bark_config = notifier_config.get("bark")
        if bark_config and bark_config.get("enabled", True):
            notifiers.append(BarkNotifier(bark_config))

        if config.get("log_notifications", config.get("stdout", True)):
            notifiers.append(LoggerNotifier())

        return cls(notifiers)

    def notify(self, title: str, body: str, level: str, kind: str) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(title, body, level, kind)
            except Exception as exc:
                logger.warning("Notifier %s failed: %s", type(notifier).__name__, exc)
