"""Unit tests for adhd.bus core logic."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import adhd.bus as bus


def _sample_message() -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "session_id": "sess-123",
        "agent_id": "agent-a",
        "branch": "feat/test",
        "type": "signin",
        "topic": "agent-lifecycle",
        "payload": {},
    }


@pytest.fixture
def temp_bus(tmp_path: Path) -> Path:
    """Provide a temporary bus file and patch resolve() to use it."""
    bus_file = tmp_path / "bus.jsonl"
    with patch.object(bus, "resolve", return_value=bus_file):
        yield bus_file


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_resolve_default(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    toplevel = tmp_path / "my-project"
    toplevel.mkdir()

    with patch.dict(os.environ, {}, clear=True):
        with patch("adhd.bus.Path.home", return_value=fake_home):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = str(toplevel) + "\n"
                mock_run.return_value.returncode = 0
                result = bus.resolve()

    expected = fake_home / ".brainxio" / "adhd" / "my-project" / "bus.jsonl"
    assert result == expected
    assert expected.parent.exists()


def test_resolve_adhd_bus_path_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom-bus.jsonl"
    custom.write_text("")
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(custom)}):
        result = bus.resolve()
    assert result == custom.resolve()


def test_resolve_adhd_bus_repo_slug(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch.dict(os.environ, {"ADHD_BUS_REPO_SLUG": "projects"}, clear=True):
        with patch("adhd.bus.Path.home", return_value=fake_home):
            result = bus.resolve()
    expected = fake_home / ".brainxio" / "adhd" / "projects" / "bus.jsonl"
    assert result == expected


def test_resolve_fallback_no_git(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch.dict(os.environ, {}, clear=True):
        with patch("adhd.bus.Path.home", return_value=fake_home):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
                result = bus.resolve()
    expected = fake_home / ".brainxio" / "adhd" / "default" / "bus.jsonl"
    assert result == expected


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


def test_session_id_from_env() -> None:
    with patch.object(bus, "_session_id", "abc123"):
        assert bus.session_id() == "abc123"


def test_session_id_random() -> None:
    sid = bus.session_id()
    assert len(sid) == 8


def test_agent_id_from_env() -> None:
    with patch.dict(os.environ, {"ADHD_AGENT_ID": "my-agent"}):
        assert bus.agent_id() == "my-agent"


def test_agent_id_default() -> None:
    with patch.object(bus, "_session_id", "sess-1"):
        with patch.dict(os.environ, {}, clear=True):
            assert bus.agent_id() == "agent-sess-1"


# ---------------------------------------------------------------------------
# Bus I/O
# ---------------------------------------------------------------------------


def test_write_message(temp_bus: Path) -> None:
    bus.write_message(_sample_message())
    assert temp_bus.exists()
    lines = temp_bus.read_text().strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["type"] == "signin"
    assert stored["agent_id"] == "agent-a"


def test_read_messages_empty(temp_bus: Path) -> None:
    assert bus.read_messages() == []


def test_read_messages_limit(temp_bus: Path) -> None:
    for i in range(5):
        msg = _sample_message()
        msg["agent_id"] = f"agent-{i}"
        bus.write_message(msg)
    msgs = bus.read_messages(limit=3)
    assert len(msgs) == 3
    assert msgs[0]["agent_id"] == "agent-2"


def test_read_messages_type_filter(temp_bus: Path) -> None:
    signin_msg = _sample_message()
    signin_msg["type"] = "signin"
    bus.write_message(signin_msg)

    hb_msg = _sample_message()
    hb_msg["type"] = "heartbeat"
    bus.write_message(hb_msg)

    msgs = bus.read_messages(type_filter="heartbeat")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "heartbeat"


def test_read_messages_topic_filter(temp_bus: Path) -> None:
    coord_msg = _sample_message()
    coord_msg["topic"] = "coordination"
    bus.write_message(coord_msg)

    activity_msg = _sample_message()
    activity_msg["topic"] = "agent-activity"
    bus.write_message(activity_msg)

    msgs = bus.read_messages(topic_filter="agent-activity")
    assert len(msgs) == 1
    assert msgs[0]["topic"] == "agent-activity"


def test_read_messages_agent_filter(temp_bus: Path) -> None:
    alice_msg = _sample_message()
    alice_msg["agent_id"] = "alice"
    bus.write_message(alice_msg)

    bob_msg = _sample_message()
    bob_msg["agent_id"] = "bob"
    bus.write_message(bob_msg)

    msgs = bus.read_messages(agent_filter="alice")
    assert len(msgs) == 1
    assert msgs[0]["agent_id"] == "alice"


def test_read_skips_invalid_json(temp_bus: Path) -> None:
    temp_bus.write_text("not json\n")
    assert bus.read_messages() == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_valid() -> None:
    line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s1",
            "agent_id": "a1",
            "branch": "main",
            "type": "signin",
            "topic": "agent-lifecycle",
            "payload": {},
        }
    )
    ok, err = bus.validate(line)
    assert ok is True
    assert err == ""


def test_validate_invalid_json() -> None:
    ok, err = bus.validate("not json")
    assert ok is False
    assert "Invalid JSON" in err


def test_validate_missing_fields() -> None:
    line = json.dumps({"type": "signin"})
    ok, err = bus.validate(line)
    assert ok is False
    assert "Missing fields" in err


def test_validate_payload_not_object() -> None:
    line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s1",
            "agent_id": "a1",
            "branch": "main",
            "type": "signin",
            "topic": "agent-lifecycle",
            "payload": "string",
        }
    )
    ok, err = bus.validate(line)
    assert ok is False
    assert "payload must be an object" in err


def test_validate_invalid_type() -> None:
    line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "s1",
            "agent_id": "a1",
            "branch": "main",
            "type": "bad_type",
            "topic": "agent-lifecycle",
            "payload": {},
        }
    )
    ok, err = bus.validate(line)
    assert ok is False
    assert "Invalid type" in err


def test_validate_bus_empty(temp_bus: Path) -> None:
    ok, msg = bus.validate_bus()
    assert ok is True
    assert "does not exist" in msg


def test_validate_bus_valid(temp_bus: Path) -> None:
    bus.write_message(_sample_message())
    ok, msg = bus.validate_bus()
    assert ok is True
    assert msg == "Bus is valid"


def test_validate_bus_invalid(temp_bus: Path) -> None:
    temp_bus.write_text("bad json\n")
    ok, msg = bus.validate_bus()
    assert ok is False
    assert "Invalid JSON" in msg


# ---------------------------------------------------------------------------
# Main session management
# ---------------------------------------------------------------------------


def test_check_main_no_messages(temp_bus: Path) -> None:
    assert bus.check_main() is None


def test_check_main_set(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["type"] = "main_session_set"
    msg["topic"] = "coordination"
    msg["agent_id"] = "coordinator"
    bus.write_message(msg)
    assert bus.check_main() == "coordinator"


def test_check_main_released(temp_bus: Path) -> None:
    set_msg = _sample_message()
    set_msg["type"] = "main_session_set"
    set_msg["topic"] = "coordination"
    set_msg["agent_id"] = "coordinator"
    bus.write_message(set_msg)

    rel_msg = _sample_message()
    rel_msg["type"] = "main_session_released"
    rel_msg["topic"] = "coordination"
    rel_msg["agent_id"] = "coordinator"
    bus.write_message(rel_msg)

    assert bus.check_main() is None


def test_claim_main_success(temp_bus: Path) -> None:
    result = bus.claim_main(agent_id_str="new-main")
    assert result.success is True
    assert "claimed by new-main" in result.message


def test_claim_main_blocked_by_active(temp_bus: Path) -> None:
    ts = datetime.now(UTC).isoformat()

    set_msg = _sample_message()
    set_msg["timestamp"] = ts
    set_msg["type"] = "main_session_set"
    set_msg["topic"] = "coordination"
    set_msg["agent_id"] = "existing-main"
    bus.write_message(set_msg)

    hb_msg = _sample_message()
    hb_msg["timestamp"] = ts
    hb_msg["type"] = "heartbeat"
    hb_msg["topic"] = "agent-lifecycle"
    hb_msg["agent_id"] = "existing-main"
    bus.write_message(hb_msg)

    result = bus.claim_main(agent_id_str="new-main")
    assert result.success is False
    assert "held by existing-main" in result.message


def test_claim_main_allowed_after_expiry(temp_bus: Path) -> None:
    old_ts = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

    set_msg = _sample_message()
    set_msg["timestamp"] = old_ts
    set_msg["type"] = "main_session_set"
    set_msg["topic"] = "coordination"
    set_msg["agent_id"] = "old-main"
    bus.write_message(set_msg)

    hb_msg = _sample_message()
    hb_msg["timestamp"] = old_ts
    hb_msg["type"] = "heartbeat"
    hb_msg["topic"] = "agent-lifecycle"
    hb_msg["agent_id"] = "old-main"
    bus.write_message(hb_msg)

    result = bus.claim_main(agent_id_str="new-main")
    assert result.success is True


def test_release_main(temp_bus: Path) -> None:
    bus.release_main(agent_id_str="coordinator")
    msgs = bus.read_messages(type_filter="main_session_released")
    assert len(msgs) == 1
    assert msgs[0]["agent_id"] == "coordinator"


def test_elect_main_no_sessions(temp_bus: Path) -> None:
    result = bus.elect_main()
    assert result.success is False
    assert "No active sessions" in result.message


def test_elect_main_success(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["type"] = "signin"
    msg["agent_id"] = "oldest"
    bus.write_message(msg)

    result = bus.elect_main()
    assert result.success is True
    assert "claimed by oldest" in result.message


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def test_signin(temp_bus: Path) -> None:
    msg = bus.signin()
    assert msg == "Signed in."
    msgs = bus.read_messages(type_filter="signin")
    assert len(msgs) == 1


def test_signout(temp_bus: Path) -> None:
    msg = bus.signout()
    assert msg == "Signed out."
    msgs = bus.read_messages(type_filter="signout")
    assert len(msgs) == 1


def test_post(temp_bus: Path) -> None:
    msg = bus.post(type_="status", topic="agent-activity", payload={"state": "ok"})
    assert "Posted status" in msg
    msgs = bus.read_messages(type_filter="status")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["state"] == "ok"


def test_send(temp_bus: Path) -> None:
    msg = bus.send(to="all", message="hello", topic="test", type_="request")
    assert "Sent request" in msg
    msgs = bus.read_messages(type_filter="request")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["recipient"] == "all"


# ---------------------------------------------------------------------------
# Archival
# ---------------------------------------------------------------------------


def test_archive_no_file(temp_bus: Path) -> None:
    nonexistent = temp_bus.with_name("nonexistent.jsonl")
    with patch.object(bus, "resolve", return_value=nonexistent):
        msg = bus.archive()
    assert "does not exist" in msg


def test_archive_under_limit(temp_bus: Path) -> None:
    for _ in range(10):
        bus.write_message(_sample_message())
    msg = bus.archive()
    assert "No archive needed" in msg


def test_archive_over_limit(temp_bus: Path) -> None:
    with patch.object(bus, "MAX_LINES", 5), patch.object(bus, "ARCHIVE_KEEP", 2):
        for i in range(6):
            msg = _sample_message()
            msg["agent_id"] = f"agent-{i}"
            bus.write_message(msg)
        msg = bus.archive()
    assert "Archived" in msg
    assert "Retained" in msg
    lines = temp_bus.read_text().splitlines()
    assert len(lines) == 2
