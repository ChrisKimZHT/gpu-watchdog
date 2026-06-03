from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
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

    def __init__(self, config: Dict[str, Any]) -> None:
        self.server = config["server"]
        self.device_key = config["device_key"]
        self.timeout_seconds = config["timeout_seconds"]
        self.reminder_level = config["level"]
        self.passthrough = config["passthrough"]

    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        payload = dict(self.passthrough)
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


class SMTPNotifier(Notifier):
    """SMTP email notifier using only Python standard-library modules."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.host = config["host"]
        self.port = config["port"]
        self.username = config["username"]
        self.password = config["password"]
        self.from_addr = config["from_addr"]
        self.to_addrs = config["to_addrs"]
        self.timeout_seconds = config["timeout_seconds"]
        self.use_ssl = config["ssl"]
        self.starttls = config["starttls"]

    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        message = EmailMessage()
        message["Subject"] = f"[GPU Watchdog {kind.upper()}] {title}"
        message["From"] = self.from_addr
        message["To"] = ", ".join(self.to_addrs)
        message.set_content(f"{kind.upper()}: {title}\n\n{body}")

        context = ssl.create_default_context()
        if self.use_ssl:
            with smtplib.SMTP_SSL(
                self.host,
                self.port,
                timeout=self.timeout_seconds,
                context=context,
            ) as client:
                self._send(client, message)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as client:
                if self.starttls:
                    client.starttls(context=context)
                self._send(client, message)

    def _send(self, client: smtplib.SMTP, message: EmailMessage) -> None:
        if self.username:
            client.login(self.username, self.password)
        client.send_message(message, from_addr=self.from_addr, to_addrs=self.to_addrs)


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

        smtp_config = notifier_config.get("smtp")
        if smtp_config and smtp_config["enabled"]:
            notifiers.append(SMTPNotifier(smtp_config))

        return cls(notifiers)

    def notify(self, title: str, body: str, kind: NotificationKind) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(title, body, kind)
                logger.info("Notifier %s sent successfully", type(notifier).__name__)
            except Exception as exc:
                logger.warning("Notifier %s failed: %s", type(notifier).__name__, exc)
