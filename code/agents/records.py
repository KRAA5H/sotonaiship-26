"""Records agent: the only agent that writes reports. Clean, structured, council side.

It saves through tools.save_report (which validates the category, issues the
R- reference and the private link, and links a different person's report of
the same problem), and fills in what arrives later: the street, the photo and
the photo agent's features. Every write goes through reports_db, so the
dashboard sees it within one refresh.
"""

import reports_db
import tools


def with_db(work):
    """One short-lived connection, always closed."""
    conn = reports_db.connect()
    try:
        return work(conn)
    finally:
        conn.close()


class RecordsAgent:
    name = "records"

    def save(self, decision, sender, has_photo, location=None):
        """Save the report. tools.save_report links a duplicate from someone else."""
        kwargs = {
            "category_id": decision["category_id"],
            "location": location if location is not None else decision["location"],
            "description": decision["description"],
            "severity": decision["severity"],
            "has_photo": has_photo,
            "reporter": sender,
        }
        if decision.get("area"):
            kwargs["area"] = decision["area"]   # the location agent already knows it: no lookup
        return tools.save_report(**kwargs)

    def fill_location(self, report_id, location, area=None):
        """The street for a report saved as 'Not given'. True when it landed."""
        moved = with_db(lambda c: reports_db.set_location(c, report_id, location))
        if moved and area:
            with_db(lambda c: reports_db.set_area(c, report_id, area))
        return moved

    def link(self, report_id, original):
        if original and original != report_id:
            with_db(lambda c: reports_db.link_duplicate(c, report_id, original))

    def attach_photo(self, report_id, guid, mime):
        if guid:
            return with_db(lambda c: reports_db.set_photo(c, report_id, guid, mime))
        return False

    def attach_features(self, report_id, features):
        """The photo agent's features, validated again on the way in."""
        stored, problems = with_db(lambda c: reports_db.set_photo_features(c, report_id, features))
        if problems:
            print(f"[photo] features for {report_id}: {'; '.join(problems)}")
        return stored

    def report(self, report_id):
        """Category, location, link token and reporter of one report, or None."""
        def work(c):
            row = c.execute(
                "SELECT id, category_id, location, link_token, reporter_ref, status "
                "FROM reports WHERE id = ?", (report_id,)).fetchone()
            return dict(row) if row else None
        return with_db(work)
