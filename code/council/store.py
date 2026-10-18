"""The council service catalogue, forms, rules and evidence.

The catalogue is built from checked sources only. A row is either verified or it
is marked needs_review. The specialists read only this store; they never invent a
service, a form field, a fee or an eligibility rule.
"""

import csv
import hashlib
import json
from pathlib import Path

import reports_db

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / "agent"

GROUP_MAP = {
    "street_cleansing": "cleansing",
    "highways": "highways",
    "waste": "waste",
    "housing": "housing",
    "environmental": "cleansing",
    "parking": "highways",
    "other": "housing",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS council_sources (
  source_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  kind TEXT NOT NULL,
  fetched_at TEXT,
  content_hash TEXT,
  snapshot_path TEXT,
  http_status INTEGER,
  robots_status TEXT,
  review_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS council_services (
  service_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  group_name TEXT NOT NULL,
  summary TEXT,
  who_it_is_for TEXT,
  page_url TEXT,
  form_url TEXT,
  form_kind TEXT,
  source_id TEXT,
  checked_date TEXT,
  status TEXT NOT NULL,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS council_forms (
  form_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL,
  url TEXT,
  source_id TEXT,
  fields TEXT NOT NULL,
  documents TEXT NOT NULL,
  fees TEXT NOT NULL,
  eligibility_questions TEXT NOT NULL,
  form_hash TEXT,
  checked_date TEXT
);
CREATE TABLE IF NOT EXISTS council_rules (
  rule_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL,
  condition TEXT NOT NULL,
  outcome TEXT NOT NULL,
  question_field TEXT,
  explanation TEXT,
  source_id TEXT,
  quote TEXT,
  checked_date TEXT
);
CREATE TABLE IF NOT EXISTS council_evidence (
  evidence_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL,
  fact TEXT NOT NULL,
  quote TEXT,
  source_id TEXT,
  url TEXT,
  checked_date TEXT,
  caveat TEXT
);
"""

SPECIALIST_SERVICES = {
    "permit": ("Residents parking permit", "highways",
               "https://www.southampton.gov.uk/travel-transport/apply-pay/parking/permits/"),
    "council_tax": ("Council Tax discounts", "housing",
                    "https://www.southampton.gov.uk/council-tax/discounts-exemptions/"),
    "bins": ("Bin collections", "waste",
             "https://www.southampton.gov.uk/bins-recycling/bins/collections/"),
}


def _id(prefix, value):
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:10].upper()


def _source_id(url, kind="page"):
    return _id("S-", f"{kind}:{url}")


class CouncilStore:
    def __init__(self, path=None):
        self.path = path or reports_db.DB_PATH
        self._ready = False

    def _connect(self):
        return reports_db.connect(self.path)

    def migrate(self):
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    def seed(self, force=False):
        self.migrate()
        conn = self._connect()
        try:
            count = conn.execute("SELECT COUNT(*) FROM council_services").fetchone()[0]
        finally:
            conn.close()
        if count and not force:
            return count
        categories = json.loads((AGENT_DIR / "categories.json").read_text(encoding="utf-8"))
        rows = list(csv.DictReader((AGENT_DIR / "confirmed_with_websites.csv").open(encoding="utf-8")))
        evidence = list(csv.DictReader((AGENT_DIR / "evidence.csv").open(encoding="utf-8")))
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            for category in categories["categories"]:
                service_id = category["id"]
                page = category.get("source_url") or ""
                form = category.get("official_form_url") or ""
                source_url = form or page
                if source_url:
                    conn.execute(
                        "INSERT OR REPLACE INTO council_sources (source_id, url, kind, "
                        "review_status) VALUES (?, ?, ?, 'verified')",
                        (_source_id(source_url, "form" if form else "page"), source_url,
                         "form" if form else "page"))
                conn.execute(
                    "INSERT OR REPLACE INTO council_services (service_id, name, group_name, "
                    "summary, who_it_is_for, page_url, form_url, form_kind, source_id, "
                    "checked_date, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (service_id, category["label"],
                     GROUP_MAP.get(category.get("group"), "housing"),
                     category.get("form_scope_notes") or "",
                     category.get("outcome") or "",
                     page, form, "online" if form else "none",
                     _source_id(source_url, "form" if form else "page") if source_url else None,
                     "2026-10-17", "verified",
                     "Seeded from agent/categories.json"))
                if form:
                    conn.execute(
                        "INSERT OR REPLACE INTO council_forms (form_id, service_id, url, "
                        "source_id, fields, documents, fees, eligibility_questions, "
                        "form_hash, checked_date) VALUES (?, ?, ?, ?, '[]', '[]', '[]', "
                        "'[]', NULL, ?)",
                        (_id("F-", form), service_id, form,
                         _source_id(form, "form"), "2026-10-17"))
            for row in rows:
                url = row.get("url") or ""
                if not url:
                    continue
                source = _source_id(url, "page")
                conn.execute(
                    "INSERT OR REPLACE INTO council_sources (source_id, url, kind, "
                    "review_status) VALUES (?, ?, 'page', 'verified')", (source, url))
                service_id = (row.get("category_id") or "general").split(";")[0].strip()
                if service_id and service_id not in ("general", "outside_southampton"):
                    exists = conn.execute("SELECT 1 FROM council_services WHERE service_id = ?",
                                          (service_id,)).fetchone()
                    if not exists:
                        conn.execute(
                            "INSERT OR REPLACE INTO council_services (service_id, name, "
                            "group_name, summary, who_it_is_for, page_url, form_url, "
                            "form_kind, source_id, checked_date, status, notes) "
                            "VALUES (?, ?, 'housing', ?, '', ?, NULL, 'none', ?, ?, "
                            "'verified', 'Seeded from confirmed facts')",
                            (service_id, row.get("topic") or service_id,
                             row.get("confirmed_fact") or "", url, source,
                             row.get("date_checked") or "2026-10-17"))
                conn.execute(
                    "INSERT OR REPLACE INTO council_evidence (evidence_id, service_id, "
                    "fact, quote, source_id, url, checked_date, caveat) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (_id("E-", url + row.get("confirmed_fact", "")), service_id,
                     row.get("confirmed_fact") or "", row.get("confirmed_fact") or "",
                     source, url, row.get("date_checked") or "2026-10-17",
                     row.get("caveat") or ""))
            for row in evidence:
                url = row.get("url") or ""
                service_id = row.get("category_id") or "general"
                source = _source_id(url, "page")
                conn.execute(
                    "INSERT OR REPLACE INTO council_sources (source_id, url, kind, "
                    "review_status) VALUES (?, ?, 'page', 'verified')", (source, url))
                spec = SPECIALIST_SERVICES.get(service_id)
                page = spec[2] if spec else url
                page_source = _source_id(page, "page")
                conn.execute(
                    "INSERT OR REPLACE INTO council_sources (source_id, url, kind, "
                    "review_status) VALUES (?, ?, 'page', 'verified')",
                    (page_source, page))
                conn.execute(
                    "INSERT OR REPLACE INTO council_services (service_id, name, group_name, "
                    "summary, who_it_is_for, page_url, form_url, form_kind, source_id, "
                    "checked_date, status, notes) VALUES (?, ?, ?, ?, '', ?, NULL, 'none', "
                    "?, ?, 'verified', 'Seeded from evidence.csv')",
                    (service_id, spec[0] if spec else service_id,
                     spec[1] if spec else "housing",
                     row.get("topic") or "", page, page_source,
                     row.get("date_checked") or "2026-10-18"))
                conn.execute(
                    "INSERT OR REPLACE INTO council_evidence (evidence_id, service_id, "
                    "fact, quote, source_id, url, checked_date, caveat) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (_id("E-", url + row.get("confirmed_fact", "")), service_id,
                     row.get("confirmed_fact") or "", row.get("confirmed_fact") or "",
                     source, url, row.get("date_checked") or "2026-10-18",
                     row.get("caveat") or ""))
            self._seed_rules(conn, evidence)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return len(self.services())

    def _seed_rules(self, conn, evidence):
        for row in evidence:
            service_id = row.get("category_id") or ""
            if service_id not in ("permit", "council_tax", "bins"):
                continue
            fact = row.get("confirmed_fact") or ""
            rule_id = _id("R-", service_id + fact)
            field = "address" if service_id in ("permit", "council_tax", "bins") else ""
            conn.execute(
                "INSERT OR REPLACE INTO council_rules (rule_id, service_id, condition, "
                "outcome, question_field, explanation, source_id, quote, checked_date) "
                "VALUES (?, ?, ?, 'unknown', ?, ?, ?, ?, ?)",
                (rule_id, service_id, fact, field,
                 "This rule is recorded from the checked page. The council does not expose "
                 "the live register or case system, so the result is unknown until a direct "
                 "integration exists.", _source_id(row.get("url") or "", "page"), fact,
                 row.get("date_checked") or "2026-10-18"))

    def add_source(self, url, kind, fetched_at, content_hash, snapshot_path,
                   http_status, robots_status, review_status="needs_review"):
        self.migrate()
        source_id = _source_id(url, kind)
        conn = self._connect()
        try:
            old = conn.execute("SELECT review_status FROM council_sources WHERE source_id = ?",
                               (source_id,)).fetchone()
            if old and old["review_status"] == "verified":
                return source_id
            conn.execute(
                "INSERT OR REPLACE INTO council_sources (source_id, url, kind, fetched_at, "
                "content_hash, snapshot_path, http_status, robots_status, review_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source_id, url, kind, fetched_at, content_hash, snapshot_path,
                 http_status, robots_status, review_status))
        finally:
            conn.close()
        return source_id

    def add_discovered_service(self, url, title, source_id, checked_date):
        self.migrate()
        service_id = _id("D-", url)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO council_services (service_id, name, group_name, "
                "summary, who_it_is_for, page_url, form_url, form_kind, source_id, "
                "checked_date, status, notes) VALUES (?, ?, 'unknown', ?, '', ?, NULL, "
                "'none', ?, ?, 'needs_review', 'Discovered by the crawler')",
                (service_id, title or url, "Discovered page", url, source_id, checked_date))
        finally:
            conn.close()
        return service_id

    def add_form(self, service_id, url, source_id, fields, form_hash, checked_date):
        self.migrate()
        form_id = _id("F-", url)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO council_forms (form_id, service_id, url, source_id, "
                "fields, documents, fees, eligibility_questions, form_hash, checked_date) "
                "VALUES (?, ?, ?, ?, ?, '[]', '[]', '[]', ?, ?)",
                (form_id, service_id, url, source_id, json.dumps(fields), form_hash,
                 checked_date))
        finally:
            conn.close()
        return form_id

    def coverage(self):
        self.seed()
        conn = self._connect()
        try:
            services = conn.execute("SELECT status, COUNT(*) AS n FROM council_services "
                                    "GROUP BY status").fetchall()
            forms = conn.execute("SELECT COUNT(*) AS n FROM council_forms").fetchone()["n"]
            rules = conn.execute("SELECT COUNT(*) AS n FROM council_rules").fetchone()["n"]
            evidence = conn.execute("SELECT COUNT(*) AS n FROM council_evidence").fetchone()["n"]
            sources = conn.execute("SELECT COUNT(*) AS n FROM council_sources").fetchone()["n"]
        finally:
            conn.close()
        return {"services": {row["status"]: row["n"] for row in services},
                "forms": forms, "rules": rules, "evidence": evidence, "sources": sources}

    def services(self):
        self.seed()
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM council_services ORDER BY service_id").fetchall()]
        finally:
            conn.close()

    def service(self, service_id):
        self.seed()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM council_services WHERE service_id = ?",
                               (service_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def evidence(self, service_id):
        self.seed()
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM council_evidence WHERE service_id = ? ORDER BY evidence_id",
                (service_id,)).fetchall()]
        finally:
            conn.close()

    def rules(self, service_id):
        self.seed()
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM council_rules WHERE service_id = ? ORDER BY rule_id",
                (service_id,)).fetchall()]
        finally:
            conn.close()

    def form(self, service_id):
        self.seed()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM council_forms WHERE service_id = ? LIMIT 1",
                               (service_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
