"""Core business logic for the ADHD coordination bus."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

logger = logging.getLogger(__name__)


def _get_secret() -> str | None:
    """Return the shared HMAC secret if configured, or None if signing is disabled."""
    return os.environ.get("ADHD_BUS_SECRET") or None


def resolve() -> Path:
    """Return the absolute path to the ADHD bus file.

    Path resolution order:
    1. ADHD_BUS_PATH env var (storage directory prefix, default: ~/.brainxio/adhd/)
    2. ADHD_BUS_SLUG env var (bus name, default: git toplevel basename)
    3. Full path: {ADHD_BUS_PATH}/{ADHD_BUS_SLUG}/bus.jsonl

    When inside a git submodule, the parent project root is used instead of
    the submodule directory so the bus is shared across the workspace.
    """
    base_dir = Path(os.environ.get("ADHD_BUS_PATH", "~/.brainxio/adhd")).expanduser()

    bus_name = os.environ.get("ADHD_BUS_SLUG")
    if not bus_name:
        try:
            superproject = subprocess.run(
                ["git", "rev-parse", "--show-superproject-working-tree"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if superproject:
                bus_name = Path(superproject).name
            else:
                toplevel = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                bus_name = Path(toplevel).name
        except subprocess.CalledProcessError:
            bus_name = "default"

    bus_dir = base_dir / bus_name
    bus_dir.mkdir(parents=True, exist_ok=True)
    return bus_dir / "bus.jsonl"


_session_id: str = os.environ.get("ADHD_SESSION_ID", str(uuid.uuid4())[:8])


def session_id() -> str:
    return _session_id


def agent_id() -> str:
    return os.environ.get("ADHD_AGENT_ID") or f"agent-{session_id()}"


def current_branch() -> str:
    try:
        return (
            subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or "main"
        )
    except Exception:
        return "unknown"


def now() -> str:
    return datetime.now(UTC).isoformat()


_PERF_LEVELS = frozenset({"low", "medium", "high"})


def get_perf_level() -> str:
    """Return the session performance level from ADHD_PERF_LEVEL env var.

    Valid values: low, medium, high. Default: medium.
    Invalid values log a warning and fall back to medium.
    """
    raw = os.environ.get("ADHD_PERF_LEVEL", "medium").lower()
    if raw not in _PERF_LEVELS:
        logger.warning("ADHD_PERF_LEVEL=%r invalid, falling back to 'medium'", raw)
        return "medium"
    return raw


# ---------------------------------------------------------------------------
# Bus I/O
# ---------------------------------------------------------------------------


def _compute_hmac(payload_json: str, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for a JSON string."""
    return hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()


def sign_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the message with an 'hmac' field added.

    The HMAC is computed over the full JSON representation of the message
    (excluding any existing 'hmac' field). If no secret is configured, the
    message is returned as-is.

    The message is serialized with sorted keys and compact separators for
    deterministic signing.
    """
    secret = _get_secret()
    if not secret:
        return msg
    payload = {k: v for k, v in msg.items() if k != "hmac"}
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signed = dict(msg)
    signed["hmac"] = _compute_hmac(payload_json, secret)
    return signed


def verify_signature(msg: dict[str, Any]) -> bool:
    """Verify the HMAC signature on a bus message.

    Returns True if signing is disabled (no secret configured), or if the
    message's 'hmac' field matches the recomputed HMAC. Returns False if
    the message has been tampered with or if the 'hmac' field is missing
    when signing is enabled.
    """
    secret = _get_secret()
    if not secret:
        return True
    if "hmac" not in msg:
        return False
    received_hmac = msg["hmac"]
    payload = {k: v for k, v in msg.items() if k != "hmac"}
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    expected_hmac = _compute_hmac(payload_json, secret)
    return hmac.compare_digest(received_hmac, expected_hmac)


def write_message(msg: dict[str, Any]) -> None:
    """Append a message to the bus after signing and validating it."""
    msg = sign_message(msg)
    bus_path = resolve()
    with bus_path.open("a") as f:
        f.write(json.dumps(msg, separators=(",", ":")) + "\n")


def read_messages(
    limit: int = 50,
    type_filter: str | None = None,
    topic_filter: str | None = None,
    agent_filter: str | None = None,
    recipient_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Read recent messages from the bus with optional filtering."""
    bus_path = resolve()
    if not bus_path.exists():
        return []

    messages: list[dict[str, Any]] = []
    with bus_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if type_filter and msg.get("type") != type_filter:
                continue
            if topic_filter and msg.get("topic") != topic_filter:
                continue
            if agent_filter and msg.get("agent_id") != agent_filter:
                continue
            if recipient_filter is not None:
                payload = msg.get("payload", {})
                if isinstance(payload, dict):
                    rcpt = payload.get("recipient")
                    if recipient_filter == "all":
                        if rcpt != "all":
                            continue
                    elif rcpt != recipient_filter:
                        continue
                else:
                    continue
            messages.append(msg)

    return messages[-limit:]


