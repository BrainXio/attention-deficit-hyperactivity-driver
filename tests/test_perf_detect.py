"""Unit tests for scripts/detect-perf-level."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

_script_path = Path(__file__).resolve().parents[1] / "scripts" / "detect-perf-level.py"
_loader = importlib.machinery.SourceFileLoader("detect_perf_level", str(_script_path))
_spec = importlib.util.spec_from_loader("detect_perf_level", _loader)
_module = importlib.util.module_from_spec(_spec)
sys.modules["detect_perf_level"] = _module
_loader.exec_module(_module)

from detect_perf_level import (  # noqa: E402
    _check_env_override,
    _cpu_cores,
    _detect,
    _gpu_vram_mb,
    _ram_mb,
)

# ---------------------------------------------------------------------------
# Env override
# ---------------------------------------------------------------------------


def test_env_override_set(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.dict(os.environ, {"ADHD_PERF_LEVEL": "high"}, clear=True):
        result = _check_env_override()
        assert result == "high"
        captured = capsys.readouterr()
        assert "already set" in captured.out


def test_env_override_not_set() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert _check_env_override() is None


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------


def test_gpu_vram_nvidia_smi_not_found() -> None:
    with patch("detect_perf_level.shutil.which", return_value=None):
        assert _gpu_vram_mb() == 0


def test_gpu_vram_single_gpu() -> None:
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "8192\n"
    with (
        patch("detect_perf_level.shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _gpu_vram_mb() == 8192


def test_gpu_vram_multi_gpu() -> None:
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "4096\n4096\n"
    with (
        patch("detect_perf_level.shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _gpu_vram_mb() == 8192


def test_gpu_vram_nvidia_smi_fails() -> None:
    mock_result = Mock()
    mock_result.returncode = 1
    with (
        patch("detect_perf_level.shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch("subprocess.run", return_value=mock_result),
    ):
        assert _gpu_vram_mb() == 0


def test_gpu_vram_timeout() -> None:
    with (
        patch("detect_perf_level.shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 10)),
    ):
        assert _gpu_vram_mb() == 0


# ---------------------------------------------------------------------------
# CPU detection
# ---------------------------------------------------------------------------


def test_cpu_cores() -> None:
    cores = _cpu_cores()
    assert isinstance(cores, int)
    assert cores > 0


def test_cpu_cores_unknown() -> None:
    with patch("os.cpu_count", return_value=None):
        assert _cpu_cores() == 0


# ---------------------------------------------------------------------------
# RAM detection
# ---------------------------------------------------------------------------


def test_ram_mb_from_proc_meminfo(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:        8192000 kB\n")
    with patch("builtins.open", return_value=meminfo.open()):
        ram = _ram_mb()
        assert ram == 8000  # 8192000 kB / 1024 = 8000 MB


def test_ram_mb_no_file() -> None:
    with patch("builtins.open", side_effect=OSError):
        assert _ram_mb() == 0


# ---------------------------------------------------------------------------
# Level suggestion logic
# ---------------------------------------------------------------------------


def test_detect_high() -> None:
    with (
        patch("detect_perf_level._gpu_vram_mb", return_value=16384),
        patch("detect_perf_level._cpu_cores", return_value=16),
        patch("detect_perf_level._ram_mb", return_value=32768),
    ):
        assert _detect() == "high"


def test_detect_medium_from_gpu() -> None:
    with (
        patch("detect_perf_level._gpu_vram_mb", return_value=4096),
        patch("detect_perf_level._cpu_cores", return_value=2),
        patch("detect_perf_level._ram_mb", return_value=4096),
    ):
        assert _detect() == "medium"


def test_detect_medium_from_cpu_ram() -> None:
    with (
        patch("detect_perf_level._gpu_vram_mb", return_value=0),
        patch("detect_perf_level._cpu_cores", return_value=8),
        patch("detect_perf_level._ram_mb", return_value=16384),
    ):
        assert _detect() == "medium"


def test_detect_low() -> None:
    with (
        patch("detect_perf_level._gpu_vram_mb", return_value=0),
        patch("detect_perf_level._cpu_cores", return_value=2),
        patch("detect_perf_level._ram_mb", return_value=2048),
    ):
        assert _detect() == "low"


def test_detect_low_borderline_gpu() -> None:
    with (
        patch("detect_perf_level._gpu_vram_mb", return_value=2048),
        patch("detect_perf_level._cpu_cores", return_value=2),
        patch("detect_perf_level._ram_mb", return_value=2048),
    ):
        assert _detect() == "low"
