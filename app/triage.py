from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

VALID_TYPES = {"disk", "cpu", "memory", "pod", "deployment"}

def investigate(question: str, target: Optional[str], incident: Dict[str, Any]) -> Dict[str, Any]:
    kind = (incident.get("type") or "").lower()
    if kind not in VALID_TYPES:
        raise ValueError(f"Unsupported incident type. Choose one of: {', '.join(sorted(VALID_TYPES))}")

    evidence: List[str] = []
    findings: List[str] = []
    recommendations: List[str] = []
    risk = "LOW"
    severity = "INFO"
    summary = "No threshold breach identified from the supplied evidence."

    if kind == "disk":
        usage = incident.get("usage_percent")
        inode = incident.get("inode_usage_percent")
        growth = incident.get("growth_gb_per_hour")
        free_gb = incident.get("free_gb")
        if usage is not None:
            evidence.append(f"Filesystem usage is {usage:.1f}%.")
            if usage >= 95:
                severity, risk = "CRITICAL", "HIGH"
                findings.append("Filesystem is critically full.")
            elif usage >= 90:
                severity, risk = "HIGH", "HIGH"
                findings.append("Filesystem usage is above 90%.")
            elif usage >= 80:
                severity, risk = "WARNING", "MEDIUM"
                findings.append("Filesystem usage is above 80%.")
        if free_gb is not None:
            evidence.append(f"Free space is {free_gb:.2f} GB.")
        if inode is not None:
            evidence.append(f"Inode usage is {inode:.1f}%.")
            if inode >= 90:
                findings.append("Inode exhaustion may be a separate risk.")
                severity = "CRITICAL" if severity in {"INFO", "WARNING", "HIGH"} else severity
                risk = "HIGH"
        paths = sorted(incident.get("largest_paths") or [], key=lambda x: x.get("size_gb", 0), reverse=True)
        if paths:
            evidence.append("Largest reported paths: " + ", ".join(
                f"{p.get('path')} ({p.get('size_gb')} GB)" for p in paths[:5]
            ) + ".")
            findings.append(f"Largest reported path is {paths[0].get('path')} ({paths[0].get('size_gb')} GB).")
        if growth and growth > 0 and usage is not None and free_gb is not None:
            evidence.append(f"Reported free-space consumption rate is {growth:.2f} GB/hour.")
            hours = free_gb / growth
            findings.append(f"At the supplied rate, current free space could be consumed in about {hours:.1f} hours; this is a rough linear estimate.")
        recommendations += [
            "Confirm the filesystem, mount point, and trend using trusted monitoring data.",
            "Inspect the largest paths and identify the owning service before changing files.",
            "Check log rotation and retention configuration if logs are growing.",
            "Do not delete open files or Docker volumes without owner and impact checks."
        ]
        summary = "Disk capacity risk detected." if severity != "INFO" else summary

    elif kind in {"cpu", "memory"}:
        field = "cpu_percent" if kind == "cpu" else "memory_percent"
        value = incident.get(field)
        if value is None:
            evidence.append(f"No {kind} percentage was supplied.")
        else:
            evidence.append(f"{kind.upper()} utilization is {value:.1f}%.")
            if value >= 95:
                severity, risk = "CRITICAL", "HIGH"
                findings.append(f"{kind.upper()} utilization is critically high.")
            elif value >= 85:
                severity, risk = "WARNING", "MEDIUM"
                findings.append(f"{kind.upper()} utilization is elevated.")
            else:
                findings.append(f"{kind.upper()} utilization is below the configured warning threshold.")
        recommendations += [
            "Correlate utilization with traffic, latency, errors, and recent deployments.",
            "Identify top processes using an approved read-only telemetry source.",
            "Scale only after checking capacity, saturation, and cost constraints."
        ]
        summary = f"{kind.upper()} capacity investigation completed."

    elif kind == "pod":
        status = incident.get("pod_status") or "unknown"
        restarts = incident.get("restart_count")
        evidence.append(f"Pod status is {status}.")
        if restarts is not None:
            evidence.append(f"Restart count is {restarts}.")
        if status.lower() in {"crashloopbackoff", "error", "imagepullbackoff", "pending"} or (restarts or 0) >= 5:
            severity, risk = "HIGH", "MEDIUM"
            findings.append("Pod status or restart count indicates an unhealthy workload.")
        if incident.get("recent_change"):
            evidence.append(f"Recent change reported: {incident['recent_change']}.")
            findings.append("Correlate the incident start time with the recent change.")
        recommendations += [
            "Inspect pod events and previous-container logs.",
            "Check image availability, probes, resource limits, secrets, and config changes.",
            "Compare the current ReplicaSet with the last known healthy revision."
        ]
        summary = "Kubernetes workload health investigation completed."

    elif kind == "deployment":
        status = incident.get("deployment_status") or "unknown"
        evidence.append(f"Deployment status is {status}.")
        if status.lower() not in {"healthy", "available", "success", "successful"}:
            severity, risk = "HIGH", "MEDIUM"
            findings.append("Deployment status is not reported as healthy.")
        if incident.get("recent_change"):
            evidence.append(f"Recent change reported: {incident['recent_change']}.")
        recommendations += [
            "Inspect rollout status, events, readiness, and application health checks.",
            "Compare the deployed image/chart version with the last known healthy release.",
            "Prepare a rollback plan; require an authorized human approval before executing it."
        ]
        summary = "Deployment health investigation completed."

    if not findings:
        findings.append("The supplied evidence does not establish a specific root cause.")
    if not recommendations:
        recommendations.append("Collect more telemetry before taking action.")

    return {
        "incident_id": "DEMO-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "agent": "DevOps Copilot",
        "target": target or incident.get("host") or "unspecified",
        "question": question,
        "incident_type": kind,
        "severity": severity,
        "risk": risk,
        "summary": summary,
        "evidence": evidence,
        "findings": findings,
        "recommendations": recommendations,
        "actions_executed": [],
        "approval_required_for_changes": True,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