def get_file_size() -> int:
    """Return the current byte size of the bus file (0 if missing)."""
    bus_path = resolve()
    if not bus_path.exists():
        return 0
    return bus_path.stat().st_size


def read_messages_since(
    position: int,
    limit: int = 200,
    type_filter: str | None = None,
    topic_filter: str | None = None,
    agent_filter: str | None = None,
    recipient_filter: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Read messages from the bus starting at a byte offset.

    Returns (messages, new_position) where new_position is the end of file
    after reading. Callers track position between calls to get only new messages.
    """
    bus_path = resolve()
    if not bus_path.exists():
        return [], 0

    file_size = bus_path.stat().st_size
    if position >= file_size:
        return [], file_size

    messages: list[dict[str, Any]] = []
    with bus_path.open("r") as f:
        f.seek(position)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if type_filter and msg.get("type") != type_filter:
                continue
            if topic_filter and msg.get("topic") != topic_filter:
                continue
            if agent_filter and msg.get("agent_id") != agent_filter:
                continue
            if recipient_filter is not None:
                p = msg.get("payload", {})
                if isinstance(p, dict):
                    rcpt = p.get("recipient")
                    if recipient_filter == "all":
                        if rcpt != "all":
                            continue
                    elif rcpt != recipient_filter:
                        continue
                else:
                    continue
            messages.append(msg)

    return messages[-limit:], file_size


# ---------------------------------------------------------------------------
# Subscription protocol
# ---------------------------------------------------------------------------


def subscribe(filters: dict[str, str]) -> str:
    """Register a subscription on the bus for the current agent.

    Filters can include type, topic, and recipient keys.
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "subscription",
            "topic": "bus-subscriptions",
            "payload": {"action": "subscribe", "filters": filters},
        }
    )
    return f"Subscribed with filters: {filters}"


def unsubscribe() -> str:
    """Remove the current agent's subscription from the bus."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "unsubscription",
            "topic": "bus-subscriptions",
            "payload": {"action": "unsubscribe"},
        }
    )
    return "Unsubscribed."


def get_subscriptions() -> dict[str, dict[str, str]]:
    """Return active subscriptions keyed by agent_id.

    A subscription is active when the most recent subscription/unsubscription
    message for that agent is a subscription.
    """
    messages = read_messages(topic_filter="bus-subscriptions", limit=500)
    subs: dict[str, dict[str, str]] = {}
    for msg in messages:
        payload = msg.get("payload", {})
        if not isinstance(payload, dict):
            continue
        action = payload.get("action")
        agent = msg.get("agent_id", "")
        if action == "subscribe":
            filters = payload.get("filters", {})
            if isinstance(filters, dict):
                subs[agent] = {str(k): str(v) for k, v in filters.items()}
        elif action == "unsubscribe":
            subs.pop(agent, None)
    return subs


# ---------------------------------------------------------------------------
# Migration protocol (poll → push)
# ---------------------------------------------------------------------------


def announce_migration() -> str:
    """Broadcast a migration announcement to all active agents."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "migration_announce",
            "topic": "bus-migration",
            "payload": {
                "action": "migrate-to-push",
                "message": "Switch to push/event-driven delivery and ditch polling monitors.",
            },
        }
    )
    return "Migration announcement posted."


def ack_migration() -> str:
    """Acknowledge migration to push-based delivery for the current agent."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "migration_ack",
            "topic": "bus-migration",
            "payload": {"action": "ack"},
        }
    )
    return "Migration acknowledged."


def get_pending_migration_acks(active_agents: list[str]) -> list[str]:
    """Return agent IDs that have NOT yet acknowledged migration.

    Only tracks agents in the active_agents list.
    """
    messages = read_messages(topic_filter="bus-migration", limit=500)
    acked: set[str] = set()
    for msg in messages:
        if msg.get("type") == "migration_ack":
            agent = msg.get("agent_id", "")
            if isinstance(agent, str):
                acked.add(agent)
    return [a for a in active_agents if a not in acked]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(line: str) -> tuple[bool, str]:
    """Return (valid, error_message) for a single bus line."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        return False, f"Invalid JSON: {exc}"

    required = {"timestamp", "session_id", "agent_id", "branch", "type", "topic", "payload"}
    missing = required - set(obj.keys())
    if missing:
        return False, f"Missing fields: {sorted(missing)}"

    if not isinstance(obj.get("payload"), dict):
        return False, "payload must be an object"

    valid_types = {
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
        "request",
        "response",
        "hitl_claim",
        "hitl_release",
        "hitl_rpe",
        "hitl_approve",
        "hitl_split",
        "subscription",
        "unsubscription",
        "migration_announce",
        "migration_ack",
    }
    if obj["type"] not in valid_types:
        return False, f"Invalid type: {obj['type']}"

    return True, ""


