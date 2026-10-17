"""Streaming anomaly detection: EWMA z-score + static limits + sustained-breach filter."""
from __future__ import annotations
import math
from dataclasses import dataclass
from .config import DetectorCfg

METRICS = ("cpu_percent", "mem_percent", "disk_percent", "load1")


@dataclass
class Anomaly:
    metric: str
    value: float
    kind: str        # "static" | "statistical"
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.metric}={self.value}: {self.detail}"


class EwmaStat:
    def __init__(self, alpha: float = 0.1):
        self.alpha, self.mean, self.var, self.n = alpha, 0.0, 0.0, 0

    def z(self, x: float) -> float:
        if self.n < 2:
            return 0.0
        std = math.sqrt(self.var)
        return abs(x - self.mean) / max(std, 1.0)   # floor std to avoid noise blow-ups

    def update(self, x: float) -> None:
        if self.n == 0:
            self.mean = x
        else:
            d = x - self.mean
            self.mean += self.alpha * d
            self.var = (1 - self.alpha) * (self.var + self.alpha * d * d)
        self.n += 1


class Detector:
    def __init__(self, cfg: DetectorCfg):
        self.cfg = cfg
        self.stats = {m: EwmaStat() for m in METRICS}
        self.breaches = {m: 0 for m in METRICS}

    def update(self, sample: dict) -> list[Anomaly]:
        out: list[Anomaly] = []
        for m in METRICS:
            x = sample.get(m)
            if x is None:
                continue
            st = self.stats[m]
            hit: Anomaly | None = None

            limit = self.cfg.static_limits.get(m)
            if limit is not None and x >= limit:
                hit = Anomaly(m, x, "static", f"exceeds hard limit {limit}")
            elif st.n >= self.cfg.warmup_samples:
                z = st.z(x)
                if z >= self.cfg.z_threshold:
                    hit = Anomaly(m, x, "statistical",
                                  f"z={z:.1f} vs baseline mean={st.mean:.1f}")

            self.breaches[m] = self.breaches[m] + 1 if hit else 0
            if hit and self.breaches[m] >= self.cfg.consecutive_breaches:
                out.append(hit)
            if not hit:                 # don't poison the baseline with anomalies
                st.update(x)
        return out


def log_error_burst(lines: list[str], threshold: int = 10) -> Anomaly | None:
    keys = ("error", "exception", "traceback", "fatal", "oom", "out of memory", "panic")
    n = sum(any(k in l.lower() for k in keys) for l in lines)
    if n >= threshold:
        return Anomaly("log_errors", n, "static", f"{n} error lines in last {len(lines)}")
    return None
