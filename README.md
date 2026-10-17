# AIOps Agent

Detects anomalies on a host, investigates with Claude (tool use), and proposes
policy-gated remediation.

```
collectors ─► detector (EWMA z-score + limits) ─► agent (Claude + tools) ─► notifier
                                                        └─► remediation engine (allowlist, cooldown, approval, dry-run)
```

## Run
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    export SLACK_WEBHOOK_URL=...        # optional
    python -m aiops_agent.main snapshot
    python -m aiops_agent.main ask "Why is the server slow?"
    python -m aiops_agent.main run
    pytest

Edit `config.yaml` (log allowlist, services/containers, dry_run, approval).

## Safety design
- LLM can only call fixed tools; no shell access. Commands run without a shell.
- Logs readable only from allow-listed paths.
- Remediation: action + target allowlists, name validation, cooldowns,
  human approval, dry-run by default, in-memory audit trail.
- Without ANTHROPIC_API_KEY it degrades to a deterministic report.

## Extend
Add a tool: append a spec to `TOOL_SPECS` and a `_t_<name>` method in `tools.py`.
Ideas: Prometheus/Datadog queries, Kubernetes (`kubectl get pods/events`),
CloudWatch, runbook RAG, PagerDuty, persistent incident store.
