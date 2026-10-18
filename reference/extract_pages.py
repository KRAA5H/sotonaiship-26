"""Pull the readable parts out of the cached council pages (no network).

For each path in council_page_list.txt: the page title (h1), links to online
forms, UK phone numbers, and the main text. Writes reference/.page_cache/text/<n>.txt
for reading, and prints a short summary. Used to fill council_pages.csv by hand.

Run: python reference/extract_pages.py
"""

import html as htmllib
import json
import re
from pathlib import Path

import fetch_pages

HERE = Path(__file__).resolve().parent
BASE = "https://www.southampton.gov.uk"
FORM_HOSTS = ("verintcloudservices.com", "/forms/", "my.southampton.gov.uk", "southampton.gov.uk/contact-us/online-forms")
PHONE = re.compile(r"\b(0\d{2,4}[  ]?\d{3,4}[  ]?\d{3,4}|999|101|105)\b")


def main_text(page):
    body = re.search(r"<main\b.*?</main>", page, re.S | re.I)
    body = body.group(0) if body else page
    body = re.sub(r"<(script|style|nav|header|footer)\b.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<(br|/p|/li|/h\d|/tr|/div)\b[^>]*>", "\n", body, flags=re.I)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def links(page):
    out = []
    for href, label in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        label = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", label)).split())
        href = htmllib.unescape(href)
        if any(h in href for h in FORM_HOSTS):
            out.append((label, href if href.startswith("http") else BASE + href))
    return out


def main():
    paths = [l.strip() for l in (HERE / "council_page_list.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    out_dir = fetch_pages.CACHE / "text"
    out_dir.mkdir(exist_ok=True)
    summary = []
    for n, path in enumerate(paths, 1):
        url = BASE + path
        page = fetch_pages.fetch(url)   # cached: no network
        title = re.search(r"<h1\b[^>]*>(.*?)</h1>", page, re.S | re.I)
        title = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", title.group(1))).split()) if title else ""
        text = main_text(page)
        forms = sorted(set(links(page)))
        phones = sorted(set(PHONE.findall(text)))
        (out_dir / f"{n:02d}.txt").write_text(f"{url}\n{title}\n\n{text}", encoding="utf-8")
        summary.append({"n": n, "url": url, "title": title, "forms": forms, "phones": phones})
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for s in summary:
        print(f"{s['n']:02d} {s['title']} | {s['url'].replace(BASE, '')}")
        for label, href in s["forms"]:
            print(f"     form: {label} -> {href}")
        if s["phones"]:
            print(f"     phones: {', '.join(s['phones'])}")


if __name__ == "__main__":
    main()
