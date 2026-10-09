# DevOps Copilot — AIOps Agent Starter

A safe, read-only starter agent for DevOps engineers. It accepts incident questions, inspects supplied or demo infrastructure data, and returns a structured diagnosis. It does **not** execute shell commands, delete files, restart services, or change AWS/Kubernetes resources.

## Features
- Disk, CPU, memory, Kubernetes pod, and deployment incident triage
- Rule-based checks before producing a report
- Optional LLM summary via Amazon Bedrock (disabled by default)
- FastAPI HTTP API
- Dockerfile
- Clear path to connect Prometheus, CloudWatch, AWS Systems Manager (SSM), and Kubernetes APIs

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs and try `POST /investigate`.

Example body:

```json
{
  "question": "Investigate high disk usage",
  "target": "prod-api-02",
  "incident": {
    "type": "disk",
    "host": "prod-api-02",
    "filesystem": "/var",
    "usage_percent": 96,
    "free_gb": 4,
    "growth_gb_per_hour": 1.2,
    "inode_usage_percent": 45,
    "largest_paths": [
      {"path": "/var/log", "size_gb": 28},
      {"path": "/var/lib/docker", "size_gb": 12}
    ]
  }
}
```

## API endpoints
- `GET /health` — liveness check
- `GET /demo/incidents` — sample incidents
- `POST /investigate` — investigate an incident payload

## Optional Amazon Bedrock summary

The starter works without an LLM. To enable Bedrock, set:

```bash
export ENABLE_BEDROCK=true
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID="your-approved-model-id"
```

Configure AWS credentials using an IAM role or your normal AWS credential chain. The Bedrock model must be enabled for your AWS account/region. Keep Bedrock optional; deterministic checks remain the source of truth.

## Production integration plan

1. **Metrics:** Prometheus / Amazon Managed Service for Prometheus.
2. **Logs:** CloudWatch Logs Insights, with restricted query access.
3. **Host investigation:** AWS Systems Manager Run Command using a fixed allowlist of read-only commands.
4. **Kubernetes:** Kubernetes API with a read-only service account and narrow RBAC.
5. **Notifications:** SNS, Slack, or Microsoft Teams.
6. **Audit:** Record incident ID, evidence, recommendation, tool calls, approvals, and outcome.
7. **Remediation:** Add a separate policy-controlled service. Require human approval for destructive/high-impact actions; do not give the LLM unrestricted shell or administrator access.

## Safety
- Demo data is synthetic.
- No commands are run on hosts by this app.
- No remediation endpoint is provided.
- Do not put credentials, secrets, tokens, or sensitive log data in prompts.
- Before production, add authentication, authorization, TLS, rate limits, input validation, audit retention, and tests.
