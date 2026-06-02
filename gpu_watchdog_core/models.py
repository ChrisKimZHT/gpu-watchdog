from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ResourceUsage:
    total: float
    used: float
    percent: float


@dataclass
class TriggerState:
    active: bool = False
    last_trigger_at: float = 0.0


@dataclass
class RuleResult:
    rule_id: str
    triggered: bool
    title: str
    body: str
    kind: str
    command: Optional[Any]
    notify: bool
    cooldown_seconds: float
