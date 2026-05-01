"""Tests for agent cryptographic identity (Ed25519 keypairs)."""

from __future__ import annotations

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
    with patch.dict(os.environ, {"ADHD_BUS_PATH": str(tmp_path)}):
        yield kd


@pytest.fixture
def temp_bus(tmp_path: Path) -> Path:
    """Provide a temporary bus file and patch resolve() to use it."""
    bus_file = tmp_path / "bus.jsonl"
    with patch.object(bus, "resolve", return_value=bus_file):
        yield bus_file


class TestKeyGeneration:
    def test_generate_keypair_creates_files(self, key_dir: Path) -> None:
        pub_hex = bus.generate_keypair("agent-test")
        assert isinstance(pub_hex, str)
        assert len(pub_hex) == 64  # 32 bytes = 64 hex chars

        priv_path = key_dir / "agent-test.pem"
        pub_path = key_dir / "agent-test.pub"

        assert priv_path.exists()
        assert priv_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")

        assert pub_path.exists()
        assert pub_path.read_text().strip() == pub_hex

    def test_generate_multiple_agents(self, key_dir: Path) -> None:
        k1 = bus.generate_keypair("agent-a")
        k2 = bus.generate_keypair("agent-b")
        assert k1 != k2  # different keys

    def test_generate_overwrites_existing(self, key_dir: Path) -> None:
        k1 = bus.generate_keypair("agent-overwrite")
        k2 = bus.generate_keypair("agent-overwrite")
        assert k1 != k2  # regeneration produces a different key


class TestKeyLoading:
    def test_load_private_key(self, key_dir: Path) -> None:
        bus.generate_keypair("agent-load")
        key = bus.load_private_key("agent-load")
        assert key is not None

    def test_load_private_key_missing(self, key_dir: Path) -> None:
        key = bus.load_private_key("agent-nonexistent")
        assert key is None

    def test_load_public_key(self, key_dir: Path) -> None:
        bus.generate_keypair("agent-pub")
        key = bus.load_public_key("agent-pub")
        assert key is not None

    def test_load_public_key_missing(self, key_dir: Path) -> None:
        key = bus.load_public_key("agent-nonexistent")
        assert key is None


class TestSignAndVerify:
    def test_sign_and_verify(self, key_dir: Path) -> None:
        bus.generate_keypair("agent-sign")
        challenge = "sess-123:2026-05-01T12:00:00"
        sig = bus.sign_challenge("agent-sign", challenge)
        assert sig is not None
        assert isinstance(sig, str)
        assert len(sig) == 128  # 64 bytes = 128 hex chars

        assert bus.verify_agent("agent-sign", challenge, sig) is True

    def test_verify_wrong_signature(self, key_dir: Path) -> None:
        bus.generate_keypair("agent-v1")
        challenge = "sess-123:2026-05-01T12:00:00"
        sig = bus.sign_challenge("agent-v1", challenge)
        assert sig is not None

        assert bus.verify_agent("agent-v1", challenge + "x", sig) is False

    def test_verify_no_key(self, key_dir: Path) -> None:
        assert bus.verify_agent("nonexistent", "challenge", "signature") is False

    def test_sign_no_key(self, key_dir: Path) -> None:
        sig = bus.sign_challenge("nonexistent", "challenge")
        assert sig is None


class TestSigninIntegration:
    def test_signin_without_key(self, temp_bus: Path) -> None:
        result = bus.signin()
        assert "Signed in" in result
        assert "identity" not in result

    def test_signin_with_key(self, key_dir: Path, tmp_path: Path) -> None:
        bus.generate_keypair(bus.agent_id())

        bus_file = tmp_path / "bus.jsonl"
        with patch.object(bus, "resolve", return_value=bus_file):
            result = bus.signin()
            assert "identity verified" in result.lower()

            msgs = bus.read_messages(limit=10)

        assert len(msgs) >= 1
        signed_in = msgs[-1]
        payload = signed_in.get("payload", {})
        assert "public_key" in payload
        assert "signature" in payload
        assert "challenge" in payload

        # Verify the signature on the signin message
        assert (
            bus.verify_agent(
                bus.agent_id(),
                payload["challenge"],
                payload["signature"],
            )
            is True
        )

    def test_signin_with_key_then_verify(self, key_dir: Path, tmp_path: Path) -> None:
        """End-to-end: sign in with key, then verify a new challenge."""
        bus.generate_keypair(bus.agent_id())

        bus_file = tmp_path / "bus.jsonl"
        with patch.object(bus, "resolve", return_value=bus_file):
            bus.signin()

        # Later, a new challenge proves continued identity
        new_challenge = "sess-456:2026-05-01T13:00:00"
        new_sig = bus.sign_challenge(bus.agent_id(), new_challenge)
        assert new_sig is not None
        assert bus.verify_agent(bus.agent_id(), new_challenge, new_sig) is True
