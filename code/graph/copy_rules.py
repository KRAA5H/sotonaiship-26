"""Copy constants shared by the graph schemas and the writer.

Zero project imports: importing voice.py would pull in llm.py and requests, which
the contract layer must not depend on. A test compares these patterns with the
ones in voice.py so the two cannot drift.
"""

import re

MAX_CHARS = 300
MAX_BUBBLES = 3

MARKDOWN = re.compile(r"[*_#`]")
EM_DASH = "\u2014"
EN_DASH = "\u2013"
URLISH = re.compile(
    r"https?://|www\.|google\.|search\?q=|"
    r"\b[a-z0-9-]+\.(?:gov\.uk|co\.uk|org\.uk|ac\.uk|uk|com|org|net|io)\b",
    re.I,
)
REPORT_ID = re.compile(r"\bR-\d{4}\b", re.I)
