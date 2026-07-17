"""QQ email client: send via SMTP, read/search via IMAP.

QQ email requires an authorization code (授权码) for both SMTP and IMAP.
Generate it in QQ Mail Settings → Account → POP3/IMAP/SMTP service.

SMTP: smtp.qq.com:465 (SSL)
IMAP: imap.qq.com:993 (SSL)
"""

import email
import imaplib
import logging
import smtplib
from email.header import decode_header
from email.message import EmailMessage
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_IMAP_TIMEOUT = 30
_SMTP_TIMEOUT = 30

# QQ mail IMAP folders
KNOWN_FOLDERS = {
    "INBOX": "INBOX",
    "收件箱": "INBOX",
    "已发送": "已发送",
    "垃圾箱": "垃圾箱",
    "草稿箱": "草稿箱",
    "已删除": "已删除",
}


def _resolve_folder(folder: str) -> str:
    """Map Chinese folder names to actual IMAP folder names."""
    return KNOWN_FOLDERS.get(folder, folder)


def _check_config() -> None:
    """Raise ConnectionError if QQ email is not configured."""
    if not settings.qq_email_address or not settings.qq_email_auth_code:
        raise ConnectionError(
            "QQ邮箱未配置。请在设置中心填写邮箱地址和 QQ 邮箱授权码。\n"
            "授权码获取：QQ邮箱 → 设置 → 账户 → POP3/IMAP/SMTP服务 → 生成授权码"
        )


def _get_imap() -> imaplib.IMAP4_SSL:
    """Open an authenticated IMAP connection to QQ."""
    _check_config()
    try:
        conn = imaplib.IMAP4_SSL("imap.qq.com", 993, timeout=_IMAP_TIMEOUT)
        conn.login(settings.qq_email_address, settings.qq_email_auth_code)
        return conn
    except (OSError, imaplib.IMAP4.error) as exc:
        logger.warning("QQ IMAP connection failed: %s", exc)
        raise ConnectionError(
            "无法连接或登录 QQ 邮箱，请检查网络、邮箱地址和授权码。"
        ) from exc


def _get_smtp() -> smtplib.SMTP_SSL:
    """Open an authenticated SMTP connection to QQ."""
    _check_config()
    try:
        conn = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=_SMTP_TIMEOUT)
        conn.login(settings.qq_email_address, settings.qq_email_auth_code)
        return conn
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("QQ SMTP connection failed: %s", exc)
        raise ConnectionError(
            "无法连接或登录 QQ 邮箱，请检查网络、邮箱地址和授权码。"
        ) from exc


def _decode_email_header(header_value: str | None) -> str:
    """Decode an encoded email header into plain text.

    Handles =?UTF-8?B?...?= and =?GBK?B?...?= encodings.
    """
    if not header_value:
        return ""
    try:
        decoded_parts = decode_header(header_value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)
    except Exception:
        return str(header_value)


def _parse_email_summary(raw_email: bytes) -> dict[str, Any]:
    """Parse raw IMAP email bytes into a summary dict.

    Returns: {subject, from_, date, snippet}
    """
    msg = email.message_from_bytes(raw_email)

    subject = _decode_email_header(msg.get("Subject", ""))
    from_ = _decode_email_header(msg.get("From", ""))
    date = msg.get("Date", "")

    # Extract plain text body for snippet (~100 chars)
    snippet = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and "attachment" not in (part.get("Content-Disposition", "") or ""):
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        snippet = payload.decode(charset, errors="replace")[:150]
                    break
                # Fallback to text/html if no plain text found
                if ct == "text/html" and not snippet:
                    payload = part.get_payload(decode=True)
                    if payload:
                        snippet = payload.decode("utf-8", errors="replace")[:150]
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                snippet = payload.decode(charset, errors="replace")[:150]
    except Exception:
        pass

    snippet = snippet.replace("\r\n", " ").replace("\n", " ").strip()
    if not snippet:
        snippet = "(无正文内容)"

    return {
        "subject": subject or "(无主题)",
        "from": from_ or "(未知发件人)",
        "date": date or "(未知时间)",
        "snippet": snippet,
    }


def send_email(
    to_address: str,
    subject: str,
    body: str,
) -> str:
    """Send an email via QQ SMTP.

    Args:
        to_address: Recipient email address.
        subject: Email subject (UTF-8).
        body: Email body text.

    Returns:
        Confirmation string.

    Raises:
        ConnectionError: If QQ email is not configured.
        smtplib.SMTPException: If sending fails.
    """
    msg = EmailMessage()
    msg["From"] = settings.qq_email_address
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with _get_smtp() as server:
        server.send_message(msg)

    logger.info("Email sent to %s: %s", to_address, subject[:60])
    return f"✅ 邮件已发送至 {to_address}（主题：{subject[:60]}）"


