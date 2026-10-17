"""Score the evaluation set built by collect.py and select.py.

  Category accuracy: the keyword baseline (baseline.py) on the 60 reports, and
  the agent's own triage (code/triage.py) only with --agent, because that sends
  the real report text to the external text model.

  Duplicates: the rule in code/tools.py (check_duplicate), applied to each pair
  as if report A were already in the database when report B arrived. The
  category given to the rule is FixMyStreet's category mapped through
  categories.json, the same for both reports, so this tests the location and
  time part of the rule, not classification. Location is the road name
  OpenStreetMap gives for each report's point, because Open311 has no street.

Needs raw/proposed.json (from select.py) and labels.json. Writes results.json:
ids, labels and predictions only, no report text.

Run:
  python code/eval/fms/score.py            baseline and duplicate rule
  python code/eval/fms/score.py --agent    also the agent's triage (external model calls)
"""

import argparse
import json
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent.parent
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(HERE))

import baseline  # noqa: E402
import reports_db  # noqa: E402
import tools  # noqa: E402


def load():
    proposed = json.loads((HERE / "raw" / "proposed.json").read_text(encoding="utf-8"))
    labels = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
    return proposed, labels


def score_categories(proposed, labels, use_agent):
    rows = []
    for report in proposed["reports"]:
        fid = str(report["fms_id"])
        expected = labels["categories"][fid]["label"]
        text = f"{report['title']}. {report['text']}" if report["title"] not in report["text"] else report["text"]
        row = {"fms_id": fid, "expected": expected, "baseline": baseline.classify(text)}
        if use_agent:
            import triage  # noqa: E402  (imports llm, so only when asked)
            decision = triage.triage(text)
            row["agent"] = decision.get("category_id")
        rows.append(row)

    def accuracy(system):
        clear = [r for r in rows if r["expected"] != "ambiguous" and system in r]
        right = sum(r[system] == r["expected"] for r in clear)
        return {"right": right, "total": len(clear), "accuracy": round(right / len(clear), 3) if clear else None}

    summary = {"clear": sum(r["expected"] != "ambiguous" for r in rows),
               "ambiguous": sum(r["expected"] == "ambiguous" for r in rows),
               "baseline": accuracy("baseline")}
    if use_agent:
        summary["agent"] = accuracy("agent")
    return rows, summary


def _rule_flags(conn, a, b):
    """True or False from check_duplicate, or None when either report has no street."""
    if not a["street"].strip() or not b["street"].strip():
        return None
    conn.execute("DELETE FROM reports")
    conn.execute(
        "INSERT INTO reports (id, created_at, category_id, status, location, description, has_photo, "
        "link_token) VALUES ('E-A', ?, ?, 'new', ?, 'eval', 0, 'eval-token-a')",
        (f"{a['date']}T12:00:00+00:00", a["proposed"], a["street"]),
    )
    now = datetime.fromisoformat(f"{b['date']}T12:00:00+00:00")
    return tools.check_duplicate(b["proposed"], b["street"], conn=conn, now=now)["is_duplicate"]


def score_duplicates(proposed, labels):
    expected = {}
    for kind in ("repeats", "pairs"):
        for a, b, label, _ in labels["same_problem"][kind]:
            expected[(a, b)] = label
    ambiguous_negative = {("1178514", "1209812")}

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "eval.db"
        reports_db.init_db(path, seed=False)
        conn = reports_db.connect(path)
        try:
            for kind in ("repeats", "pairs", "negatives"):
                for pair in proposed[kind]:
                    a, b = pair["a"], pair["b"]
                    key = (str(a["fms_id"]), str(b["fms_id"]))
                    if kind == "negatives":
                        label = "ambiguous" if key in ambiguous_negative else "no"
                    else:
                        label = expected[key]
                    flagged = _rule_flags(conn, a, b)
                    rows.append({"set": kind, "a": key[0], "b": key[1], "expected": label,
                                 "rule": "no street" if flagged is None else ("duplicate" if flagged else "not duplicate"),
                                 "same_street_text": a["street"] == b["street"], "metres": pair["metres"],
                                 "days_apart": pair["days_apart"]})
        finally:
            conn.close()

    def rate(label):
        group = [r for r in rows if r["expected"] == label]
        flagged = sum(r["rule"] == "duplicate" for r in group)
        return {"flagged": flagged, "total": len(group), "no_street": sum(r["rule"] == "no street" for r in group)}

    by_set = {kind: Counter(f"{r['expected']}/{r['rule']}" for r in rows if r["set"] == kind)
              for kind in ("repeats", "pairs", "negatives")}
    return rows, {"true_duplicates": rate("yes"), "not_duplicates": rate("no"), "ambiguous": rate("ambiguous"),
                  "by_set": {k: dict(v) for k, v in by_set.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--agent", action="store_true", help="also run code/triage.py (external model calls)")
    args = parser.parse_args()

    proposed, labels = load()
    category_rows, category_summary = score_categories(proposed, labels, args.agent)
    duplicate_rows, duplicate_summary = score_duplicates(proposed, labels)
    out = {
        "scored_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "categories": {"summary": category_summary, "rows": category_rows},
        "duplicates": {"summary": duplicate_summary, "rows": duplicate_rows},
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({"categories": category_summary, "duplicates": duplicate_summary}, indent=1))


if __name__ == "__main__":
    main()
