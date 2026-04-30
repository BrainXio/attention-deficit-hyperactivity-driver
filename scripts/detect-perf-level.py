#!/usr/bin/env python3
"""Suggest an ADHD_PERF_LEVEL based on available hardware.

Usage:
    python scripts/detect-perf-level.py

Environment:
    ADHD_PERF_LEVEL     If set, this script prints its value and exits.
                        Otherwise probes hardware and prints a suggestion.

Exit codes:
    0 — suggestion printed
    1 — detection error (suggestion may still be printed)

This script is standalone. It is not imported by adhd-mcp.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def _check_env_override() -> str | None:
    value = os.environ.get("ADHD_PERF_LEVEL")
    if value:
        print(f"ADHD_PERF_LEVEL is already set to '{value}'.")
    return value


def _gpu_vram_mb() -> int:
    """Return total GPU VRAM in MB via nvidia-smi, or 0 if unavailable."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return 0

    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0

    if result.returncode != 0:
        return 0

    total = 0
    for line in result.stdout.strip().splitlines():
        try:
            total += int(line.strip())
        except ValueError:
            continue
    return total


def _cpu_cores() -> int:
    """Return logical CPU count, or 0 if unknown."""
    try:
        return os.cpu_count() or 0
    except Exception:
        return 0


def _ram_mb() -> int:
    """Return total system RAM in MB via /proc/meminfo, or 0 if unavailable."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    kb = int(parts[1])
                    return kb // 1024
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _detect() -> str:
    """Probe hardware and return a suggested perf_level."""
    vram = _gpu_vram_mb()
    cpu = _cpu_cores()
    ram = _ram_mb()

    has_strong_gpu = vram >= 8192
    has_any_gpu = vram >= 4096
    has_many_cores = cpu >= 8
    has_enough_cores = cpu >= 4
    has_much_ram = ram >= 16384
    has_enough_ram = ram >= 8192

    if has_strong_gpu and has_many_cores and has_much_ram:
        return "high"
    if has_any_gpu or (has_enough_cores and has_enough_ram):
        return "medium"
    return "low"


def _print_details(vram: int, cpu: int, ram: int, suggestion: str) -> None:
    print(f"  GPU VRAM : {vram} MB" if vram else "  GPU VRAM : not detected")
    print(f"  CPU cores: {cpu}" if cpu else "  CPU cores: unknown")
    print(f"  RAM      : {ram} MB" if ram else "  RAM      : unknown")
    print(f"  Suggested: {suggestion}")
    print(f"\n  export ADHD_PERF_LEVEL={suggestion}")


def main() -> None:
    override = _check_env_override()
    if override:
        return

    print("Probing hardware for ADHD_PERF_LEVEL suggestion ...")
    suggestion = _detect()
    vram = _gpu_vram_mb()
    cpu = _cpu_cores()
    ram = _ram_mb()
    _print_details(vram, cpu, ram, suggestion)


if __name__ == "__main__":
    main()
