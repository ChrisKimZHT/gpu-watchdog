from __future__ import annotations

import ctypes
import os
import shutil
from typing import Any, Dict, List

import nvsmi

from .models import ResourceUsage


class ResourceSampler:
    @staticmethod
    def cpu_pressure(path: str = "/proc/pressure/cpu") -> Dict[str, float]:
        result: Dict[str, float] = {}
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                parts = raw_line.strip().split()
                if not parts:
                    continue
                prefix = parts[0]
                for item in parts[1:]:
                    if "=" not in item:
                        continue
                    key, value = item.split("=", 1)
                    try:
                        result[f"{prefix}.{key}"] = float(value)
                    except ValueError:
                        continue
        return result

    @staticmethod
    def memory_usage() -> ResourceUsage:
        if os.name == "nt":
            return ResourceSampler._windows_memory_usage()
        return ResourceSampler._meminfo_memory_usage()

    @staticmethod
    def _meminfo_memory_usage() -> ResourceUsage:
        values: Dict[str, float] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for raw_line in handle:
                if ":" not in raw_line:
                    continue
                key, rest = raw_line.split(":", 1)
                parts = rest.strip().split()
                if parts:
                    try:
                        values[key] = float(parts[0])
                    except ValueError:
                        pass

        total = values.get("MemTotal", 0.0)
        available = values.get("MemAvailable")
        if available is None:
            available = (
                values.get("MemFree", 0.0)
                + values.get("Buffers", 0.0)
                + values.get("Cached", 0.0)
            )
        if total <= 0:
            raise RuntimeError("MemTotal is missing from /proc/meminfo")
        used = total - available
        return ResourceUsage(
            total=total * 1024,
            used=used * 1024,
            percent=used / total * 100.0,
        )

    @staticmethod
    def _windows_memory_usage() -> ResourceUsage:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError()

        total = float(status.ullTotalPhys)
        if total <= 0:
            raise RuntimeError("physical memory total is zero")
        used = float(status.ullTotalPhys - status.ullAvailPhys)
        return ResourceUsage(
            total=total,
            used=used,
            percent=used / total * 100.0,
        )

    @staticmethod
    def disk_usage(mount_point: str) -> ResourceUsage:
        usage = shutil.disk_usage(mount_point)
        if usage.total <= 0:
            raise RuntimeError(f"disk total is zero for {mount_point}")
        return ResourceUsage(
            total=float(usage.total),
            used=float(usage.total - usage.free),
            percent=(1.0 - usage.free / usage.total) * 100.0,
        )

    @staticmethod
    def gpus() -> List[Any]:
        return list(nvsmi.get_gpus())

    @staticmethod
    def gpu_processes() -> List[Any]:
        return list(nvsmi.get_gpu_processes())
