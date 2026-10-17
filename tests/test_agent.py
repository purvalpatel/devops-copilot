import random
from aiops_agent.config import DetectorCfg, RemediationCfg
from aiops_agent.detector import Detector, log_error_burst
from aiops_agent.remediation import RemediationEngine
from aiops_agent.tools import ToolRunner


def sample(cpu):
    return {"cpu_percent": cpu, "mem_percent": 40, "disk_percent": 50, "load1": 1.0}


def test_statistical_spike_detected_after_sustained_breach():
    d = Detector(DetectorCfg(warmup_samples=20))
    random.seed(1)
    for _ in range(40):
        assert d.update(sample(20 + random.random() * 4)) == []
    assert d.update(sample(75)) == []          # 1st breach: filtered
    out = d.update(sample(76))                 # 2nd: sustained
    assert out and out[0].metric == "cpu_percent"


def test_static_limit():
    d = Detector(DetectorCfg(consecutive_breaches=1))
    assert d.update(sample(95))[0].kind == "static"


def test_log_burst():
    assert log_error_burst(["ERROR x"] * 12)
    assert log_error_burst(["ok"] * 50) is None


def test_remediation_policy():
    eng = RemediationEngine(RemediationCfg(dry_run=True, require_approval=False,
                                           allowed_services=["nginx"]))
    assert "REJECTED" in eng.propose("restart_service", "sshd", "x")
    assert "REJECTED" in eng.propose("restart_service", "nginx; rm -rf /", "x")
    assert "REJECTED" in eng.propose("delete_everything", "nginx", "x")
    assert "DRY-RUN" in eng.propose("restart_service", "nginx", "x")
    assert "cooldown" in eng.propose("restart_service", "nginx", "x")


def test_log_path_allowlist(tmp_path):
    f = tmp_path / "a.log"; f.write_text("ERROR boom\nok\n")
    tr = ToolRunner([str(f)], RemediationEngine(RemediationCfg()))
    assert "boom" in tr.run("search_logs", {"path": str(f), "pattern": "error"})
    assert "not allow-listed" in tr.run("search_logs", {"path": "/etc/passwd"})
