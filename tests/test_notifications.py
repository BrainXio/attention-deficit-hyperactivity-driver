"""Unit tests for adhd.notifications."""

from __future__ import annotations

import os
from unittest.mock import Mock, patch

from adhd.notifications import send_notification

# ---------------------------------------------------------------------------
# notify-send tests
# ---------------------------------------------------------------------------


def test_send_notification_notify_send_success() -> None:
    with patch("adhd.notifications._try_notify_send", return_value=True) as mock_ns:
        result = send_notification("Test Title", "Test Body")
        assert result is True
        mock_ns.assert_called_once_with("Test Title", "Test Body", "normal")


def test_send_notification_falls_back_to_telegram() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=False),
        patch("adhd.notifications._try_telegram", return_value=True) as mock_tg,
    ):
        result = send_notification("Test Title", "Test Body")
        assert result is True
        mock_tg.assert_called_once_with("Test Title", "Test Body")


def test_send_notification_both_fail() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=False),
        patch("adhd.notifications._try_telegram", return_value=False),
    ):
        result = send_notification("Test Title", "Test Body")
        assert result is False


# ---------------------------------------------------------------------------
# Env var: ADHD_NOTIFY_URGENCY
# ---------------------------------------------------------------------------


def test_urgency_env_var_default() -> None:
    with patch("adhd.notifications._try_notify_send", return_value=True) as mock_ns:
        send_notification("Test")
        mock_ns.assert_called_once_with("Test", "", "normal")


def test_urgency_env_var_custom() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=True) as mock_ns,
        patch.dict(os.environ, {"ADHD_NOTIFY_URGENCY": "critical"}, clear=False),
    ):
        send_notification("Test", "Body", "low")
        mock_ns.assert_called_once_with("Test", "Body", "critical")


# ---------------------------------------------------------------------------
# notify-send subprocess (integration-style)
# ---------------------------------------------------------------------------


def test_notify_send_subprocess_success() -> None:
    with (
        patch("subprocess.run") as mock_run,
        patch.dict(os.environ, {}, clear=True),
    ):
        mock_run.return_value = Mock(returncode=0)
        result = send_notification("Test", "Body", "normal")
        assert result is True
        mock_run.assert_called_once_with(
            ["notify-send", "-u", "normal", "Test", "Body"],
            capture_output=True,
            check=True,
            timeout=5,
        )


def test_notify_send_not_found_falls_back() -> None:
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch("adhd.notifications._try_telegram", return_value=True) as mock_tg,
        patch.dict(os.environ, {}, clear=True),
    ):
        result = send_notification("Test", "Body")
        assert result is True
        mock_tg.assert_called_once()


# ---------------------------------------------------------------------------
# Telegram tests
# ---------------------------------------------------------------------------


def test_telegram_missing_token() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=False),
        patch.dict(os.environ, {}, clear=True),
    ):
        result = send_notification("Test")
        assert result is False


def test_telegram_missing_chat_id() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=False),
        patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok"}, clear=True),
    ):
        result = send_notification("Test")
        assert result is False


def test_telegram_sends_request() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=False),
        patch("adhd.notifications._try_telegram", return_value=True) as mock_tg,
    ):
        result = send_notification("Test Title", "Test Body")
        assert result is True
        mock_tg.assert_called_once_with("Test Title", "Test Body")


def test_telegram_network_error_graceful() -> None:
    with (
        patch("adhd.notifications._try_notify_send", return_value=False),
        patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"},
            clear=True,
        ),
        patch("urllib.request.urlopen", side_effect=OSError("network down")),
    ):
        result = send_notification("Test")
        assert result is False
