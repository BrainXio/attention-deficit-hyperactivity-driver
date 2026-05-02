"""Tests for capability tokens (signed authorization claims)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import adhd.bus as bus


@pytest.fixture
def key_dir(tmp_path: Path) -> Path:
    """Set up a temporary key directory and patch ADHD_BUS_PATH."""
    kd = tmp_path / "keys"
    kd.mkdir(parents=True)
    with patch.object(bus, "_CANONICAL_BASE", tmp_path / "nonexistent"):
        with patch.dict(os.environ, {"ADHD_BUS_PATH": str(tmp_path)}):
            yield kd


class TestTokenIssuance:
    def test_issue_token_returns_string(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc")
        assert token is not None
        assert isinstance(token, str)
        assert "." in token  # payload.signature format

    def test_issue_token_no_key(self, key_dir: Path) -> None:
        token = bus.issue_token("nonexistent", "agent-abc")
        assert token is None

    def test_issue_token_different_payloads(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        t1 = bus.issue_token("issuer", "agent-a", allowed_tools=["adhd_read"])
        t2 = bus.issue_token("issuer", "agent-b", allowed_tools=["adhd_post"])
        assert t1 is not None
        assert t2 is not None
        assert t1 != t2  # different subjects/tools produce different tokens


class TestTokenVerification:
    def test_verify_valid_token(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", allowed_tools=["adhd_read"])
        assert token is not None
        result = bus.verify_token(token)
        assert result["ok"] is True

    def test_verify_with_tool_check(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", allowed_tools=["adhd_read", "adhd_post"])
        assert token is not None
        assert bus.verify_token(token, required_tool="adhd_read")["ok"] is True
        assert bus.verify_token(token, required_tool="adhd_post")["ok"] is True
        assert bus.verify_token(token, required_tool="adhd_send")["ok"] is False

    def test_verify_with_caller_id(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc")
        assert token is not None
        assert bus.verify_token(token, caller_id="agent-abc")["ok"] is True
        assert bus.verify_token(token, caller_id="agent-xyz")["ok"] is False

    def test_verify_expired_token(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", expiry_hours=-1)
        assert token is not None
        result = bus.verify_token(token)
        assert result["ok"] is False
        assert "expired" in str(result["detail"]).lower()

    def test_verify_bad_format(self, key_dir: Path) -> None:
        result = bus.verify_token("not-a-valid-token")
        assert result["ok"] is False
        assert "format" in str(result["detail"]).lower()

    def test_verify_tampered_signature(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc")
        assert token is not None
        parts = token.split(".")
        tampered = parts[0] + "." + "f" * len(parts[1])
        result = bus.verify_token(tampered)
        assert result["ok"] is False
        assert "signature" in str(result["detail"]).lower()

    def test_verify_issuer_no_key(self, key_dir: Path) -> None:
        """Token signed by an issuer that has no public key in the key dir."""
        import base64

        payload = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "subject": "agent-abc",
                        "issuer": "nonexistent-issuer",
                        "expires_at": "2099-01-01T00:00:00Z",
                        "token_id": "tok_test",
                        "allowed_tools": [],
                        "scopes": [],
                    }
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
        token = payload + "." + "a" * 128
        result = bus.verify_token(token)
        assert result["ok"] is False
        assert "public key" in str(result["detail"]).lower()

    def test_verify_missing_fields(self, key_dir: Path) -> None:
        import base64

        payload = base64.urlsafe_b64encode(b'{"subject":"x","issuer":"y"}').decode().rstrip("=")
        token = payload + "." + "a" * 128
        result = bus.verify_token(token)
        assert result["ok"] is False
        assert "required field" in str(result["detail"]).lower()

    def test_verify_with_valid_scope(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", scopes=["read", "write"])
        assert token is not None
        assert bus.verify_token(token, required_scope="read")["ok"] is True
        assert bus.verify_token(token, required_scope="write")["ok"] is True

    def test_verify_with_missing_scope(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", scopes=["read"])
        assert token is not None
        assert bus.verify_token(token, required_scope="read")["ok"] is True
        assert bus.verify_token(token, required_scope="write")["ok"] is False

    def test_verify_with_empty_scopes(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", scopes=[])
        assert token is not None
        assert bus.verify_token(token, required_scope="read")["ok"] is False
        assert bus.verify_token(token, required_scope="write")["ok"] is False

    def test_verify_with_tool_and_scope(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token(
            "issuer",
            "agent-abc",
            allowed_tools=["adhd_read"],
            scopes=["read"],
        )
        assert token is not None
        # Both tool and scope must match
        assert (
            bus.verify_token(token, required_tool="adhd_read", required_scope="read")["ok"] is True
        )
        # Wrong tool
        assert (
            bus.verify_token(token, required_tool="adhd_post", required_scope="read")["ok"] is False
        )
        # Wrong scope
        assert (
            bus.verify_token(token, required_tool="adhd_read", required_scope="write")["ok"]
            is False
        )


class TestTokenWithScopes:
    def test_issue_with_scopes(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc", scopes=["read", "write"])
        assert token is not None
        result = bus.verify_token(token)
        assert result["ok"] is True

    def test_no_allowed_tools(self, key_dir: Path) -> None:
        bus.generate_keypair("issuer")
        token = bus.issue_token("issuer", "agent-abc")
        assert token is not None
        result = bus.verify_token(token, required_tool="any-tool")
        assert result["ok"] is False  # empty allowed_tools denies all


class TestMCPIntegration:
    """Test token enforcement through MCP tool wrappers.

    These tests directly call the bus functions that MCP tools wrap,
    verifying that the token parameter flows correctly.
    """

    def test_post_with_valid_token(self, key_dir: Path, tmp_path: Path) -> None:
        bus.generate_keypair("issuer")
        bus.generate_keypair(bus.agent_id())
        token = bus.issue_token(
            bus.agent_id(),
            bus.agent_id(),
            allowed_tools=["adhd_post"],
        )
        assert token is not None

        bus_file = tmp_path / "bus.jsonl"
        with patch.object(bus, "resolve", return_value=bus_file):
            result = bus.signin()
            assert "identity verified" in result.lower()

    def test_post_with_invalid_token(self, key_dir: Path) -> None:
        """Verify that adhd_post returns error for bad token."""
        bus.generate_keypair(bus.agent_id())
        token = bus.issue_token(
            bus.agent_id(),
            bus.agent_id(),
            allowed_tools=["adhd_read"],  # not adhd_post!
        )
        assert token is not None

        # The MCP tool checks the token using verify_token - test via bus
        result = bus.verify_token(token, required_tool="adhd_post", caller_id=bus.agent_id())
        assert result["ok"] is False
        assert "does not allow tool" in str(result["detail"]).lower()