def validate_bus() -> tuple[bool, str]:
    """Validate every line in the bus file."""
    bus_path = resolve()
    if not bus_path.exists():
        return True, "Bus file does not exist yet"

    for i, line in enumerate(bus_path.open(), 1):
        line = line.strip()
        if not line:
            continue
        ok, err = validate(line)
        if not ok:
            return False, f"Line {i}: {err}"

    return True, "Bus is valid"


# ---------------------------------------------------------------------------
# Supporter management
# ---------------------------------------------------------------------------

_REAP_THRESHOLD = timedelta(minutes=15)


def _is_session_alive(msg: dict[str, Any]) -> bool:
    """Check if a session's most recent activity is within the heartbeat window."""
    ts_str = msg.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        return False
    return (datetime.now(UTC) - ts) < timedelta(minutes=20)


def check_supporters() -> list[dict[str, Any]]:
    """Return active supporter sessions (signin/heartbeat with supporter=True in payload).

    A session is considered active if its most recent heartbeat or signin is
    within the last 20 minutes.
    """
    messages = read_messages(limit=500)
    active: dict[str, dict[str, Any]] = {}

    for msg in messages:
        sid = msg.get("session_id")
        if not isinstance(sid, str):
            continue

        if msg.get("type") == "signout":
            active.pop(sid, None)
            continue

        if msg.get("type") in {"signin", "heartbeat"}:
            payload = msg.get("payload") or {}
            if payload.get("supporter") is True:
                active[sid] = msg

    return [
        {
            "session_id": sid,
            "agent_id": msg.get("agent_id", "unknown"),
            "timestamp": msg.get("timestamp", ""),
            "alive": _is_session_alive(msg),
        }
        for sid, msg in active.items()
        if _is_session_alive(msg)
    ]


def reap_stale_heartbeats() -> list[dict[str, str]]:
    """Auto-signout sessions whose most recent heartbeat is older than 15 minutes.

    Scans the bus for active sessions and writes signout messages for any
    whose last heartbeat/signin exceeds the reaping threshold. This keeps
    the active-supporters list accurate when agents crash or exit without
    signing out.

    Returns a list of reaped sessions with session_id and agent_id.
    """
    messages = read_messages(limit=500)
    sessions: dict[str, dict[str, str]] = {}
    cutoff = datetime.now(UTC) - _REAP_THRESHOLD

    for msg in messages:
        sid = msg.get("session_id")
        if not isinstance(sid, str):
            continue

        if msg.get("type") == "signout":
            sessions.pop(sid, None)
            continue

        if msg.get("type") in {"signin", "heartbeat"}:
            ts_str = msg.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            if ts > cutoff:
                sessions.pop(sid, None)
                continue
            if sid not in sessions:
                sessions[sid] = {
                    "session_id": sid,
                    "agent_id": msg.get("agent_id", "unknown"),
                    "last_seen": ts_str,
                }

    reaped: list[dict[str, str]] = []
    for sid, info in sessions.items():
        write_message(
            {
                "timestamp": now(),
                "session_id": sid,
                "agent_id": info["agent_id"],
                "branch": "unknown",
                "type": "signout",
                "topic": "agent-lifecycle",
                "payload": {"reason": "stale-heartbeat-reaped"},
            }
        )
        reaped.append(info)

    return reaped


# ---------------------------------------------------------------------------
# Agent identity — Ed25519 keypairs
# ---------------------------------------------------------------------------


def _get_key_dir() -> Path:
    """Return the key storage directory, creating it if needed."""
    base = Path(os.environ.get("ADHD_BUS_PATH", "~/.brainxio/adhd")).expanduser()
    key_dir = base / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    return key_dir


def _key_path(agent_id: str, suffix: str = ".pem") -> Path:
    """Return the full path to an agent's key file."""
    return _get_key_dir() / f"{agent_id}{suffix}"


