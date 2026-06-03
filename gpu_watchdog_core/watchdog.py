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
        total_count = 0
        passed_count = 0
        failed_rule_ids = []
        for result in self.evaluator.evaluate():
            total_count += 1
            if not result.triggered:
                passed_count += 1
            else:
                failed_rule_ids.append(result.rule_id)
            logger.debug("Evaluation result: %s", result)
            self.handle_result(result, now)
        time_usage = (time.time() - now) * 1000
        failed_text = ", ".join(failed_rule_ids) if failed_rule_ids else "none"
        logger.info(
            f"Evaluation summary: {passed_count}/{total_count} passed; failed: {failed_text}; Time used: {time_usage:.2f} ms",
        )

    def handle_result(self, result: RuleResult, now: float) -> None:
        state = self.states.setdefault(result.rule_id, TriggerState())
        should_fire = False
        if result.triggered:
            # Enter or continue the pending window for this uninterrupted trigger.
            if state.triggered_since is None:
                state.triggered_since = now
            elapsed = now - state.triggered_since
            if elapsed < result.pending_period:
                state.active = True
                return

            # Once pending has passed, fire immediately for a new trigger streak;
            # after that, repeated notifications are gated by cooldown.
            first_fire_for_current_trigger = (
                state.last_trigger_at <= 0 or state.last_trigger_at < state.triggered_since
            )
            should_fire = first_fire_for_current_trigger or (
                result.cooldown_seconds > 0
                and now - state.last_trigger_at >= result.cooldown_seconds
            )
            state.active = True
        else:
            # A healthy evaluation ends the trigger streak and resets pending.
            state.active = False
            state.triggered_since = None

        if not should_fire:
            return

        # Notifications and callbacks share the same firing decision.
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
