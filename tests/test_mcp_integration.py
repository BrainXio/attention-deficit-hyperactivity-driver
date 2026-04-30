"""Integration tests for the MCP server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import adhd.bus as bus
import adhd.mcp_server as mcp_server_mod
from adhd.mcp_server import (
    adhd_archive,
    adhd_main_check,
    adhd_main_claim,
    adhd_main_elect,
    adhd_main_release,
    adhd_post,
    adhd_read,
    adhd_resolve,
    adhd_send,
    adhd_signin,
    adhd_signout,
    adhd_start_heartbeat,
    adhd_validate,
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
def allow_main() -> None:
    """Set ADHD_ENABLE_COORDINATOR for tests that need it."""
    with patch.dict(os.environ, {"ADHD_ENABLE_COORDINATOR": "1"}):
        yield


# ---------------------------------------------------------------------------
# Lifecycle tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_signin(temp_bus: Path) -> None:
    result = await adhd_signin(role="sub")
    assert "Signed in" in result
    msgs = bus.read_messages(type_filter="signin")
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_adhd_signin_main_blocked_without_env(temp_bus: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = await adhd_signin(role="main")
    assert "ERROR" in result
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_adhd_signout(temp_bus: Path) -> None:
    await adhd_signin(role="sub")
    result = await adhd_signout()
    assert "Signed out" in result


# ---------------------------------------------------------------------------
# Read / write tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_read(temp_bus: Path) -> None:
    await adhd_signin(role="sub")
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
# Main session tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adhd_main_check_no_main(temp_bus: Path) -> None:
    result = await adhd_main_check()
    assert "No main session" in result


@pytest.mark.asyncio
async def test_adhd_main_claim_blocked_without_env(temp_bus: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = await adhd_main_claim()
    assert "ERROR" in result
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_adhd_main_claim_with_env(temp_bus: Path, allow_main: Any) -> None:
    result = await adhd_main_claim()
    assert "claimed" in result.lower()
    msgs = bus.read_messages(type_filter="main_session_set")
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_adhd_main_release_no_main(temp_bus: Path) -> None:
    result = await adhd_main_release()
    assert "ERROR" in result
    assert "no main session" in result.lower()


@pytest.mark.asyncio
async def test_adhd_main_elect_no_sessions(temp_bus: Path, allow_main: Any) -> None:
    result = await adhd_main_elect()
    assert "ERROR" in result
    assert "No active sessions" in result


@pytest.mark.asyncio
async def test_adhd_main_elect_success(temp_bus: Path, allow_main: Any) -> None:
    await adhd_signin(role="sub")
    result = await adhd_main_elect()
    assert "claimed" in result.lower()


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