def generate_keypair(agent_id: str) -> str:
    """Generate an Ed25519 keypair for *agent_id* and persist to disk.

    Private key: PEM-encoded PKCS8 at ``{key_dir}/{agent_id}.pem``.
    Public  key: raw hex bytes at ``{key_dir}/{agent_id}.pub``.

    Returns the public-key hex.
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    pem_private = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    _key_path(agent_id, ".pem").write_bytes(pem_private)

    pub_hex = public_key.public_bytes_raw().hex()
    _key_path(agent_id, ".pub").write_text(pub_hex + "\n")
    return pub_hex


def load_private_key(agent_id: str) -> Ed25519PrivateKey | None:
    """Load the agent's Ed25519 private key, or *None* if missing."""
    path = _key_path(agent_id, ".pem")
    if not path.exists():
        return None
    try:
        key = load_pem_private_key(path.read_bytes(), password=None)
        return key if isinstance(key, Ed25519PrivateKey) else None
    except Exception:
        return None


def load_public_key(agent_id: str) -> Ed25519PublicKey | None:
    """Load an agent's Ed25519 public key, or *None* if missing."""
    path = _key_path(agent_id, ".pub")
    if not path.exists():
        return None
    try:
        pub_hex = path.read_text().strip()
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
    except Exception:
        return None


def sign_challenge(agent_id: str, challenge: str) -> str | None:
    """Sign *challenge* with the agent's private key.

    Returns hex-encoded signature or *None* when no key exists.
    """
    private_key = load_private_key(agent_id)
    if private_key is None:
        return None
    return private_key.sign(challenge.encode()).hex()


def verify_agent(agent_id: str, challenge: str, signature: str) -> bool:
    """Verify *signature* of *challenge* against the agent's public key.

    Returns *True* when the signature is valid.  Returns *False* when the
    public key is missing or verification fails (impersonation / tampering).
    """
    public_key = load_public_key(agent_id)
    if public_key is None:
        return False
    try:
        public_key.verify(bytes.fromhex(signature), challenge.encode())
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Capability tokens — signed authorization claims
# ---------------------------------------------------------------------------


def _generate_token_id() -> str:
    """Generate a short unique token identifier."""
    import secrets

    return "tok_" + secrets.token_hex(4)


def issue_token(
    issuer_id: str,
    subject: str,
    *,
    allowed_tools: list[str] | None = None,
    scopes: list[str] | None = None,
    expiry_hours: int = 24,
) -> str | None:
    """Issue a signed capability token for *subject* signed by *issuer_id*.

    The token is a dot-separated string: ``base64(payload).signature_hex``
    where the payload is a JSON object with subject, issuer, timestamps,
    allowed_tools, scopes, and token_id.  The signature is the issuer's
    Ed25519 signature over the payload JSON.

    Returns the encoded token string, or ``None`` if the issuer's private
    key is missing.
    """
    import base64

    private_key = load_private_key(issuer_id)
    if private_key is None:
        return None

    payload: dict[str, Any] = {
        "subject": subject,
        "issuer": issuer_id,
        "issued_at": now(),
        "expires_at": (datetime.now(UTC) + timedelta(hours=expiry_hours)).isoformat(),
        "allowed_tools": allowed_tools or [],
        "scopes": scopes or [],
        "token_id": _generate_token_id(),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
    signature = private_key.sign(payload_json.encode()).hex()
    return f"{payload_b64}.{signature}"


def verify_token(
    token_str: str,
    *,
    required_tool: str | None = None,
    caller_id: str | None = None,
) -> dict[str, object]:
    """Verify a signed capability token.

    Checks:
    1. Token format (two dot-separated parts)
    2. Payload is valid JSON with required fields
    3. Signature is valid against the issuer's Ed25519 public key
    4. Token has not expired
    5. ``caller_id`` matches ``subject`` (when provided)
    6. ``required_tool`` is in ``allowed_tools`` (when provided)

    Returns ``{"ok": True}`` or ``{"ok": False, "detail": "..."}``.
    """
    import base64

    parts = token_str.split(".", 1)
    if len(parts) != 2:
        return {"ok": False, "detail": "Invalid token format"}

    payload_b64, signature_hex = parts

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
        payload = json.loads(payload_bytes)
    except Exception:
        return {"ok": False, "detail": "Invalid token payload encoding"}

    if not isinstance(payload, dict):
        return {"ok": False, "detail": "Token payload must be a JSON object"}

    for field in ("subject", "issuer", "expires_at", "token_id"):
        if field not in payload:
            return {"ok": False, "detail": f"Token missing required field: {field}"}

    issuer_id = payload["issuer"]
    public_key = load_public_key(issuer_id)
    if public_key is None:
        return {
            "ok": False,
            "detail": f"Issuer '{issuer_id}' has no public key",
        }

    payload_json = json.dumps(payload, separators=(",", ":"))
    try:
        public_key.verify(bytes.fromhex(signature_hex), payload_json.encode())
    except Exception:
        return {"ok": False, "detail": "Token signature invalid"}

    expires_at_str = payload["expires_at"]
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires_at:
            return {"ok": False, "detail": "Token has expired"}
    except (ValueError, TypeError):
        return {"ok": False, "detail": "Token has invalid expires_at"}

    if caller_id is not None and payload["subject"] != caller_id:
        return {
            "ok": False,
            "detail": f"Token subject '{payload['subject']}' does not match caller '{caller_id}'",
        }

    if required_tool is not None:
        allowed = payload.get("allowed_tools", [])
        if required_tool not in allowed:
            return {
                "ok": False,
                "detail": f"Token does not allow tool '{required_tool}'",
            }

    return {"ok": True}


# ---------------------------------------------------------------------------
# High-level helpers (signin, signout, heartbeat, post, send)
# ---------------------------------------------------------------------------


def signin() -> str:
    """Write a signin message with optional identity proof.

    When the agent has an Ed25519 keypair, the signin includes a
    cryptographic proof of identity (public_key, challenge, signature).
    """
    payload: dict[str, Any] = {}
    if os.environ.get("ADHD_ENABLE_SUPPORTER"):
        payload["supporter"] = True
        payload["perf_level"] = get_perf_level()

    agent = agent_id()
    challenge = f"{session_id()}:{now()}"
    sig = sign_challenge(agent, challenge)
    if sig is not None:
        pub_key = load_public_key(agent)
        if pub_key is not None:
            payload["public_key"] = pub_key.public_bytes_raw().hex()
            payload["signature"] = sig
            payload["challenge"] = challenge

    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent,
            "branch": current_branch(),
            "type": "signin",
            "topic": "agent-lifecycle",
            "payload": payload,
        }
    )
    if sig is not None:
        return "Signed in (identity verified)."
    if payload.get("supporter"):
        return "Signed in as supporter."
    return "Signed in."


