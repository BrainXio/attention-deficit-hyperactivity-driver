"""Integration tests for the MCP server."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import adhd.bus as bus
import adhd.mcp_server as mcp_server_mod
from adhd.mcp_server import (
    adhd_archive,
    adhd_bridge_list,
    adhd_bridge_register,
    adhd_bridge_unregister,
    adhd_discover,
    adhd_get_rules,
    adhd_main_check,
    adhd_mcp_change_check,
    adhd_mcp_change_prepare,
    adhd_mcp_change_ready,
    adhd_migrate_to_push,
    adhd_noise_check,
    adhd_poll,
    adhd_post,
    adhd_read,
    adhd_resolve,
    adhd_send,
    adhd_signin,
    adhd_signout,
    adhd_snapshot,
    adhd_start_heartbeat,
    adhd_subscribe,
    adhd_unsubscribe,
    adhd_validate,
    adhd_verify_signature,
    adhd_wait,
)


@pytest.fixture(autouse=True)
def temp_bus(tmp_path: Path) -> Path:
    """Patch resolve() to use a temporary bus file."""
    bus_file = tmp_path / "bus.jsonl"
    with (
        patch.object(bus, "resolve", return_value=bus_file),
        patch.object(mcp_server_mod, "resolve", return_value=bus_file),
    ):
        yield bus_file


@pytest.fixture
def key_dir(tmp_path: Path) -> Path:
    """Set up a temporary key directory and patch ADHD_BUS_PATH."""
    kd = tmp_path / "keys"
    kd.mkdir(parents=True)
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(tmp_path)}):
        yield kd


@pytest.fixture
def allow_supporter() -> None:
    """Set ADHD_ENABLE_SUPPORTER for tests that need it."""
    with patch.dict(os.environ, {"ADHD_ENABLE_SUPPORTER": "1"}):
        yield


# ---------------------------------------------------------------------------
# Lifecycle tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_signin(temp_bus: Path) -> None:
    result = await adhd_signin()
    assert "Signed in" in result
    msgs = bus.read_messages(type_filter="signin")
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_adhd_signin_supporter(temp_bus: Path, allow_supporter: Any) -> None:
    result = await adhd_signin()
    assert "supporter" in result.lower()
    msgs = bus.read_messages(type_filter="signin")
    assert msgs[0]["payload"]["supporter"] is True


@pytest.mark.asyncio
async def test_adhd_signout(temp_bus: Path) -> None:
    await adhd_signin()
    result = await adhd_signout()
    assert "Signed out" in result


# ---------------------------------------------------------------------------
# Read / write tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_read(temp_bus: Path) -> None:
    await adhd_signin()
    result = await adhd_read(limit=5)
    assert "signin" in result


@pytest.mark.asyncio
async def test_adhd_post(temp_bus: Path) -> None:
    result = await adhd_post(type="status", topic="agent-activity", payload='{"state":"ok"}')
    assert "Posted" in result


@pytest.mark.asyncio
async def test_adhd_post_invalid_payload(temp_bus: Path) -> None:
    result = await adhd_post(type="status", topic="agent-activity", payload="not json")
    assert "ERROR" in result
    assert "Invalid JSON" in result


@pytest.mark.asyncio
async def test_adhd_send(temp_bus: Path) -> None:
    result = await adhd_send(to="all", message="hello", topic="test")
    assert "Sent" in result


# ---------------------------------------------------------------------------
# Supporter tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_main_check_no_supporters(temp_bus: Path) -> None:
    result = await adhd_main_check()
    assert "No active supporter" in result


@pytest.mark.asyncio
async def test_adhd_main_check_with_supporter(temp_bus: Path, allow_supporter: Any) -> None:
    await adhd_signin()
    result = await adhd_main_check()
    assert "supporter" in result.lower()
    assert "agent-" in result


# ---------------------------------------------------------------------------
# Performance level
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_signin_includes_perf_level(temp_bus: Path, allow_supporter: Any) -> None:
    """Supporter signin includes perf_level in payload."""
    with patch.dict(os.environ, {"ADHD_PERF_LEVEL": "low"}):
        result = await adhd_signin()
    assert "supporter" in result.lower()
    msgs = bus.read_messages(type_filter="signin")
    assert msgs[0]["payload"]["perf_level"] == "low"


# ---------------------------------------------------------------------------
# MCP change notification tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_mcp_change_prepare(temp_bus: Path) -> None:
    """adhd_mcp_change_prepare returns success message."""
    result = await adhd_mcp_change_prepare(server="asd")
    assert "preparing" in result.lower()
    assert "asd" in result


@pytest.mark.asyncio
async def test_adhd_mcp_change_ready(temp_bus: Path) -> None:
    """adhd_mcp_change_ready returns success message."""
    await adhd_mcp_change_prepare(server="ocd")
    result = await adhd_mcp_change_ready(server="ocd", commit="abc123")
    assert "ready" in result.lower()
    assert "ocd" in result


@pytest.mark.asyncio
async def test_adhd_mcp_change_check_empty(temp_bus: Path) -> None:
    """adhd_mcp_change_check reports no servers when bus has no preparing."""
    result = await adhd_mcp_change_check()
    assert "No MCP servers" in result


@pytest.mark.asyncio
async def test_adhd_mcp_change_check_in_flux(temp_bus: Path) -> None:
    """adhd_mcp_change_check reports in-flux server after a prepare."""
    await adhd_mcp_change_prepare(server="asd")
    result = await adhd_mcp_change_check()
    assert "asd" in result
    assert "in flux" in result.lower()


@pytest.mark.asyncio
async def test_adhd_mcp_change_check_cleared_after_ready(temp_bus: Path) -> None:
    """adhd_mcp_change_check shows no servers after prepare + ready."""
    await adhd_mcp_change_prepare(server="ocd")
    await adhd_mcp_change_ready(server="ocd")
    result = await adhd_mcp_change_check()
    assert "No MCP servers" in result


@pytest.mark.asyncio
async def test_adhd_mcp_change_full_roundtrip(temp_bus: Path) -> None:
    """End-to-end: prepare, check shows in-flux, ready, check shows clear."""
    assert "No MCP servers" in await adhd_mcp_change_check()

    await adhd_mcp_change_prepare(server="adhd")
    check1 = await adhd_mcp_change_check()
    assert "adhd" in check1

    await adhd_mcp_change_ready(server="adhd", commit="deadbeef")
    check2 = await adhd_mcp_change_check()
    assert "No MCP servers" in check2


@pytest.mark.asyncio
async def test_adhd_post_rejects_protected_topic(temp_bus: Path) -> None:
    """adhd_post rejects messages with topic='mcp-change'."""
    result = await adhd_post(
        type="event",
        topic="mcp-change",
        payload='{"server":"asd","action":"preparing"}',
    )
    assert "ERROR" in result
    assert "protected" in result.lower()


# ---------------------------------------------------------------------------
# Maintenance tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_validate(temp_bus: Path) -> None:
    result = await adhd_validate()
    assert "does not exist" in result or "Bus is valid" in result


@pytest.mark.asyncio
async def test_adhd_archive(temp_bus: Path) -> None:
    result = await adhd_archive()
    assert "does not exist" in result or "No archive" in result


@pytest.mark.asyncio
async def test_adhd_resolve(temp_bus: Path) -> None:
    result = await adhd_resolve()
    assert result.endswith("bus.jsonl")


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_start_heartbeat(temp_bus: Path) -> None:
    result = await adhd_start_heartbeat()
    assert "started" in result.lower()

    # Second call should report already running
    result2 = await adhd_start_heartbeat()
    assert "already running" in result2.lower()


# ---------------------------------------------------------------------------
# Cross-bus bridging tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_register(temp_bus: Path) -> None:
    """Registering a bridge via MCP returns success."""
    result = await adhd_bridge_register("target-bus", type="status")
    assert "Bridge registered" in result
    assert "target-bus" in result


@pytest.mark.asyncio
async def test_bridge_unregister(temp_bus: Path) -> None:
    """Unregistering a bridge via MCP returns success."""
    await adhd_bridge_register("target-bus")
    result = await adhd_bridge_unregister("target-bus")
    assert "removed" in result.lower()


@pytest.mark.asyncio
async def test_bridge_list_empty(temp_bus: Path) -> None:
    """Listing bridges when none are registered."""
    result = await adhd_bridge_list()
    assert "No active bridge rules" in result


@pytest.mark.asyncio
async def test_bridge_list_with_rules(temp_bus: Path) -> None:
    """Listing bridges returns registered rules."""
    await adhd_bridge_register("bus-a")
    await adhd_bridge_register("bus-b", type="event")
    result = await adhd_bridge_list()
    data = json.loads(result)
    assert len(data) == 2


# ---------------------------------------------------------------------------
# Self-describing rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_get_rules() -> None:
    """adhd_get_rules returns valid JSON with expected structure."""
    result = await adhd_get_rules()
    data = json.loads(result)
    assert data["package"] == "adhd"
    assert "protocols" in data
    assert "message_types" in data
    assert "env_vars" in data
    assert "tools" in data
    assert data["protocols"]["heartbeat"]["interval_minutes"] == 10


# ---------------------------------------------------------------------------
# Noise threshold monitoring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_noise_check_empty_bus(temp_bus: Path) -> None:
    result = await adhd_noise_check()
    data = json.loads(result)
    assert "metrics" in data
    assert data["metrics"]["total_messages"] == 0
    assert data["metrics"]["warning_active"] is False


@pytest.mark.asyncio
async def test_adhd_noise_check_with_messages(temp_bus: Path) -> None:
    await adhd_signin()
    result = await adhd_noise_check()
    data = json.loads(result)
    assert data["metrics"]["total_messages"] >= 1
    assert "status" in data


# ---------------------------------------------------------------------------
# Push/event-driven delivery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_subscribe(temp_bus: Path) -> None:
    result = await adhd_subscribe(type="heartbeat", topic="agent-lifecycle")
    assert "Subscribed" in result
    msgs = bus.read_messages(topic_filter="bus-subscriptions")
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_adhd_subscribe_no_filters(temp_bus: Path) -> None:
    result = await adhd_subscribe()
    assert "ERROR" in result


@pytest.mark.asyncio
async def test_adhd_unsubscribe(temp_bus: Path) -> None:
    await adhd_subscribe(type="heartbeat")
    result = await adhd_unsubscribe()
    assert "Unsubscribed" in result


@pytest.mark.asyncio
async def test_adhd_poll_empty(temp_bus: Path) -> None:
    result = await adhd_poll()
    assert result == "[]"


@pytest.mark.asyncio
async def test_adhd_poll_returns_new(temp_bus: Path) -> None:
    await adhd_subscribe(type="request")
    # adhd_send posts messages with type "request"
    await adhd_send(to=bus.agent_id(), message="test")
    result = await adhd_poll()
    assert bus.agent_id() in result


@pytest.mark.asyncio
async def test_adhd_poll_respects_filters(temp_bus: Path) -> None:
    await adhd_subscribe(type="signin")
    # Post a heartbeat message — should be filtered out
    bus.post("heartbeat", "agent-lifecycle", {"note": "ignore"})
    result = await adhd_poll()
    assert result == "[]"


@pytest.mark.asyncio
async def test_adhd_wait_timeout(temp_bus: Path) -> None:
    await adhd_subscribe(type="heartbeat")
    result = await adhd_wait(timeout=0.5)
    assert result == "[]"


@pytest.mark.asyncio
async def test_adhd_migrate_to_push_no_supporters(temp_bus: Path) -> None:
    await adhd_signin()
    # Ack migration for our agent before running the broadcast
    bus.ack_migration()
    result = await adhd_migrate_to_push()
    assert "acknowledged" in result.lower()


# ---------------------------------------------------------------------------
# Message signing verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_verify_signature_no_secret(temp_bus: Path) -> None:
    """When ADHD_BUS_SECRET is not set, verification reports signing disabled."""
    with patch.dict(os.environ, {}, clear=True):
        msg = _sample_message()
        result = json.loads(await adhd_verify_signature(json.dumps(msg)))
    assert result["ok"] is True
    assert "not enabled" in result["detail"]


@pytest.mark.asyncio
async def test_adhd_verify_signature_valid(temp_bus: Path) -> None:
    """A correctly signed message passes verification."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        signed = bus.sign_message(_sample_message())
        result = json.loads(await adhd_verify_signature(json.dumps(signed)))
    assert result["ok"] is True
    assert result["detail"] == "Signature valid"


