"""Keyword baseline for category accuracy.

Deliberately simple, and fixed before scoring: the keywords for each category
are the words in its label and example_phrases in agent/categories.json, minus
a fixed stopword list. Nothing here was tuned on the FixMyStreet test set.

classify(text) -> category_id. The category with the most keyword hits wins;
ties go to the category listed first in categories.json; no hit at all gives
unclear_other.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent"))
import loader  # noqa: E402

STOPWORDS = set("""
a an the and or of on in to by at for from with is are was be been has have had it its this that
there their they them my our your his her we you i me all every never nobody not no
left near next door day days today again weeks months full gone going up down over under
street road path pavement council house home who what how will do get stay out move when
""".split())


def _words(text):
    words = re.findall(r"[a-z]+", text.lower())
    # Crude plural folding so "potholes" matches "pothole".
    return [w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words]


def _keywords():
    categories, _ = loader.load(ROOT / "agent")
    table = {}
    for cid, category in categories.items():
        source = " ".join([category["label"], *category.get("example_phrases", [])])
        table[cid] = {w for w in _words(source) if len(w) > 2 and w not in STOPWORDS}
    return table


KEYWORDS = _keywords()


def classify(text):
    words = set(_words(text or ""))
    best, best_hits = "unclear_other", 0
    for cid, keys in KEYWORDS.items():
        hits = len(words & keys)
        if hits > best_hits:
            best, best_hits = cid, hits
    return best


if __name__ == "__main__":
    for cid, keys in KEYWORDS.items():
        print(f"{cid}: {', '.join(sorted(keys))}")
