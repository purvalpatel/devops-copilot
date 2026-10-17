from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class DetectorCfg:
    warmup_samples: int = 20
    z_threshold: float = 3.5
    consecutive_breaches: int = 2
    static_limits: dict = field(default_factory=lambda: {
        "cpu_percent": 90, "mem_percent": 90, "disk_percent": 90})


@dataclass
class RemediationCfg:
    dry_run: bool = True
    require_approval: bool = True
    cooldown_seconds: int = 600
    allowed_services: list = field(default_factory=list)
    allowed_containers: list = field(default_factory=list)


@dataclass
class Config:
    interval_seconds: int = 15
    model: str = "claude-sonnet-5-5"
    max_agent_steps: int = 8
    incident_cooldown_seconds: int = 300
    detector: DetectorCfg = field(default_factory=DetectorCfg)
    remediation: RemediationCfg = field(default_factory=RemediationCfg)
    log_paths: list = field(default_factory=list)
    slack_webhook_env: str = "SLACK_WEBHOOK_URL"


def load_config(path: str | None = None) -> Config:
    raw = {}
    p = Path(path or "config.yaml")
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
    cfg = Config(
        interval_seconds=raw.get("interval_seconds", 15),
        model=os.getenv("AIOPS_MODEL", raw.get("model", "claude-sonnet-5-5")),
        max_agent_steps=raw.get("max_agent_steps", 8),
        incident_cooldown_seconds=raw.get("incident_cooldown_seconds", 300),
        detector=DetectorCfg(**raw.get("detector", {})),
        remediation=RemediationCfg(**raw.get("remediation", {})),
        log_paths=raw.get("log_paths", []),
        slack_webhook_env=raw.get("notifier", {}).get(
            "slack_webhook_env", "SLACK_WEBHOOK_URL"),
    )
    return cfg
