from __future__ import annotations

import email
import html
import imaplib
import re
import ssl
from datetime import date
from email.header import decode_header, make_header
from email.message import Message
from email.policy import default
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from .config import Config


def _header(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError):
        return value


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return html.unescape(value)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if self.current_href is not None and tag.lower() == "img" and values.get("alt"):
            self.current_text.append(values["alt"] or "")
            return
        if tag.lower() != "a" or self.current_href is not None:
            return
        self.current_href = values.get("href")
        self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            text = re.sub(r"\s+", " ", " ".join(self.current_text)).strip()
            self.links.append((text, self.current_href))
            self.current_href = None
            self.current_text = []


_TLDR_ARTICLE_LABEL = re.compile(
    r"\((?:\d+\s+(?:minute|hour)s?\s+read|website|github repo)\)\s*$",
    re.IGNORECASE,
)


def _links(message: Message, limit: int = 60) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() != "text/html":
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        parser = _LinkParser()
        parser.feed(content)
        for label, url in parser.links:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            label = label.strip() or "Read article"
            # TLDR editorial links have a stable reading-time/type suffix. A strict
            # allowlist excludes sponsors, jobs, referrals, account links, and CTAs.
            if not _TLDR_ARTICLE_LABEL.search(label) or url in seen:
                continue
            seen.add(url)
            found.append({"label": label[:300], "url": url[:4000]})
            if len(found) >= limit:
                return found
    return found


def _body(message: Message, max_chars: int) -> str:
    plain: list[str] = []
    rich: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        (plain if content_type == "text/plain" else rich).append(content)
    text = "\n".join(plain) if plain else _html_to_text("\n".join(rich))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def parse_message(uid: str, raw: bytes, max_body_chars: int) -> dict[str, Any]:
    message = email.message_from_bytes(raw, policy=default)
    received_at = None
    if message.get("Date"):
        try:
            received_at = parsedate_to_datetime(message["Date"]).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    return {
        "uid": uid,
        "message_id": str(message.get("Message-ID", "")) or None,
        "received_at": received_at,
        "sender": _header(message.get("From"), "Unknown sender"),
        "subject": _header(message.get("Subject"), "(No subject)"),
        "body": _body(message, max_body_chars),
        "links": _links(message),
    }


def quote_mailbox(value: str) -> str:
    """Quote an IMAP mailbox name so spaces and quotes remain one argument."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class ProtonBridgeReader:
    def __init__(self, config: Config):
        self.config = config

    def fetch_day(self, target: date) -> list[dict[str, Any]]:
        cfg = self.config
        cfg.require_job_secrets()
        client = self._connect()
        try:
            status, _ = client.select(quote_mailbox(cfg.imap_mailbox), readonly=True)
            if status != "OK":
                raise RuntimeError(f"Could not open IMAP mailbox {cfg.imap_mailbox!r}")
            start = target.strftime("%d-%b-%Y")
            end = date.fromordinal(target.toordinal() + 1).strftime("%d-%b-%Y")
            status, data = client.uid("search", None, "SINCE", start, "BEFORE", end)
            if status != "OK":
                raise RuntimeError("IMAP search failed")
            uids = data[0].split()[: cfg.max_emails]
            messages: list[dict[str, Any]] = []
            for uid_bytes in uids:
                uid = uid_bytes.decode("ascii", errors="replace")
                status, payload = client.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK" or not payload:
                    continue
                raw = next(
                    (item[1] for item in payload if isinstance(item, tuple) and isinstance(item[1], bytes)),
                    None,
                )
                if raw is not None:
                    messages.append(parse_message(uid, raw, cfg.max_body_chars))
            return messages
        finally:
            self._logout(client)

    def check_connection(self) -> None:
        self.config.require_job_secrets()
        client = self._connect()
        try:
            status, _ = client.select(quote_mailbox(self.config.imap_mailbox), readonly=True)
            if status != "OK":
                raise RuntimeError(f"Could not open IMAP mailbox {self.config.imap_mailbox!r}")
        finally:
            self._logout(client)

    def list_mailboxes(self) -> list[str]:
        self.config.require_job_secrets()
        client = self._connect()
        try:
            status, rows = client.list()
            if status != "OK":
                raise RuntimeError("Could not list IMAP mailboxes")
            names: list[str] = []
            for row in rows:
                if not isinstance(row, bytes):
                    continue
                text = row.decode("utf-8", errors="replace")
                match = re.match(r'^\([^)]*\)\s+"[^"]*"\s+(.+)$', text)
                value = match.group(1) if match else text
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1].replace(r'\"', '"').replace(r'\\', '\\')
                names.append(value)
            return names
        finally:
            self._logout(client)

    def _connect(self) -> imaplib.IMAP4:
        cfg = self.config
        context = ssl.create_default_context()
        if not cfg.imap_verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        if cfg.imap_security == "ssl":
            client: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                cfg.imap_host, cfg.imap_port, ssl_context=context
            )
        else:
            client = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
            if cfg.imap_security == "starttls":
                client.starttls(ssl_context=context)
        client.login(cfg.imap_username, cfg.imap_password)
        return client

    @staticmethod
    def _logout(client: imaplib.IMAP4) -> None:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
