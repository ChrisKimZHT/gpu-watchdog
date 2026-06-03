# GPU Watchdog

Zero-dependency Linux watchdog for CPU, memory, disk, GPU utilization, GPU memory,
and GPU training process disappearance.

## Run

```bash
python3 gpu_watchdog.py --version
python3 gpu_watchdog.py --samples
python3 gpu_watchdog.py --once
python3 gpu_watchdog.py --config config.example.json --once
python3 gpu_watchdog.py
```

`--samples` logs the metrics visible on the current host. Memory, disk, and GPU
memory output includes used amount, total amount, and percentage. Long-running
mode uses `interval_seconds` from the config. Logging verbosity is controlled by
the config-level `log_level` option. When `--config` is omitted, the watchdog
loads `./config.json`; if that file does not exist, it exits with an error.

## Layout

- `gpu_watchdog.py`: thin command-line entry point.
- `gpu_watchdog_core/cli.py`: argument parsing, config file loading, and command dispatch.
- `gpu_watchdog_core/config.py`: config validation and default value normalization.
- `gpu_watchdog_core/diagnostics.py`: formatted sample diagnostics.
- `gpu_watchdog_core/sampler.py`: CPU, memory, disk, GPU, and GPU process sampling.
- `gpu_watchdog_core/rules.py`: unified rule evaluation.
- `gpu_watchdog_core/watchdog.py`: polling, trigger state, cooldown, notification, and callback orchestration.
- `gpu_watchdog_core/notifiers.py`: notification channels, currently logger, Bark, and SMTP.
- `gpu_watchdog_core/callbacks.py`: command callback execution.

## Config

The project intentionally uses JSON because it is supported by the Python
standard library.

Top-level options:

- `interval_seconds`: required polling interval.
- `cooldown_seconds`: default minimum seconds between repeated triggers for the
  same active rule. Required top-level option.
- `log_level`: standard Python logging level. Defaults to `INFO`.
- Logger notifications are always enabled.
- `notifiers.bark`: Bark settings. `enabled`, `server`, `device_key`,
  `timeout_seconds`, and `level` are consumed by this project. Put Bark-specific
  POST body fields under `passthrough`; non-null passthrough fields are sent
  with the request. Alert events force `level=critical`; reminders use the
  configured Bark `level`.
- `notifiers.smtp`: SMTP email settings using Python standard-library modules.
  `enabled`, `host`, `port`, `username`, `password`, `from_addr`, `to_addrs`,
  `timeout_seconds`, `ssl`, and `starttls` are consumed by this project.
  `to_addrs` must be a list of recipient addresses. `ssl` uses implicit TLS,
  usually port `465`; `starttls` upgrades a plain connection, usually port
  `587`. They cannot both be true. When `username` is empty, SMTP auth is
  skipped.

Rule fields:

- `id`: stable rule identifier used for trigger state and callbacks.
- `type`: one of `cpu`, `memory`, `disk`, `gpu`, or `process`.
- `notify`: send notification when true. Defaults to true.
- `command`: optional shell command or argv list to run as a callback.
- `cooldown_seconds`: optional per-rule cooldown override.
- `pending_period`: optional seconds a rule must stay triggered before
  notification and callback execution. Defaults to `0`. If the rule recovers
  before this duration, the timer is reset.
- `event`: optional notification kind, either `alert` or `reminder`.
  Defaults to `alert` for `busy` rules and process rules, or `reminder` for
  `idle` rules.
- `options`: object containing fields specific to the rule `type`.

CPU, memory, and disk rule options:

- `kind`: `busy` for resource occupation alerts, `idle` for idle reminders.
  Defaults to `busy`.
- `threshold`: percentage threshold for CPU pressure, memory, and disk rules.

GPU rule options:

- `kind`: `busy` for occupation alerts, `idle` for idle reminders. Defaults to
  `idle`.
- `gpus`: GPU IDs to check, as strings matching `nvidia-smi` output. When omitted,
  all visible GPUs are checked.
- `gpu_match`: `any` or `all`. This is applied across the selected GPU IDs.
  Defaults to `any`.
- `threshold_match`: optional `any` or `all`. This is applied across configured
  thresholds on each GPU.
- `threshold`: object containing optional `compute` and `memory` percentage
  thresholds.

For `busy` GPU rules, a GPU is triggered when any configured threshold is met or
exceeded. For `idle` GPU rules, a GPU is triggered when all configured thresholds
have fallen back to or below their values. Set `threshold_match` to override this
default. Thresholds that are not configured are not checked.

Callback commands receive these environment variables:

- `GPU_WATCHDOG_RULE`
- `GPU_WATCHDOG_KIND`
- `GPU_WATCHDOG_TITLE`
- `GPU_WATCHDOG_BODY`

## Resources

CPU rules use `/proc/pressure/cpu`. The default `options.metric` is
`some.avg10`; other PSI fields such as `some.avg60`, `some.avg300`, or
`full.avg10` can be configured when available on the host.

Memory uses `/proc/meminfo` on Linux, based on `MemAvailable`, and
`GlobalMemoryStatusEx` on Windows. The sampler returns total bytes, used bytes,
and used percentage.

Disk rules monitor one `options.mount` point per rule with `shutil.disk_usage`.
The sampler returns total bytes, used bytes, and used percentage.

GPU rules use the provided `nvsmi.py` interface. GPU memory descriptions include
used memory, total memory, and percentage.

Process rules watch whether one or more PIDs are still present in the
`nvidia-smi` compute process list. Set `options.pids` to the process IDs to
watch. A rule alerts when any configured PID is no longer present, which means
normal training completion can also trigger an alert.
