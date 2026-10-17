"""Duplicate agent: two different checks, kept apart on purpose.

  same_user     the SAME person reporting the same open problem again: nothing new
                is saved, they are told it is already with the council
  same problem  a DIFFERENT person reporting it: saved and linked to the first one,
                so the council handles one job (tools.check_duplicate, applied by
                save_report with this category's own window)

Both use the category agent's window (fly-tipping 7 days, pothole 30...), only
open reports, and never match on a missing location.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import reports_db
import tools


class DuplicateAgent:
    name = "duplicate"

    def same_user(self, sender, category_id, location, conn=None):
        """This sender's open report of the same thing at the same place, or None."""
        if not sender or not category_id:
            return None
        wanted = tools._normalise_location(location)
        if wanted in tools.MISSING_LOCATIONS:
            return None
        since = datetime.now(timezone.utc) - timedelta(days=tools.duplicate_window_days(category_id))
        reference = tools.reporter_ref(sender)

        def work(c):
            rows = c.execute(
                "SELECT id, created_at, location, link_token FROM reports "
                "WHERE reporter_ref = ? AND category_id = ? AND status IN ('new', 'in_review') "
                "ORDER BY created_at DESC",
                (reference, category_id),
            ).fetchall()
            for row in rows:
                try:
                    created = datetime.fromisoformat(str(row["created_at"]))
                except (TypeError, ValueError):
                    continue
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if created < since:
                    continue
                if tools._same_place(tools._normalise_location(row["location"]), wanted):
                    return {"id": row["id"], "link": f"{tools.SITE_URL}/r/{row['link_token']}"}
            return None

        try:
            if conn is not None:
                return work(conn)
            handle = reports_db.connect()
            try:
                return work(handle)
            finally:
                handle.close()
        except sqlite3.Error as error:
            # A lookup that fails must never stop a report being saved.
            print(f"[duplicate] same-user check skipped: {error}")
            return None

    @staticmethod
    def same_problem(category_id, location, conn=None):
        """Someone else's open report this one should be linked to: tools.check_duplicate."""
        result = tools.check_duplicate(category_id, location, conn=conn)
        return result.get("duplicate_of") if result.get("ok") else None