def signout() -> str:
    """Write a signout message."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "signout",
            "topic": "agent-lifecycle",
            "payload": {},
        }
    )
    return "Signed out."


def post(
    type_: str,
    topic: str,
    payload: dict[str, Any] | None = None,
    agent_id_override: str | None = None,
    branch_override: str | None = None,
) -> str:
    """Post a generic message to the bus."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id_override or agent_id(),
            "branch": branch_override or current_branch(),
            "type": type_,
            "topic": topic,
            "payload": payload or {},
        }
    )
    return f"Posted {type_} to {topic}."


def send(to: str, message: str, topic: str = "agent-request", type_: str = "request") -> str:
    """Send a message to a specific agent."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": type_,
            "topic": topic,
            "payload": {"recipient": to, "message": message},
        }
    )
    return f"Sent {type_} to {to}."


# ---------------------------------------------------------------------------
# MCP change notification protocol
# ---------------------------------------------------------------------------


def prepare_mcp_change(server: str) -> str:
    """Write a preparing notification for MCP server code changes.

    Other sessions reading the bus should pause tool calls to 'server'
    until a matching ready message appears.
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "event",
            "topic": "mcp-change",
            "payload": {
                "server": server,
                "action": "preparing",
                "branch": current_branch(),
                "session_id": session_id(),
            },
        }
    )
    return f"MCP change preparing for {server}."


def mark_mcp_change_ready(server: str, commit: str = "") -> str:
    """Write a ready notification, signaling the server code change is deployed.

    Other sessions can resume tool calls to 'server'.
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "event",
            "topic": "mcp-change",
            "payload": {
                "server": server,
                "action": "ready",
                "commit": commit,
                "session_id": session_id(),
            },
        }
    )
    return f"MCP change ready for {server}."


def check_mcp_change_status() -> list[dict[str, object]]:
    """Return list of servers currently in flux (preparing without matching ready).

    Scans the bus for mcp-change events. A server is "in flux" when the most
    recent mcp-change event for that server has action="preparing".
    """
    messages = read_messages(topic_filter="mcp-change", limit=500)
    in_flux: dict[str, dict[str, object]] = {}

    for msg in messages:
        payload = msg.get("payload") or {}
        server = payload.get("server")
        if not isinstance(server, str):
            continue
        action = payload.get("action")
        if action == "preparing":
            in_flux[server] = {
                "server": server,
                "session_id": msg.get("session_id", ""),
                "agent_id": msg.get("agent_id", ""),
                "timestamp": msg.get("timestamp", ""),
            }
        elif action == "ready":
            in_flux.pop(server, None)

    return list(in_flux.values())


# ---------------------------------------------------------------------------
# Merge-queue claim protocol
# ---------------------------------------------------------------------------

_CLAIM_TTL = timedelta(minutes=5)


def claim_pr(pr_number: int) -> str:
    """Claim a PR for merging. Other supporters skip claimed PRs.

    Claims auto-expire after 5 minutes to handle crashed agents.
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "event",
            "topic": "merge-queue",
            "payload": {
                "pr": pr_number,
                "action": "claim",
                "session_id": session_id(),
            },
        }
    )
    return f"Claimed PR #{pr_number} for merging."


