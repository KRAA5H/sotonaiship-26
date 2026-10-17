"""Generates SYNTHETIC reports in the schema.sql shape. Not real residents or incidents.
Run: python3 make_fake_reports.py categories.json"""
import json, random, sys, csv, secrets
from datetime import datetime, timedelta, timezone
random.seed(7)
cats = [c for c in json.load(open(sys.argv[1]))["categories"] if c["outcome"] == "council_report"]
streets = ["Portswood Road","Highfield Road","Bevois Valley","Shirley High Street","Winchester Road","Hill Lane","Burgess Road","Bitterne Road","Old Northam Road","Cumberland Place"]
now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
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
for r in random.sample(rows[:40], 8):
    d = mk(len(rows)+1, by_id[r["category_id"]], datetime.fromisoformat(r["created_at"]) + timedelta(days=2), "new", r["location"], r["id"])
    rows.append(d)
json.dump(rows, open("fake_reports.json","w"), indent=2)
with open("fake_reports.csv","w",newline="") as f:
    w = csv.DictWriter(f, rows[0].keys()); w.writeheader(); w.writerows(rows)
print(len(rows), "synthetic reports")
