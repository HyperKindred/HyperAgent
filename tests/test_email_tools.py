"""Tests for QQ email tools (mocked IMAP/SMTP connections)."""

from unittest.mock import MagicMock, patch

import pytest

from app.agent.tools import (
    list_emails_tool,
    read_email_tool,
    search_emails_tool,
    send_email_tool,
)


@pytest.fixture(autouse=True)
def setup_email_config():
    """Set fake QQ email credentials so config validation passes."""
    import app.config
    app.config.settings.qq_email_address = "test@qq.com"
    app.config.settings.qq_email_auth_code = "fake_auth_code"


def _make_imap_mock():
    """Create a properly configured IMAP mock.

    The IMAP connection is used via ``with _get_imap() as conn:``.
    ``_get_imap()`` returns the IMAP4_SSL instance directly, and
    Python's ``with`` calls ``__enter__`` on it.  By default MagicMock's
    ``__enter__`` returns a *different* MagicMock, so we wire it to
    return itself.
    """
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    return mock_conn


# ── send_email_tool ───────────────────────────────────────────────────


class TestSendEmailTool:
    @patch("app.email.client.smtplib.SMTP_SSL")
    def test_send_basic(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_conn

        result = send_email_tool.invoke({
            "to_address": "friend@qq.com",
            "subject": "Hello",
            "body": "Test message",
        })
        assert "已发送" in result
        mock_conn.send_message.assert_called_once()

    @patch("app.email.client.smtplib.SMTP_SSL")
    def test_send_chinese(self, mock_smtp):
        """Test sending email with Chinese subject and body."""
        mock_conn = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_conn

        result = send_email_tool.invoke({
            "to_address": "friend@qq.com",
            "subject": "周末聚会",
            "body": "周六下午3点见",
        })
        assert "已发送" in result

    def test_send_missing_config(self):
        """Should raise ConnectionError when email not configured."""
        import app.config
        app.config.settings.qq_email_address = ""
        app.config.settings.qq_email_auth_code = ""

        import app.email.client
        with pytest.raises(ConnectionError):
            app.email.client.send_email(
                to_address="friend@qq.com",
                subject="Test",
                body="Test",
            )


# ── list_emails_tool ─────────────────────────────────────────────────


class TestListEmailsTool:
    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_list_inbox(self, mock_imap_class):
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"5"])
        mock_conn.search.return_value = ("OK", [b"1 2 3 4 5"])

        raw_email = (
            b"From: sender@qq.com\r\n"
            b"To: test@qq.com\r\n"
            b"Subject: Test Subject\r\n"
            b"Date: Wed, 17 Jun 2026 10:00:00 +0800\r\n"
            b"\r\n"
            b"Hello, this is a test email body."
        )
        mock_conn.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        result = list_emails_tool.invoke({})
        assert "收件箱" in result or "INBOX" in result
        assert "Test Subject" in result
        mock_conn.select.assert_called_once()

    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_list_empty(self, mock_imap_class):
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"0"])
        mock_conn.search.return_value = ("OK", [b""])

        result = list_emails_tool.invoke({})
        assert "没有" in result

    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_list_chinese_folder(self, mock_imap_class):
        """Test listing emails in a Chinese-named folder."""
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"0"])
        mock_conn.search.return_value = ("OK", [b""])

        result = list_emails_tool.invoke({"folder": "已发送"})
        assert "没有" in result
        # Verify the folder name was passed to select
        call_args = mock_conn.select.call_args[0]
        assert call_args[0] == "已发送"


# ── search_emails_tool ────────────────────────────────────────────────


class TestSearchEmailsTool:
    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_search_with_results(self, mock_imap_class):
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.search.return_value = ("OK", [b"1 2 3"])

        raw_email = (
            b"From: sender@qq.com\r\n"
            b"To: test@qq.com\r\n"
            b"Subject: Meeting tomorrow\r\n"
            b"Date: Wed, 17 Jun 2026 10:00:00 +0800\r\n"
            b"\r\n"
            b"Let's meet at 3pm."
        )
        mock_conn.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        result = search_emails_tool.invoke({
            "keyword": "meeting",
        })
        assert "Meeting" in result
        assert "找到" in result

    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_search_no_results(self, mock_imap_class):
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.search.return_value = ("OK", [b""])

        result = search_emails_tool.invoke({
            "keyword": "nonexistent",
        })
        assert "未找到" in result or "没有" in result


# ── read_email_tool ───────────────────────────────────────────────────


class TestReadEmailTool:
    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_read_email(self, mock_imap_class):
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"1"])

        raw_email = (
            b"From: sender@qq.com\r\n"
            b"To: test@qq.com\r\n"
            b"Subject: Important Meeting\r\n"
            b"Date: Wed, 17 Jun 2026 14:00:00 +0800\r\n"
            b"\r\n"
            b"Dear team,\r\n\r\n"
            b"This is the meeting agenda:\r\n"
            b"1. Project update\r\n"
            b"2. Budget review\r\n"
            b"3. Next steps\r\n\r\n"
            b"Best,\r\nManager"
        )
        mock_conn.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        result = read_email_tool.invoke({
            "message_id": 1,
        })
        assert "Important Meeting" in result
        assert "sender@qq.com" in result
        assert "Project update" in result or "agenda" in result

    @patch("app.email.client.imaplib.IMAP4_SSL")
    def test_read_email_not_found(self, mock_imap_class):
        mock_conn = _make_imap_mock()
        mock_imap_class.return_value = mock_conn
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.fetch.return_value = ("BAD", None)

        result = read_email_tool.invoke({
            "message_id": 999,
        })
        assert "未找到" in result