def release_pr(pr_number: int) -> str:
    """Release a previously claimed PR."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "event",
            "topic": "merge-queue",
            "payload": {
                "pr": pr_number,
                "action": "release",
                "session_id": session_id(),
            },
        }
    )
    return f"Released claim on PR #{pr_number}."


def get_active_claims() -> list[dict[str, object]]:
    """Return list of PRs with active claims (not released, not stale).

    A claim is stale when its timestamp is more than 5 minutes old.
    """
    messages = read_messages(topic_filter="merge-queue", limit=500)
    claims: dict[int, dict[str, object]] = {}
    cutoff = datetime.now(UTC) - _CLAIM_TTL

    for msg in messages:
        payload = msg.get("payload") or {}
        pr = payload.get("pr")
        if not isinstance(pr, int):
            continue
        action = payload.get("action")
        if action == "claim":
            ts_str = msg.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            if ts > cutoff:
                claims[pr] = {
                    "pr": pr,
                    "session_id": msg.get("session_id", ""),
                    "agent_id": msg.get("agent_id", ""),
                    "timestamp": ts_str,
                }
        elif action == "release":
            claims.pop(pr, None)

    return list(claims.values())


# ---------------------------------------------------------------------------
# Human-In-The-Loop (HITL) protocol
# ---------------------------------------------------------------------------

_HITL_DECISION_TTL = timedelta(minutes=30)


def hitl_claim_decision(decision_id: str, description: str, urgency: str = "medium") -> str:
    """Claim a pending decision for human review.

    Args:
        decision_id: Unique identifier for the decision (e.g., "pr-42-merge")
        description: Human-readable summary of what needs deciding
        urgency: low | medium | high (default medium)
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "hitl_claim",
            "topic": "hitl-decisions",
            "payload": {
                "decision_id": decision_id,
                "description": description,
                "urgency": urgency,
                "action": "claim",
            },
        }
    )
    return f"Claimed decision '{decision_id}' for human review."


def hitl_release_decision(decision_id: str) -> str:
    """Release a previously claimed decision."""
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "hitl_release",
            "topic": "hitl-decisions",
            "payload": {
                "decision_id": decision_id,
                "action": "release",
            },
        }
    )
    return f"Released claim on decision '{decision_id}'."


def hitl_provide_rpe(decision_id: str, rpe_value: float, notes: str = "") -> str:
    """Provide Reward Prediction Error feedback for a decision.

    Args:
        decision_id: The decision this RPE applies to
        rpe_value: Numeric RPE (positive = better than expected, negative = worse)
        notes: Optional human-readable context
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "hitl_rpe",
            "topic": "hitl-decisions",
            "payload": {
                "decision_id": decision_id,
                "rpe": rpe_value,
                "notes": notes,
            },
        }
    )
    return f"Recorded RPE {rpe_value} for decision '{decision_id}'."


def hitl_approve_gonogo(decision_id: str, approved: bool, reason: str = "") -> str:
    """Approve or reject a Go/NoGo action.

    Args:
        decision_id: The action under review
        approved: True to approve, False to reject
        reason: Optional explanation for the decision
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "hitl_approve",
            "topic": "hitl-decisions",
            "payload": {
                "decision_id": decision_id,
                "approved": approved,
                "reason": reason,
            },
        }
    )
    status = "approved" if approved else "rejected"
    return f"Go/NoGo '{decision_id}' {status}."


def hitl_split_duties(duties: list[str], target_agents: list[str]) -> str:
    """Split or supplement supporter duties across agents.

    Args:
        duties: List of duty descriptions (e.g., ["bus-monitor", "pr-scan"])
        target_agents: Agent IDs or "all" to broadcast
    """
    write_message(
        {
            "timestamp": now(),
            "session_id": session_id(),
            "agent_id": agent_id(),
            "branch": current_branch(),
            "type": "hitl_split",
            "topic": "hitl-decisions",
            "payload": {
                "duties": duties,
                "target_agents": target_agents,
            },
        }
    )
    return f"Split duties {duties} across {target_agents}."


