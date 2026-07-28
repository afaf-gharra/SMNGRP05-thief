"""Host specification for the signed step-zero declaration (book ch.5).

Computational fairness is scored in this league: a clever algorithm on a modest
laptop should outrank a wasteful one on a workstation. That comparison only
means anything if each side states what it ran on *before* play and seals the
statement, so it cannot be revised once the result is known.

Everything here degrades gracefully. A missing GPU, an unreadable ``/proc``, no
``psutil`` — none of that may stop a match, so every probe falls back to
``None`` and the declaration simply records what could be established.
"""

import os
import platform
import shutil
import subprocess

_NVIDIA_QUERY = ["--query-gpu=name,memory.total", "--format=csv,noheader"]


def collect_spec() -> dict:
    """Best-effort hardware and platform description."""
    gpu_name, vram_gb = _gpu()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpu_type": _cpu_name(),
        "cpu_cores": os.cpu_count(),
        "cpu_freq_mhz": _cpu_freq_mhz(),
        "ram_gb": _ram_gb(),
        "gpu_type": gpu_name,
        "vram_gb": vram_gb,
    }


def _cpu_name() -> str:
    name = platform.processor() or ""
    if name.strip():
        return name.strip()
    return platform.machine() or "unknown"


def _psutil():
    try:
        import psutil  # noqa: PLC0415 - optional dependency, probed at call time
    except ImportError:
        return None
    return psutil


def _cpu_freq_mhz() -> int | None:
    psutil = _psutil()
    if psutil is None:
        return None
    try:
        freq = psutil.cpu_freq()
    except (OSError, AttributeError):
        return None
    return int(freq.max or freq.current) if freq else None


def _ram_gb() -> float | None:
    psutil = _psutil()
    if psutil is not None:
        try:
            return round(psutil.virtual_memory().total / 1024**3, 1)
        except (OSError, AttributeError):
            pass
    try:  # POSIX fallback, no third-party dependency needed
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page_size / 1024**3, 1)
    except (ValueError, OSError, AttributeError):
        return None


def _gpu() -> tuple[str | None, float | None]:
    """Query NVIDIA tooling if present; report nothing rather than guessing."""
    if not shutil.which("nvidia-smi"):
        return None, None
    try:
        output = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
            ["nvidia-smi", *_NVIDIA_QUERY],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    if not output:
        return None, None
    name, _, memory = output.splitlines()[0].partition(",")
    return name.strip() or None, _mib_to_gb(memory)


def _mib_to_gb(text: str) -> float | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    return round(int(digits) / 1024, 1) if digits else None