@pytest.mark.asyncio
async def test_adhd_verify_signature_invalid(temp_bus: Path) -> None:
    """A tampered message fails verification."""
    with patch.dict(os.environ, {"ADHD_BUS_SECRET": "test-key"}, clear=True):
        signed = bus.sign_message(_sample_message())
        signed["type"] = "signout"  # tamper
        result = json.loads(await adhd_verify_signature(json.dumps(signed)))
    assert result["ok"] is False
    assert "invalid" in result["detail"]


@pytest.mark.asyncio
async def test_adhd_verify_signature_bad_json(temp_bus: Path) -> None:
    """Non-JSON input returns an error."""
    result = json.loads(await adhd_verify_signature("not valid json"))
    assert result["ok"] is False
    assert "Invalid JSON" in result["detail"]


def _sample_message() -> dict[str, Any]:
    return {
        "timestamp": bus.now(),
        "session_id": "sess-123",
        "agent_id": "agent-a",
        "branch": "feat/test",
        "type": "signin",
        "topic": "agent-lifecycle",
        "payload": {},
    }


# ---------------------------------------------------------------------------
# Bus snapshot tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_snapshot_empty(temp_bus: Path) -> None:
    """adhd_snapshot returns a structured checkpoint of an empty bus."""
    result = json.loads(await adhd_snapshot())
    assert result["message_count"] == 0
    assert "bus_path" in result
    assert "registered_agents" in result


