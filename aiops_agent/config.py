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
class LLMCfg:
    base_url: str = "http://10.120.130.68:8000/v1"
    model: str = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B"
    api_key_env: str = "LLM_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 2000
    timeout_seconds: int = 120
    tool_calling: bool = True


@dataclass
class NotifierCfg:
    # Secrets are read from environment variables; these are the variable NAMES.
    slack_webhook_env: str = "SLACK_WEBHOOK_URL"
    webhook_url_env: str = "WEBHOOK_URL"            # generic JSON webhook
    telegram_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
    smtp_host: str = ""                              # set to enable email
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_user_env: str = "SMTP_USER"
    smtp_password_env: str = "SMTP_PASSWORD"
    email_from: str = ""
    email_to: list = field(default_factory=list)
    heartbeat_url_env: str = "HEARTBEAT_URL"        # dead-man's-switch ping URL
    heartbeat_interval_seconds: int = 60
    notify_on_start: bool = True


@dataclass
class Config:
    interval_seconds: float = 15
    llm: LLMCfg = field(default_factory=LLMCfg)
    max_agent_steps: int = 8
    incident_cooldown_seconds: int = 300
    resolve_after_clear_cycles: int = 4
    max_loop_stall_seconds: int = 1800   # liveness stops if the loop is stuck this long
    data_dir: str = "./data"
    detector: DetectorCfg = field(default_factory=DetectorCfg)
    remediation: RemediationCfg = field(default_factory=RemediationCfg)
    notifier: NotifierCfg = field(default_factory=NotifierCfg)
    log_paths: list = field(default_factory=list)


def _llm(raw: dict) -> LLMCfg:
    cfg = LLMCfg(**raw)
    cfg.base_url = os.getenv("AIOPS_LLM_BASE_URL", cfg.base_url)
    cfg.model = os.getenv("AIOPS_LLM_MODEL", cfg.model)
    return cfg


def load_config(path: str | None = None) -> Config:
    raw = {}
    p = Path(path or "config.yaml")
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
    return Config(
        interval_seconds=raw.get("interval_seconds", 15),
        llm=_llm(raw.get("llm", {})),
        max_agent_steps=raw.get("max_agent_steps", 8),
        incident_cooldown_seconds=raw.get("incident_cooldown_seconds", 300),
        resolve_after_clear_cycles=raw.get("resolve_after_clear_cycles", 4),
        max_loop_stall_seconds=raw.get("max_loop_stall_seconds", 1800),
        data_dir=os.getenv("AIOPS_DATA_DIR", raw.get("data_dir", "./data")),
        detector=DetectorCfg(**raw.get("detector", {})),
        remediation=RemediationCfg(**raw.get("remediation", {})),
        notifier=NotifierCfg(**raw.get("notifier", {})),
        log_paths=raw.get("log_paths", []),
    )
