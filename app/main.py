from typing import Any, Dict, List, Optional
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.triage import investigate

app = FastAPI(
    title="DevOps Copilot",
    description="Read-only AIOps starter for infrastructure incident triage.",
    version="0.1.0",
)

class PathSize(BaseModel):
    path: str
    size_gb: float = Field(ge=0)

class Incident(BaseModel):
    type: str = Field(description="disk, cpu, memory, pod, or deployment")
    host: Optional[str] = None
    filesystem: Optional[str] = None
    usage_percent: Optional[float] = Field(default=None, ge=0, le=100)
    free_gb: Optional[float] = Field(default=None, ge=0)
    growth_gb_per_hour: Optional[float] = Field(default=None, ge=0)
    inode_usage_percent: Optional[float] = Field(default=None, ge=0, le=100)
    cpu_percent: Optional[float] = Field(default=None, ge=0, le=100)
    memory_percent: Optional[float] = Field(default=None, ge=0, le=100)
    namespace: Optional[str] = None
    pod: Optional[str] = None
    pod_status: Optional[str] = None
    restart_count: Optional[int] = Field(default=None, ge=0)
    deployment_status: Optional[str] = None
    recent_change: Optional[str] = None
    largest_paths: List[PathSize] = []

class InvestigateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    target: Optional[str] = None
    incident: Incident

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "agent": "devops-copilot"}

@app.get("/demo/incidents")
def demo_incidents() -> List[Dict[str, Any]]:
    return [
        {
            "type": "disk", "host": "prod-api-02", "filesystem": "/var",
            "usage_percent": 96, "free_gb": 4, "growth_gb_per_hour": 1.2,
            "inode_usage_percent": 45,
            "largest_paths": [
                {"path": "/var/log", "size_gb": 28},
                {"path": "/var/lib/docker", "size_gb": 12}
            ]
        },
        {
            "type": "pod", "host": "eks-prod", "namespace": "payments",
            "pod": "payments-api-7d9b", "pod_status": "CrashLoopBackOff",
            "restart_count": 14, "recent_change": "image tag changed 12 minutes ago"
        },
        {
            "type": "cpu", "host": "prod-web-01", "cpu_percent": 94,
            "recent_change": "traffic increased 35% over baseline"
        }
    ]

@app.post("/investigate")
def investigate_endpoint(req: InvestigateRequest) -> Dict[str, Any]:
    try:
        report = investigate(req.question, req.target, req.incident.model_dump())
        return report
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
