"""Unit tests for adhd.bus HITL protocol."""

from __future__ import annotations

import json
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
# Decision claim / release
# ---------------------------------------------------------------------------


def test_hitl_claim_decision(temp_bus: Path) -> None:
    result = bus.hitl_claim_decision("pr-7-merge", "Approve the refactor PR")
    assert "Claimed decision" in result
    msgs = bus.read_messages(topic_filter="hitl-decisions")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "hitl_claim"
    assert msgs[0]["payload"]["decision_id"] == "pr-7-merge"
    assert msgs[0]["payload"]["urgency"] == "medium"


def test_hitl_release_decision(temp_bus: Path) -> None:
    bus.hitl_claim_decision("pr-7-merge", "Approve the refactor PR")
    result = bus.hitl_release_decision("pr-7-merge")
    assert "Released claim" in result
    msgs = bus.read_messages(topic_filter="hitl-decisions")
    assert msgs[1]["type"] == "hitl_release"


# ---------------------------------------------------------------------------
# RPE and approval
# ---------------------------------------------------------------------------


def test_hitl_provide_rpe(temp_bus: Path) -> None:
    result = bus.hitl_provide_rpe("pr-7-merge", 0.75, "Better than expected")
    assert "Recorded RPE 0.75" in result
    msgs = bus.read_messages(topic_filter="hitl-decisions")
    assert msgs[0]["payload"]["rpe"] == 0.75


def test_hitl_approve_gonogo(temp_bus: Path) -> None:
    result = bus.hitl_approve_gonogo("deploy-x", True, "Looks safe")
    assert "approved" in result
    msgs = bus.read_messages(topic_filter="hitl-decisions")
    assert msgs[0]["payload"]["approved"] is True


def test_hitl_reject_gonogo(temp_bus: Path) -> None:
    result = bus.hitl_approve_gonogo("deploy-x", False, "Too risky")
    assert "rejected" in result
    msgs = bus.read_messages(topic_filter="hitl-decisions")
    assert msgs[0]["payload"]["approved"] is False


# ---------------------------------------------------------------------------
# Duty split
# ---------------------------------------------------------------------------


def test_hitl_split_duties(temp_bus: Path) -> None:
    result = bus.hitl_split_duties(["bus-monitor", "pr-scan"], ["agent-a", "agent-b"])
    assert "Split duties" in result
    msgs = bus.read_messages(topic_filter="hitl-decisions")
    assert msgs[0]["payload"]["duties"] == ["bus-monitor", "pr-scan"]


# ---------------------------------------------------------------------------
# Pending decisions query
# ---------------------------------------------------------------------------


def test_get_pending_decisions_empty(temp_bus: Path) -> None:
    assert bus.get_pending_decisions() == []


def test_get_pending_decisions_active(temp_bus: Path) -> None:
    bus.hitl_claim_decision("pr-1", "First decision")
    bus.hitl_claim_decision("pr-2", "Second decision")
    pending = bus.get_pending_decisions()
    assert len(pending) == 2
    ids = {d["decision_id"] for d in pending}
    assert ids == {"pr-1", "pr-2"}


def test_get_pending_decisions_released_removed(temp_bus: Path) -> None:
    bus.hitl_claim_decision("pr-1", "First decision")
    bus.hitl_release_decision("pr-1")
    assert bus.get_pending_decisions() == []


def test_get_pending_decisions_approved_removed(temp_bus: Path) -> None:
    bus.hitl_claim_decision("pr-1", "First decision")
    bus.hitl_approve_gonogo("pr-1", True)
    assert bus.get_pending_decisions() == []


def test_get_pending_decisions_stale(temp_bus: Path) -> None:
    old_ts = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    msg = _sample_message()
    msg["timestamp"] = old_ts
    msg["type"] = "hitl_claim"
    msg["topic"] = "hitl-decisions"
    msg["payload"] = {"decision_id": "old-1", "description": "stale", "action": "claim"}
    bus.write_message(msg)
    assert bus.get_pending_decisions() == []


# ---------------------------------------------------------------------------
# Decision history query
# ---------------------------------------------------------------------------


def test_get_decision_history(temp_bus: Path) -> None:
    bus.hitl_claim_decision("pr-1", "First decision")
    bus.hitl_provide_rpe("pr-1", 0.5)
    history = bus.get_decision_history("pr-1")
    assert len(history) == 2
    types = [h["type"] for h in history]
    assert types == ["hitl_claim", "hitl_rpe"]


def test_get_decision_history_empty(temp_bus: Path) -> None:
    assert bus.get_decision_history("nonexistent") == []


# ---------------------------------------------------------------------------
# Validation covers new types
# ---------------------------------------------------------------------------


def test_validate_hitl_types() -> None:
    for msg_type in ("hitl_claim", "hitl_release", "hitl_rpe", "hitl_approve", "hitl_split"):
        line = json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "session_id": "s1",
                "agent_id": "a1",
                "branch": "main",
                "type": msg_type,
                "topic": "hitl-decisions",
                "payload": {},
            }
        )
        ok, err = bus.validate(line)
        assert ok is True, f"{msg_type} should be valid: {err}"
