from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, cast

from .log import logger
from .models import NotificationKind, ResourceUsage, RuleResult


def warn_skip(scope: str, exc: BaseException) -> None:
    logger.warning("%s unavailable; skipping related rules: %s", scope, exc)


def pct(value: float) -> str:
    return f"{value:.1f}%"


def human_bytes(value: float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    size = float(value)
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PiB"


def mib(value: float) -> str:
    return f"{value:.1f}MiB"


def usage_text(usage: ResourceUsage) -> str:
    return f"{pct(usage.percent)} ({human_bytes(usage.used)}/{human_bytes(usage.total)})"


def normalize_ids(values: Optional[Iterable[Any]]) -> Optional[set]:
    if values is None:
        return None
    return {str(value) for value in values}


def compare(kind: str, value: float, threshold: float) -> bool:
    if kind == "busy":
        return value >= threshold
    if kind == "idle":
        return value <= threshold
    raise ValueError("rule kind must be 'busy' or 'idle'")


def event_kind(rule_kind: str, rule: Dict[str, Any]) -> NotificationKind:
    if "event" in rule:
        event = str(rule["event"])
        if event not in {"alert", "reminder"}:
            raise ValueError("rule event must be 'alert' or 'reminder'")
        return cast(NotificationKind, event)
    return "alert" if rule_kind == "busy" else "reminder"


def rule_notify(rule: Dict[str, Any]) -> bool:
    return bool(rule.get("notify", True))


def rule_cooldown(rule: Dict[str, Any], config: Dict[str, Any]) -> float:
    return float(rule.get("cooldown_seconds", config["cooldown_seconds"]))


def rule_pending_period(rule: Dict[str, Any]) -> float:
    period = float(rule.get("pending_period", 0))
    if period < 0:
        raise ValueError("rule pending_period must be greater than or equal to 0")
    return period


def build_result(
    rule: Dict[str, Any],
    rule_id: str,
    triggered: bool,
    title: str,
    body: str,
    kind: NotificationKind,
    config: Dict[str, Any],
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        triggered=triggered,
        title=title,
        body=body,
        kind=kind,
        command=rule.get("command"),
        notify=rule_notify(rule),
        cooldown_seconds=rule_cooldown(rule, config),
        pending_period=rule_pending_period(rule),
    )
