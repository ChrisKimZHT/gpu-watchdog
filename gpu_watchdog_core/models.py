from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional


NotificationKind = Literal["alert", "reminder"]


@dataclass(frozen=True)
class ResourceUsage:
    total: float
    used: float
    percent: float


@dataclass
class TriggerState:
    active: bool = False
    last_trigger_at: float = 0.0
    triggered_since: Optional[float] = None


@dataclass
class RuleResult:
    rule_id: str
    triggered: bool
    title: str
    body: str
    kind: NotificationKind
    command: Optional[Any]
    notify: bool
    cooldown_seconds: float
    pending_period: float
