import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aiops_agent.agent import Agent
from aiops_agent.config import Config, LLMCfg, RemediationCfg
from aiops_agent.remediation import RemediationEngine
from aiops_agent.tools import ToolRunner


def make_server(handler_fn):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code, payload = handler_fn(body, self.headers)
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def agent_for(srv, tool_calling=True):
    cfg = Config(llm=LLMCfg(base_url=f"http://127.0.0.1:{srv.server_port}/v1",
                            tool_calling=tool_calling, timeout_seconds=5))
    return Agent(cfg, ToolRunner([], RemediationEngine(RemediationCfg())))


def test_tool_calling_roundtrip(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret")
    seen = {}
    def handler(body, headers):
        seen["auth"] = headers["Authorization"]
        if not any(m["role"] == "tool" for m in body["messages"]):
            return 200, {"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "get_system_metrics", "arguments": "{}"}}]}}]}
        return 200, {"choices": [{"message": {"content": "<think>hmm</think>SEVERITY: low"}}]}
    srv = make_server(handler)
    out = agent_for(srv).ask("why slow?")
    assert out == "SEVERITY: low" and seen["auth"] == "Bearer secret"


def test_falls_back_to_evidence_mode_when_tools_unsupported():
    def handler(body, headers):
        if "tools" in body:
            return 400, {"error": "\"auto\" tool choice requires --enable-auto-tool-choice"}
        return 200, {"choices": [{"message": {"content": "SEVERITY: medium"}}]}
    assert agent_for(make_server(handler)).ask("x") == "SEVERITY: medium"


def test_unreachable_llm_returns_fallback_report():
    cfg = Config(llm=LLMCfg(base_url="http://127.0.0.1:1/v1", timeout_seconds=1))
    out = Agent(cfg, ToolRunner([], RemediationEngine(RemediationCfg()))).ask("x")
    assert "LLM unavailable" in out
