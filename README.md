# GPU Watchdog

Zero-dependency Linux watchdog for CPU, memory, disk, GPU utilization, GPU memory,
and GPU training process disappearance.

## Run

```bash
python3 gpu_watchdog.py --samples
python3 gpu_watchdog.py --config config.example.json --once
python3 gpu_watchdog.py --config config.example.json
```

`--samples` logs the metrics visible on the current host. Memory, disk, and GPU
memory output includes used amount, total amount, and percentage. Long-running
mode uses `interval_seconds` from the config. Logging verbosity is controlled by
the config-level `log_level` option.

## Layout

- `gpu_watchdog.py`: thin command-line entry point.
- `gpu_watchdog_core/cli.py`: argument parsing, config loading, sample printing.
- `gpu_watchdog_core/sampler.py`: CPU, memory, disk, GPU, and GPU process sampling.
- `gpu_watchdog_core/rules.py`: resource and process rule evaluation.
- `gpu_watchdog_core/watchdog.py`: polling, trigger state, cooldown, notification, and callback orchestration.
- `gpu_watchdog_core/notifiers.py`: notification channels, currently logger and Bark.
- `gpu_watchdog_core/callbacks.py`: command callback execution.

## Config

The project intentionally uses JSON because it is supported by the Python
standard library.

Top-level options:

- `interval_seconds`: polling interval.
- `cooldown_seconds`: default minimum seconds between repeated triggers for the
  same active rule.
- `log_level`: standard Python logging level.
- `log_notifications`: also emit notifications through the configured logger.
- `notifiers.bark`: Bark settings. `isArchive`, `icon`, `group`, and `level`
  are passed through to Bark. Busy/process alerts force `level=critical`;
  idle reminders use the configured Bark `level`.

Rule fields:

- `kind`: `busy` for resource occupation alerts, `idle` for idle reminders.
- `threshold`: percentage threshold for CPU pressure, memory, disk, and simple
  GPU rules.
- `notify`: send notification when true. Defaults to true.
- `command`: optional shell command or argv list to run as a callback.
- `cooldown_seconds`: optional per-rule cooldown override.

Callback commands receive these environment variables:

- `GPU_WATCHDOG_RULE`
- `GPU_WATCHDOG_KIND`
- `GPU_WATCHDOG_TITLE`
- `GPU_WATCHDOG_BODY`

## Resources

CPU uses `/proc/pressure/cpu`. The default metric is `some.avg10`; other PSI
fields such as `some.avg60`, `some.avg300`, or `full.avg10` can be configured
when available on the host.

Memory uses `/proc/meminfo` and monitors used percentage based on
`MemAvailable`. The sampler returns total bytes, used bytes, and used
percentage.

Disk rules monitor one mount point per rule with `shutil.disk_usage`. The
sampler returns total bytes, used bytes, and used percentage.

GPU rules use the provided `nvsmi.py` interface. Set `mode` to `compute`,
`memory`, or `both`. Set `match` to `any` or `all` when multiple GPUs or
multiple metrics are checked. GPU IDs are strings, matching `nvidia-smi` output.
GPU memory descriptions include used memory, total memory, and percentage.

Process rules watch whether a PID is still present in the `nvidia-smi` compute
process list. This intentionally alerts when the process disappears, which means
normal training completion can also trigger an alert.