@pytest.mark.asyncio
async def test_adhd_snapshot_with_data(temp_bus: Path) -> None:
    """adhd_snapshot reflects messages on the bus."""
    bus.write_message(_sample_message())
    result = json.loads(await adhd_snapshot())
    assert result["message_count"] >= 1
    assert result["file_size_bytes"] > 0


# ---------------------------------------------------------------------------
# Bus discovery tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_discover(tmp_path: Path) -> None:
    """adhd_discover finds the current channel."""
    slug = "test-channel"
    channel_dir = tmp_path / slug
    channel_dir.mkdir()
    bus_file = channel_dir / "bus.jsonl"

    # discover_buses scans ADHD_BUS_PATH for subdirectories with bus.jsonl,
    # while write_message uses resolve(). Patch both.
    with (
        patch.object(bus, "resolve", return_value=bus_file),
        patch.object(mcp_server_mod, "resolve", return_value=bus_file),
        patch.dict(os.environ, {"ADHD_BUS_PATH": str(tmp_path)}),
    ):
        bus.write_message(_sample_message())
        result = json.loads(await adhd_discover())

    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["slug"] == slug
    assert "message_count" in result[0]


# ---------------------------------------------------------------------------
# Access control enforcement
# ---------------------------------------------------------------------------


def _make_token() -> str:
    """Generate an issuer+subject keypair and return a write-scoped token."""
    bus.generate_keypair("issuer")
    bus.generate_keypair(bus.agent_id())
    token = bus.issue_token(
        "issuer",
        bus.agent_id(),
        allowed_tools=["adhd_post", "adhd_read", "adhd_poll", "adhd_archive", "adhd_signout"],
        scopes=["read", "write"],
    )
    assert token is not None
    return token


