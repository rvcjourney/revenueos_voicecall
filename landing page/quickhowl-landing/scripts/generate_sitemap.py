#!/usr/bin/env python3
"""
generate_sitemap.py — Builds sitemap.xml for quickhowl.com.

Combines two sources of pages:
  1. The landing site's own static routes (home, privacy policy, terms of
     service) -- hardcoded below since there are only a handful and they
     rarely change.
  2. Every pSEO page currently sitting in the "Remote path" the pSEO tool
     SFTPs .html files into (see the Caddy /blog/* handle_path block in
     /etc/caddy/Caddyfile) -- scanned fresh on every run, so newly published
     or removed pages are picked up automatically without a code deploy.

Run on a schedule (cron) on the VPS, NOT as part of the landing site's own
Docker build -- the pSEO directory lives directly on the host filesystem
and changes independently of any git deploy. See the accompanying setup
instructions for the cron entry and the Caddy block that serves the output.

Also writes /blog/index.html (a plain list of every pSEO page) into the
pSEO directory, so the articles are linked from somewhere a crawler can
follow -- Google treats sitemap-only pages as low priority.

Writes atomically (temp file + rename) so Caddy never serves a half-written
file if this runs while something else is mid-write.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

BASE_URL = "https://quickhowl.com"

# (path relative to BASE_URL, changefreq, priority) -- lastmod for these is
# just "today" on every run since there's no cheap way to know when the
# landing site's own content last changed from this script's vantage point;
# good enough for a marketing site's static pages.
STATIC_PAGES = [
    ("/", "weekly", "1.0"),
    ("/privacy-policy", "yearly", "0.3"),
    ("/terms-of-service", "yearly", "0.3"),
]


def _url_entry(loc: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


def _pseo_pages(pseo_dir: Path) -> list[Path]:
    # index.html is the blog index this script writes itself, not a pSEO page
    return [f for f in sorted(pseo_dir.glob("*.html")) if f.name != "index.html"]


def _page_meta(html_file: Path) -> tuple[str, str]:
    text = html_file.read_text(encoding="utf-8", errors="replace")
    title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    desc = re.search(r'<meta\s+name="description"\s+content="(.*?)"', text, re.S | re.I)
    fallback = html_file.stem.replace("-", " ").capitalize()
    return (
        html.unescape(title.group(1).strip()) if title else fallback,
        html.unescape(desc.group(1).strip()) if desc else "",
    )


def build_blog_index(pseo_dir: Path) -> str:
    items = []
    for html_file in _pseo_pages(pseo_dir):
        title, desc = _page_meta(html_file)
        items.append(
            f'<li><a href="/blog/{escape(html_file.name)}">{escape(title)}</a>'
            + (f"<p>{escape(desc)}</p>" if desc else "")
            + "</li>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Blog — QuickHowl AI Voice Calling</title>
<meta name="description" content="Guides on AI voice agents, outbound sales calling, appointment reminders and customer support automation in Hindi, English and Indian languages." />
<link rel="canonical" href="{BASE_URL}/blog/" />
<link rel="icon" type="image/png" href="/favicon.png" />
<style>
  body {{ margin: 0; background: #0b0d12; color: #e6e8ee; font: 16px/1.6 Inter, system-ui, sans-serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 32px 16px 64px; }}
  .top {{ font-size: 14px; }}
  h1 {{ font-size: 32px; line-height: 1.2; margin: 24px 0 8px; }}
  .lead {{ color: #9aa1b2; margin: 0 0 32px; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{ padding: 16px 0; border-top: 1px solid #23262f; }}
  a {{ color: #8ab4ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  li a {{ font-weight: 600; font-size: 18px; }}
  li p {{ margin: 4px 0 0; color: #9aa1b2; font-size: 15px; }}
</style>
</head>
<body>
<main>
<a class="top" href="/">&larr; QuickHowl home</a>
<h1>QuickHowl Blog</h1>
<p class="lead">Guides on using AI voice agents for sales, support and reminders.</p>
<ul>
{chr(10).join(items)}
</ul>
</main>
</body>
</html>
"""


def build_sitemap(pseo_dir: Path) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = [_url_entry(BASE_URL + path, today, freq, prio) for path, freq, prio in STATIC_PAGES]

    if pseo_dir.is_dir():
        entries.append(_url_entry(f"{BASE_URL}/blog/", today, "weekly", "0.8"))
        for html_file in _pseo_pages(pseo_dir):
            lastmod = datetime.fromtimestamp(html_file.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            loc = f"{BASE_URL}/blog/{html_file.name}"
            entries.append(_url_entry(loc, lastmod, "monthly", "0.7"))
    else:
        print(f"warning: pSEO directory {pseo_dir} not found -- skipping blog pages", file=sys.stderr)

    body = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def write_atomic(content: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dest.parent, prefix=".sitemap-", suffix=".xml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # mkstemp() creates the file 0600 (owner-only) by design -- since this
        # usually runs as root (cron) but is served by Caddy running as its
        # own less-privileged user, the renamed-into-place file would
        # otherwise 404/403 for everyone but root. World-readable, like any
        # other static asset Caddy serves.
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, dest)  # atomic on the same filesystem
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pseo-dir", default="/var/www/pseo-pages", help="Directory the pSEO tool SFTPs .html pages into")
    parser.add_argument("--out", default="/var/www/quickhowl-seo/sitemap.xml", help="Where to write the generated sitemap.xml")
    args = parser.parse_args()

    pseo_dir = Path(args.pseo_dir)
    sitemap = build_sitemap(pseo_dir)
    write_atomic(sitemap, Path(args.out))
    print(f"wrote {args.out}")

    if pseo_dir.is_dir():
        index_path = pseo_dir / "index.html"
        write_atomic(build_blog_index(pseo_dir), index_path)
        print(f"wrote {index_path}")


if __name__ == "__main__":
    main()
