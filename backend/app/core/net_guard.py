"""
app/core/net_guard.py — SSRF guard for hosts that tenants type in (webhook
URLs, SMTP servers): the server must only ever connect to public addresses.
"""
from __future__ import annotations

import ipaddress
import socket

from app.core.exceptions import ValidationError


def assert_public_host(host: str, port: int, label: str) -> None:
    """Every address `host` resolves to must be public (not loopback, private,
    link-local/cloud-metadata...). `label` names the field in error messages.
    shortcut: resolved at check time only (DNS rebinding between check and connect), upgrade if untrusted tenants matter."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise ValidationError(f"{label} host could not be resolved")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValidationError(f"{label} must point to a public address")
