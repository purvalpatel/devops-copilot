"""LLM investigation loop for any OpenAI-compatible endpoint (vLLM, TGI, NIM, ...)."""
from __future__ import annotations
import json
import os
import re
import requests
from .config import Config, LLMCfg
from .detector import Anomaly
from .tools import TOOL_SPECS, ToolRunner

SYSTEM = """You are an on-call SRE agent. You receive anomalies detected on a host.
Investigate using the tools: gather evidence BEFORE concluding. Be efficient (few tool calls).
Rules:
- Never guess; cite the evidence (metric values, log lines) behind each conclusion.
- Only call propose_remediation when evidence supports it and the fix is low-risk.
  Prefer the least disruptive action. The policy engine may reject it; accept that.
- Finish with a concise incident report in this format:
  SEVERITY: low|medium|high|critical
  SUMMARY: one sentence
  ROOT CAUSE: most likely cause + confidence (low/med/high)
  EVIDENCE: bullets
  ACTIONS TAKEN/PROPOSED: bullets
  NEXT STEPS: bullets for humans
"""

# OpenAI "function" format, generated from the shared tool specs
OPENAI_TOOLS = [{"type": "function",
                 "function": {"name": t["name"], "description": t["description"],
                              "parameters": t["input_schema"]}} for t in TOOL_SPECS]


class LLMError(Exception):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


class LLMClient:
    def __init__(self, cfg: LLMCfg):
        self.cfg = cfg
        self.url = cfg.base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Content-Type": "application/json"}
        key = os.getenv(cfg.api_key_env, "")
        if key:
            self.headers["Authorization"] = f"Bearer {key}"

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body = {"model": self.cfg.model, "messages": messages,
                "max_tokens": self.cfg.max_tokens, "temperature": self.cfg.temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        try:
            r = requests.post(self.url, headers=self.headers, json=body,
                              timeout=self.cfg.timeout_seconds)
        except requests.RequestException as e:
            raise LLMError(f"cannot reach LLM at {self.url}: {e}") from e
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}", r.status_code)
        return r.json()["choices"][0]["message"]


def clean(text: str | None) -> str:
    """Drop reasoning blocks some models emit."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class Agent:
    def __init__(self, cfg: Config, tools: ToolRunner):
        self.cfg, self.tools = cfg, tools
        self.llm = LLMClient(cfg.llm)

    def investigate(self, anomalies: list[Anomaly], snapshot: dict) -> str:
        brief = ("Detected anomalies:\n" + "\n".join(f"- {a}" for a in anomalies)
                 + f"\n\nLatest snapshot: {snapshot}")
        return self._run(brief)

    def ask(self, question: str) -> str:
        return self._run(question)

    def _run(self, user_msg: str) -> str:
        try:
            if self.cfg.llm.tool_calling:
                try:
                    return self._run_with_tools(user_msg)
                except LLMError as e:
                    # server not started with tool-calling support -> degrade gracefully
                    if e.status in (400, 404, 422) and "tool" in str(e).lower():
                        print("(server rejected tool calling; using evidence mode)")
                    else:
                        raise
            return self._run_with_evidence(user_msg)
        except LLMError as e:
            return self._fallback(user_msg, str(e))

    # -- mode 1: native function calling -------------------------------------
    def _run_with_tools(self, user_msg: str) -> str:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_msg}]
        for _ in range(self.cfg.max_agent_steps):
            msg = self.llm.chat(messages, OPENAI_TOOLS)
            calls = msg.get("tool_calls") or []
            if not calls:
                return clean(msg.get("content"))
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": calls})
            for call in calls:
                fn = call["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": self.tools.run(fn["name"], args)})
        return "Investigation stopped: step limit reached. Escalate to a human."

    # -- mode 2: no function calling; we collect evidence, model analyses ----
    def _run_with_evidence(self, user_msg: str) -> str:
        parts = [("system metrics", self.tools.run("get_system_metrics", {})),
                 ("top processes (cpu)", self.tools.run("top_processes", {"n": 5})),
                 ("top processes (memory)", self.tools.run("top_processes", {"n": 5, "by": "memory"})),
                 ("docker ps", self.tools.run("docker_ps", {}))]
        for path in sorted(self.tools.log_paths):
            parts.append((f"errors in {path}",
                          self.tools.run("search_logs", {"path": path,
                                                         "pattern": "error|exception|fatal|oom|panic"})))
        evidence = "\n\n".join(f"## {k}\n{v}" for k, v in parts)
        msg = self.llm.chat([
            {"role": "system", "content": SYSTEM + "\nNo tools are available; "
             "base your report only on the evidence provided."},
            {"role": "user", "content": f"{user_msg}\n\nEVIDENCE:\n{evidence}"}])
        return clean(msg.get("content"))

    def _fallback(self, brief: str, err: str) -> str:
        procs = self.tools.run("top_processes", {"n": 5})
        return (f"SEVERITY: unknown (LLM unavailable: {err})\n{brief}\n\nTop processes:\n{procs}")
