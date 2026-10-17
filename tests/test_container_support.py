import os, threading, time
from aiops_agent.collectors import collect_system
from aiops_agent.main import healthcheck, run_loop


def cfg(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(f"interval_seconds: 0.2\ndata_dir: {tmp_path}/data\nnotifier: {{notify_on_start: false}}\n")
    return str(f)


def test_healthcheck_states(tmp_path):
    c = cfg(tmp_path)
    assert healthcheck(c) == 1                                  # no file yet
    alive = tmp_path / "data" / "alive"; alive.parent.mkdir(); alive.touch()
    assert healthcheck(c) == 0                                  # fresh
    old = time.time() - 600; os.utime(alive, (old, old))
    assert healthcheck(c) == 1                                  # stale


def test_running_agent_keeps_liveness_file_fresh(tmp_path):
    c, stop = cfg(tmp_path), threading.Event()
    t = threading.Thread(target=run_loop, args=(c, stop), daemon=True); t.start()
    time.sleep(1.5)
    assert healthcheck(c) == 0
    stop.set(); t.join(5)


def test_disk_path_override(monkeypatch):
    monkeypatch.setenv("AIOPS_DISK_PATH", "/etc/hostname")      # a file works for statvfs
    assert 0 <= collect_system()["disk_percent"] <= 100
