# Test Load Scripts

Install requirements for GPU scripts:

```bash
python3 -m pip install -r tests/requirements.txt
```

Examples:

```bash
python3 tests/stress_cpu.py --duration 60  # 100% cpu, 60s
python3 tests/stress_memory.py --size 4G --duration 60     # 4GB ram, 60s
python3 tests/stress_memory.py --percent 80 --duration 60  # 80% ram, 60s
python3 tests/stress_gpu.py --gpu 0 --compute --duration 60     # 100% gpu, 60s
python3 tests/stress_gpu.py --gpu 0 --percent 90 --duration 60  # 90% vram, 60s
python3 tests/stress_gpu.py --gpu 0 --size 8G --duration 60     # 8GB vram, 60s
python3 tests/stress_gpu.py --gpu 0 --compute --percent 80 --duration 60 # compute & 80% vram, 60s
```

Use Ctrl-C to stop scripts that were started without `--duration`.
