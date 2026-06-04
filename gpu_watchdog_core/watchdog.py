from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .callbacks import CommandRunner
from .config import normalize_config
from .log import logger
from .models import RuleResult, TriggerState
from .notifiers import NotificationHub
from .rules import RuleEvaluator


class Watchdog:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = normalize_config(config)
        self.evaluator = RuleEvaluator(self.config)
        self.notifier = NotificationHub.from_config(self.config)
        self.states: Dict[str, TriggerState] = {}

    def reload_config(self, config: Dict[str, Any]) -> None:
        self.config = normalize_config(config)
        self.evaluator = RuleEvaluator(self.config)
        self.notifier = NotificationHub.from_config(self.config)
        active_rule_ids = {rule["id"] for rule in self.config["rules"]}
        self.states = {rule_id: state for rule_id, state in self.states.items() if rule_id in active_rule_ids}

    def run_forever(self, config_reloader: Optional[Callable[[], Optional[Dict[str, Any]]]] = None) -> None:
        while True:
            if config_reloader is not None:
                config = config_reloader()
                if config is not None:  # Reload if changed.
                    self.reload_config(config)
            self.run_once()
            time.sleep(self.config["interval_seconds"])

    def run_once(self) -> None:
        now = time.time()
        total_count = 0
        passed_count = 0
        pending_rules = []
        cooldown_rules = []
        for result in self.evaluator.evaluate():
            total_count += 1
            if not result.triggered:
                passed_count += 1
            logger.debug("Evaluation result: %s", result)
            self.handle_result(result, now)
            if self._is_pending(result, now):
                pending_rules.append((result.rule_id, self._pending_seconds_remaining(result, now)))
            if self._is_in_cooldown(result, now):
                cooldown_rules.append((result.rule_id, self._cooldown_seconds_remaining(result, now)))
        time_usage = (time.time() - now) * 1000
        logger.info(
            f"Summary: {passed_count}/{total_count} passed; "
            f"pending: {len(pending_rules)} [{self._format_rule_statuses(pending_rules)}]; "
            f"cooldown: {len(cooldown_rules)} [{self._format_rule_statuses(cooldown_rules)}]; "
            f"Time used: {time_usage:.2f} ms",
        )

    def _is_pending(self, result: RuleResult, now: float) -> bool:
        state = self.states.get(result.rule_id)
        if not result.triggered or state is None or state.triggered_since is None:
            return False
        return now - state.triggered_since < result.pending_period

    def _is_in_cooldown(self, result: RuleResult, now: float) -> bool:
        state = self.states.get(result.rule_id)
        if not result.triggered or state is None or state.triggered_since is None:
            return False
        if now - state.triggered_since < result.pending_period:
            return False
        return (
            result.cooldown_seconds > 0
            and state.last_trigger_at > 0
            and now - state.last_trigger_at < result.cooldown_seconds
        )

    def _pending_seconds_remaining(self, result: RuleResult, now: float) -> float:
        state = self.states.get(result.rule_id)
        if state is None or state.triggered_since is None:
            return 0.0
        return max(0.0, result.pending_period - (now - state.triggered_since))

    def _cooldown_seconds_remaining(self, result: RuleResult, now: float) -> float:
        state = self.states.get(result.rule_id)
        if state is None:
            return 0.0
        return max(0.0, result.cooldown_seconds - (now - state.last_trigger_at))

    @staticmethod
    def _format_rule_statuses(rule_statuses: List[Tuple[str, float]]) -> str:
        if not rule_statuses:
            return "none"
        return ", ".join(
            f"{rule_id}({seconds:.1f}s)"
            for rule_id, seconds in rule_statuses
        )

    def handle_result(self, result: RuleResult, now: float) -> None:
        state = self.states.setdefault(result.rule_id, TriggerState())
        should_fire = False
        if result.triggered:
            # Track the start of this trigger streak.
            if state.triggered_since is None:
                state.triggered_since = now
            if self._is_pending(result, now):
                state.active = True
                return

            # Skip repeated notifications during cooldown.
            if self._is_in_cooldown(result, now):
                state.active = True
                return

            should_fire = True
            state.active = True
        else:
            # Healthy again; clear streak state.
            state.active = False
            state.triggered_since = None
            state.last_trigger_at = 0.0

        if not should_fire:
            return

        # Notify and run callbacks together.
        state.last_trigger_at = now
        if result.notify:
            self.notifier.notify(result.title, result.body, kind=result.kind)
        event_env = {  # default env vars for callbacks
            "GPU_WATCHDOG_RULE": result.rule_id,
            "GPU_WATCHDOG_KIND": result.kind,
            "GPU_WATCHDOG_TITLE": result.title,
            "GPU_WATCHDOG_BODY": result.body,
        }
        event_env.update(result.env)  # add extra env vars from the result
        CommandRunner.run(result.command, event_env)
