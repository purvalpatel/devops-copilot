"""Tools exposed to the LLM. All read-only except `propose_remediation` (policy-gated)."""
from __future__ import annotations
import json
import os
import re
from . import collectors as c
from .remediation import RemediationEngine

TOOL_SPECS = [
    {"name": "get_system_metrics",
     "description": "Current CPU, memory, disk, load average.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "top_processes",
     "description": "Top N processes by cpu or memory.",
     "input_schema": {"type": "object", "properties": {
         "n": {"type": "integer", "default": 5},
         "by": {"type": "string", "enum": ["cpu", "memory"], "default": "cpu"}}}},
    {"name": "search_logs",
     "description": "Search recent lines of an allow-listed log file with a regex.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "pattern": {"type": "string", "description": "regex, case-insensitive"},
         "lines": {"type": "integer", "default": 500}},
         "required": ["path"]}},
    {"name": "docker_ps",
     "description": "List running docker containers.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "docker_logs",
     "description": "Last N log lines of a container.",
     "input_schema": {"type": "object", "properties": {
         "container": {"type": "string"}, "lines": {"type": "integer", "default": 100}},
         "required": ["container"]}},
    {"name": "service_status",
     "description": "systemctl is-active for a service.",
     "input_schema": {"type": "object", "properties": {"service": {"type": "string"}},
                      "required": ["service"]}},
    {"name": "propose_remediation",
     "description": "Propose a fix. Policy engine may reject or require human approval. "
                    "Actions: restart_service, restart_container.",
     "input_schema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["restart_service", "restart_container"]},
         "target": {"type": "string"}, "reason": {"type": "string"}},
         "required": ["action", "target", "reason"]}},
]

_NAME = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


class ToolRunner:
    def __init__(self, log_paths: list[str], remediation: RemediationEngine):
        self.log_paths = {os.path.realpath(p) for p in log_paths}
        self.remediation = remediation

    def run(self, name: str, args: dict) -> str:
        try:
            fn = getattr(self, f"_t_{name}", None)
            if fn is None:
                return f"error: unknown tool {name}"
            return str(fn(**args))[:6000]
        except Exception as e:  # tool errors go back to the model, not crash the loop
            return f"error: {type(e).__name__}: {e}"

    def _t_get_system_metrics(self):
        return json.dumps(c.collect_system())

    def _t_top_processes(self, n=5, by="cpu"):
        return json.dumps(c.top_processes(min(int(n), 20), by))

    def _t_search_logs(self, path, pattern=".", lines=500):
        if os.path.realpath(path) not in self.log_paths:
            return f"error: path not allow-listed. Allowed: {sorted(self.log_paths)}"
        rx = re.compile(pattern, re.I)
        hits = [l.rstrip() for l in c.tail_file(path, min(int(lines), 5000)) if rx.search(l)]
        return "\n".join(hits[-60:]) or "no matches"

    def _t_docker_ps(self):
        return c.run_cmd(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"])

    def _t_docker_logs(self, container, lines=100):
        if not _NAME.match(container):
            return "error: invalid container name"
        return c.run_cmd(["docker", "logs", "--tail", str(min(int(lines), 500)), container])

    def _t_service_status(self, service):
        if not _NAME.match(service):
            return "error: invalid service name"
        return c.run_cmd(["systemctl", "is-active", service])

    def _t_propose_remediation(self, action, target, reason):
        return self.remediation.propose(action, target, reason)
