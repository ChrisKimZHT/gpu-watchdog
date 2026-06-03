# GPU Watchdog

一个零依赖、单文件的 Linux 监控工具，用于监控 CPU、内存、磁盘、GPU 利用率、GPU 显存，以及 GPU 训练进程是否消失。

## 快速开始

不需要任何依赖，仅需 Python 3.8+ 原生库，兼容性 Linux>Windows>macOS，可构建为方便使用的 `.py` 单文件。

```bash
# 打印当前系统资源情况，测试程序是否可读取指标
python3 gpu_watchdog.py --samples

# 配置示例：空闲 GPU 自动提醒
python3 gpu_watchdog.py --config config_examples/idle_gpu_notification.json

# 配置示例：空闲 GPU 自动关机（适用于 AutoDL 等按量付费环境）
python3 gpu_watchdog.py --config config_examples/idle_auto_shutdown.json

# 配置示例：磁盘即将占满告警
python3 gpu_watchdog.py --config config_examples/disk_full_notification.json

# 配置示例：训练进程崩溃告警/训练结束提醒
python3 gpu_watchdog.py --config config_examples/crash_notification.json
```

省略 `--config` 时，程序会加载 `./config.json`，完整配置示例在 `config_examples/full_config.json`.

## 资源采样

CPU 规则使用 `/proc/pressure/cpu`。默认 `options.metric` 为 `some.avg10`；如果主机支持，也可以配置其他 PSI 字段，例如 `some.avg60`、`some.avg300` 或 `full.avg10`。

内存在 Linux 上使用 `/proc/meminfo`，基于 `MemAvailable` 计算；在 Windows 上使用 `GlobalMemoryStatusEx`。采样器会返回总字节数、已用字节数和已用百分比。

磁盘规则通过 `shutil.disk_usage` 监控每条规则中的一个 `options.mount` 挂载点。采样器会返回总字节数、已用字节数和已用百分比。

GPU 规则使用 [`nvsmi.py`](https://github.com/pmav99/nvsmi/blob/master/nvsmi.py) 封装 `nvidia-smi` 输出，监控 GPU 利用率、显存利用率以及指定 PID 是否存在。

进程规则会检查一个或多个 PID 是否仍存在于 `nvidia-smi` 的计算进程列表中。将 `options.pids` 设置为要监控的进程 ID。只要任一配置的 PID 不再出现，规则就会告警；这也意味着正常的训练结束同样可能触发告警。

> **Windows 不支持 CPU 规则** ：由于 Windows 没有 PSI，而只读取 CPU 利用率是客观的（CPU 满载不等于系统卡顿），因此 Windows 上的 CPU 规则会被自动禁用。