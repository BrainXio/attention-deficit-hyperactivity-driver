"""Pydantic models for the ADHD message bus."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BusMessage(BaseModel):
    """A single message on the ADHD coordination bus."""

    timestamp: str
    session_id: str
    agent_id: str
    branch: str
    type: Literal[
        "signin",
        "signout",
        "heartbeat",
        "status",
        "schema",
        "dependency",
        "question",
        "answer",
        "event",
        "tool_use",
        "main_session_set",
        "main_session_released",
        "request",
        "response",
        "hitl_claim",
        "hitl_release",
        "hitl_rpe",
        "hitl_approve",
        "hitl_split",
    ]
    topic: str
    payload: dict[str, object] = Field(default_factory=dict)
    lamport_clock: int = Field(default=0, description="Lamport logical clock value")
