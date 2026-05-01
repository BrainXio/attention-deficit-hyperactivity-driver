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
    """Provide a temporary bus file, reset Lamport clock, and patch resolve()."""
    bus_file = tmp_path / "bus.jsonl"
    bus_file.write_text("")  # ensure the file exists
    bus._lamport_clock = 0
    with patch.object(bus, "resolve", return_value=bus_file):
        yield bus_file
    bus._lamport_clock = 0


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_resolve_default(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    toplevel = tmp_path / "my-project"
    toplevel.mkdir()

    env = {"HOME": str(fake_home)}
    with patch.dict(os.environ, env, clear=True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = str(toplevel) + "\n"
            mock_run.return_value.returncode = 0
            result = bus.resolve()

    expected = fake_home / ".brainxio" / "adhd" / "my-project" / "bus.jsonl"
    assert result == expected
    assert expected.parent.exists()


def test_resolve_adhd_bus_path_override(tmp_path: Path) -> None:
    custom_dir = tmp_path / "custom-store"
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(custom_dir), "ADHD_BUS_SLUG": "mybus"}):
        result = bus.resolve()
    assert result == (custom_dir / "mybus" / "bus.jsonl").resolve()


def test_resolve_adhd_bus_slug(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {"HOME": str(fake_home), "ADHD_BUS_SLUG": "projects"}
    with patch.dict(os.environ, env, clear=True):
        result = bus.resolve()
    expected = fake_home / ".brainxio" / "adhd" / "projects" / "bus.jsonl"
    assert result == expected


def test_resolve_fallback_no_git(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {"HOME": str(fake_home)}
    with patch.dict(os.environ, env, clear=True):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = bus.resolve()
    expected = fake_home / ".brainxio" / "adhd" / "default" / "bus.jsonl"
    assert result == expected


def test_resolve_superproject(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    superproject = tmp_path / "workspace-root"
    superproject.mkdir()

    def _mock_run(cmd: list[str], **kwargs: Any) -> Any:
        class _Result:
            stdout = ""
            returncode = 0

        result = _Result()
        if "--show-superproject-working-tree" in cmd:
            result.stdout = str(superproject) + "\n"
        elif "--show-toplevel" in cmd:
            result.stdout = str(tmp_path / "adhd-submodule") + "\n"
        return result

    env = {"HOME": str(fake_home)}
    with patch.dict(os.environ, env, clear=True):
        with patch("subprocess.run", side_effect=_mock_run):
            result = bus.resolve()
    expected = fake_home / ".brainxio" / "adhd" / "workspace-root" / "bus.jsonl"
    assert result == expected


def test_resolve_superproject_empty_uses_toplevel(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    toplevel = tmp_path / "my-project"
    toplevel.mkdir()

    def _mock_run(cmd: list[str], **kwargs: Any) -> Any:
        class _Result:
            stdout = ""
            returncode = 0

        result = _Result()
        if "--show-superproject-working-tree" in cmd:
            result.stdout = "\n"  # empty → not a submodule
        elif "--show-toplevel" in cmd:
            result.stdout = str(toplevel) + "\n"
        return result

    env = {"HOME": str(fake_home)}
    with patch.dict(os.environ, env, clear=True):
        with patch("subprocess.run", side_effect=_mock_run):
            result = bus.resolve()
    expected = fake_home / ".brainxio" / "adhd" / "my-project" / "bus.jsonl"
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
# Performance level
# ---------------------------------------------------------------------------


def test_get_perf_level_default() -> None:
    """get_perf_level returns 'medium' when ADHD_PERF_LEVEL is not set."""
    with patch.dict(os.environ, {}, clear=True):
        assert bus.get_perf_level() == "medium"


def test_get_perf_level_from_env() -> None:
    """get_perf_level returns the value from ADHD_PERF_LEVEL env var."""
    with patch.dict(os.environ, {"ADHD_PERF_LEVEL": "high"}):
        assert bus.get_perf_level() == "high"
    with patch.dict(os.environ, {"ADHD_PERF_LEVEL": "low"}):
        assert bus.get_perf_level() == "low"


def test_get_perf_level_case_insensitive() -> None:
    """get_perf_level handles mixed case."""
    with patch.dict(os.environ, {"ADHD_PERF_LEVEL": "HIGH"}):
        assert bus.get_perf_level() == "high"


def test_get_perf_level_invalid() -> None:
    """get_perf_level falls back to 'medium' for invalid values."""
    with patch.dict(os.environ, {"ADHD_PERF_LEVEL": "extreme"}):
        assert bus.get_perf_level() == "medium"


def test_signin_includes_perf_level_when_supporter(temp_bus: Path) -> None:
    """Signin payload includes perf_level when ADHD_ENABLE_SUPPORTER is set."""
    with patch.dict(os.environ, {"ADHD_ENABLE_SUPPORTER": "1", "ADHD_PERF_LEVEL": "low"}):
        bus.signin()
    msgs = bus.read_messages(type_filter="signin")
    assert msgs[0]["payload"]["supporter"] is True
    assert msgs[0]["payload"]["perf_level"] == "low"


def test_signin_no_perf_level_when_not_supporter(temp_bus: Path) -> None:
    """Signin payload does NOT include perf_level when not a supporter."""
    bus.signin()
    msgs = bus.read_messages(type_filter="signin")
    assert "perf_level" not in msgs[0]["payload"]


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


def test_read_messages_recipient_filter_exact(temp_bus: Path) -> None:
    msg1 = _sample_message()
    msg1["payload"] = {"recipient": "agent-xyz", "message": "hello"}
    bus.write_message(msg1)

    msg2 = _sample_message()
    msg2["payload"] = {"recipient": "agent-abc", "message": "hi"}
    bus.write_message(msg2)

    msgs = bus.read_messages(recipient_filter="agent-xyz")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["recipient"] == "agent-xyz"


def test_read_messages_recipient_filter_all_wildcard(temp_bus: Path) -> None:
    msg1 = _sample_message()
    msg1["payload"] = {"recipient": "all", "message": "broadcast"}
    bus.write_message(msg1)

    msg2 = _sample_message()
    msg2["payload"] = {"recipient": "agent-specific", "message": "direct"}
    bus.write_message(msg2)

    msgs = bus.read_messages(recipient_filter="all")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["recipient"] == "all"


def test_read_messages_recipient_filter_no_match(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["payload"] = {"recipient": "agent-known", "message": "data"}
    bus.write_message(msg)

    msgs = bus.read_messages(recipient_filter="agent-unknown")
    assert msgs == []


def test_read_messages_recipient_filter_default_none(temp_bus: Path) -> None:
    msg1 = _sample_message()
    msg1["payload"] = {}
    bus.write_message(msg1)

    msg2 = _sample_message()
    msg2["payload"] = {"recipient": "someone", "message": "hi"}
    bus.write_message(msg2)

    msgs = bus.read_messages()
    assert len(msgs) == 2


def test_read_messages_recipient_filter_missing_payload(temp_bus: Path) -> None:
    msg1 = _sample_message()
    msg1["payload"] = {"recipient": "agent-target", "message": "found"}
    bus.write_message(msg1)

    msg2 = _sample_message()
    msg2["payload"] = {}
    bus.write_message(msg2)

    msg3 = _sample_message()
    msg3["payload"] = "not-a-dict"
    bus.write_message(msg3)

    msgs = bus.read_messages(recipient_filter="agent-target")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["recipient"] == "agent-target"


def test_read_skips_invalid_json(temp_bus: Path) -> None:
    temp_bus.write_text("not json\n")
    assert bus.read_messages() == []


# ---------------------------------------------------------------------------
# Position-based reading
# ---------------------------------------------------------------------------


def test_get_file_size_empty(temp_bus: Path) -> None:
    assert bus.get_file_size() == 0


def test_get_file_size_with_messages(temp_bus: Path) -> None:
    bus.write_message(_sample_message())
    assert bus.get_file_size() > 0


def test_read_messages_since_empty(temp_bus: Path) -> None:
    msgs, pos = bus.read_messages_since(0)
    assert msgs == []
    assert pos == 0


def test_read_messages_since_returns_new_messages(temp_bus: Path) -> None:
    bus.write_message(_sample_message())
    msgs, pos = bus.read_messages_since(0)
    assert len(msgs) == 1
    assert pos > 0


def test_read_messages_since_skips_already_read(temp_bus: Path) -> None:
    bus.write_message(_sample_message())
    _, pos = bus.read_messages_since(0)
    # Second read from same position returns nothing
    msgs, new_pos = bus.read_messages_since(pos)
    assert msgs == []
    assert new_pos == pos


def test_read_messages_since_sees_new_appends(temp_bus: Path) -> None:
    bus.write_message(_sample_message())
    _, pos = bus.read_messages_since(0)
    # Write another message
    msg2 = _sample_message()
    msg2["agent_id"] = "agent-b"
    bus.write_message(msg2)
    msgs, new_pos = bus.read_messages_since(pos)
    assert len(msgs) == 1
    assert msgs[0]["agent_id"] == "agent-b"
    assert new_pos > pos


def test_read_messages_since_with_filters(temp_bus: Path) -> None:
    msg1 = _sample_message()
    msg1["type"] = "heartbeat"
    bus.write_message(msg1)
    msg2 = _sample_message()
    msg2["type"] = "signin"
    bus.write_message(msg2)
    msgs, pos = bus.read_messages_since(0, type_filter="heartbeat")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "heartbeat"
    assert pos > 0


# ---------------------------------------------------------------------------
# Subscription protocol
# ---------------------------------------------------------------------------


def test_subscribe_writes_message(temp_bus: Path) -> None:
    result = bus.subscribe({"type": "heartbeat"})
    assert "Subscribed" in result
    msgs = bus.read_messages(topic_filter="bus-subscriptions")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "subscription"
    assert msgs[0]["payload"]["filters"] == {"type": "heartbeat"}


def test_unsubscribe_writes_message(temp_bus: Path) -> None:
    bus.subscribe({"type": "heartbeat"})
    result = bus.unsubscribe()
    assert "Unsubscribed" in result
    msgs = bus.read_messages(topic_filter="bus-subscriptions")
    assert msgs[-1]["type"] == "unsubscription"


def test_get_subscriptions_returns_active(temp_bus: Path) -> None:
    bus.subscribe({"topic": "agent-lifecycle"})
    subs = bus.get_subscriptions()
    assert bus.agent_id() in subs
    assert subs[bus.agent_id()] == {"topic": "agent-lifecycle"}


def test_get_subscriptions_removes_unsubscribed(temp_bus: Path) -> None:
    bus.subscribe({"recipient": "test-agent"})
    bus.unsubscribe()
    subs = bus.get_subscriptions()
    assert bus.agent_id() not in subs


def test_get_subscriptions_multiple_agents(temp_bus: Path) -> None:
    # Write subscription messages for different agents using post with override
    bus.post(
        "subscription",
        "bus-subscriptions",
        {"action": "subscribe", "filters": {"type": "heartbeat"}},
        agent_id_override="agent-x",
    )
    bus.post(
        "subscription",
        "bus-subscriptions",
        {"action": "subscribe", "filters": {"recipient": "all"}},
        agent_id_override="agent-y",
    )
    subs = bus.get_subscriptions()
    assert "agent-x" in subs
    assert "agent-y" in subs
    assert subs["agent-x"] == {"type": "heartbeat"}
    assert subs["agent-y"] == {"recipient": "all"}


# ---------------------------------------------------------------------------
# Migration protocol
# ---------------------------------------------------------------------------


def test_announce_migration(temp_bus: Path) -> None:
    result = bus.announce_migration()
    assert "announcement" in result.lower()
    msgs = bus.read_messages(topic_filter="bus-migration")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "migration_announce"


def test_ack_migration(temp_bus: Path) -> None:
    result = bus.ack_migration()
    assert "acknowledged" in result.lower()
    msgs = bus.read_messages(topic_filter="bus-migration")
    assert msgs[0]["type"] == "migration_ack"


def test_get_pending_migration_acks_none_acked(temp_bus: Path) -> None:
    pending = bus.get_pending_migration_acks(["agent-a", "agent-b"])
    assert sorted(pending) == ["agent-a", "agent-b"]


def test_get_pending_migration_acks_some_acked(temp_bus: Path) -> None:
    # Write ack for agent-a using post with override
    bus.post(
        "migration_ack",
        "bus-migration",
        {"action": "ack"},
        agent_id_override="agent-a",
    )
    pending = bus.get_pending_migration_acks(["agent-a", "agent-b"])
    assert pending == ["agent-b"]


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
    # Remove the pre-created file to test the "does not exist" path
    temp_bus.unlink()
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
# Supporter management
# ---------------------------------------------------------------------------


def test_check_supporters_empty(temp_bus: Path) -> None:
    assert bus.check_supporters() == []


def test_check_supporters_no_flag(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["type"] = "signin"
    msg["payload"] = {}
    bus.write_message(msg)
    assert bus.check_supporters() == []


def test_check_supporters_active(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["type"] = "signin"
    msg["payload"] = {"supporter": True}
    msg["agent_id"] = "supporter-a"
    bus.write_message(msg)

    result = bus.check_supporters()
    assert len(result) == 1
    assert result[0]["agent_id"] == "supporter-a"
    assert result[0]["alive"] is True


def test_check_supporters_expired(temp_bus: Path) -> None:
    old_ts = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    msg = _sample_message()
    msg["timestamp"] = old_ts
    msg["type"] = "signin"
    msg["payload"] = {"supporter": True}
    bus.write_message(msg)

    assert bus.check_supporters() == []


def test_check_supporters_signout_removed(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["type"] = "signin"
    msg["payload"] = {"supporter": True}
    msg["session_id"] = "sess-s1"
    bus.write_message(msg)

    out_msg = _sample_message()
    out_msg["type"] = "signout"
    out_msg["session_id"] = "sess-s1"
    bus.write_message(out_msg)

    assert bus.check_supporters() == []


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def test_signin(temp_bus: Path) -> None:
    msg = bus.signin()
    assert msg == "Signed in."
    msgs = bus.read_messages(type_filter="signin")
    assert len(msgs) == 1


def test_signin_supporter(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_ENABLE_SUPPORTER": "1"}):
        msg = bus.signin()
    assert "supporter" in msg.lower()
    msgs = bus.read_messages(type_filter="signin")
    assert msgs[0]["payload"]["supporter"] is True


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
# MCP change notification protocol
# ---------------------------------------------------------------------------


def test_prepare_mcp_change(temp_bus: Path) -> None:
    """Preparing writes an event/mcp-change message with action=preparing."""
    result = bus.prepare_mcp_change("asd")
    assert "preparing" in result.lower()
    msgs = bus.read_messages(topic_filter="mcp-change")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "event"
    assert msgs[0]["payload"]["server"] == "asd"
    assert msgs[0]["payload"]["action"] == "preparing"


def test_mark_mcp_change_ready(temp_bus: Path) -> None:
    """Ready writes an event/mcp-change message with action=ready and commit."""
    bus.prepare_mcp_change("ocd")
    result = bus.mark_mcp_change_ready("ocd", "abc123def")
    assert "ready" in result.lower()
    msgs = bus.read_messages(topic_filter="mcp-change")
    assert len(msgs) == 2
    assert msgs[1]["payload"]["action"] == "ready"
    assert msgs[1]["payload"]["commit"] == "abc123def"


def test_mark_mcp_change_ready_no_commit(temp_bus: Path) -> None:
    """Ready with no commit defaults to empty string."""
    bus.prepare_mcp_change("adhd")
    result = bus.mark_mcp_change_ready("adhd")
    assert "ready" in result.lower()
    msgs = bus.read_messages(topic_filter="mcp-change")
    assert msgs[1]["payload"]["commit"] == ""


def test_check_mcp_change_status_empty(temp_bus: Path) -> None:
    """Empty bus returns empty list."""
    assert bus.check_mcp_change_status() == []


def test_check_mcp_change_status_in_flux(temp_bus: Path) -> None:
    """A single preparing without ready shows the server as in flux."""
    bus.prepare_mcp_change("asd")
    status = bus.check_mcp_change_status()
    assert len(status) == 1
    assert status[0]["server"] == "asd"


def test_check_mcp_change_status_ready_clears(temp_bus: Path) -> None:
    """A ready message removes the server from the in-flux list."""
    bus.prepare_mcp_change("ocd")
    assert len(bus.check_mcp_change_status()) == 1
    bus.mark_mcp_change_ready("ocd", "def456")
    assert bus.check_mcp_change_status() == []


def test_check_mcp_change_status_multiple_servers(temp_bus: Path) -> None:
    """Multiple servers can be in flux simultaneously."""
    bus.prepare_mcp_change("asd")
    bus.prepare_mcp_change("ocd")
    status = bus.check_mcp_change_status()
    assert len(status) == 2
    servers = {s["server"] for s in status}
    assert servers == {"asd", "ocd"}


def test_check_mcp_change_status_second_prepare_overwrites(temp_bus: Path) -> None:
    """A second preparing for the same server replaces the first in the status."""
    bus.prepare_mcp_change("asd")
    bus.prepare_mcp_change("asd")
    status = bus.check_mcp_change_status()
    assert len(status) == 1
    assert status[0]["server"] == "asd"


def test_check_mcp_change_status_ready_without_preparing(temp_bus: Path) -> None:
    """A ready without a preceding preparing is harmless (no-op on status)."""
    bus.mark_mcp_change_ready("adhd", "abc")
    assert bus.check_mcp_change_status() == []


def test_check_mcp_change_status_ignores_non_mcp_change(temp_bus: Path) -> None:
    """Non-mcp-change event messages are ignored by status check."""
    bus.post(type_="event", topic="other-topic", payload={"server": "asd", "action": "preparing"})
    assert bus.check_mcp_change_status() == []


# ---------------------------------------------------------------------------
# Merge-queue claim protocol
# ---------------------------------------------------------------------------


def test_claim_pr(temp_bus: Path) -> None:
    result = bus.claim_pr(42)
    assert "Claimed PR #42" in result
    msgs = bus.read_messages(topic_filter="merge-queue")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["action"] == "claim"


def test_release_pr(temp_bus: Path) -> None:
    bus.claim_pr(7)
    result = bus.release_pr(7)
    assert "Released claim" in result
    msgs = bus.read_messages(topic_filter="merge-queue")
    assert len(msgs) == 2
    assert msgs[1]["payload"]["action"] == "release"


def test_get_active_claims_empty(temp_bus: Path) -> None:
    assert bus.get_active_claims() == []


def test_get_active_claims_active(temp_bus: Path) -> None:
    bus.claim_pr(99)
    claims = bus.get_active_claims()
    assert len(claims) == 1
    assert claims[0]["pr"] == 99


def test_get_active_claims_released(temp_bus: Path) -> None:
    bus.claim_pr(5)
    bus.release_pr(5)
    assert bus.get_active_claims() == []


def test_get_active_claims_stale(temp_bus: Path) -> None:
    old_ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    msg = _sample_message()
    msg["timestamp"] = old_ts
    msg["type"] = "event"
    msg["topic"] = "merge-queue"
    msg["payload"] = {"pr": 3, "action": "claim"}
    bus.write_message(msg)
    assert bus.get_active_claims() == []


# ---------------------------------------------------------------------------
# Noise threshold monitoring
# ---------------------------------------------------------------------------


def test_get_noise_metrics_empty_bus(temp_bus: Path) -> None:
    metrics = bus.get_noise_metrics()
    assert metrics["messages_per_minute"] == 0.0
    assert metrics["active_agents"] == 0
    assert metrics["total_messages"] == 0
    assert metrics["warning_active"] is False


def test_get_noise_metrics_default_thresholds(temp_bus: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        metrics = bus.get_noise_metrics()
    assert metrics["threshold_per_minute"] == 50
    assert metrics["threshold_agents"] == 20


def test_get_noise_metrics_custom_thresholds(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_THRESHOLD": "30", "ADHD_NOISE_AGENT_THRESHOLD": "10"}):
        metrics = bus.get_noise_metrics()
    assert metrics["threshold_per_minute"] == 30
    assert metrics["threshold_agents"] == 10


def test_get_noise_metrics_counts_messages_in_window(temp_bus: Path) -> None:
    for _ in range(5):
        bus.write_message(_sample_message())
    metrics = bus.get_noise_metrics(window_minutes=60)
    assert metrics["total_messages"] == 5
    assert metrics["messages_per_minute"] > 0
    assert metrics["active_agents"] >= 1


def test_get_noise_metrics_excludes_messages_outside_window(temp_bus: Path) -> None:
    old_ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    msg = _sample_message()
    msg["timestamp"] = old_ts
    bus.write_message(msg)
    metrics = bus.get_noise_metrics(window_minutes=5)
    assert metrics["total_messages"] == 0


def test_get_noise_metrics_unique_agents(temp_bus: Path) -> None:
    for agent in ["agent-a", "agent-b", "agent-c"]:
        msg = _sample_message()
        msg["agent_id"] = agent
        bus.write_message(msg)
    metrics = bus.get_noise_metrics(window_minutes=60)
    assert metrics["active_agents"] == 3


def test_get_noise_metrics_rate_warning(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_THRESHOLD": "2"}):
        for _ in range(10):
            bus.write_message(_sample_message())
        metrics = bus.get_noise_metrics(window_minutes=1)
    assert metrics["warning_active"] is True


def test_get_noise_metrics_agent_warning(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_AGENT_THRESHOLD": "1"}):
        for agent in ["agent-a", "agent-b"]:
            msg = _sample_message()
            msg["agent_id"] = agent
            bus.write_message(msg)
        metrics = bus.get_noise_metrics(window_minutes=60)
    assert metrics["warning_active"] is True


def test_get_noise_metrics_no_warning_when_below_thresholds(temp_bus: Path) -> None:
    with patch.dict(
        os.environ, {"ADHD_NOISE_THRESHOLD": "100", "ADHD_NOISE_AGENT_THRESHOLD": "100"}
    ):
        bus.write_message(_sample_message())
        metrics = bus.get_noise_metrics(window_minutes=60)
    assert metrics["warning_active"] is False


def test_check_noise_threshold_normal(temp_bus: Path) -> None:
    with patch.dict(
        os.environ, {"ADHD_NOISE_THRESHOLD": "100", "ADHD_NOISE_AGENT_THRESHOLD": "100"}
    ):
        bus.write_message(_sample_message())
        result = bus.check_noise_threshold()
    assert "normal" in result.lower()


def test_check_noise_threshold_exceeded_rate(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_THRESHOLD": "1", "ADHD_NOISE_AGENT_THRESHOLD": "100"}):
        for _ in range(10):
            bus.write_message(_sample_message())
        result = bus.check_noise_threshold()
    assert "WARNING" in result
    assert "message rate" in result


def test_check_noise_threshold_exceeded_agents(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_THRESHOLD": "100", "ADHD_NOISE_AGENT_THRESHOLD": "1"}):
        for agent in ["agent-a", "agent-b", "agent-c"]:
            msg = _sample_message()
            msg["agent_id"] = agent
            bus.write_message(msg)
        result = bus.check_noise_threshold()
    assert "WARNING" in result
    assert "active agents" in result


def test_check_noise_threshold_posts_warning_message(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_THRESHOLD": "1", "ADHD_NOISE_AGENT_THRESHOLD": "100"}):
        for _ in range(10):
            bus.write_message(_sample_message())
        bus.check_noise_threshold()
    warnings = bus.read_messages(topic_filter="bus-noise")
    assert len(warnings) == 1
    assert warnings[0]["payload"]["warning"] == "density_warning"


def test_check_noise_threshold_exceeded_both(temp_bus: Path) -> None:
    with patch.dict(os.environ, {"ADHD_NOISE_THRESHOLD": "1", "ADHD_NOISE_AGENT_THRESHOLD": "1"}):
        for agent in ["agent-a", "agent-b", "agent-a", "agent-b", "agent-a", "agent-b"]:
            msg = _sample_message()
            msg["agent_id"] = agent
            bus.write_message(msg)
        result = bus.check_noise_threshold()
    assert "WARNING" in result
    assert "message rate" in result
    assert "active agents" in result


def test_check_noise_threshold_skips_invalid_timestamps(temp_bus: Path) -> None:
    msg = _sample_message()
    msg["timestamp"] = "not-a-timestamp"
    bus.write_message(msg)
    result = bus.check_noise_threshold()
    assert "normal" in result.lower()


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


# ---------------------------------------------------------------------------
# Stale heartbeat reaper
# ---------------------------------------------------------------------------


def _write_heartbeat(session_id: str, agent_id: str, hours_ago: float = 0) -> None:
    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    bus.write_message(
        {
            "timestamp": ts,
            "session_id": session_id,
            "agent_id": agent_id,
            "branch": "feat/test",
            "type": "heartbeat",
            "topic": "agent-lifecycle",
            "payload": {"supporter": True},
        }
    )


def test_reap_stale_no_sessions(temp_bus: Path) -> None:
    reaped = bus.reap_stale_heartbeats()
    assert reaped == []


def test_reap_stale_signout_clears_session(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0.5)
    bus.write_message(
        {
            "timestamp": bus.now(),
            "session_id": "sess-1",
            "agent_id": "agent-a",
            "branch": "feat/test",
            "type": "signout",
            "topic": "agent-lifecycle",
            "payload": {},
        }
    )
    reaped = bus.reap_stale_heartbeats()
    assert reaped == []


def test_reap_stale_recent_heartbeat_not_reaped(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0)
    reaped = bus.reap_stale_heartbeats()
    assert reaped == []


def test_reap_stale_old_heartbeat_reaped(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0.5)
    reaped = bus.reap_stale_heartbeats()
    assert len(reaped) == 1
    assert reaped[0]["session_id"] == "sess-1"
    assert reaped[0]["agent_id"] == "agent-a"


def test_reap_stale_only_reaps_when_latest_is_old(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0.5)
    _write_heartbeat("sess-1", "agent-a", hours_ago=0)
    reaped = bus.reap_stale_heartbeats()
    assert reaped == []


def test_reap_stale_multiple_sessions(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0.5)
    _write_heartbeat("sess-2", "agent-b", hours_ago=0.3)
    _write_heartbeat("sess-3", "agent-c", hours_ago=0)
    reaped = bus.reap_stale_heartbeats()
    reaped_ids = {r["session_id"] for r in reaped}
    assert reaped_ids == {"sess-1", "sess-2"}


def test_reap_stale_writes_signout_message(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0.5)
    bus.reap_stale_heartbeats()
    msgs = bus.read_messages(type_filter="signout")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["reason"] == "stale-heartbeat-reaped"


def test_reap_stale_does_not_reap_twice(temp_bus: Path) -> None:
    _write_heartbeat("sess-1", "agent-a", hours_ago=0.5)
    first = bus.reap_stale_heartbeats()
    assert len(first) == 1
    second = bus.reap_stale_heartbeats()
    assert second == []


# ---------------------------------------------------------------------------
# Message signing (HMAC)
# ---------------------------------------------------------------------------


def test_sign_message_no_secret(temp_bus: Path) -> None:
    """When ADHD_BUS_SECRET is not set, sign_message returns message unchanged."""
    with patch.dict(os.environ, {}, clear=True):
        msg = _sample_message()
        signed = bus.sign_message(msg)
    assert signed == msg
    assert "hmac" not in signed


def test_sign_message_with_secret(temp_bus: Path) -> None:
    """sign_message adds an 'hmac' field when secret is configured."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        msg = _sample_message()
        signed = bus.sign_message(msg)
    assert "hmac" in signed
    assert isinstance(signed["hmac"], str)
    assert len(signed["hmac"]) == 64  # SHA-256 hex digest


def test_sign_message_deterministic(temp_bus: Path) -> None:
    """Same input with same secret produces the same HMAC."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        msg = _sample_message()
        s1 = bus.sign_message(msg)
        s2 = bus.sign_message(msg)
    assert s1["hmac"] == s2["hmac"]


def test_sign_message_different_keys_produce_different_hmac(temp_bus: Path) -> None:
    """Different secrets produce different HMACs for the same message."""
    msg = _sample_message()
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "key-one"}, clear=True):
        s1 = bus.sign_message(msg)
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "key-two"}, clear=True):
        s2 = bus.sign_message(msg)
    assert s1["hmac"] != s2["hmac"]


def test_sign_message_different_payloads_produce_different_hmac(temp_bus: Path) -> None:
    """Different messages produce different HMACs with the same secret."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        m1 = _sample_message()
        m2 = _sample_message()
        m2["type"] = "heartbeat"
        s1 = bus.sign_message(m1)
        s2 = bus.sign_message(m2)
    assert s1["hmac"] != s2["hmac"]


def test_sign_message_removes_existing_hmac(temp_bus: Path) -> None:
    """If message already has an 'hmac' field, it is replaced."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        msg = _sample_message()
        msg["hmac"] = "old-fake-hmac"
        signed = bus.sign_message(msg)
    assert signed["hmac"] != "old-fake-hmac"


def test_verify_signature_no_secret(temp_bus: Path) -> None:
    """When no secret is configured, verify_signature always returns True."""
    with patch.dict(os.environ, {}, clear=True):
        assert bus.verify_signature(_sample_message()) is True


def test_verify_signature_valid(temp_bus: Path) -> None:
    """A signed message should verify successfully."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        msg = bus.sign_message(_sample_message())
        assert bus.verify_signature(msg) is True


def test_verify_signature_tampered(temp_bus: Path) -> None:
    """A tampered message should fail verification."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        msg = bus.sign_message(_sample_message())
        msg["type"] = "signout"  # tamper with the message
        assert bus.verify_signature(msg) is False


def test_verify_signature_missing_hmac(temp_bus: Path) -> None:
    """A message without an 'hmac' field should fail when signing is enabled."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        assert bus.verify_signature(_sample_message()) is False


def test_write_message_signs(temp_bus: Path) -> None:
    """write_message adds HMAC when secret is configured."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        bus.write_message(_sample_message())
    lines = temp_bus.read_text().splitlines()
    msg = json.loads(lines[0])
    assert "hmac" in msg


def test_write_message_roundtrip(temp_bus: Path) -> None:
    """Message written with secret can be read back and verified."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        bus.write_message(_sample_message())
    lines = temp_bus.read_text().splitlines()
    msg = json.loads(lines[0])
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        assert bus.verify_signature(msg) is True


# ---------------------------------------------------------------------------
# Lamport logical clocks
# ---------------------------------------------------------------------------


def test_lamport_starts_at_zero(temp_bus: Path) -> None:
    """get_lamport_time returns 0 before any messages are written."""
    assert bus.get_lamport_time() == 0


def test_lamport_ticks_on_write(temp_bus: Path) -> None:
    """Each write_message increments the Lamport clock."""
    assert bus.get_lamport_time() == 0
    bus.write_message(_sample_message())
    assert bus.get_lamport_time() == 1
    bus.write_message(_sample_message())
    assert bus.get_lamport_time() == 2
    bus.write_message(_sample_message())
    assert bus.get_lamport_time() == 3


def test_write_message_stamps_lamport(temp_bus: Path) -> None:
    """Messages written to the bus carry a monotonically increasing lamport_clock."""
    bus.write_message(_sample_message())
    bus.write_message(_sample_message())
    bus.write_message(_sample_message())

    messages = [json.loads(line) for line in temp_bus.read_text().splitlines() if line.strip()]
    assert len(messages) == 3
    assert messages[0]["lamport_clock"] == 1
    assert messages[1]["lamport_clock"] == 2
    assert messages[2]["lamport_clock"] == 3


def test_read_messages_updates_lamport(temp_bus: Path) -> None:
    """Reading messages updates the local Lamport clock per Lamport receive rule."""
    # Pre-populate the bus with messages at specific clocks
    for i in range(1, 6):
        msg = _sample_message()
        msg["lamport_clock"] = i * 10
        temp_bus.write_text(
            temp_bus.read_text() + json.dumps(msg, separators=(",", ":")) + "\n",
        )

    assert bus.get_lamport_time() == 0
    bus.read_messages(limit=50)
    assert bus.get_lamport_time() == 51  # max(0, 50) + 1


def test_read_messages_empty_bus_does_not_tick(temp_bus: Path) -> None:
    """Reading an empty bus does not change the Lamport clock."""
    assert bus.get_lamport_time() == 0
    bus.read_messages(limit=50)
    assert bus.get_lamport_time() == 0


def test_read_messages_only_applied_to_returned(temp_bus: Path) -> None:
    """Lamport clock updates only from the messages actually returned (after limit)."""
    for i in range(1, 6):
        msg = _sample_message()
        msg["lamport_clock"] = i
        temp_bus.write_text(
            temp_bus.read_text() + json.dumps(msg, separators=(",", ":")) + "\n",
        )

    # Read only last 2 messages (clocks 4 and 5)
    result = bus.read_messages(limit=2)
    assert len(result) == 2
    # max(0, 4, 5) + 1 = 6
    assert bus.get_lamport_time() == 6


def test_update_lamport_ignores_zero_clock(temp_bus: Path) -> None:
    """Messages with lamport_clock=0 do not advance the local clock."""
    bus._update_lamport_from_messages(
        [{"lamport_clock": 0}, {"lamport_clock": 0, "type": "heartbeat"}],
    )
    assert bus.get_lamport_time() == 0


def test_update_lamport_ignores_missing_clock(temp_bus: Path) -> None:
    """Messages without a lamport_clock field do not advance the clock."""
    bus._update_lamport_from_messages(
        [_sample_message(), {"timestamp": "now", "type": "event"}],
    )
    assert bus.get_lamport_time() == 0


def test_happens_before_lower_clock(temp_bus: Path) -> None:
    """A message with a lower clock potentially happened before one with a higher clock."""
    msg_a = {"lamport_clock": 5, "agent_id": "agent-x", "type": "status"}
    msg_b = {"lamport_clock": 10, "agent_id": "agent-y", "type": "event"}
    assert bus.happens_before(msg_a, msg_b) is True


def test_happens_before_higher_clock(temp_bus: Path) -> None:
    """A message with a higher clock did NOT happen before one with a lower clock."""
    msg_a = {"lamport_clock": 10, "agent_id": "agent-x"}
    msg_b = {"lamport_clock": 5, "agent_id": "agent-y"}
    assert bus.happens_before(msg_a, msg_b) is False


def test_happens_before_equal_clock_different_agents(temp_bus: Path) -> None:
    """Equal clocks from different agents mean concurrent (neither happened before)."""
    msg_a = {"lamport_clock": 7, "agent_id": "agent-x"}
    msg_b = {"lamport_clock": 7, "agent_id": "agent-y"}
    assert bus.happens_before(msg_a, msg_b) is False
    assert bus.happens_before(msg_b, msg_a) is False


def test_happens_before_equal_clock_same_agent(temp_bus: Path) -> None:
    """Equal clocks from the same agent should not happen-before either."""
    msg_a = {"lamport_clock": 7, "agent_id": "agent-same"}
    msg_b = {"lamport_clock": 7, "agent_id": "agent-same"}
    assert bus.happens_before(msg_a, msg_b) is False


def test_happens_before_same_agent_lower_clock(temp_bus: Path) -> None:
    """Same agent with lower clock definitively happened before."""
    msg_a = {"lamport_clock": 3, "agent_id": "agent-x"}
    msg_b = {"lamport_clock": 8, "agent_id": "agent-x"}
    assert bus.happens_before(msg_a, msg_b) is True


def test_happens_before_both_zero_clocks(temp_bus: Path) -> None:
    """When both clocks are 0 (pre-Lamport messages), neither happened before."""
    msg_a = {"agent_id": "agent-x"}
    msg_b = {"agent_id": "agent-y"}
    assert bus.happens_before(msg_a, msg_b) is False


def test_happens_before_one_zero_clock(temp_bus: Path) -> None:
    """A message with clock=0 might have happened before a clocked message."""
    msg_a = {"agent_id": "agent-old"}
    msg_b = {"lamport_clock": 5, "agent_id": "agent-new"}
    assert bus.happens_before(msg_a, msg_b) is True


def test_read_messages_since_updates_lamport(temp_bus: Path) -> None:
    """read_messages_since also updates the Lamport clock."""
    for i in range(1, 4):
        msg = _sample_message()
        msg["lamport_clock"] = i * 5
        temp_bus.write_text(
            temp_bus.read_text() + json.dumps(msg, separators=(",", ":")) + "\n",
        )

    result, pos = bus.read_messages_since(0)
    assert len(result) == 3
    assert bus.get_lamport_time() == 16  # max(0, 5, 10, 15) + 1


def test_lamport_persists_across_read_and_write(temp_bus: Path) -> None:
    """Clock advances correctly across a full read-then-write cycle."""
    # Simulate receiving messages from other agents
    for i in range(1, 4):
        msg = _sample_message()
        msg["lamport_clock"] = i * 2
        temp_bus.write_text(
            temp_bus.read_text() + json.dumps(msg, separators=(",", ":")) + "\n",
        )

    bus.read_messages(limit=50)
    clock_after_read = bus.get_lamport_time()
    assert clock_after_read == 7  # max(0, 2,4,6) + 1

    bus.write_message(_sample_message())
    assert bus.get_lamport_time() == 8  # ticked on send


# Bus snapshots
# ---------------------------------------------------------------------------


def test_create_snapshot_empty_bus(temp_bus: Path) -> None:
    """Snapshot on an empty bus returns zero counts and structure."""
    snap = bus.create_snapshot()
    assert snap["message_count"] == 0
    assert snap["timestamp_range"]["first"] is None
    assert snap["active_agents"] == []
    assert snap["registered_agents"] == []
    assert "bus_path" in snap


def test_create_snapshot_with_messages(temp_bus: Path) -> None:
    """Snapshot reflects messages on the bus."""
    bus.write_message(_sample_message())
    bus.write_message(_sample_message())
    snap = bus.create_snapshot()
    assert snap["message_count"] == 2
    assert snap["timestamp_range"]["first"] is not None
    assert snap["file_size_bytes"] > 0
    assert len(snap["registered_agents"]) >= 1


def test_create_snapshot_includes_subscriptions(temp_bus: Path) -> None:
    """Snapshot captures current subscription state."""
    bus.subscribe({"type": "heartbeat"})
    snap = bus.create_snapshot()
    assert "subscriptions" in snap


# ---------------------------------------------------------------------------
# Bus discovery
# ---------------------------------------------------------------------------


def test_discover_buses_empty(tmp_path: Path) -> None:
    """discover_buses returns empty list when no buses exist."""
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(tmp_path / "nonexistent")}):
        assert bus.discover_buses() == []


def test_discover_buses_finds_channels(tmp_path: Path) -> None:
    """discover_buses finds bus files in subdirectories."""
    store = tmp_path / "buses"
    store.mkdir()
    chan = store / "test-channel"
    chan.mkdir()
    (chan / "bus.jsonl").write_text(
        '{"timestamp":"2026-05-01T00:00:00Z","session_id":"s1","agent_id":"a1",'
        '"branch":"main","type":"signin","topic":"agent-lifecycle","payload":{}}\n'
    )
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(store)}):
        results = bus.discover_buses()
    assert len(results) == 1
    assert results[0]["slug"] == "test-channel"
    assert results[0]["message_count"] == 1
    assert results[0]["agent_count"] == 1


def test_discover_buses_skips_directories_without_bus(tmp_path: Path) -> None:
    """Directories without bus.jsonl are skipped."""
    store = tmp_path / "buses"
    store.mkdir()
    (store / "empty-chan").mkdir()
    chan = store / "good-chan"
    chan.mkdir()
    (chan / "bus.jsonl").write_text(
        '{"timestamp":"2026-05-01T00:00:00Z","session_id":"s1","agent_id":"a1",'
        '"branch":"main","type":"signin","topic":"agent-lifecycle","payload":{}}\n'
    )
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(store)}):
        results = bus.discover_buses()
    assert len(results) == 1
    assert results[0]["slug"] == "good-chan"


def test_discover_buses_sorted(tmp_path: Path) -> None:
    """Results are alphabetically sorted by slug."""
    store = tmp_path / "buses"
    store.mkdir()
    for name in ["z-chan", "a-chan"]:
        chan = store / name
        chan.mkdir()
        (chan / "bus.jsonl").write_text(
            '{"timestamp":"2026-05-01T00:00:00Z","session_id":"s1","agent_id":"a1",'
            '"branch":"main","type":"signin","topic":"agent-lifecycle","payload":{}}\n'
        )
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(store)}):
        results = bus.discover_buses()
    assert results[0]["slug"] == "a-chan"
    assert results[1]["slug"] == "z-chan"


# ---------------------------------------------------------------------------
# Cross-bus bridging
# ---------------------------------------------------------------------------


def test_register_bridge_writes_message(temp_bus: Path) -> None:
    bus.register_bridge("target-bus", type_filter="status")
    msgs = bus.read_messages(topic_filter="bridge-rules")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "bridge_rule"
    assert msgs[0]["payload"]["target_slug"] == "target-bus"
    assert msgs[0]["payload"]["action"] == "register"
    assert msgs[0]["payload"]["filters"] == {"type": "status"}


def test_register_bridge_no_filters(temp_bus: Path) -> None:
    bus.register_bridge("target-bus")
    msgs = bus.read_messages(topic_filter="bridge-rules")
    assert msgs[0]["payload"]["filters"] == {}


def test_unregister_bridge_writes_message(temp_bus: Path) -> None:
    bus.register_bridge("target-bus")
    bus.unregister_bridge("target-bus")
    msgs = bus.read_messages(topic_filter="bridge-rules")
    assert msgs[-1]["payload"]["action"] == "unregister"


def test_get_bridge_rules_empty(temp_bus: Path) -> None:
    assert bus.get_bridge_rules() == []


def test_get_bridge_rules_active(temp_bus: Path) -> None:
    bus.register_bridge("target-a")
    bus.register_bridge("target-b", type_filter="event")
    rules = bus.get_bridge_rules()
    assert len(rules) == 2
    slugs = {r["target_slug"] for r in rules}
    assert slugs == {"target-a", "target-b"}


def test_get_bridge_rules_unregistered_removed(temp_bus: Path) -> None:
    bus.register_bridge("target-a")
    bus.register_bridge("target-b")
    bus.unregister_bridge("target-a")
    rules = bus.get_bridge_rules()
    assert len(rules) == 1
    assert rules[0]["target_slug"] == "target-b"


def test_get_bridge_targets_no_match(temp_bus: Path) -> None:
    msg = _sample_message()
    assert bus.get_bridge_targets(msg) == []


def test_get_bridge_targets_match_type(temp_bus: Path) -> None:
    bus.register_bridge("target-bus", type_filter="status")
    msg = _sample_message()
    msg["type"] = "status"
    targets = bus.get_bridge_targets(msg)
    assert targets == ["target-bus"]


def test_get_bridge_targets_match_topic(temp_bus: Path) -> None:
    bus.register_bridge("target-bus", topic_filter="agent-activity")
    msg = _sample_message()
    msg["topic"] = "agent-activity"
    targets = bus.get_bridge_targets(msg)
    assert targets == ["target-bus"]


def test_get_bridge_targets_match_both_filters(temp_bus: Path) -> None:
    bus.register_bridge("target-bus", type_filter="status", topic_filter="agent-activity")
    msg = _sample_message()
    msg["type"] = "status"
    msg["topic"] = "wrong-topic"
    assert bus.get_bridge_targets(msg) == []
    msg["topic"] = "agent-activity"
    targets = bus.get_bridge_targets(msg)
    assert targets == ["target-bus"]


def test_get_bridge_targets_no_filters_forward_all(temp_bus: Path) -> None:
    bus.register_bridge("target-bus")
    msg = _sample_message()
    msg["type"] = "status"
    targets = bus.get_bridge_targets(msg)
    assert targets == ["target-bus"]


def test_get_bridge_targets_no_filters_skips_bridge_rules(temp_bus: Path) -> None:
    bus.register_bridge("target-bus")
    msg = _sample_message()
    msg["type"] = "bridge_rule"
    targets = bus.get_bridge_targets(msg)
    assert targets == []


def test_get_bridge_targets_loop_prevention(temp_bus: Path) -> None:
    bus.register_bridge("target-bus", type_filter="status")
    msg = _sample_message()
    msg["type"] = "status"
    msg["bridged_from"] = "target-bus"
    targets = bus.get_bridge_targets(msg)
    assert targets == []


def test_resolve_bus_path(temp_bus: Path) -> None:
    path = bus.resolve_bus_path("my-channel")
    assert path.name == "bus.jsonl"
    assert path.parent.name == "my-channel"


def test_forward_message_writes_to_target(temp_bus: Path) -> None:
    target_slug = "forward-target"
    target_path = bus.resolve_bus_path(target_slug)
    try:
        msg = _sample_message()
        msg["payload"] = {"key": "value"}
        bus.forward_message(msg, target_slug)
        assert target_path.exists()
        content = json.loads(target_path.read_text().strip())
        assert content["payload"] == {"key": "value"}
        assert content["bridged_from"] == bus._bus_slug()
    finally:
        target_path.unlink(missing_ok=True)


def test_forward_message_includes_bridged_from(temp_bus: Path) -> None:
    target_slug = "loop-target"
    target_path = bus.resolve_bus_path(target_slug)
    try:
        msg = _sample_message()
        bus.forward_message(msg, target_slug)
        content = json.loads(target_path.read_text().strip())
        assert "bridged_from" in content
        assert content["bridged_from"] == bus._bus_slug()
    finally:
        target_path.unlink(missing_ok=True)
