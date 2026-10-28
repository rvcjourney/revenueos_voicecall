"""
app/core/mail_inbox.py — read new message headers from an org's mailbox over
IMAP (SSL, port 993), so replies to lead emails can be counted.

Read-only: INBOX is opened readonly and fetched with BODY.PEEK, so nothing is
marked as read in the customer's mailbox. Only headers are fetched, never bodies.
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import re
import ssl
from dataclasses import dataclass
from datetime import date, timedelta
from email.utils import getaddresses

from app.core.net_guard import assert_public_host

IMAP_PORT = 993
_TIMEOUT = 30
_FIRST_RUN_DAYS = 3      # first check after setup looks this far back
_MAX_PER_RUN = 200
_HEADERS = "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])"
_MSGID_RE = re.compile(r"<[^<>\s]+>")


class InboxError(Exception):
    pass


@dataclass(frozen=True)
class InboxMessage:
    uid: int
    message_id: str
    thread_ids: tuple[str, ...]   # In-Reply-To + References: the Message-IDs this answers
    from_email: str
    subject: str
    date: str


def _parse(uid: int, raw: bytes) -> InboxMessage:
    h = email.message_from_bytes(raw, policy=email.policy.default)
    addrs = getaddresses([str(h.get("From", ""))])
    return InboxMessage(
        uid=uid,
        message_id=str(h.get("Message-ID", "")).strip(),
        thread_ids=tuple(_MSGID_RE.findall(f"{h.get('In-Reply-To', '')} {h.get('References', '')}")),
        from_email=(addrs[0][1] if addrs else "").strip().lower(),
        subject=str(h.get("Subject", ""))[:300],
        date=str(h.get("Date", ""))[:100],
    )


def fetch_new_messages(host: str, username: str, password: str, last_uid: int | None) -> tuple[list[InboxMessage], int | None]:
    """Headers of INBOX messages newer than last_uid (or from the last few days
    on the first run). Returns (messages, new last_uid). Blocking — run in a thread.
    shortcut: ignores UIDVALIDITY changes (mailbox rebuilt); dedupe by Message-ID downstream covers re-reads."""
    assert_public_host(host, IMAP_PORT, "IMAP server")
    try:
        with imaplib.IMAP4_SSL(host, IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=_TIMEOUT) as imap:
            imap.login(username, password)
            imap.select("INBOX", readonly=True)
            if last_uid is None:
                since = (date.today() - timedelta(days=_FIRST_RUN_DAYS)).strftime("%d-%b-%Y")
                _, data = imap.uid("SEARCH", None, "SINCE", since)
            else:
                _, data = imap.uid("SEARCH", None, "UID", f"{last_uid + 1}:*")
            uids = sorted(int(u) for u in (data[0] or b"").split())
            # "N:*" always matches the newest message even when its UID is below N.
            uids = [u for u in uids if last_uid is None or u > last_uid][:_MAX_PER_RUN]
            if not uids:
                return [], last_uid
            _, parts = imap.uid("FETCH", ",".join(map(str, uids)), _HEADERS)
    except imaplib.IMAP4.error as exc:
        raise InboxError(f"Mailbox login or read failed: {str(exc)[:200]}") from exc
    except (OSError, ssl.SSLError) as exc:
        raise InboxError(f"Could not connect to {host}:{IMAP_PORT} ({type(exc).__name__})") from exc

    messages = []
    for part in parts:
        if not isinstance(part, tuple):
            continue
        m = re.search(rb"UID (\d+)", part[0])
        if m:
            messages.append(_parse(int(m.group(1)), part[1]))
    return messages, max(uids)
