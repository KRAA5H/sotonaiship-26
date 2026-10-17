"""Answers built only from the checked facts, with attribution we control.

No vector database and no keyword lists. All 53 dated facts fit in one prompt
(about 2,940 tokens), so the model reads the question and the facts and picks
the ones it used. It returns their numbers; we turn those numbers into the
source line. The model never writes a URL, so provenance cannot be invented.

  python code/rag.py "how long does a pothole take to fix"
"""

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
FACTS_CSV = AGENT_DIR / "confirmed_with_websites.csv"
CATEGORIES = AGENT_DIR / "categories.json"
MAX_CITED = 3

SYSTEM = (
    "You answer questions for Southampton City Council's text message line.\n"
    "Below are numbered facts, each checked with the council on the date shown.\n"
    "Use only those facts. Do not add anything you were not given.\n"
    "Never write a web address or a phone number that is not in the facts.\n"
    "The answer must be two sentences at most, plain English, no jargon.\n"
    "If the facts do not answer the question, return an empty facts list and an "
    "empty answer. Do not guess.\n"
    "Reply with one JSON object and nothing else:\n"
    '{"answer": "the reply", "facts": [1, 2]}'
)
RETRY = ("\n\nYour previous reply could not be read as JSON. Reply with the JSON "
         "object only.")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


@lru_cache(maxsize=1)
def corpus():
    """Every fact we are allowed to answer from, with its source and date."""
    import csv

    facts = []
    with FACTS_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            facts.append({
                "topic": row["topic"],
                "text": row["confirmed_fact"],
                "url": row["url"],
                "source_name": row["source_name"],
                "date_checked": row["date_checked"],
                "caveat": row.get("caveat", ""),
                "kind": "fact",
            })

    rulebook = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    checked = rulebook["meta"].get("created", "")
    for link in rulebook.get("guidance_links", {}).values():
        contact = link.get("contact") or ""
        url = link.get("url") or link.get("source") or ""
        text = f"{link['label']}. {contact}".strip()
        if text:
            facts.append({
                "topic": link["label"],
                "text": text,
                "url": url,
                "source_name": link["label"],
                "date_checked": checked,
                "caveat": "",
                "kind": "contact",
            })
    return facts


def _number(facts):
    return "\n".join(f"[{index}] {fact['topic']}: {fact['text']} "
                     f"(source: {fact['source_name']}, checked {fact['date_checked']})"
                     for index, fact in enumerate(facts, 1))


def _json_object(raw):
    if not raw:
        return None
    fenced = _FENCE.search(raw)
    text = fenced.group(1) if fenced else raw
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _pick(numbers, available):
    """Trust only integer indices that exist in the corpus."""
    picked = []
    for number in numbers or []:
        try:
            index = int(number)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= available and index not in picked:
            picked.append(index)
    return picked[:MAX_CITED]


def source_line(facts):
    """Attribution we write ourselves. The model is never trusted with this."""
    if not facts:
        return ""
    names = []
    for fact in facts:
        label = fact["source_name"]
        if fact.get("date_checked"):
            label += f", checked {fact['date_checked']}"
        names.append(label)
    line = "Source: " + "; ".join(names)
    urls = [fact["url"] for fact in facts if fact.get("url")]
    return line + ("\n" + urls[0] if urls else "")


def answer(question, category_id=None):
    """Return (text, facts_cited). Empty text means we had no checked answer."""
    facts = corpus()
    # The facts block comes first and never changes, so the provider can cache
    # the prefix. The per-message hint goes last, where it cannot break it.
    system = SYSTEM + "\n\nFacts:\n" + _number(facts)
    if category_id:
        system += f"\nThe message was triaged as: {category_id}."

    raw, mode = llm.chat(system, question)
    if mode != "model":
        return "", []

    data = _json_object(raw)
    if data is None:
        raw, mode = llm.chat(system, question + RETRY)
        data = _json_object(raw) if mode == "model" else None
    if data is None:
        return "", []

    picked = _pick(data.get("facts"), len(facts))
    body = " ".join(str(data.get("answer") or "").split())
    body = re.sub(r"https?://\S+", "", body).strip()
    if not picked or not body:
        return "", []

    cited = [facts[index - 1] for index in picked]
    return f"{body}\n\n{source_line(cited)}", cited


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text, used = answer(" ".join(sys.argv[1:]))
        print(text or "no checked answer")
        print("\n cited:", [fact["topic"] for fact in used])
    else:
        for sample in ("how long does a pothole take to fix",
                       "who do I call about a gas leak"):
            print(sample)
            print(answer(sample)[0] or "no checked answer")
            print()
