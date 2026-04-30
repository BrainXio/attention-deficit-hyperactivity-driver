"""Desktop and Telegram notification helpers for HITL decisions."""

from __future__ import annotations

import logging
import os
import subprocess
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

NOTIFY_SEND_BIN = "notify-send"


def send_notification(title: str, body: str = "", urgency: str = "normal") -> bool:
    """Send a notification via the best available channel.

    Tries notify-send first (Linux desktop), falls back to Telegram Bot API.
    Returns True if at least one channel succeeded.
    """
    urgency = os.environ.get("ADHD_NOTIFY_URGENCY", urgency)
    if _try_notify_send(title, body, urgency):
        return True
    if _try_telegram(title, body):
        return True
    logger.warning("No notification channel available (notify-send or Telegram)")
    return False


def _try_notify_send(title: str, body: str, urgency: str) -> bool:
    try:
        subprocess.run(
            [NOTIFY_SEND_BIN, "-u", urgency, title, body],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _try_telegram(title: str, body: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    text = f"*{title}*\n{body}" if body else f"*{title}*"
    params: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        import json

        data = json.dumps(params).encode("utf-8")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        logger.debug("Telegram notification failed", exc_info=True)
        return False
