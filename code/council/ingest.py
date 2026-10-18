"""Crawl the public council pages into the source and form catalogue.

This is a discovery and review pipeline, not an auto-publisher. Fetched rows are
marked needs_review. Only the seeded, checked rows are used by specialists until a
human verifies a discovered service or form.
"""

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from .store import CouncilStore

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = ROOT / "data" / "council_sources"
USER_AGENT = "KerbsideDemo/1.0 (council service catalogue; contact: local demo)"
MAX_BYTES = 2_000_000
PATH_HINTS = ("report", "apply", "request", "permit", "bin", "parking",
              "council-tax", "housing", "environment", "waste", "road", "form")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.forms = []
        self.links = []
        self._form = None
        self._select = None
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "form":
            self._form = {"action": attrs.get("action") or "", "method": attrs.get("method") or "get",
                          "fields": []}
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            name = attrs.get("name")
            if name:
                self._form["fields"].append({
                    "name": name, "type": attrs.get("type") or "text",
                    "required": "required" in attrs,
                    "label": attrs.get("aria-label") or attrs.get("placeholder") or "",
                    "options": [],
                })
        elif tag == "select" and self._form is not None:
            self._select = {"name": attrs.get("name") or "", "type": "select",
                            "required": "required" in attrs, "label": "", "options": []}
            self._form["fields"].append(self._select)
        elif tag == "textarea" and self._form is not None:
            self._textarea = {"name": attrs.get("name") or "", "type": "textarea",
                              "required": "required" in attrs, "label": "", "options": []}
            self._form["fields"].append(self._textarea)
        elif tag == "option" and self._select is not None and attrs.get("value"):
            self._select["options"].append(attrs["value"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "form":
            self._form = None
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def _hash(body):
    return hashlib.sha256(body).hexdigest()


def _robots(url):
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser.can_fetch(USER_AGENT, url), "allowed" if parser.can_fetch(USER_AGENT, url) else "blocked"
    except Exception:
        return True, "unknown"


def fetch(url, timeout=15):
    allowed, robots_status = _robots(url)
    if not allowed:
        return {"url": url, "ok": False, "robots": robots_status, "http": None,
                "body": b"", "content_type": "", "error": "robots.txt blocked"}
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES)
            return {"url": response.geturl(), "ok": True, "robots": robots_status,
                    "http": response.status, "body": body,
                    "content_type": response.headers.get("Content-Type", ""), "error": None}
    except Exception as error:  # noqa: BLE001 - a fetch failure is data, not a crash
        return {"url": url, "ok": False, "robots": robots_status, "http": None,
                "body": b"", "content_type": "", "error": str(error)}


def ingest_url(url, store, limit=1):
    result = fetch(url)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    content_hash = _hash(result["body"])
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = SNAPSHOT_DIR / f"{content_hash[:20]}.html"
    if result["body"]:
        snapshot.write_bytes(result["body"])
    source_id = store.add_source(
        result["url"], "page", fetched_at, content_hash,
        str(snapshot.relative_to(ROOT)) if result["body"] else None,
        result["http"], result["robots"], "needs_review")
    if not result["ok"] or "html" not in (result["content_type"] or "").lower():
        return {"url": url, "source_id": source_id, "forms": 0, "links": [],
                "error": result["error"]}
    parser = PageParser()
    try:
        parser.feed(result["body"].decode("utf-8", "replace"))
    except Exception as error:  # noqa: BLE001
        return {"url": url, "source_id": source_id, "forms": 0, "links": [],
                "error": str(error)}
    forms = 0
    service = None
    for existing in store.services():
        if result["url"] in (existing.get("page_url"), existing.get("form_url")):
            service = existing["service_id"]
            break
    if service is None:
        service = store.add_discovered_service(result["url"], parser.title.strip(),
                                               source_id, fetched_at[:10])
    for form in parser.forms:
        if not form["fields"]:
            continue
        action = urllib.parse.urljoin(result["url"], form["action"] or result["url"])
        store.add_form(service, action, source_id, form["fields"], content_hash, fetched_at[:10])
        forms += 1
    links = []
    for link in parser.links:
        absolute = urllib.parse.urljoin(result["url"], link)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.netloc.endswith("southampton.gov.uk") and any(
                hint in parsed.path.lower() for hint in PATH_HINTS):
            links.append(absolute.split("#")[0])
    return {"url": result["url"], "source_id": source_id, "service_id": service,
            "forms": forms, "links": list(dict.fromkeys(links)),
            "title": parser.title.strip(), "error": result["error"]}


def discover(start_urls, store, limit=20, same_host="www.southampton.gov.uk"):
    queue = list(start_urls)
    seen = set()
    results = []
    while queue and len(results) < limit:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        result = ingest_url(url, store)
        results.append(result)
        for link in result.get("links") or []:
            if link not in seen:
                queue.append(link)
        time.sleep(0.4)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    urls = args.url or ["https://www.southampton.gov.uk/"]
    store = CouncilStore()
    for result in discover(urls, store, limit=args.limit):
        print(json.dumps(result, ensure_ascii=False))
    print(json.dumps(store.coverage(), indent=2))


if __name__ == "__main__":
    main()
