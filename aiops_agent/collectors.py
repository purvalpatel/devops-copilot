"""Read-only telemetry collectors."""
from __future__ import annotations
import shutil
import subprocess
import time
import psutil


def collect_system() -> dict:
    load1 = psutil.getloadavg()[0] if hasattr(psutil, "getloadavg") else 0.0
    return {
        "ts": time.time(),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "mem_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        "load1": round(load1, 2),
        "cpu_count": psutil.cpu_count(),
    }


def top_processes(n: int = 5, by: str = "cpu") -> list[dict]:
    key = "cpu_percent" if by == "cpu" else "memory_percent"
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except psutil.Error:
            continue
    procs.sort(key=lambda x: x.get(key) or 0, reverse=True)
    return [{**p, "cpu_percent": round(p["cpu_percent"] or 0, 1),
             "memory_percent": round(p["memory_percent"] or 0, 1)} for p in procs[:n]]


def tail_file(path: str, lines: int = 200) -> list[str]:
    with open(path, "r", errors="replace") as f:
        return f.readlines()[-lines:]


def run_cmd(args: list[str], timeout: int = 10) -> str:
    """Run a command WITHOUT a shell. Returns stdout+stderr (truncated)."""
    if shutil.which(args[0]) is None:
        return f"error: '{args[0]}' not installed"
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr)[-6000:]
    except subprocess.TimeoutExpired:
        return "error: command timed out"
