from __future__ import annotations

from typing import Any, Dict, Optional

from .log import logger
from .models import ResourceUsage, RuleResult


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


def compare(kind: str, value: float, threshold: float) -> bool:
    if kind == "busy":
        return value >= threshold
    if kind == "idle":
        return value <= threshold
    raise ValueError("rule kind must be 'busy' or 'idle'")


def build_result(
    rule: Dict[str, Any],
    rule_id: str,
    triggered: bool,
    title: str,
    body: str,
    env: Optional[Dict[str, str]] = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        triggered=triggered,
        title=title,
        body=body,
        kind=rule["event"],
        command=rule.get("command"),
        notify=rule["notify"],
        cooldown_seconds=rule["cooldown_seconds"],
        pending_period=rule["pending_period"],
        env=env or {},
    )
