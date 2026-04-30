#!/usr/bin/env python3
"""Poll the ADHD bus for pending HITL decisions and notify the human.

Usage:
    hitl-notify.py                          # one-shot check
    hitl-notify.py --daemon                 # poll continuously
    hitl-notify.py --daemon --interval 60   # custom interval (seconds)

Environment variables:
    ADHD_NOTIFY_INTERVAL   Poll interval in seconds (default: 30)
    ADHD_NOTIFY_URGENCY    notify-send urgency: low, normal, critical
    TELEGRAM_BOT_TOKEN     Telegram bot token for fallback
    TELEGRAM_CHAT_ID       Telegram chat ID for fallback
    ADHD_BUS_PATH          Bus storage directory prefix
    ADHD_BUS_SLUG          Bus name
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure the ADHD package is importable when running as a standalone script.
_THIS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _THIS_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from adhd.bus import get_pending_decisions  # noqa: E402
from adhd.notifications import send_notification  # noqa: E402


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(path.read_text().splitlines())


def _save_seen(path: Path, seen: set[str]) -> None:
    path.write_text("\n".join(sorted(seen)) + "\n")


def poll(seen_file: Path) -> int:
    """Check for pending decisions and notify for new ones.

    Returns the number of new decisions found.
    """
    seen = _load_seen(seen_file)
    decisions = get_pending_decisions()
    new_count = 0

    for d in decisions:
        did = d["decision_id"]
        if did in seen:
            continue
        title = f"HITL Decision: {did}"
        urgency = d.get("urgency", "medium")
        body = d.get("description", "No description")
        send_notification(title, body, urgency)
        seen.add(did)
        new_count += 1

    if new_count:
        _save_seen(seen_file, seen)

    return new_count


def main() -> None:
    daemon = "--daemon" in sys.argv
    interval = int(os.environ.get("ADHD_NOTIFY_INTERVAL", "30"))

    for arg in sys.argv[1:]:
        if arg.startswith("--interval="):
            interval = int(arg.split("=", 1)[1])

    # Store seen decisions in the same directory as the bus
    bus_dir = os.environ.get("ADHD_BUS_PATH", str(Path.home() / ".brainxio" / "adhd"))
    slug = os.environ.get("ADHD_BUS_SLUG", "attention-deficit-hyperactivity-driver")
    seen_file = Path(bus_dir) / slug / ".hitl_notified_ids"

    if daemon:
        while True:
            try:
                poll(seen_file)
            except Exception:
                pass
            time.sleep(interval)
    else:
        new = poll(seen_file)
        if new:
            print(f"Sent {new} notification(s)")
        else:
            print("No new pending decisions.")


if __name__ == "__main__":
    main()
