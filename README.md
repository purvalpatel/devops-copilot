# AIOps Agent

Detects anomalies on a host, investigates with your OpenAI-compatible LLM (tool calling), and proposes
policy-gated remediation.

### Safety

- The model has no shell access, and commands run without a shell.
- Log files are readable only from the paths you list in config.yaml.
- Restarts of services or containers need an allowlisted target, a cooldown, and terminal approval.
- Remediation is dry-run by default, so nothing executes until you set remediation.dry_run: false.
- Without ANTHROPIC_API_KEY it falls back to a deterministic report instead of crashing.


```
collectors ─► detector (EWMA z-score + limits) ─► agent (LLM + tools) ─► notifier
                                                        └─► remediation engine (allowlist, cooldown, approval, dry-run)
```

### components:
| Components | File | What is does |
| -----------| ---- | ------------ |
| Collectors | Collectors.py | Collect CPU, Memory, load and disk. |
| Detector | detector.py | Combines a rolling baseline with hardlimits. | 
| Agent core | Agent.py | is the loop that talks to the LLM. | 
| Safe tools | tools.py | ToolRunner exposes 7 tools. Logs can only be read from paths listed in  config.yaml | 
| Policy gate | remediation.py | it asks for the approval and runs in dry-run by default.| 
| Notifier | notifier.py | sends to slack or telegram. | 
| Orchestrator | main.py | ties everything together and handles shutdown signals. | 
| Settings | config.py, config.yaml | All threashold, allowlist and the LLM endpoint | 
| Always-on | deploy/ | The systemd unit, install script, Dockerfile and compose file. | 


## Run
    pip install -r requirements.txt
    export LLM_API_KEY=...   # bearer token for your LLM server
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
- If the LLM is unreachable it degrades to a deterministic report.

## Extend
Add a tool: append a spec to `TOOL_SPECS` and a `_t_<name>` method in `tools.py`.
Ideas: Prometheus/Datadog queries, Kubernetes (`kubectl get pods/events`),
CloudWatch, runbook RAG, PagerDuty, persistent incident store.
