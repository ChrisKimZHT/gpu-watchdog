from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .log import logger
from .models import RuleResult
from .sampler import ResourceSampler
from .utils import build_result, compare, event_kind, mib, normalize_ids, pct, usage_text, warn_skip


class RuleEvaluator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.rules = self.config.get("rules", [])

    def evaluate(self) -> Iterable[RuleResult]:
        for rule in self.rules:
            rule_type = str(rule["type"])
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
        metric = str(options.get("metric", "some.avg10"))
        threshold = float(options["threshold"])
        kind = str(options.get("kind", "busy"))
        value = metrics.get(metric)
        if value is None:
            logger.warning("CPU pressure metric %r is unavailable; skipping", metric)
            return
        triggered = compare(kind, value, threshold)
        title = str(rule.get("title", f"CPU {kind}: {metric} {pct(value)}"))
        body = str(rule.get("body", f"CPU pressure {metric} is {pct(value)}, threshold {pct(threshold)}"))
        rule_id = str(rule["id"])
        yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def evaluate_memory_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        try:
            usage = ResourceSampler.memory_usage()
        except Exception as exc:
            warn_skip("memory", exc)
            return

        options = self.rule_options(rule)
        threshold = float(options["threshold"])
        kind = str(options.get("kind", "busy"))
        triggered = compare(kind, usage.percent, threshold)
        title = str(rule.get("title", f"MEM {kind}: {usage_text(usage)}"))
        body = str(rule.get("body", f"Memory used is {usage_text(usage)}, threshold {pct(threshold)}"))
        rule_id = str(rule["id"])
        yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def evaluate_disk_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        options = self.rule_options(rule)
        mount_point = str(options["mount"])
        try:
            usage = ResourceSampler.disk_usage(mount_point)
        except Exception as exc:
            warn_skip(f"disk {mount_point}", exc)
            return
        threshold = float(options["threshold"])
        kind = str(options.get("kind", "busy"))
        triggered = compare(kind, usage.percent, threshold)
        title = str(rule.get("title", f"Disk {kind}: {mount_point} {usage_text(usage)}"))
        body = str(rule.get("body", f"Disk {mount_point} used is {usage_text(usage)}, threshold {pct(threshold)}"))
        rule_id = str(rule["id"])
        yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def evaluate_gpu_rule(self, rule: Dict[str, Any]) -> Iterable[RuleResult]:
        try:
            gpus = ResourceSampler.gpus()
        except Exception as exc:
            warn_skip("GPU metrics", exc)
            return

        options = self.rule_options(rule)
        selected_ids = normalize_ids(options.get("ids"))
        selected_uuids = normalize_ids(options.get("uuids"))
        selected = [
            gpu
            for gpu in gpus
            if (selected_ids is None or str(gpu.id) in selected_ids)
            and (selected_uuids is None or str(gpu.uuid) in selected_uuids)
        ]
        if not selected:
            logger.warning("GPU rule %r matched no GPUs; skipping", rule["id"])
            return

        mode = str(options.get("mode", "both"))
        kind = str(options.get("kind", "idle"))
        match = str(options.get("match", "any"))
        checks = self.gpu_checks(options, selected, mode, kind)
        if match == "all":
            triggered = all(item[0] for item in checks)
        elif match == "any":
            triggered = any(item[0] for item in checks)
        else:
            raise ValueError("GPU rule match must be 'any' or 'all'")

        metric_text = ", ".join(item[1] for item in checks)
        title = str(rule.get("title", f"GPU {kind}: {metric_text}"))
        body = str(rule.get("body", metric_text))
        rule_id = str(rule["id"])
        yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def gpu_checks(
        self,
        options: Dict[str, Any],
        gpus: Iterable[Any],
        mode: str,
        kind: str,
    ) -> List[Tuple[bool, str]]:
        checks: List[Tuple[bool, str]] = []
        use_compute = mode in {"compute", "both"}
        use_memory = mode in {"memory", "both"}
        if not use_compute and not use_memory:
            raise ValueError("GPU rule mode must be 'compute', 'memory', or 'both'")

        for gpu in gpus:
            if use_compute:
                threshold = float(
                    options.get("compute_threshold", options.get("threshold", 5 if kind == "idle" else 90))
                )
                value = float(gpu.gpu_util)
                checks.append(
                    (
                        compare(kind, value, threshold),
                        f"GPU {gpu.id} compute {pct(value)} threshold {pct(threshold)}",
                    )
                )
            if use_memory:
                threshold = float(
                    options.get("memory_threshold", options.get("threshold", 5 if kind == "idle" else 90))
                )
                value = float(gpu.mem_util)
                checks.append(
                    (
                        compare(kind, value, threshold),
                        (
                            f"GPU {gpu.id} memory {mib(float(gpu.mem_used))} / "
                            f"{mib(float(gpu.mem_total))} ({pct(value)}) threshold {pct(threshold)}"
                        ),
                    )
                )
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
        name = str(options.get("name", ",".join(str(pid) for pid in pids)))
        title = str(rule.get("title", f"GPU process disappeared: {name}"))
        body = str(
            rule.get(
                "body",
                (
                    f"Missing GPU process PID(s): {missing_pids}; "
                    f"still present PID(s): {present_pids}"
                ),
            )
        )
        rule_id = str(rule["id"])
        yield build_result(rule, rule_id, triggered, title, body, event_kind("busy", rule), self.config)

    @staticmethod
    def process_rule_pids(options: Dict[str, Any]) -> List[int]:
        raw_pids = options["pids"]
        return [int(pid) for pid in raw_pids]
