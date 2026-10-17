from __future__ import annotations
import argparse
import json
import logging
import re
import signal
import threading
import time
from pathlib import Path
from .agent import Agent
from .collectors import collect_system, tail_file
from .config import load_config
from .detector import Detector, log_error_burst
from .notifier import Notifier
from .remediation import RemediationEngine
from .tools import ToolRunner

log = logging.getLogger("aiops")
LEVEL = {"low": "warning", "medium": "warning", "high": "critical", "critical": "critical"}


def build(cfg_path):
    cfg = load_config(cfg_path)
    rem = RemediationEngine(cfg.remediation)
    tools = ToolRunner(cfg.log_paths, rem)
    return cfg, Detector(cfg.detector), Agent(cfg, tools), Notifier(cfg.notifier), rem


def check_logs(cfg):
    for p in cfg.log_paths:
        try:
            a = log_error_burst(tail_file(p, 200))
            if a:
                yield a
        except OSError:
            continue


def save_incident(data_dir: str, anomalies, report: str) -> None:
    try:
        d = Path(data_dir)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "incidents.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), "anomalies": [str(a) for a in anomalies],
                                "report": report}) + "\n")
    except OSError as e:
        log.warning("could not persist incident: %s", e)


def _heartbeat_thread(notifier: Notifier, interval: int, stop: threading.Event):
    while not stop.is_set():
        notifier.ping_heartbeat()
        stop.wait(interval)


def _liveness_thread(path: Path, state: dict, max_stall: int, stop: threading.Event):
    """Touch a file every 10s while the main loop is making progress (Docker healthcheck reads it)."""
    while not stop.is_set():
        if time.time() - state["last_loop"] < max_stall:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            except OSError:
                pass
        stop.wait(10)


def healthcheck(cfg_path: str, max_age: float = 90) -> int:
    path = Path(load_config(cfg_path).data_dir) / "alive"
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        print("unhealthy: no liveness file")
        return 1
    if age > max_age:
        print(f"unhealthy: liveness file is {age:.0f}s old")
        return 1
    print("healthy")
    return 0


def run_loop(cfg_path: str, stop: threading.Event | None = None) -> None:
    cfg, det, agent, notifier, _ = build(cfg_path)
    if stop is None:                       # normal service mode: handle SIGTERM/SIGINT
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())

    state = {"last_loop": time.time()}
    threading.Thread(target=_liveness_thread, daemon=True, name="liveness",
                     args=(Path(cfg.data_dir) / "alive", state, cfg.max_loop_stall_seconds, stop)).start()
    if notifier.heartbeat_url():           # runs separately so slow LLM calls don't stall it
        threading.Thread(target=_heartbeat_thread, daemon=True, name="heartbeat",
                         args=(notifier, cfg.notifier.heartbeat_interval_seconds, stop)).start()
    if cfg.notifier.notify_on_start:
        notifier.send("AIOps agent started",
                      f"interval={cfg.interval_seconds}s dry_run={cfg.remediation.dry_run} "
                      f"model={cfg.llm.model}", "info")

    last_incident, open_incident, clear_cycles, errors = 0.0, False, 0, 0
    while not stop.is_set():
        state["last_loop"] = time.time()
        try:
            sample = collect_system()
            anomalies = det.update(sample) + list(check_logs(cfg))
            if anomalies:
                clear_cycles = 0
                if time.time() - last_incident > cfg.incident_cooldown_seconds:
                    last_incident, open_incident = time.time(), True
                    report = agent.investigate(anomalies, sample)
                    m = re.search(r"SEVERITY:\s*(\w+)", report, re.I)
                    level = LEVEL.get(m.group(1).lower(), "warning") if m else "warning"
                    save_incident(cfg.data_dir, anomalies, report)
                    notifier.send("Incident detected", report, level)
            elif open_incident:
                clear_cycles += 1
                if clear_cycles >= cfg.resolve_after_clear_cycles:
                    open_incident = False
                    notifier.send("Incident resolved",
                                  f"Metrics back to normal. Latest: {sample}", "resolved")
            errors = 0
        except Exception as e:             # noqa: BLE001 - the loop must survive anything
            errors += 1
            log.exception("loop iteration failed")
            if errors == 3:
                notifier.send("Agent loop is failing", f"{type(e).__name__}: {e}", "critical")
        stop.wait(cfg.interval_seconds)
    log.info("agent stopped cleanly")


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="aiops")
    ap.add_argument("-c", "--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="continuous monitoring loop")
    sub.add_parser("snapshot", help="print current metrics once")
    sub.add_parser("healthcheck", help="exit 0 if the running agent is alive (Docker HEALTHCHECK)")
    q = sub.add_parser("ask", help="ask the agent to investigate a question")
    q.add_argument("question")
    n = sub.add_parser("notify", help="send a notification (used by systemd on stop/crash)")
    n.add_argument("title")
    n.add_argument("message")
    n.add_argument("--level", default="critical")
    args = ap.parse_args()

    if args.cmd == "run":
        run_loop(args.config)
    elif args.cmd == "healthcheck":
        raise SystemExit(healthcheck(args.config))
    elif args.cmd == "snapshot":
        print(collect_system())
    elif args.cmd == "notify":
        Notifier(load_config(args.config).notifier).send(args.title, args.message, args.level)
    else:
        _, _, agent, notifier, _ = build(args.config)
        notifier.send("Agent answer", agent.ask(args.question))


if __name__ == "__main__":
    main()
