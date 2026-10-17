# AIOps Agent

Detects anomalies on a host, investigates with your OpenAI-compatible LLM (tool calling), and proposes
policy-gated remediation.

```
collectors ─► detector (EWMA z-score + limits) ─► agent (LLM + tools) ─► notifier
                                                        └─► remediation engine (allowlist, cooldown, approval, dry-run)
```

## Run
    pip install -r requirements.txt
    export LLM_API_KEY=...   # bearer token for your LLM server
    export SLACK_WEBHOOK_URL=...        # optional
    python -m aiops_agent.main snapshot
    python -m aiops_agent.main ask "Why is the server slow?"
    python -m aiops_agent.main run
    pytest

Edit `config.yaml` (log allowlist, services/containers, dry_run, approval).

## Run 24/7 (systemd, recommended)
    sudo ./deploy/install.sh          # 1st run creates /etc/aiops-agent.env
    sudo nano /etc/aiops-agent.env    # LLM_API_KEY + notification channels
    sudo nano /opt/aiops-agent/config.yaml
    sudo ./deploy/install.sh          # 2nd run installs + starts the service
    journalctl -u aiops-agent -f
    systemctl status aiops-agent

`Restart=always` revives it after crashes; `enable` starts it on boot.
`ExecStopPost` sends an alert every time the service stops or crashes.

## Run 24/7 in Docker (Linux host)
    cp deploy/aiops-agent.env.example .env      # set LLM_API_KEY + alert channels
    nano config.yaml                            # log paths, allowlists, dry_run
    docker compose up -d --build
    docker compose logs -f
    docker ps                                   # STATUS shows (healthy)

`restart: unless-stopped` brings it back after crashes, daemon restarts and reboots
(make sure Docker itself starts on boot: `sudo systemctl enable docker`).
The built-in healthcheck turns the container `unhealthy` if the agent loop stalls.
Docker does not auto-restart unhealthy containers; add `willfarrell/autoheal` if you want that.

Host visibility: `pid: host` (processes), `/var/log` read-only, and the host disk is read
through a bind-mounted probe file, so the whole host filesystem is never exposed.
Container actions (`docker ps/logs`, restarting allow-listed containers) are OFF by default:
    docker compose -f docker-compose.yml -f docker-compose.docker-access.yml up -d
This mounts docker.sock, which is root-equivalent. Service restarts via systemctl are not
possible from a container; use the systemd install for that.

## Alerts
Enabled automatically when env vars are set: Slack (`SLACK_WEBHOOK_URL`),
Telegram (`TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`), generic JSON webhook
(`WEBHOOK_URL`), Email (`smtp_host`+`email_to` in config, `SMTP_USER/PASSWORD`).
You get: start, incident (with LLM report, severity -> level), resolved, loop failing.
Incidents are also stored in `data/incidents.jsonl`.

### Who watches the watcher?
If the whole host dies, the agent cannot alert. Set `HEARTBEAT_URL` to a push monitor
(healthchecks.io, Uptime Kuma): the agent pings it every 60s and the monitor alerts you
when pings stop.

### Permissions for real remediation (dry_run: false)
The service runs as unprivileged user `aiops`. To let it restart specific services, add a
polkit rule (or run a narrow sudoers entry) for only those units; `docker restart`
requires docker-group membership, which is root-equivalent, so grant it deliberately.

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
