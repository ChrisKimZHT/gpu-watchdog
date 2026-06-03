from __future__ import annotations

import time
from typing import Any, Dict

from .callbacks import CommandRunner
from .log import logger
from .models import RuleResult, TriggerState
from .notifiers import NotificationHub
from .rules import RuleEvaluator


class Watchdog:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.evaluator = RuleEvaluator(config)
        self.notifier = NotificationHub.from_config(config)
        self.states: Dict[str, TriggerState] = {}

    def run_forever(self, interval_seconds: float) -> None:
        while True:
            self.run_once()
            time.sleep(interval_seconds)

    def run_once(self) -> None:
        now = time.time()
        for result in self.evaluator.evaluate():
            logger.debug("Evaluation result: %s", result)
            self.handle_result(result, now)

    def handle_result(self, result: RuleResult, now: float) -> None:
        state = self.states.setdefault(result.rule_id, TriggerState())
        should_fire = False
        if result.triggered:
            should_fire = (not state.active) or (
                result.cooldown_seconds > 0
                and now - state.last_trigger_at >= result.cooldown_seconds
            )
            state.active = True
        else:
            state.active = False

        if not should_fire:
            return

        state.last_trigger_at = now
        if result.notify:
            self.notifier.notify(result.title, result.body, kind=result.kind)
        CommandRunner.run(
            result.command,
            {
                "GPU_WATCHDOG_RULE": result.rule_id,
                "GPU_WATCHDOG_KIND": result.kind,
                "GPU_WATCHDOG_TITLE": result.title,
                "GPU_WATCHDOG_BODY": result.body,
            },
        )
