from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Tuple

from .log import logger
from .models import RuleResult
from .sampler import ResourceSampler
from .utils import build_result, compare, mib, pct, usage_text, warn_skip


CPU_TITLE_TEMPLATE = "CPU <|kind|>: <|metric|> <|value|>"
CPU_BODY_TEMPLATE = "CPU pressure <|metric|> is <|value|>, threshold <|threshold|>"

MEMORY_TITLE_TEMPLATE = "MEM <|kind|>: <|usage|>"
MEMORY_BODY_TEMPLATE = "Memory used is <|usage|>, threshold <|threshold|>"

DISK_TITLE_TEMPLATE = "Disk <|kind|>: <|mount_point|> <|usage|>"
DISK_BODY_TEMPLATE = "Disk <|mount_point|> used is <|usage|>, threshold <|threshold|>"

GPU_TITLE_TEMPLATE = "GPU <|kind|>: <|matched|>/<|total|> GPU(s) matched"
GPU_BODY_TEMPLATE = "\n".join([
    "# Matched GPU(s):",
    "<|matched_gpus|>",
    "",
    "# Not matched GPU(s):",
    "<|not_matched_gpus|>",
])

PROCESS_TITLE_TEMPLATE = "GPU process disappeared: <|name|>"
PROCESS_BODY_TEMPLATE = "\n".join([
    "# Missing PID(s):",
    "<|missing_pids|>",
    "",
    "# Alive PID(s):",
    "<|present_pids|>"
])


def render_template(template: str, slots: Mapping[str, Any]) -> str:
    text = template
    for key, value in slots.items():
        text = text.replace(f"<|{key}|>", str(value))
    return text


def render_rule_text(
    rule: Dict[str, Any],
    title_template: str,
    body_template: str,
    slots: Mapping[str, Any],
) -> Tuple[str, str]:
    title = render_template(rule.get("title", title_template), slots)
    body = render_template(rule.get("body", body_template), slots)
    return title, body


class GpuCheck(NamedTuple):
    triggered: bool
    gpu_id: str
    compute_util: float
    memory_util: float
    metrics: List[str]


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
        title, body = render_rule_text(rule, CPU_TITLE_TEMPLATE, CPU_BODY_TEMPLATE, {
            "kind": kind,
            "metric": metric,
            "value": pct(value),
            "threshold": pct(threshold),
        })
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
        title, body = render_rule_text(rule, MEMORY_TITLE_TEMPLATE, MEMORY_BODY_TEMPLATE, {
            "kind": kind,
            "usage": usage_text(usage),
            "threshold": pct(threshold),
        })
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
        title, body = render_rule_text(rule, DISK_TITLE_TEMPLATE, DISK_BODY_TEMPLATE, {
            "kind": kind,
            "mount_point": mount_point,
            "usage": usage_text(usage),
            "threshold": pct(threshold),
        })
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
        idle_count = options.get("idle_count")
        if kind == "idle" and idle_count is not None:
            triggered = sum(1 for item in checks if item.triggered) >= idle_count
        elif gpu_match == "all":
            triggered = all(item.triggered for item in checks)
        else:
            triggered = any(item.triggered for item in checks)

        slots = self.gpu_notification_slots(kind, checks)
        title, body = render_rule_text(rule, GPU_TITLE_TEMPLATE, GPU_BODY_TEMPLATE, slots)
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body, self.gpu_result_env(checks, idle_count))

    @staticmethod
    def gpu_result_env(checks: Iterable[GpuCheck], idle_count: Any = None) -> Dict[str, str]:
        check_list = list(checks)
        matched_gpu_ids = [check.gpu_id for check in check_list if check.triggered]
        env = {
            "GPU_WATCHDOG_EXTRAENV_MATCHED_GPUS": ",".join(matched_gpu_ids),
            "GPU_WATCHDOG_EXTRAENV_MATCHED_GPU_COUNT": str(len(matched_gpu_ids)),
        }
        if idle_count is not None:
            matched_checks = [check for check in check_list if check.triggered]
            prefer_compute = sorted(matched_checks, key=lambda check: (check.compute_util, check.gpu_id))
            prefer_memory = sorted(matched_checks, key=lambda check: (check.memory_util, check.gpu_id))
            env.update({
                "GPU_WATCHDOG_EXTRAENV_PREFER_COMPUTE_GPUS": ",".join(check.gpu_id for check in prefer_compute[:idle_count]),
                "GPU_WATCHDOG_EXTRAENV_PREFER_MEMORY_GPUS": ",".join(check.gpu_id for check in prefer_memory[:idle_count]),
            })
        return env

    @staticmethod
    def gpu_notification_slots(kind: str, checks: Iterable[GpuCheck]) -> Dict[str, Any]:
        check_list = list(checks)
        total = len(check_list)
        matched = sum(1 for check in check_list if check.triggered)
        slots = {
            "kind": kind,
            "matched": matched,
            "total": total,
            "matched_gpus": RuleEvaluator.gpu_group_text(check_list, True),
            "not_matched_gpus": RuleEvaluator.gpu_group_text(check_list, False),
        }
        return slots

    @staticmethod
    def gpu_group_text(checks: Iterable[GpuCheck], triggered: bool) -> str:
        group = [check for check in checks if check.triggered == triggered]
        if not group:
            return "- None"
        return "\n".join(
            f"- GPU {check.gpu_id} | {' | '.join(check.metrics)}"
            for check in group
        )

    def gpu_checks(
        self,
        options: Dict[str, Any],
        gpus: Iterable[Any],
        kind: str,
        threshold_match: str,
    ) -> List[GpuCheck]:
        checks: List[GpuCheck] = []
        thresholds = options["threshold"]
        use_compute = "compute" in thresholds
        use_memory = "memory" in thresholds

        for gpu in gpus:
            metric_checks: List[Tuple[bool, str]] = []
            if use_compute:
                threshold = thresholds["compute"]
                value = float(gpu.gpu_util)
                message = f"compute: {pct(value)} (thr. {pct(threshold)})"
                metric_checks.append((compare(kind, value, threshold), message))
            if use_memory:
                threshold = thresholds["memory"]
                value = float(gpu.mem_util)
                message = f"memory: {mib(float(gpu.mem_used))} / {mib(float(gpu.mem_total))} ({pct(value)}, thr. {pct(threshold)})"
                metric_checks.append((compare(kind, value, threshold), message))
            if threshold_match == "any":
                triggered = any(item[0] for item in metric_checks)
            else:
                triggered = all(item[0] for item in metric_checks)
            checks.append(GpuCheck(
                triggered,
                str(gpu.id),
                float(gpu.gpu_util),
                float(gpu.mem_util),
                [item[1] for item in metric_checks],
            ))
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
        title, body = render_rule_text(rule, PROCESS_TITLE_TEMPLATE, PROCESS_BODY_TEMPLATE, {
            "name": name,
            "missing_pids": missing_pids,
            "present_pids": present_pids
        })
        rule_id = rule["id"]
        yield build_result(rule, rule_id, triggered, title, body)

    @staticmethod
    def process_rule_pids(options: Dict[str, Any]) -> List[int]:
        return options["pids"]
