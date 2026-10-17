"""Generates SYNTHETIC reports in the schema.sql shape. Not real residents or incidents.
Also refreshes the copy embedded in prototype/index.html so the two never drift.
Run: python3 make_fake_reports.py ../agent/categories.json"""
import json, random, re, sys, csv, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
random.seed(7)
here = Path(__file__).resolve().parent
cats = [c for c in json.load(open(sys.argv[1], encoding="utf-8"))["categories"] if c["outcome"] == "council_report"]
streets = ["Portswood Road","Highfield Road","Bevois Valley","Shirley High Street","Winchester Road","Hill Lane","Burgess Road","Bitterne Road","Old Northam Road","Cumberland Place"]
now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
dup_gap = timedelta(days=2)
rows = []
def mk(i, c, created, status, loc, dup=""):
    return {"id": f"R-{i:04d}", "created_at": created.isoformat(), "category_id": c["id"], "status": status,
            "severity": random.choice(["high","medium","medium","low"]), "location": loc,
            "description": f"Synthetic example: {c['label'].lower()}", "has_photo": int(random.random() < 0.5),
            "duplicate_of": dup, "reporter_ref": f"synthetic-{random.randint(1000,9999)}", "link_token": secrets.token_urlsafe(12)}
for i in range(1, 61):
    c = random.choice(cats)
    rows.append(mk(i, c, now - timedelta(hours=random.randint(1, 24*30)),
                   random.choice(["new","new","new","in_review","resolved"]),
                   f"{random.randint(1,120)} {random.choice(streets)}"))
by_id = {c["id"]: c for c in cats}
newest = max(datetime.fromisoformat(r["created_at"]) for r in rows)
# A repeat is only flagged against an open report (resolved ones are not
# duplicates), and must not be dated after the newest original.
candidates = [r for r in rows[:40] if r["status"] in ("new", "in_review")
              and datetime.fromisoformat(r["created_at"]) + dup_gap <= newest]
for r in random.sample(candidates, 8):
    d = mk(len(rows)+1, by_id[r["category_id"]], datetime.fromisoformat(r["created_at"]) + dup_gap, "new", r["location"], r["id"])
    rows.append(d)
assert max(r["created_at"] for r in rows) == newest.isoformat()
# Synthetic placeholder photo for every report that "has" one (make_fake_photos.py).
sys.path.insert(0, str(here))
from make_fake_photos import photo_for  # noqa: E402
for r in rows:
    r["photo_path"] = photo_for(r["category_id"]) if r["has_photo"] else ""
    # Left empty: no model has looked at these placeholders, and hand-written
    # text must never be shown under the "AI-generated description" label.
    r["photo_features"] = ""
# When an officer first changed the status, for "time to first action". Its own
# seeded generator per report, so adding it does not shift the data above.
for r in rows:
    created = datetime.fromisoformat(r["created_at"])
    if r["status"] == "new":
        r["status_changed_at"] = ""
    else:
        hours = random.Random(f"status-{r['id']}").randint(2, 96)
        r["status_changed_at"] = min(created + timedelta(hours=hours), now).isoformat()
json.dump(rows, open(here / "fake_reports.json", "w", newline="\n"), indent=2)
with open(here / "fake_reports.csv", "w", newline="") as f:
    w = csv.DictWriter(f, rows[0].keys()); w.writeheader(); w.writerows(rows)
proto = here / "prototype" / "index.html"
html = open(proto, encoding="utf-8", newline="").read()
# (?=\r?$): the file may be checked out with CRLF line endings.
html, n = re.subn(r"^const DATA=\[.*?\];(?=\r?$)",lambda _: f"const DATA={json.dumps(rows)};", html, count=1, flags=re.M)
assert n == 1, "const DATA line not found in prototype/index.html"
proto.write_text(html, encoding="utf-8", newline="")
print(len(rows), "synthetic reports")
