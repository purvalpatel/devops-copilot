from __future__ import annotations
import os
import requests


class Notifier:
    def __init__(self, webhook_env: str = "SLACK_WEBHOOK_URL"):
        self.webhook = os.getenv(webhook_env)

    def send(self, title: str, body: str) -> None:
        print(f"\n=== {title} ===\n{body}\n")
        if self.webhook:
            try:
                requests.post(self.webhook, timeout=5,
                              json={"text": f"*{title}*\n```{body[:2800]}```"})
            except requests.RequestException as e:
                print(f"(slack notify failed: {e})")
