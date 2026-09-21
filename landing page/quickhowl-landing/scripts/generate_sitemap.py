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

Writes atomically (temp file + rename) so Caddy never serves a half-written
file if this runs while something else is mid-write.
"""
from __future__ import annotations

import argparse
import os
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


def build_sitemap(pseo_dir: Path) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = [_url_entry(BASE_URL + path, today, freq, prio) for path, freq, prio in STATIC_PAGES]

    if pseo_dir.is_dir():
        for html_file in sorted(pseo_dir.glob("*.html")):
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

    sitemap = build_sitemap(Path(args.pseo_dir))
    write_atomic(sitemap, Path(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
