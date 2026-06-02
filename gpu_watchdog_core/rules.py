from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .log import logger
from .models import RuleResult
from .sampler import ResourceSampler
from .utils import build_result, compare, event_kind, normalize_ids, pct, warn_skip


class RuleEvaluator:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def evaluate(self) -> Iterable[RuleResult]:
        yield from self.evaluate_cpu_rules()
        yield from self.evaluate_memory_rules()
        yield from self.evaluate_disk_rules()
        yield from self.evaluate_gpu_rules()
        yield from self.evaluate_process_rules()

    def evaluate_cpu_rules(self) -> Iterable[RuleResult]:
        rules = self.config.get("resources", {}).get("cpu", [])
        if not rules:
            return
        try:
            metrics = ResourceSampler.cpu_pressure()
        except FileNotFoundError:
            logger.warning("/proc/pressure/cpu is not available on this host; skipping CPU rules")
            return
        except Exception as exc:
            warn_skip("CPU pressure", exc)
            return

        for index, rule in enumerate(rules):
            metric = str(rule.get("metric", "some.avg10"))
            threshold = float(rule["threshold"])
            kind = str(rule.get("kind", "busy"))
            value = metrics.get(metric)
            if value is None:
                logger.warning("CPU pressure metric %r is unavailable; skipping", metric)
                continue
            triggered = compare(kind, value, threshold)
            title = str(rule.get("title", f"CPU {kind}: {metric} {pct(value)}"))
            body = str(rule.get("body", f"CPU pressure {metric} is {pct(value)}, threshold {pct(threshold)}"))
            rule_id = str(rule.get("id", f"cpu:{index}:{metric}:{kind}"))
            yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def evaluate_memory_rules(self) -> Iterable[RuleResult]:
        rules = self.config.get("resources", {}).get("mem", [])
        if not rules:
            return
        try:
            value = ResourceSampler.memory_used_percent()
        except Exception as exc:
            warn_skip("memory", exc)
            return

        for index, rule in enumerate(rules):
            threshold = float(rule["threshold"])
            kind = str(rule.get("kind", "busy"))
            triggered = compare(kind, value, threshold)
            title = str(rule.get("title", f"MEM {kind}: {pct(value)}"))
            body = str(rule.get("body", f"Memory used is {pct(value)}, threshold {pct(threshold)}"))
            rule_id = str(rule.get("id", f"mem:{index}:{kind}"))
            yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def evaluate_disk_rules(self) -> Iterable[RuleResult]:
        rules = self.config.get("resources", {}).get("disk", [])
        for index, rule in enumerate(rules):
            mount_point = str(rule["mount"])
            try:
                value = ResourceSampler.disk_used_percent(mount_point)
            except Exception as exc:
                warn_skip(f"disk {mount_point}", exc)
                continue
            threshold = float(rule["threshold"])
            kind = str(rule.get("kind", "busy"))
            triggered = compare(kind, value, threshold)
            title = str(rule.get("title", f"Disk {kind}: {mount_point} {pct(value)}"))
            body = str(rule.get("body", f"Disk {mount_point} used is {pct(value)}, threshold {pct(threshold)}"))
            rule_id = str(rule.get("id", f"disk:{index}:{mount_point}:{kind}"))
            yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def evaluate_gpu_rules(self) -> Iterable[RuleResult]:
        rules = self.config.get("resources", {}).get("gpu", [])
        if not rules:
            return
        try:
            gpus = ResourceSampler.gpus()
        except Exception as exc:
            warn_skip("GPU metrics", exc)
            return

        for index, rule in enumerate(rules):
            selected_ids = normalize_ids(rule.get("ids"))
            selected_uuids = normalize_ids(rule.get("uuids"))
            selected = [
                gpu
                for gpu in gpus
                if (selected_ids is None or str(gpu.id) in selected_ids)
                and (selected_uuids is None or str(gpu.uuid) in selected_uuids)
            ]
            if not selected:
                logger.warning("GPU rule %r matched no GPUs; skipping", rule.get("id", index))
                continue

            mode = str(rule.get("mode", "both"))
            kind = str(rule.get("kind", "idle"))
            match = str(rule.get("match", "any"))
            checks = self.gpu_checks(rule, selected, mode, kind)
            if match == "all":
                triggered = all(item[0] for item in checks)
            elif match == "any":
                triggered = any(item[0] for item in checks)
            else:
                raise ValueError("GPU rule match must be 'any' or 'all'")

            metric_text = ", ".join(item[1] for item in checks)
            title = str(rule.get("title", f"GPU {kind}: {metric_text}"))
            body = str(rule.get("body", metric_text))
            rule_id = str(rule.get("id", f"gpu:{index}:{mode}:{kind}"))
            yield build_result(rule, rule_id, triggered, title, body, event_kind(kind, rule), self.config)

    def gpu_checks(
        self,
        rule: Dict[str, Any],
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
                threshold = float(rule.get("compute_threshold", rule.get("threshold", 5 if kind == "idle" else 90)))
                value = float(gpu.gpu_util)
                checks.append(
                    (
                        compare(kind, value, threshold),
                        f"GPU {gpu.id} compute {pct(value)} threshold {pct(threshold)}",
                    )
                )
            if use_memory:
                threshold = float(rule.get("memory_threshold", rule.get("threshold", 5 if kind == "idle" else 90)))
                value = float(gpu.mem_util)
                checks.append(
                    (
                        compare(kind, value, threshold),
                        f"GPU {gpu.id} memory {pct(value)} threshold {pct(threshold)}",
                    )
                )
        return checks

    def evaluate_process_rules(self) -> Iterable[RuleResult]:
        rules = self.config.get("processes", [])
        if not rules:
            return
        try:
            gpu_processes = ResourceSampler.gpu_processes()
        except Exception as exc:
            warn_skip("GPU process list", exc)
            return

        gpu_pids = {int(proc.pid) for proc in gpu_processes}
        for index, rule in enumerate(rules):
            pid = int(rule["pid"])
            triggered = pid not in gpu_pids
            name = str(rule.get("name", pid))
            title = str(rule.get("title", f"GPU process disappeared: {name}"))
            body = str(rule.get("body", f"Process {pid} is no longer present in nvidia-smi compute process list"))
            rule_id = str(rule.get("id", f"process:{pid}:{index}"))
            yield build_result(rule, rule_id, triggered, title, body, "alert", self.config)
