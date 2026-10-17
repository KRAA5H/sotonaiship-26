"""Joins categories.json (rules) to confirmed_with_websites.csv (facts) on category_id.
Rows whose category_id holds several ids separated by ';' apply to each id.
Never load scope_checks.csv, confirmed_categories.csv, partly_confirmed_categories.csv, council_forms.csv into the agent."""
import csv, json
def load(folder="."):
    cats = {c["id"]: c for c in json.load(open(f"{folder}/categories.json"))["categories"]}
    facts = {k: [] for k in cats}
    facts["general"] = []
    for r in csv.DictReader(open(f"{folder}/confirmed_with_websites.csv")):
        for cid in [x.strip() for x in r["category_id"].split(";")]:
            facts.setdefault(cid, []).append(r)
    return cats, facts
if __name__ == "__main__":
    c, f = load()
    print(len(c), "categories;", sum(len(v) for v in f.values()), "fact links")
    print("categories with no facts:", [k for k in c if not f.get(k)])
