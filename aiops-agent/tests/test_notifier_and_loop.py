import json, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import aiops_agent.notifier as nmod
from aiops_agent.config import NotifierCfg
from aiops_agent.main import run_loop
from aiops_agent.notifier import Notifier


def test_channels_retry_and_isolation(monkeypatch):
    monkeypatch.setattr(nmod.time, "sleep", lambda s: None)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://slack.test/x")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOK")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    calls = []

    class R:
        def raise_for_status(self): pass

    def fake_post(url, json=None, timeout=None):
        calls.append(url)
        if "slack" in url and calls.count(url) == 1:
            raise RuntimeError("transient")      # first slack attempt fails -> retried
        return R()
    monkeypatch.setattr(nmod.requests, "post", fake_post)
    Notifier(NotifierCfg()).send("t", "b", "critical")
    assert calls.count("http://slack.test/x") == 2
    assert any("api.telegram.org/botTOK" in u for u in calls)


def test_email_channel(monkeypatch):
    sent = {}
    class FakeSMTP:
        def __init__(self, host, port, timeout=None): sent["host"] = host
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, m): sent["to"], sent["subj"] = m["To"], m["Subject"]
    monkeypatch.setattr(nmod.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    for k in ("SLACK_WEBHOOK_URL", "WEBHOOK_URL", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    Notifier(NotifierCfg(smtp_host="smtp.test", email_to=["a@b.c"])).send("Down", "x", "critical")
    assert sent["to"] == "a@b.c" and sent["tls"] and "Down" in sent["subj"]


def test_end_to_end_incident_flow(tmp_path, monkeypatch):
    """Real loop: breach -> LLM report -> webhook alert -> persisted -> resolved."""
    received = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.endswith("/chat/completions"):
                out = {"choices": [{"message": {"content": "SEVERITY: high\nSUMMARY: test"}}]}
            else:
                received.append(body); out = {}
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(out).encode())
        def log_message(self, *a): pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_port
    monkeypatch.setenv("WEBHOOK_URL", f"http://127.0.0.1:{port}/hook")
    for k in ("SLACK_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    cfgfile = tmp_path / "c.yaml"
    cfgfile.write_text(f"""
interval_seconds: 0.2
data_dir: {tmp_path}/data
resolve_after_clear_cycles: 2
incident_cooldown_seconds: 1000
llm: {{base_url: "http://127.0.0.1:{port}/v1", tool_calling: false, timeout_seconds: 5}}
detector: {{consecutive_breaches: 1, static_limits: {{mem_percent: 0.1}}}}
""")
    stop = threading.Event()
    t = threading.Thread(target=run_loop, args=(str(cfgfile), stop), daemon=True)
    t.start()
    deadline = time.time() + 15
    while time.time() < deadline and not any(r["title"] == "Incident detected" for r in received):
        time.sleep(0.2)
    stop.set(); t.join(5)

    titles = [r["title"] for r in received]
    assert "AIOps agent started" in titles
    inc = next(r for r in received if r["title"] == "Incident detected")
    assert inc["level"] == "critical"                      # parsed from "SEVERITY: high"
    saved = (tmp_path / "data" / "incidents.jsonl").read_text()
    assert "SEVERITY: high" in saved
