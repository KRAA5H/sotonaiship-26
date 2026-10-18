"""Verified evidence imported from the council pages, with URL and checked date.

This is the evidence layer. It is not a model and it does not invent. Answers may
only use rows here or in the confirmed fact sheet. A missing topic means the agent
says it has no checked source.
"""

import csv
import re
from functools import lru_cache
from pathlib import Path

EVIDENCE_PATH = Path(__file__).resolve().parents[2] / "agent" / "evidence.csv"

_WORDS = re.compile(r"[a-z0-9]+")
_CATEGORY_HINTS = {
    "permit": ("permit", "parking"),
    "council_tax": ("council tax", "discount", "exemption", "single person"),
    "bins": ("bin", "bins", "collection", "waste"),
}
_STOP = {"a", "an", "and", "are", "do", "does", "for", "how", "i", "is", "it",
         "my", "of", "on", "the", "to", "what", "when", "where", "who", "why",
         "can", "could", "need", "get", "have", "with"}


@lru_cache(maxsize=1)
def _rows():
    if not EVIDENCE_PATH.exists():
        return ()
    with EVIDENCE_PATH.open(encoding="utf-8", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def known_facts():
    return {row["url"]: row["date_checked"] for row in _rows()}


def _category(text):
    lowered = (text or "").lower()
    for category, hints in _CATEGORY_HINTS.items():
        if any(hint in lowered for hint in hints):
            return category
    return None


def search(text, limit=4):
    """Return the best matching checked rows, with a source and date."""
    lowered = (text or "").lower()
    category = _category(lowered)
    wanted = {word for word in _WORDS.findall(lowered) if word not in _STOP}
    scored = []
    for row in _rows():
        if category and row.get("category_id") != category:
            continue
        haystack = " ".join([
            row.get("category_id") or "", row.get("topic") or "",
            row.get("confirmed_fact") or "",
        ]).lower()
        tokens = set(_WORDS.findall(haystack))
        score = len(wanted & tokens)
        if score or category:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [dict(row) for _, row in scored[:limit]]


def as_fact(row):
    return {
        "fact": row.get("confirmed_fact"),
        "url": row.get("url"),
        "date": row.get("date_checked"),
        "topic": row.get("topic"),
        "source": row.get("source_name"),
        "caveat": row.get("caveat") or "",
    }
