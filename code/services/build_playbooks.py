"""Generate verified playbooks from agent/categories.json and the dated fact sheet.

Usage:
    python code/services/build_playbooks.py            # write code/services/playbooks
    python code/services/build_playbooks.py --check    # fail if the files have drifted

No network, no model, no clock. Two runs are byte-identical.
"""

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / "agent"
OUT_DIR = Path(__file__).resolve().parent / "playbooks"

# The four groups a specialist subgraph can be asked for. The rulebook groups are
# finer than this; the mapping is explicit so no consumer has to guess.
SPECIALIST_GROUPS = {
    "street_cleansing": "cleansing",
    "roads_and_parking": "highways",
    "bins": "waste",
    "housing": "housing",
}
GROUP_ORDER = ("cleansing", "highways", "waste", "housing")
NUMBER = re.compile(r"\b0\d{2,4}\s?\d{3,4}\s?\d{0,4}\b")
DETAIL_SKIP = {"description", "location", "address", "photo_recommended"}


def _read_source():
    categories_raw = (AGENT_DIR / "categories.json").read_bytes()
    facts_raw = (AGENT_DIR / "confirmed_with_websites.csv").read_bytes()
    data = json.loads(categories_raw.decode("utf-8"))
    rows = list(csv.DictReader(facts_raw.decode("utf-8").splitlines()))
    return data, rows, hashlib.sha256(facts_raw).hexdigest()[:12]


def _split_ids(value):
    return [item.strip() for item in (value or "").split(";") if item.strip()]


def _fact_rows(rows):
    fact_rows = []
    for index, row in enumerate(rows, start=1):
        key = hashlib.sha256(
            "|".join((row["topic"], row["confirmed_fact"], row["url"],
                      row["date_checked"])).encode("utf-8")).hexdigest()[:12]
        fact_rows.append({
            "id": f"F{index:03d}",
            "fact_key": key,
            "topic": row["topic"],
            "fact": row["confirmed_fact"],
            "url": row["url"],
            "date": row["date_checked"],
            "caveat": row.get("caveat") or "",
            "category_ids": _split_ids(row["category_id"]),
        })
    return fact_rows


def _known_facts(fact_rows):
    known = {}
    for row in fact_rows:
        existing = known.get(row["url"])
        if existing is not None and existing != row["date"]:
            raise ValueError(f"{row['url']} has two checked dates")
        known[row["url"]] = row["date"]
    return dict(sorted(known.items()))


def _question_field(category, index):
    mode = (category.get("agent") or {}).get("location_mode") or "pin"
    if index == 0 and mode == "pin":
        return "location"
    if index == 0 and mode == "address":
        return "address"
    return "detail"


def _questions(category):
    return [{"field": _question_field(category, index), "text": text}
            for index, text in enumerate(category.get("follow_up_questions") or [])]


def _location_mode(category):
    return (category.get("agent") or {}).get("location_mode") or "pin"


def _required_local(category):
    mode = _location_mode(category)
    if mode == "handoff":
        return []
    if mode == "address":
        return ["description", "address"]
    return ["description", "location"]


def _required_detail(category):
    return [field for field in (category.get("required_fields") or [])
            if field not in DETAIL_SKIP]


def _playbook(category, facts, version, facts_date, default_window):
    mode = _location_mode(category)
    group = category.get("group")
    questions = _questions(category)
    allowed = sorted({"description", "photo"} | {item["field"] for item in questions})
    return {
        "id": category["id"],
        "service_id": category["id"],
        "version": version,
        "source_date": facts_date,
        "generated_from": {"categories": "0.3", "facts_date": facts_date},
        "label": category["label"],
        "rulebook_group": group,
        "specialist_group": SPECIALIST_GROUPS.get(group),
        "outcome": category["outcome"],
        "location_mode": mode,
        "handoff": mode == "handoff",
        "emergency": group == "emergency",
        "team": category.get("team"),
        "team_confirmed": bool(category.get("team_confirmed")),
        "duplicate_window_days": (category.get("agent") or {}).get(
            "dup_window_days", default_window),
        "required_capture_any": ["description", "photo"],
        "required_local": _required_local(category),
        "required_detail": _required_detail(category),
        "rulebook_required_fields": list(category.get("required_fields") or []),
        "required_submission": [],
        "submission_status": "unverified",
        "questions": questions,
        "allowed_question_fields": allowed,
        "form_url": category.get("official_form_url"),
        "source_url": category.get("source_url") or category.get("answer_source"),
        "form_notes": category.get("form_scope_notes") or "",
        "severity": category.get("severity_hints") or {},
        "severity_keywords": (category.get("agent") or {}).get("severity_keywords") or {},
        "detail_question": (category.get("agent") or {}).get("detail_question"),
        "detail_words": list((category.get("agent") or {}).get("detail_words") or []),
        "detail_pattern": (category.get("agent") or {}).get("detail_pattern"),
        "redirect_to": category.get("redirect_to"),
        "show_guidance": list(category.get("show_guidance") or []),
        "info_first": bool(category.get("info_first")),
        "check_ownership": category.get("check_ownership"),
        "note": category.get("note"),
        "example_phrases": list(category.get("example_phrases") or []),
        "fms_categories": list(category.get("fms_categories") or []),
        "facts": facts,
    }