def list_emails(folder: str = "INBOX", max_results: int = 10) -> str:
    """List recent emails from a QQ mail folder.

    Args:
        folder: IMAP folder name. Common: "INBOX" (收件箱), "已发送", "垃圾箱".
        max_results: Number of recent emails to return (default 10).

    Returns:
        Formatted email list string.
    """
    imap_folder = _resolve_folder(folder)

    with _get_imap() as conn:
        status, _ = conn.select(imap_folder)
        if status != "OK":
            return f"❌ 无法打开文件夹「{folder}」，请检查文件夹名称是否正确。"

        _, data = conn.search(None, "ALL")
        if not data or not data[0]:
            return f"📭 文件夹「{folder}」中没有邮件。"

        all_ids = data[0].split()
        # Get most recent N messages (last N in the list)
        recent_ids = all_ids[-max_results:]

        lines = [f"📧 **{folder}** 最近 {len(recent_ids)} 封邮件："]
        for msg_id in reversed(recent_ids):
            try:
                _, msg_data = conn.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                parsed = _parse_email_summary(raw)
                lines.append(
                    f"  [{msg_id.decode()}] 📨 **{parsed['subject'][:60]}**"
                )
                lines.append(f"       发件人：{parsed['from'][:40]}")
                lines.append(f"       摘要：{parsed['snippet'][:80]}")
            except Exception:
                continue

        return "\n".join(lines)


def search_emails(
    keyword: str,
    folder: str = "INBOX",
    max_results: int = 10,
) -> str:
    """Search emails by subject keyword.

    Note: QQ IMAP SEARCH does not support UTF-8 subjects natively.
    Chinese keyword search may have limited accuracy.

    Args:
        keyword: Search keyword (best results with ASCII/English).
        folder: IMAP folder to search.
        max_results: Max results to return (default 10).

    Returns:
        Formatted search results string.
    """
    imap_folder = _resolve_folder(folder)

    with _get_imap() as conn:
        status, _ = conn.select(imap_folder)
        if status != "OK":
            return f"❌ 无法打开文件夹「{folder}」，请检查文件夹名称是否正确。"

        # Try searching with the keyword
        status, data = conn.search(None, f'SUBJECT "{keyword}"')

        if status != "OK" or not data or not data[0]:
            # Try a broader search on the text body
            try:
                status, data = conn.search(None, f'TEXT "{keyword}"')
            except Exception:
                pass

        if status != "OK" or not data or not data[0]:
            return f"🔍 在「{folder}」中未找到包含「{keyword}」的邮件。"

        msg_ids = data[0].split()[-max_results:]

        lines = [f"🔍 在「{folder}」中找到 {len(msg_ids)} 封包含「{keyword}」的邮件："]
        for msg_id in reversed(msg_ids):
            try:
                _, msg_data = conn.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                parsed = _parse_email_summary(raw)
                lines.append(
                    f"  [{msg_id.decode()}] 📨 **{parsed['subject'][:60]}**"
                )
                lines.append(f"       发件人：{parsed['from'][:40]}")
            except Exception:
                continue

        return "\n".join(lines)


def read_email(message_id: int, folder: str = "INBOX") -> str:
    """Read the full content of a specific email.

    Args:
        message_id: IMAP sequence number (visible in list/search results).
        folder: IMAP folder containing the email.

    Returns:
        Full email content string (headers + body).
    """
    imap_folder = _resolve_folder(folder)

    with _get_imap() as conn:
        status, _ = conn.select(imap_folder)
        if status != "OK":
            return f"❌ 无法打开文件夹「{folder}」。"

        status, msg_data = conn.fetch(str(message_id), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            return f"❌ 未找到 ID 为 {message_id} 的邮件。"

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        # Decode headers
        subject = _decode_email_header(msg.get("Subject", ""))
        from_ = _decode_email_header(msg.get("From", ""))
        to_ = _decode_email_header(msg.get("To", ""))
        date = msg.get("Date", "")

        # Extract body text
        body_text = ""
        is_truncated = False
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    disposition = part.get("Content-Disposition", "") or ""
                    if "attachment" in disposition:
                        continue
                    if ct == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_text = payload.decode(charset, errors="replace")
                        break
                    # Fallback: first text/html
                    if ct == "text/html" and not body_text:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_text = payload.decode("utf-8", errors="replace")
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")
        except Exception:
            body_text = "(无法解析邮件正文)"

        MAX_BODY = 3000
        if len(body_text) > MAX_BODY:
            body_text = body_text[:MAX_BODY]
            is_truncated = True

        result = (
            f"📧 **{subject}**\n"
            f"   发件人：{from_}\n"
            f"   收件人：{to_}\n"
            f"   时间：{date}\n"
            f"   ── 正文 ──\n"
            f"{body_text.strip()}"
        )
        if is_truncated:
            result += "\n\n...(邮件内容过长，已截断)"
        return result
