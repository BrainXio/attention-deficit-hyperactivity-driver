"""Tests for Ed25519 agent identity — keypair generation, signin proof, verification."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path
from unittest.mock import patch

import adhd.identity as identity

# ── Keypair generation ──────────────────────────────────────────────────────


def test_generate_keypair_returns_32_bytes_each() -> None:
    private, public = identity.generate_keypair()
    assert len(private) == 32
    assert len(public) == 32
    assert private != public


def test_generate_keypair_is_random() -> None:
    priv1, pub1 = identity.generate_keypair()
    priv2, pub2 = identity.generate_keypair()
    assert priv1 != priv2
    assert pub1 != pub2


# ── Sign and verify ────────────────────────────────────────────────────────


def test_sign_and_verify_valid() -> None:
    private, public = identity.generate_keypair()
    challenge = "session-1:2026-05-01T00:00:00Z"
    sig = identity.sign_challenge(private, challenge)
    assert len(sig) == 64
    assert identity.verify_challenge(public, challenge, sig) is True


def test_verify_wrong_challenge() -> None:
    private, public = identity.generate_keypair()
    challenge = "session-1:2026-05-01T00:00:00Z"
    sig = identity.sign_challenge(private, challenge)
    assert identity.verify_challenge(public, "wrong:challenge", sig) is False


def test_verify_wrong_public_key() -> None:
    private, public = identity.generate_keypair()
    _, other_public = identity.generate_keypair()
    challenge = "session-1:2026-05-01T00:00:00Z"
    sig = identity.sign_challenge(private, challenge)
    assert identity.verify_challenge(other_public, challenge, sig) is False


def test_verify_tampered_signature() -> None:
    private, public = identity.generate_keypair()
    challenge = "session-1:2026-05-01T00:00:00Z"
    sig = identity.sign_challenge(private, challenge)
    tampered = bytes(b ^ 0xFF for b in sig)
    assert identity.verify_challenge(public, challenge, tampered) is False


def test_verify_empty_challenge() -> None:
    private, public = identity.generate_keypair()
    sig = identity.sign_challenge(private, "")
    assert identity.verify_challenge(public, "", sig) is True


def test_verify_invalid_public_key_bytes() -> None:
    sig = b"\x00" * 64
    assert identity.verify_challenge(b"not-a-valid-ed25519-public-key--", "challenge", sig) is False


# ── Identity persistence ───────────────────────────────────────────────────


def test_load_or_create_creates_new_identity(tmp_path: Path) -> None:
    agent_id = "agent-test-1"
    keys_dir = tmp_path / "keys"
    with patch.object(identity, "_keys_dir", return_value=keys_dir):
        private, public = identity.load_or_create_identity(agent_id)

    assert len(private) == 32
    assert len(public) == 32
    assert (keys_dir / agent_id / "id_ed25519").exists()
    assert (keys_dir / agent_id / "id_ed25519.pub").exists()


def test_load_or_create_loads_existing_identity(tmp_path: Path) -> None:
    agent_id = "agent-test-2"
    keys_dir = tmp_path / "keys"

    with patch.object(identity, "_keys_dir", return_value=keys_dir):
        priv1, pub1 = identity.load_or_create_identity(agent_id)
        # Second call should load the same keys
        priv2, pub2 = identity.load_or_create_identity(agent_id)

    assert priv1 == priv2
    assert pub1 == pub2


def test_load_or_create_different_agents_different_keys(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    with patch.object(identity, "_keys_dir", return_value=keys_dir):
        _, pub1 = identity.load_or_create_identity("agent-a")
        _, pub2 = identity.load_or_create_identity("agent-b")

    assert pub1 != pub2
    assert (keys_dir / "agent-a" / "id_ed25519").exists()
    assert (keys_dir / "agent-b" / "id_ed25519").exists()


def test_get_public_key_returns_none_for_unknown_agent(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    with patch.object(identity, "_keys_dir", return_value=keys_dir):
        assert identity.get_public_key("nonexistent") is None


def test_get_public_key_returns_stored_key(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    with patch.object(identity, "_keys_dir", return_value=keys_dir):
        _, pub = identity.load_or_create_identity("agent-x")
        stored = identity.get_public_key("agent-x")

    assert stored == pub


def test_private_key_permissions_restricted(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    with patch.object(identity, "_keys_dir", return_value=keys_dir):
        identity.load_or_create_identity("agent-secure")

    priv_path = keys_dir / "agent-secure" / "id_ed25519"
    import stat

    mode = priv_path.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


# ── Challenge format ───────────────────────────────────────────────────────


def test_challenge_must_match_when_verifying() -> None:
    private, public = identity.generate_keypair()
    challenge = "abc123:2026-05-01T12:00:00+00:00"
    sig = identity.sign_challenge(private, challenge)

    # Same challenge — valid
    assert identity.verify_challenge(public, challenge, sig) is True
    # Different session
    assert identity.verify_challenge(public, "xyz789:2026-05-01T12:00:00+00:00", sig) is False
    # Different timestamp
    assert identity.verify_challenge(public, "abc123:2026-05-01T12:00:01+00:00", sig) is False


# ── Round-trip via bus signin ──────────────────────────────────────────────


def _setup_bus_mocks(tmp_path: Path) -> tuple[object, object]:
    """Set up bus.resolve and identity._keys_dir patches for a test.

    Returns (resolve_ctx, keys_ctx) — caller must enter them.
    """
    bus_file = tmp_path / "bus.jsonl"
    keys_dir = tmp_path / "keys"
    return (
        patch("adhd.bus.resolve", return_value=bus_file),
        patch("adhd.identity._keys_dir", return_value=keys_dir),
    )


def test_signin_includes_identity_proof(tmp_path: Path) -> None:
    """signin() writes public_key, identity_challenge, and identity_signature."""
    import adhd.bus as bus

    resolve_ctx, keys_ctx = _setup_bus_mocks(tmp_path)
    with resolve_ctx, keys_ctx, patch.dict("os.environ", {}, clear=True):
        bus.signin()
        msgs = bus.read_messages(type_filter="signin")

    assert len(msgs) == 1
    payload = msgs[0]["payload"]
    assert "public_key" in payload
    assert "identity_challenge" in payload
    assert "identity_signature" in payload

    # Verify the signature is valid
    public_bytes = urlsafe_b64decode(payload["public_key"])
    challenge = payload["identity_challenge"]
    sig = urlsafe_b64decode(payload["identity_signature"])
    assert identity.verify_challenge(public_bytes, challenge, sig) is True


def test_signin_identity_proof_with_supporter(tmp_path: Path) -> None:
    """Supporter signin includes both identity proof and supporter fields."""
    import adhd.bus as bus

    resolve_ctx, keys_ctx = _setup_bus_mocks(tmp_path)
    env = {"ADHD_ENABLE_SUPPORTER": "1"}
    with resolve_ctx, keys_ctx, patch.dict("os.environ", env, clear=True):
        bus.signin()
        msgs = bus.read_messages(type_filter="signin")

    payload = msgs[0]["payload"]
    assert "public_key" in payload
    assert payload["supporter"] is True


# ── verify_agent_identity via bus ──────────────────────────────────────────


def test_verify_agent_identity_success(tmp_path: Path) -> None:
    """verify_agent_identity returns ok=True for a valid signin."""
    import adhd.bus as bus

    resolve_ctx, keys_ctx = _setup_bus_mocks(tmp_path)
    with resolve_ctx, keys_ctx, patch.dict("os.environ", {}, clear=True):
        bus.signin()
        agent = bus.agent_id()
        result = bus.verify_agent_identity(agent)

    assert result["ok"] is True
    assert result["agent_id"] == agent
    assert "Identity verified" in result["detail"]


def test_verify_agent_identity_not_found(tmp_path: Path) -> None:
    """verify_agent_identity returns ok=False when agent has no signin."""
    import adhd.bus as bus

    resolve_ctx, _ = _setup_bus_mocks(tmp_path)
    with resolve_ctx:
        result = bus.verify_agent_identity("unknown-agent")

    assert result["ok"] is False
    assert "No signin found" in result["detail"]


def test_verify_agent_identity_tampered_signature(tmp_path: Path) -> None:
    """verify_agent_identity detects tampered identity signatures."""
    import json

    import adhd.bus as bus

    resolve_ctx, keys_ctx = _setup_bus_mocks(tmp_path)
    with resolve_ctx, keys_ctx, patch.dict("os.environ", {}, clear=True):
        bus.signin()
        agent = bus.agent_id()

        # Write a tampered signin message directly to the bus
        msgs = bus.read_messages(type_filter="signin")
        tampered = dict(msgs[0])
        tampered["payload"] = dict(tampered["payload"])
        tampered["payload"]["identity_signature"] = urlsafe_b64encode(b"\x00" * 64).decode()
        # Append tampered message directly
        bus_path = bus.resolve()
        with open(bus_path, "a") as f:
            f.write(json.dumps(tampered, separators=(",", ":")) + "\n")

        # This should now see the tampered signin (latest one) and fail
        result = bus.verify_agent_identity(agent)

    # The latest signin has a bad signature
    assert result["ok"] is False
    assert "Identity signature invalid" in result["detail"]


def test_verify_agent_identity_missing_fields(tmp_path: Path) -> None:
    """Signin without identity fields fails verification."""
    import adhd.bus as bus

    resolve_ctx, _ = _setup_bus_mocks(tmp_path)
    with resolve_ctx:
        bus.post(
            "signin",
            "agent-lifecycle",
            {"message": "no identity"},
            agent_id_override="legacy-agent",
        )
        result = bus.verify_agent_identity("legacy-agent")

    assert result["ok"] is False
    assert "missing identity proof fields" in result["detail"]


# ── Identity persistence across bus sessions ───────────────────────────────


def test_same_agent_reuses_keypair(tmp_path: Path) -> None:
    """The same agent_id gets the same keypair across signins."""
    import adhd.bus as bus

    resolve_ctx, keys_ctx = _setup_bus_mocks(tmp_path)
    with resolve_ctx, keys_ctx, patch.dict("os.environ", {}, clear=True):
        bus.signin()
        msgs = bus.read_messages(type_filter="signin")
        pub1 = msgs[0]["payload"]["public_key"]

    with resolve_ctx, keys_ctx, patch.dict("os.environ", {}, clear=True):
        bus.signin()
        msgs = bus.read_messages(type_filter="signin")
        pub2 = msgs[-1]["payload"]["public_key"]

    assert pub1 == pub2