def get_pending_decisions() -> list[dict[str, Any]]:
    """Return decisions that are claimed but not yet resolved.

    A decision is pending when it has a hitl_claim without a matching
    hitl_release or hitl_approve for the same decision_id.
    """
    messages = read_messages(topic_filter="hitl-decisions", limit=500)
    decisions: dict[str, dict[str, Any]] = {}
    cutoff = datetime.now(UTC) - _HITL_DECISION_TTL

    for msg in messages:
        payload = msg.get("payload") or {}
        did = payload.get("decision_id")
        if not isinstance(did, str):
            continue
        msg_type = msg.get("type", "")
        if msg_type == "hitl_claim":
            ts_str = msg.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            if ts > cutoff:
                decisions[did] = {
                    "decision_id": did,
                    "description": payload.get("description", ""),
                    "urgency": payload.get("urgency", "medium"),
                    "claimed_by": msg.get("agent_id", ""),
                    "timestamp": ts_str,
                }
        elif msg_type in {"hitl_release", "hitl_approve"}:
            decisions.pop(did, None)

    return list(decisions.values())


def get_decision_history(decision_id: str) -> list[dict[str, Any]]:
    """Return all bus messages for a given decision_id."""
    messages = read_messages(topic_filter="hitl-decisions", limit=500)
    return [msg for msg in messages if msg.get("payload", {}).get("decision_id") == decision_id]


# ---------------------------------------------------------------------------
# Noise threshold monitoring
# ---------------------------------------------------------------------------

_NOISE_WINDOW_MINUTES = 5


def get_noise_metrics(window_minutes: int = _NOISE_WINDOW_MINUTES) -> dict[str, Any]:
    """Return current bus density metrics over the given time window.

    Returns message rate, active agent count, and threshold configuration.
    """
    threshold_per_minute = int(os.environ.get("ADHD_NOISE_THRESHOLD", "50"))
    threshold_agents = int(os.environ.get("ADHD_NOISE_AGENT_THRESHOLD", "20"))

    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
    messages = read_messages(limit=2000)

    window_msgs: list[dict[str, Any]] = []
    agents: set[str] = set()
    for msg in messages:
        ts_str = msg.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            continue
        if ts >= cutoff:
            window_msgs.append(msg)
            agent = msg.get("agent_id", "")
            if isinstance(agent, str):
                agents.add(agent)

    msg_count = len(window_msgs)
    rate = msg_count / window_minutes if window_minutes > 0 else 0.0

    return {
        "messages_per_minute": round(rate, 2),
        "active_agents": len(agents),
        "total_messages": msg_count,
        "window_minutes": window_minutes,
        "threshold_per_minute": threshold_per_minute,
        "threshold_agents": threshold_agents,
        "warning_active": rate > threshold_per_minute or len(agents) > threshold_agents,
    }


def check_noise_threshold() -> str:
    """Check bus density against configured thresholds and post a warning if exceeded.

    Posts a density warning message to the bus when the message rate or active
    agent count exceeds the configured thresholds. Warnings include the current
    metrics so agents can self-regulate.
    """
    metrics = get_noise_metrics()
    rate = metrics["messages_per_minute"]
    agents = metrics["active_agents"]
    threshold_rate = metrics["threshold_per_minute"]
    threshold_agents = metrics["threshold_agents"]

    if rate > threshold_rate or agents > threshold_agents:
        reasons: list[str] = []
        if rate > threshold_rate:
            reasons.append(f"message rate {rate}/min exceeds threshold {threshold_rate}/min")
        if agents > threshold_agents:
            reasons.append(f"active agents {agents} exceeds threshold {threshold_agents}")

        write_message(
            {
                "timestamp": now(),
                "session_id": session_id(),
                "agent_id": agent_id(),
                "branch": current_branch(),
                "type": "event",
                "topic": "bus-noise",
                "payload": {
                    "warning": "density_warning",
                    "reasons": reasons,
                    "metrics": metrics,
                },
            }
        )
        return f"WARNING: Bus density exceeded thresholds. {', '.join(reasons)}."

    return (
        f"Bus density normal: {rate}/min rate, {agents} active agents "
        f"(thresholds: {threshold_rate}/min, {threshold_agents} agents)."
    )


# ---------------------------------------------------------------------------
# Archival
# ---------------------------------------------------------------------------

MAX_LINES = 10_000
ARCHIVE_KEEP = 2_000
COMPACTION_WARN_AT = 0.8  # warn at 80% of MAX_LINES