def _make_readonly_token() -> str:
    """Generate a read-only token (no write scope)."""
    bus.generate_keypair("read-issuer")
    bus.generate_keypair(bus.agent_id())
    token = bus.issue_token(
        "read-issuer",
        bus.agent_id(),
        allowed_tools=["adhd_read", "adhd_poll"],
        scopes=["read"],
    )
    assert token is not None
    return token


@pytest.mark.asyncio
async def test_read_without_token_no_enforcement(temp_bus: Path) -> None:
    """Without enforcement, read works without a token."""
    result = await adhd_read()
    data = json.loads(result)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_post_without_token_no_enforcement(temp_bus: Path) -> None:
    """Without enforcement, post works without a token."""
    result = await adhd_post(type="status", topic="test", payload='{"msg":"ok"}')
    assert "ERROR" not in result


@pytest.mark.asyncio
async def test_post_with_valid_token(temp_bus: Path, key_dir: Path) -> None:
    """Post with valid token succeeds."""
    token = _make_token()
    result = await adhd_post(type="status", topic="test", payload='{"msg":"ok"}', token=token)
    assert "ERROR" not in result


@pytest.mark.asyncio
async def test_post_with_readonly_token(temp_bus: Path, key_dir: Path) -> None:
    """Post with read-only token is denied."""
    token = _make_readonly_token()
    result = await adhd_post(type="status", topic="test", payload='{"msg":"ok"}', token=token)
    assert "access_denied" in result


