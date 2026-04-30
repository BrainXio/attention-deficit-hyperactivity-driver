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
