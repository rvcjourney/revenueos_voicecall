"""
app/core/email_sender.py — send a plain-text email (optionally with attachments)
through the org's own mailbox (set by an admin in Settings → Integrations,
stored on Organization). The sender email is also the SMTP login.

Used by POST /api/leads/{id}/email, the automatic brochure email
(app/workers/tasks/brochure.py) and the admin "Send test email" button.
Standard library only: smtplib runs in a worker thread so the API stays async.
No Reply-To: replies land in the same mailbox, where the IMAP reader counts them.
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.core.crypto import decrypt_value
from app.core.net_guard import assert_public_host

# Encrypted only. The security choice fixes the port, so admins never type one.
PORT_FOR_SECURITY = {"starttls": 587, "ssl": 465}
_TIMEOUT = 20


@dataclass(frozen=True)
class Attachment:
    filename: str
    data: bytes
    content_type: str  # e.g. "application/pdf"


class EmailSendError(Exception):
    pass


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str


def smtp_configured(org) -> bool:
    return bool(org and org.smtp_host and org.smtp_port and org.smtp_from_email and org.smtp_security)


def org_smtp_config(org) -> SmtpConfig | None:
    """None until the org's admin has saved a mail server."""
    if not smtp_configured(org):
        return None
    return SmtpConfig(
        host=org.smtp_host, port=org.smtp_port, security=org.smtp_security,
        username=org.smtp_username or "", password=decrypt_value(org.smtp_password) if org.smtp_password else "",
        from_email=org.smtp_from_email, from_name=org.smtp_from_name or "",
    )


def build_message(
    cfg: SmtpConfig, *, to: str, subject: str, body: str, attachments: list[Attachment] | None = None,
) -> EmailMessage:
    """Raises EmailSendError if a header would contain a line break (header injection)."""
    msg = EmailMessage()
    try:
        msg["From"] = formataddr((cfg.from_name, cfg.from_email))
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=cfg.from_email.rsplit("@", 1)[-1])
    except ValueError:
        raise EmailSendError("The subject or an email address contains characters that aren't allowed")
    msg.set_content(body)
    for a in attachments or []:
        maintype, _, subtype = a.content_type.partition("/")
        msg.add_attachment(a.data, maintype=maintype or "application", subtype=subtype or "octet-stream",
                           filename=a.filename)
    return msg


def _send_sync(cfg: SmtpConfig, msg: EmailMessage) -> None:
    ctx = ssl.create_default_context()
    if cfg.security == "ssl":
        server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=_TIMEOUT, context=ctx)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=_TIMEOUT)
    with server:
        if cfg.security == "starttls":
            server.starttls(context=ctx)
        if cfg.username:
            try:
                server.login(cfg.username, cfg.password)
            except smtplib.SMTPAuthenticationError:
                raise
            except smtplib.SMTPException as exc:
                # Some servers just hang up on a bad password instead of answering 535.
                raise smtplib.SMTPAuthenticationError(535, str(exc).encode()) from exc
        server.send_message(msg)


async def send_email(
    cfg: SmtpConfig, *, to: str, subject: str, body: str, attachments: list[Attachment] | None = None,
) -> str:
    """Returns the Message-ID. Raises EmailSendError with a message the user can act on."""
    msg = build_message(cfg, to=to, subject=subject, body=body, attachments=attachments)
    try:
        # Re-checked at send time, not only when saved: DNS can change.
        await asyncio.to_thread(assert_public_host, cfg.host, cfg.port, "Mail server")
        await asyncio.to_thread(_send_sync, cfg, msg)
    except EmailSendError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise EmailSendError(
            "Your mail server rejected the username or password. Gmail and Outlook need an app password, "
            "not your normal one."
        )
    except smtplib.SMTPRecipientsRefused:
        raise EmailSendError(f"Your mail server refused the address {to}")
    except smtplib.SMTPSenderRefused:
        raise EmailSendError(f"Your mail server won't send as {cfg.from_email}. Use the address you log in with.")
    except (ssl.SSLError, smtplib.SMTPNotSupportedError):
        raise EmailSendError("Secure connection failed. Try the other security option (STARTTLS or SSL).")
    except smtplib.SMTPDataError as exc:
        raise EmailSendError(f"Your mail server refused the message ({exc.smtp_code}), e.g. the attachment is too large")
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"Could not send through {cfg.host}:{cfg.port} ({type(exc).__name__})")
    except Exception as exc:  # e.g. ValidationError from the host guard
        raise EmailSendError(str(exc) or type(exc).__name__)
    return msg["Message-ID"]
