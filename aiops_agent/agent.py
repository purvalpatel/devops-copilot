"""LLM investigation loop (Claude tool use) with a rule-based fallback."""
from __future__ import annotations
import os
from .config import Config
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


class Agent:
    def __init__(self, cfg: Config, tools: ToolRunner):
        self.cfg, self.tools = cfg, tools
        self.client = None
        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            self.client = anthropic.Anthropic()

    def investigate(self, anomalies: list[Anomaly], snapshot: dict) -> str:
        brief = ("Detected anomalies:\n" + "\n".join(f"- {a}" for a in anomalies)
                 + f"\n\nLatest snapshot: {snapshot}")
        return self._run(brief)

    def ask(self, question: str) -> str:
        return self._run(question)

    def _run(self, user_msg: str) -> str:
        if not self.client:
            return self._fallback(user_msg)
        messages = [{"role": "user", "content": user_msg}]
        for _ in range(self.cfg.max_agent_steps):
            resp = self.client.messages.create(
                model=self.cfg.model, max_tokens=2000, system=SYSTEM,
                tools=TOOL_SPECS, messages=messages)
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text")
            messages.append({"role": "assistant", "content": resp.content})
            results = [{"type": "tool_result", "tool_use_id": b.id,
                        "content": self.tools.run(b.name, b.input)}
                       for b in resp.content if b.type == "tool_use"]
            messages.append({"role": "user", "content": results})
        return "Investigation stopped: step limit reached. Partial evidence gathered; escalate to a human."

    def _fallback(self, brief: str) -> str:
        """No API key: gather basic evidence deterministically."""
        procs = self.tools.run("top_processes", {"n": 5})
        return ("SEVERITY: unknown (LLM disabled - set ANTHROPIC_API_KEY)\n"
                f"{brief}\n\nTop processes:\n{procs}")
