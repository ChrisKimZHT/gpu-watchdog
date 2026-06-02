from __future__ import annotations

import sys
from typing import Any, Dict, Iterable, Optional

from .constants import DEFAULT_COOLDOWN_SECONDS
from .models import RuleResult


def warn_skip(scope: str, exc: BaseException) -> None:
    print(f"{scope} unavailable; skipping related rules: {exc}", file=sys.stderr)


def pct(value: float) -> str:
    return f"{value:.1f}%"


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


def event_kind(rule_kind: str, rule: Dict[str, Any]) -> str:
    if "event" in rule:
        return str(rule["event"])
    return "alert" if rule_kind == "busy" else "reminder"


def rule_notify(rule: Dict[str, Any]) -> bool:
    return bool(rule.get("notify", True))


def rule_cooldown(rule: Dict[str, Any], config: Dict[str, Any]) -> float:
    return float(
        rule.get(
            "cooldown_seconds",
            config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS),
        )
    )


def build_result(
    rule: Dict[str, Any],
    rule_id: str,
    triggered: bool,
    title: str,
    body: str,
    kind: str,
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
    )
