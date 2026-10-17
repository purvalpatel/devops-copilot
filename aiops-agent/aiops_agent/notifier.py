"""Multi-channel notifier: Slack, Telegram, Email (SMTP), generic webhook.
A channel is enabled automatically when its env vars / settings are present.
One failing channel never blocks the others."""
from __future__ import annotations
import logging
import os
import smtplib
import socket
import time
from email.message import EmailMessage
import requests
from .config import NotifierCfg

log = logging.getLogger("aiops.notify")
ICON = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨", "resolved": "✅"}


class Notifier:
    def __init__(self, cfg: NotifierCfg | None = None):
        self.cfg = cfg or NotifierCfg()
        self.host = socket.gethostname()

    def send(self, title: str, body: str, level: str = "info") -> None:
        header = f"{ICON.get(level, '')} [{self.host}] {title}"
        text = f"{header}\n\n{body}"
        print(f"\n{text}\n", flush=True)
        for name, fn in self._channels(header, text, title, body, level):
            self._with_retry(name, fn)

    # -- channels ------------------------------------------------------------
    def _channels(self, header, text, title, body, level):
        c = self.cfg
        if url := os.getenv(c.slack_webhook_env, ""):
            yield "slack", lambda: self._post(url, {"text": f"*{header}*\n```{body[:2800]}```"})
        if url := os.getenv(c.webhook_url_env, ""):
            yield "webhook", lambda: self._post(url, {
                "title": title, "body": body, "level": level,
                "host": self.host, "ts": time.time(), "text": text[:3500]})
        token, chat = os.getenv(c.telegram_token_env, ""), os.getenv(c.telegram_chat_id_env, "")
        if token and chat:
            yield "telegram", lambda: self._post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                {"chat_id": chat, "text": text[:4000]})
        if c.smtp_host and c.email_to:
            yield "email", lambda: self._email(header, text)

    @staticmethod
    def _post(url: str, payload: dict) -> None:
        requests.post(url, json=payload, timeout=10).raise_for_status()

    def _email(self, subject: str, text: str) -> None:
        c = self.cfg
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, c.email_from or "aiops@" + self.host, ", ".join(c.email_to)
        msg.set_content(text)
        with smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=15) as s:
            if c.smtp_starttls:
                s.starttls()
            user, pw = os.getenv(c.smtp_user_env, ""), os.getenv(c.smtp_password_env, "")
            if user:
                s.login(user, pw)
            s.send_message(msg)

    @staticmethod
    def _with_retry(name: str, fn, attempts: int = 3) -> None:
        for i in range(attempts):
            try:
                fn()
                return
            except Exception as e:      # noqa: BLE001 - notifier must never crash the agent
                log.warning("notify via %s failed (%d/%d): %s", name, i + 1, attempts, e)
                time.sleep(min(2 ** i, 4))

    # -- dead-man's switch ---------------------------------------------------
    def heartbeat_url(self) -> str:
        return os.getenv(self.cfg.heartbeat_url_env, "")

    def ping_heartbeat(self) -> None:
        if url := self.heartbeat_url():
            try:
                requests.get(url, timeout=10)
            except requests.RequestException as e:
                log.warning("heartbeat failed: %s", e)
