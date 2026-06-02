from __future__ import annotations

from .log import logger
from .sampler import ResourceSampler
from .utils import mib, pct, usage_text


def _unavailable(exc: BaseException) -> str:
    return f"- unavailable: {exc}"


def print_samples() -> None:
    lines = ["Resource samples:"]

    lines.append("# CPU pressure")
    try:
        pressure = ResourceSampler.cpu_pressure()
        for prefix in ("some", "full"):
            lines.append(
                "- %s: avg10=%.2f, avg60=%.2f, avg300=%.2f, total=%s"
                % (
                    prefix,
                    pressure.get(f"{prefix}.avg10", 0.0),
                    pressure.get(f"{prefix}.avg60", 0.0),
                    pressure.get(f"{prefix}.avg300", 0.0),
                    int(pressure.get(f"{prefix}.total", 0.0)),
                )
            )
    except Exception as exc:
        lines.append(_unavailable(exc))

    lines.append("\n# Memory usage")
    try:
        lines.append(f"- {usage_text(ResourceSampler.memory_usage())}")
    except Exception as exc:
        lines.append(_unavailable(exc))

    lines.append("\n# Disk usage")
    for mount_point in ("/",):
        try:
            lines.append(f"- {mount_point}: {usage_text(ResourceSampler.disk_usage(mount_point))}")
        except Exception as exc:
            lines.append(f"- {mount_point} unavailable: {exc}")

    lines.append("\n# GPUs")
    try:
        gpus = ResourceSampler.gpus()
        if not gpus:
            lines.append("  none detected")
        for gpu in gpus:
            lines.append(
                "- GPU %s: compute=%s, memory=%s (%s/%s), uuid=%s"
                % (
                    gpu.id,
                    pct(float(gpu.gpu_util)),
                    pct(float(gpu.mem_util)),
                    mib(float(gpu.mem_used)),
                    mib(float(gpu.mem_total)),
                    gpu.uuid,
                )
            )
    except Exception as exc:
        lines.append(_unavailable(exc))

    lines.append("\n# GPU processes")
    try:
        processes = ResourceSampler.gpu_processes()
        if not processes:
            lines.append("- none detected")
        for proc in processes:
            lines.append(
                "- PID %s, GPU %s, memory=%sMiB, name=%s"
                % (
                    proc.pid,
                    proc.gpu_id,
                    proc.used_memory,
                    proc.process_name,
                )
            )
    except Exception as exc:
        lines.append(_unavailable(exc))

    logger.info("%s", "\n".join(lines))