def archive() -> str:
    """Archive old messages when the bus exceeds the size limit.

    Reaps stale heartbeat entries before archiving to keep the supporters
    list accurate. Returns a compaction warning when the bus exceeds 80%
    of MAX_LINES so agents can proactively archive.
    """
    reap_stale_heartbeats()

    bus_path = resolve()
    if not bus_path.exists():
        return "Bus file does not exist."

    lines = bus_path.read_text().splitlines()
    line_count = len(lines)

    if line_count > MAX_LINES:
        archive_lines = lines[:-ARCHIVE_KEEP]
        keep_lines = lines[-ARCHIVE_KEEP:]
        archive_name = f"bus_archive_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.jsonl"
        archive_path = bus_path.with_name(archive_name)
        tmp_path = bus_path.with_name(".bus.jsonl.tmp")

        archive_path.write_text("\n".join(archive_lines) + "\n")
        tmp_path.write_text("\n".join(keep_lines) + "\n")
        tmp_path.replace(bus_path)
        return (
            f"Archived {len(archive_lines)} lines to {archive_path}. "
            f"Retained {len(keep_lines)} lines."
        )

    pct = int(line_count / MAX_LINES * 100)
    if line_count > int(MAX_LINES * COMPACTION_WARN_AT):
        return (
            f"WARNING: Bus at {pct}% capacity ({line_count}/{MAX_LINES} lines). "
            "Run adhd_archive to compact proactively."
        )

    return f"Bus has {line_count} lines ({pct}% capacity). No archive needed."


# ---------------------------------------------------------------------------
# Bus snapshots
# ---------------------------------------------------------------------------


def create_snapshot() -> dict[str, Any]:
    """Create a full-state checkpoint of the bus for recovery and replay.

    Returns message count, timestamp range, registered/active agents,
    subscription state, and bus file path. Does not write to the bus.
    """
    bus_path = resolve()
    if not bus_path.exists():
        return {
            "snapshot_at": now(),
            "message_count": 0,
            "file_size_bytes": 0,
            "timestamp_range": {"first": None, "last": None},
            "registered_agents": [],
            "active_agents": [],
            "subscriptions": {},
            "bus_path": str(bus_path),
        }

    messages = read_messages(limit=10000)
    first_ts = messages[0]["timestamp"] if messages else None
    last_ts = messages[-1]["timestamp"] if messages else None

    agents: set[str] = set()
    for msg in messages:
        a = msg.get("agent_id")
        if isinstance(a, str):
            agents.add(a)

    supporters = check_supporters()
    active_agent_ids = [s["agent_id"] for s in supporters]

    return {
        "snapshot_at": now(),
        "message_count": len(messages),
        "file_size_bytes": bus_path.stat().st_size,
        "timestamp_range": {"first": first_ts, "last": last_ts},
        "registered_agents": sorted(agents),
        "active_agents": sorted(active_agent_ids),
        "subscriptions": get_subscriptions(),
        "bus_path": str(bus_path),
    }


# ---------------------------------------------------------------------------
# Bus discovery
# ---------------------------------------------------------------------------


def discover_buses() -> list[dict[str, Any]]:
    """Scan the ADHD storage directory for active bus files.

    Returns metadata for each discovered bus: slug, message count,
    last activity timestamp, and active agent count.
    """
    base_dir = Path(os.environ.get("ADHD_BUS_PATH", "~/.brainxio/adhd")).expanduser()
    if not base_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for channel_dir in sorted(base_dir.iterdir()):
        if not channel_dir.is_dir():
            continue
        bus_file = channel_dir / "bus.jsonl"
        if not bus_file.exists():
            continue

        try:
            bus_stat = bus_file.stat()
            size = bus_stat.st_size
            mtime = datetime.fromtimestamp(bus_stat.st_mtime, tz=UTC).isoformat()
        except OSError:
            continue

        slug = channel_dir.name
        line_count = 0
        last_activity = None
        agents_seen: set[str] = set()

        try:
            with bus_file.open("r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    line_count += 1
                    try:
                        msg = json.loads(line)
                        ts = msg.get("timestamp")
                        if isinstance(ts, str):
                            last_activity = ts
                        a = msg.get("agent_id")
                        if isinstance(a, str):
                            agents_seen.add(a)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            continue

        results.append(
            {
                "slug": slug,
                "message_count": line_count,
                "last_activity": last_activity or mtime,
                "file_size_bytes": size,
                "agents_seen": sorted(agents_seen),
                "agent_count": len(agents_seen),
                "bus_path": str(bus_file),
            }
        )

    return results
