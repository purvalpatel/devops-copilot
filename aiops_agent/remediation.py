"""Policy-gated remediation. The LLM can only *propose*; this module decides."""
from __future__ import annotations
import re
import time
from .collectors import run_cmd
from .config import RemediationCfg

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


class RemediationEngine:
    def __init__(self, cfg: RemediationCfg):
        self.cfg = cfg
        self.last_run: dict[tuple, float] = {}
        self.audit: list[dict] = []

    def _validate(self, action: str, target: str) -> str | None:
        if not SAFE_NAME.match(target or ""):
            return "invalid target name"
        if action == "restart_service" and target not in self.cfg.allowed_services:
            return f"service '{target}' not in allowlist"
        if action == "restart_container" and target not in self.cfg.allowed_containers:
            return f"container '{target}' not in allowlist"
        if action not in ("restart_service", "restart_container"):
            return f"unknown action '{action}'"
        last = self.last_run.get((action, target), 0)
        if time.time() - last < self.cfg.cooldown_seconds:
            return "cooldown active (recently executed)"
        return None

    def propose(self, action: str, target: str, reason: str) -> str:
        err = self._validate(action, target)
        entry = {"ts": time.time(), "action": action, "target": target, "reason": reason}
        if err:
            entry["result"] = f"REJECTED: {err}"
        elif self.cfg.require_approval and not self._ask_human(action, target, reason):
            entry["result"] = "DENIED by operator"
        elif self.cfg.dry_run:
            entry["result"] = "DRY-RUN: would execute (set remediation.dry_run=false)"
            self.last_run[(action, target)] = time.time()
        else:
            entry["result"] = self._execute(action, target)
            self.last_run[(action, target)] = time.time()
        self.audit.append(entry)
        return entry["result"]

    @staticmethod
    def _ask_human(action, target, reason) -> bool:
        try:
            ans = input(f"\n[APPROVAL] {action} {target}\n  reason: {reason}\n  approve? [y/N] ")
        except EOFError:
            return False
        return ans.strip().lower() == "y"

    @staticmethod
    def _execute(action: str, target: str) -> str:
        if action == "restart_service":
            return run_cmd(["systemctl", "restart", target], timeout=30) or "ok"
        return run_cmd(["docker", "restart", target], timeout=60) or "ok"
