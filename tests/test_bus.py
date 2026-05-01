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
