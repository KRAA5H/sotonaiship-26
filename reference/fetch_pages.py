"""Polite, cached fetcher for southampton.gov.uk pages, used to build council_pages.csv.

- Follows robots.txt (checked 2026-10-18: only /moderngov/ is disallowed, and only
  for Baiduspider; the Verint portal allows everything).
- At most one request a second, with a user agent that names the project.
- Every page is cached in reference/.page_cache/ (gitignored), so nothing is
  fetched twice.
- A 403 or 429 stops the run: we do not retry or work around a block.

Run: python reference/fetch_pages.py <url> [<url> ...]   prints status and cache file per URL
"""

import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / ".page_cache"
USER_AGENT = "KerbsideResearch/0.1 (SotonShip 2026 hackathon; +https://github.com/KRAA5H/sotonaiship-26)"
DELAY = 1.1
_last = [0.0]


class Blocked(RuntimeError):
    """The site said no (403/429). Stop and tell a person."""


def cache_path(url):
    return CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")


def fetch(url):
    """Page HTML (from the cache if we have it), or None for a 404/410."""
    path = cache_path(url)
    if path.exists():
        return path.read_text(encoding="utf-8")
    wait = DELAY - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
            final = response.geturl()
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise Blocked(f"{error.code} on {url}") from error
        if error.code in (404, 410):
            CACHE.mkdir(exist_ok=True)
            path.write_text(f"<!-- HTTP {error.code} {url} -->", encoding="utf-8")
            return None
        raise
    CACHE.mkdir(exist_ok=True)
    path.write_text(f"<!-- fetched {url} final {final} -->\n" + body, encoding="utf-8")
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    for u in sys.argv[1:]:
        html = fetch(u)
        print(("404" if html is None else f"{len(html)} chars"), cache_path(u).name, u)
