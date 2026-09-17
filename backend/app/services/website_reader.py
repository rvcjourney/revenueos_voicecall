"""
website_reader.py — fetch a prospect's homepage and boil it down to plain text.

Used by Prime Calling (app/services/prime_prompt.py) so the LLM knows what the
contact's company actually does. The URL comes straight from an uploaded CSV,
i.e. it is untrusted input fetched from OUR server — so every hop (including
redirects) is resolved and rejected unless all its IPs are public internet
addresses (blocks localhost, private LANs, cloud metadata 169.254.169.254, …).

Never raises: any failure returns "" and the call proceeds without it.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
import structlog

log = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 8.0
_MAX_BYTES = 500_000
_MAX_REDIRECTS = 3
_MAX_SUMMARY_CHARS = 3000
_CACHE_TTL_SECONDS = 24 * 3600
_FAILED_CACHE_TTL_SECONDS = 3600  # retry unreachable sites sooner
_CACHE_PREFIX = "motm:prime:site:"
_USER_AGENT = "Mozilla/5.0 (compatible; MOTMVoiceBot/1.0)"


class UnsafeUrlError(ValueError):
    pass


def normalize_url(raw: str) -> str | None:
    """'acme.com' → 'https://acme.com'. Returns None for anything not http(s)."""
    url = (raw or "").strip()
    if not url or len(url) > 500 or any(ch.isspace() for ch in url):
        return None
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    try:
        parts.port  # raises ValueError on garbage like "javascript:alert(1)" → port "alert(1)"
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return None
    return url


async def _assert_public_host(host: str, port: int) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"cannot resolve {host}") from exc
    if not infos:
        raise UnsafeUrlError(f"cannot resolve {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise UnsafeUrlError(f"{host} resolves to non-public address")


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._in_title = False
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = {k.lower(): (v or "") for k, v in attrs}
            if a.get("name", "").lower() in ("description", "og:description") or \
                    a.get("property", "").lower() == "og:description":
                self.description = self.description or a.get("content", "").strip()
        if tag in self._SKIP and tag != "head":
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and tag != "head" and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.chunks.append(text)


def html_to_summary(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    body = re.sub(r"\s+", " ", " ".join(parser.chunks)).strip()
    parts = []
    title = re.sub(r"\s+", " ", parser.title).strip()
    if title:
        parts.append(f"Title: {title}")
    if parser.description:
        parts.append(f"Description: {parser.description}")
    if body:
        parts.append(f"Page text: {body}")
    return "\n".join(parts)[:_MAX_SUMMARY_CHARS]


async def _fetch(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise UnsafeUrlError("unsupported scheme")
            await _assert_public_host(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))

            async with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return ""
                    url = urljoin(url, location)
                    continue
                if resp.status_code != 200:
                    return ""
                if "html" not in resp.headers.get("content-type", "").lower():
                    return ""
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) >= _MAX_BYTES:
                        break
                return bytes(buf[:_MAX_BYTES]).decode(resp.encoding or "utf-8", errors="replace")
    return ""  # too many redirects


async def fetch_site_summary(raw_url: str) -> str:
    """Return a short plain-text summary of the page at raw_url, or "" on any failure."""
    url = normalize_url(raw_url)
    if not url:
        return ""

    cache_key = _CACHE_PREFIX + hashlib.sha256(url.lower().rstrip("/").encode()).hexdigest()
    redis = None
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        redis = None  # Redis down — just fetch without caching

    try:
        summary = html_to_summary(await _fetch(url))
    except Exception as exc:
        log.info("website_fetch_failed", url=url, error=str(exc)[:200])
        summary = ""

    if redis is not None:
        try:
            await redis.set(cache_key, summary, ex=_CACHE_TTL_SECONDS if summary else _FAILED_CACHE_TTL_SECONDS)
        except Exception:
            pass
    return summary