def build():
    """Return {filename: text} for the index and every category playbook."""
    data, rows, csv_hash = _read_source()
    categories = {item["id"]: item for item in data["categories"]}
    meta = data.get("meta") or {}
    default_window = ((meta.get("duplicate_rule") or {})
                      .get("default", {}).get("window_days", 30))
    version = f"{meta.get('version', '0.3')}+{csv_hash}"

    fact_rows = _fact_rows(rows)
    if not fact_rows:
        raise ValueError("the fact sheet is empty")
    dates = {row["date"] for row in fact_rows}
    if len(dates) != 1:
        raise ValueError(f"facts must share one checked date, got {sorted(dates)}")
    facts_date = next(iter(dates))
    known_facts = _known_facts(fact_rows)

    numbers = set()
    for guidance in (data.get("guidance_links") or {}).values():
        if guidance.get("contact"):
            numbers.add(guidance["contact"])
    for row in fact_rows:
        numbers.update(NUMBER.findall(row["fact"]))

    playbooks = {}
    for category_id, category in categories.items():
        facts = [
            {key: row[key] for key in ("id", "fact_key", "topic", "fact", "url",
                                       "date", "caveat")}
            for row in fact_rows if category_id in row["category_ids"]
        ]
        playbooks[category_id] = _playbook(
            category, facts, version, facts_date, default_window)

    groups = {group: sorted(category_id for category_id, item in playbooks.items()
                            if item["specialist_group"] == group)
              for group in GROUP_ORDER}
    index = {
        "version": version,
        "generated_from": {
            "categories": meta.get("version", "0.3"),
            "facts_date": facts_date,
            "fact_count": len(fact_rows),
            "category_count": len(categories),
        },
        "categories": {category_id: category["outcome"]
                       for category_id, category in categories.items()},
        "handoff_categories": sorted(
            category_id for category_id, item in playbooks.items() if item["handoff"]),
        "never_saved": sorted(
            category_id for category_id, item in playbooks.items()
            if item["outcome"] == "not_council"),
        "emergency_categories": sorted(
            category_id for category_id, item in playbooks.items() if item["emergency"]),
        "groups": groups,
        "teams": sorted({item["team"] for item in playbooks.values() if item["team"]}),
        "numbers": sorted(numbers),
        "guidance": data.get("guidance_links") or {},
        "guidance_by_category": {
            category_id: {"redirect_to": item["redirect_to"],
                          "show_guidance": item["show_guidance"]}
            for category_id, item in playbooks.items()
            if item["redirect_to"] or item["show_guidance"]
        },
        "allowed_questions": sorted({field for item in playbooks.values()
                                     for field in item["allowed_question_fields"]}),
        "allowed_questions_by_category": {
            category_id: item["allowed_question_fields"]
            for category_id, item in playbooks.items()
        },
        "location_modes": {category_id: item["location_mode"]
                           for category_id, item in playbooks.items()},
        "duplicate_windows": {category_id: item["duplicate_window_days"]
                              for category_id, item in playbooks.items()},
        "known_facts": known_facts,
        "fact_ids": {row["id"]: {"url": row["url"], "date": row["date"],
                                 "fact_key": row["fact_key"],
                                 "categories": row["category_ids"]}
                     for row in fact_rows},
        "general_fact_ids": [row["id"] for row in fact_rows
                             if "general" in row["category_ids"]],
        "playbooks": {category_id: f"{category_id}.json" for category_id in categories},
    }

    files = {f"{category_id}.json": _dump(item)
             for category_id, item in playbooks.items()}
    files["_index.json"] = _dump(index)
    return files


def _dump(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(out_dir=OUT_DIR):
    files = build()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    for existing in out_dir.glob("*.json"):
        if existing.name not in files:
            existing.unlink()
    return len(files)


def check(out_dir=OUT_DIR):
    """Return a list of drift descriptions. Empty means the files are current."""
    expected = build()
    out_dir = Path(out_dir)
    problems = []
    for name, text in sorted(expected.items()):
        path = out_dir / name
        if not path.exists():
            problems.append(f"missing {name}")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"stale {name}")
    for existing in sorted(out_dir.glob("*.json")):
        if existing.name not in expected:
            problems.append(f"extra {existing.name}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed playbooks have drifted")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        if problems:
            for problem in problems:
                print(problem)
            return 1
        print("playbooks are current")
        return 0
    count = write()
    print(f"wrote {count} files to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
