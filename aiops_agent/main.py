from __future__ import annotations
import argparse
import time
from .agent import Agent
from .collectors import collect_system, tail_file
from .config import load_config
from .detector import Detector, log_error_burst
from .notifier import Notifier
from .remediation import RemediationEngine
from .tools import ToolRunner


def build(cfg_path):
    cfg = load_config(cfg_path)
    rem = RemediationEngine(cfg.remediation)
    tools = ToolRunner(cfg.log_paths, rem)
    return cfg, Detector(cfg.detector), Agent(cfg, tools), Notifier(cfg.slack_webhook_env), rem


def check_logs(cfg):
    for p in cfg.log_paths:
        try:
            a = log_error_burst(tail_file(p, 200))
            if a:
                yield a
        except OSError:
            continue


def run_loop(cfg_path):
    cfg, det, agent, notifier, _ = build(cfg_path)
    last_incident = 0.0
    print(f"AIOps agent started (interval={cfg.interval_seconds}s, "
          f"dry_run={cfg.remediation.dry_run}). Ctrl+C to stop.")
    while True:
        sample = collect_system()
        anomalies = det.update(sample) + list(check_logs(cfg))
        if anomalies and time.time() - last_incident > cfg.incident_cooldown_seconds:
            last_incident = time.time()
            report = agent.investigate(anomalies, sample)
            notifier.send("AIOps incident report", report)
        time.sleep(cfg.interval_seconds)


def main():
    ap = argparse.ArgumentParser(prog="aiops")
    ap.add_argument("-c", "--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="continuous monitoring loop")
    sub.add_parser("snapshot", help="print current metrics once")
    q = sub.add_parser("ask", help="ask the agent to investigate a question")
    q.add_argument("question")
    args = ap.parse_args()

    if args.cmd == "run":
        run_loop(args.config)
    elif args.cmd == "snapshot":
        print(collect_system())
    else:
        _, _, agent, notifier, _ = build(args.config)
        notifier.send("Agent answer", agent.ask(args.question))


if __name__ == "__main__":
    main()