@pytest.mark.asyncio
async def test_read_with_readonly_token(temp_bus: Path, key_dir: Path) -> None:
    """Read with read-only token succeeds."""
    token = _make_readonly_token()
    result = await adhd_read(token=token)
    data = json.loads(result)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_post_requires_token_enforcement(temp_bus: Path, key_dir: Path) -> None:
    """With ADHD_ENFORCE_ACCESS_CONTROL, post rejects missing token."""
    with patch.dict(os.environ, {"ADHD_ENFORCE_ACCESS_CONTROL": "1"}):
        result = await adhd_post(type="status", topic="test", payload='{"msg":"ok"}')
    assert "access_denied" in result


@pytest.mark.asyncio
async def test_read_requires_token_enforcement(temp_bus: Path, key_dir: Path) -> None:
    """With ADHD_ENFORCE_ACCESS_CONTROL, read rejects missing token."""
    with patch.dict(os.environ, {"ADHD_ENFORCE_ACCESS_CONTROL": "1"}):
        result = await adhd_read()
    assert "access_denied" in result


@pytest.mark.asyncio
async def test_post_with_valid_token_enforcement(temp_bus: Path, key_dir: Path) -> None:
    """With enforcement, valid token allows post."""
    token = _make_token()
    with patch.dict(os.environ, {"ADHD_ENFORCE_ACCESS_CONTROL": "1"}):
        result = await adhd_post(type="status", topic="test", payload='{"msg":"ok"}', token=token)
    assert "ERROR" not in result


@pytest.mark.asyncio
async def test_poll_without_token_no_enforcement(temp_bus: Path) -> None:
    """Without enforcement, poll works without a token."""
    result = await adhd_poll()
    assert result == "[]"


@pytest.mark.asyncio
async def test_signout_requires_token_enforcement(temp_bus: Path) -> None:
    """signout with enforcement rejects missing token."""
    with patch.dict(os.environ, {"ADHD_ENFORCE_ACCESS_CONTROL": "1"}):
        result = await adhd_signout()
    assert "access_denied" in result


@pytest.mark.asyncio
async def test_archive_requires_token_enforcement(temp_bus: Path) -> None:
    """archive with enforcement rejects missing token."""
    with patch.dict(os.environ, {"ADHD_ENFORCE_ACCESS_CONTROL": "1"}):
        result = await adhd_archive()
    assert "access_denied" in result
