"""Ed25519 agent identity — keypair generation, signing, verification.

Each agent gets an Ed25519 keypair stored in the bus directory.
Signin includes a signature proving the agent owns the private key.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


def _keys_dir() -> Path:
    """Return the keys directory under the bus storage path."""
    from adhd.bus import resolve

    bus_path = resolve()
    keys_dir = bus_path.parent / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    return keys_dir


def _agent_key_path(agent_id: str) -> Path:
    return _keys_dir() / agent_id


def _private_key_path(agent_id: str) -> Path:
    return _agent_key_path(agent_id) / "id_ed25519"


def _public_key_path(agent_id: str) -> Path:
    return _agent_key_path(agent_id) / "id_ed25519.pub"


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate a new Ed25519 keypair.

    Returns (private_bytes, public_bytes) — 32 bytes each.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes_raw()
    public_bytes = public_key.public_bytes_raw()
    return private_bytes, public_bytes


def load_or_create_identity(agent_id: str) -> tuple[bytes, bytes]:
    """Load an existing keypair from disk or create and persist a new one.

    Returns (private_bytes, public_bytes).
    """
    priv_path = _private_key_path(agent_id)
    pub_path = _public_key_path(agent_id)

    if priv_path.exists() and pub_path.exists():
        return priv_path.read_bytes(), pub_path.read_bytes()

    agent_dir = _agent_key_path(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)

    private_bytes, public_bytes = generate_keypair()

    # Write with restricted permissions
    priv_path.write_bytes(private_bytes)
    os.chmod(priv_path, 0o600)
    pub_path.write_bytes(public_bytes)
    os.chmod(pub_path, 0o644)

    return private_bytes, public_bytes


def get_public_key(agent_id: str) -> bytes | None:
    """Return the public key for an agent, or None if no key exists."""
    pub_path = _public_key_path(agent_id)
    if not pub_path.exists():
        return None
    return pub_path.read_bytes()


def sign_challenge(private_bytes: bytes, challenge: str) -> bytes:
    """Sign a challenge string with the private key.

    Returns a 64-byte Ed25519 signature.
    """
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    return private_key.sign(challenge.encode())


def verify_challenge(public_bytes: bytes, challenge: str, signature: bytes) -> bool:
    """Verify a challenge signature against a public key."""
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(signature, challenge.encode())
        return True
    except (InvalidSignature, ValueError):
        return False
