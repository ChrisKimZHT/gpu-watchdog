from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .log import logger
from .models import RuleResult
from .sampler import ResourceSampler
from .utils import build_result, compare, mib, pct, usage_text, warn_skip


class RuleEvaluator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.rules = config["rules"]

    def evaluate(self) -> Iterable[RuleResult]:
        for rule in self.rules:
            rule_type = rule["type"]
            if rule_type == "cpu":
                yield from self.evaluate_cpu_rule(rule)
            elif rule_type == "memory":
                yield from self.evaluate_memory_rule(rule)
            elif rule_type == "disk":
                yield from self.evaluate_disk_rule(rule)
            elif rule_type == "gpu":
                yield from self.evaluate_gpu_rule(rule)
            elif rule_type == "process":
                yield from self.evaluate_process_rule(rule)
            else:
                logger.warning("Unknown rule type %s in rule %s; skipping", rule_type, rule["id"])

    @staticmethod
    def rule_options(rule: Dict[str, Any]) -> Dict[str, Any]:
        return rule["options"]

    def evaluate_cpu_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        try:
            metrics = ResourceSampler.cpu_pressure()
        except FileNotFoundError:
            logger.warning("/proc/pressure/cpu is not available on this host; skipping CPU rules")
            return
        except Exception as exc:
            warn_skip("CPU pressure", exc)
            return

        options = self.rule_options(rule)
        metric = options["metric"]
        threshold = options["threshold"]
        kind = options["kind"]
        value = metrics.get(metric)
        if value is None:
            logger.warning("CPU pressure metric %r is unavailable; skipping", metric)
            return
        triggered = compare(kind, value, threshold)
        title = rule.get("title", f"CPU {kind}: {metric} {pct(value)}")
        body = rule.get("body", f"CPU pressure {metric} is {pct(value)}, threshold {pct(threshold)}")
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body)

    def evaluate_memory_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        try:
            usage = ResourceSampler.memory_usage()
        except Exception as exc:
            warn_skip("memory", exc)
            return

        options = self.rule_options(rule)
        threshold = options["threshold"]
        kind = options["kind"]
        triggered = compare(kind, usage.percent, threshold)
        title = rule.get("title", f"MEM {kind}: {usage_text(usage)}")
        body = rule.get("body", f"Memory used is {usage_text(usage)}, threshold {pct(threshold)}")
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body)

    def evaluate_disk_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        options = self.rule_options(rule)
        mount_point = options["mount"]
        try:
            usage = ResourceSampler.disk_usage(mount_point)
        except Exception as exc:
            warn_skip(f"disk {mount_point}", exc)
            return
        threshold = options["threshold"]
        kind = options["kind"]
        triggered = compare(kind, usage.percent, threshold)
        title = rule.get("title", f"Disk {kind}: {mount_point} {usage_text(usage)}")
        body = rule.get("body", f"Disk {mount_point} used is {usage_text(usage)}, threshold {pct(threshold)}")
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body)

    def evaluate_gpu_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        try:
            gpus = ResourceSampler.gpus()
        except Exception as exc:
            warn_skip("GPU metrics", exc)
            return

        options = self.rule_options(rule)
        selected_gpus = set(options["gpus"]) if "gpus" in options else None
        selected = [
            gpu
            for gpu in gpus
            if selected_gpus is None or str(gpu.id) in selected_gpus
        ]
        if not selected:
            logger.warning("GPU rule %r matched no GPUs; skipping", rule["id"])
            return

        kind = options["kind"]
        gpu_match = options["gpu_match"]
        threshold_match = options["threshold_match"]
        checks = self.gpu_checks(options, selected, kind, threshold_match)
        if gpu_match == "all":
            triggered = all(item[0] for item in checks)
        else:
            triggered = any(item[0] for item in checks)

        metric_text = ", ".join(item[1] for item in checks)
        title = rule.get("title", f"GPU {kind}: {metric_text}")
        body = rule.get("body", metric_text)
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body)

    def gpu_checks(
        self,
        options: Dict[str, Any],
        gpus: Iterable[Any],
        kind: str,
        threshold_match: str,
    ) -> List[Tuple[bool, str]]:
        checks: List[Tuple[bool, str]] = []
        thresholds = options["threshold"]
        use_compute = "compute" in thresholds
        use_memory = "memory" in thresholds

        for gpu in gpus:
            metric_checks: List[Tuple[bool, str]] = []
            if use_compute:
                threshold = thresholds["compute"]
                value = float(gpu.gpu_util)
                metric_checks.append(
                    (
                        compare(kind, value, threshold),
                        f"GPU {gpu.id} compute {pct(value)} threshold {pct(threshold)}",
                    )
                )
            if use_memory:
                threshold = thresholds["memory"]
                value = float(gpu.mem_util)
                metric_checks.append(
                    (
                        compare(kind, value, threshold),
                        (
                            f"GPU {gpu.id} memory {mib(float(gpu.mem_used))} / "
                            f"{mib(float(gpu.mem_total))} ({pct(value)}) threshold {pct(threshold)}"
                        ),
                    )
                )
            if threshold_match == "any":
                triggered = any(item[0] for item in metric_checks)
            else:
                triggered = all(item[0] for item in metric_checks)
            checks.append((triggered, "; ".join(item[1] for item in metric_checks)))
        return checks

    def evaluate_process_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        try:
            gpu_processes = ResourceSampler.gpu_processes()
        except Exception as exc:
            warn_skip("GPU process list", exc)
            return

        gpu_pids = {int(proc.pid) for proc in gpu_processes}
        options = self.rule_options(rule)
        pids = self.process_rule_pids(options)
        missing_pids = [pid for pid in pids if pid not in gpu_pids]
        present_pids = [pid for pid in pids if pid in gpu_pids]
        triggered = bool(missing_pids)
        name = options["name"]
        title = rule.get("title", f"GPU process disappeared: {name}")
        body = rule.get(
            "body",
            (
                f"Missing GPU process PID(s): {missing_pids}; "
                f"still present PID(s): {present_pids}"
            ),
        )
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body)

    @staticmethod
    def process_rule_pids(options: Dict[str, Any]) -> List[int]:
        return options["pids"]
