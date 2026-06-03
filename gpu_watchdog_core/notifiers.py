from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Iterable, List

from .log import logger
from .models import NotificationKind


class Notifier:
    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        raise NotImplementedError


class LoggerNotifier(Notifier):
    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        if kind == "reminder":
            logger.warning("%s | %s | %s", kind.upper(), title, body)
        else: # kind == "alert"
            logger.critical("%s | %s | %s", kind.upper(), title, body)


class BarkNotifier(Notifier):
    """Bark notifier with user-facing options passed through."""

    PROJECT_KEYS = {"enabled", "server", "device_key", "timeout_seconds", "level"}

    def __init__(self, config: Dict[str, Any]) -> None:
        self.server = config["server"]
        self.device_key = config["device_key"]
        self.timeout_seconds = config["timeout_seconds"]
        self.reminder_level = config["level"]
        self.options = {
            key: value
            for key, value in config.items()
            if key not in self.PROJECT_KEYS and value is not None
        }

    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        payload = dict(self.options)
        payload.update(
            {
                "title": title,
                "body": body,
                "device_key": self.device_key,
                "level": "critical" if kind == "alert" else self.reminder_level,
            }
        )
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.server}/push",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            resp.read()


class NotificationHub:
    def __init__(self, notifiers: Iterable[Notifier]) -> None:
        self.notifiers = list(notifiers) or [LoggerNotifier()]

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "NotificationHub":
        notifiers: List[Notifier] = [LoggerNotifier()]
        notifier_config = config["notifiers"]

        bark_config = notifier_config.get("bark")
        if bark_config and bark_config["enabled"]:
            notifiers.append(BarkNotifier(bark_config))

        return cls(notifiers)

    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(title, body, kind)
            except Exception as exc:
                logger.warning("Notifier %s failed: %s", type(notifier).__name__, exc)
