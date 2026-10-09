from app.triage import investigate

def test_disk_critical():
    report = investigate("check disk", "server-1", {
        "type": "disk", "host": "server-1", "usage_percent": 96,
        "free_gb": 4, "growth_gb_per_hour": 1, "inode_usage_percent": 45,
        "largest_paths": [{"path": "/var/log", "size_gb": 28}]
    })
    assert report["severity"] == "CRITICAL"
    assert report["risk"] == "HIGH"
    assert report["actions_executed"] == []

def test_unhealthy_pod():
    report = investigate("check pod", "cluster-1", {
        "type": "pod", "pod_status": "CrashLoopBackOff", "restart_count": 8
    })
    assert report["severity"] == "HIGH"
