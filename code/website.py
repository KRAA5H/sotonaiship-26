"""The website: one site, two views, both reading kerbside.db.

  /council        staff dashboard, every report, status buttons. Password only.
  /r/<token>      one resident's own report, found by its link_token. Nothing else.

reporter_ref is never sent to either page. The report id never appears on the
resident page or in its link.

The views live on a Blueprint so the webhook server can serve them on the same
port (blue_bubbles.py registers it), which is what SITE_URL points at. For
working on the pages alone:
  python code/website.py           serves on WEB_PORT (default 5006)

Set COUNCIL_PASSWORD in code/.env. Without it /council is switched off rather
than left open.
"""

import csv
import hmac
import io
import os
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, current_app, jsonify, render_template, request, send_file

load_dotenv(Path(__file__).with_name(".env"))

import priority
import reports_db
import tools

import loader  # noqa: E402  (agent/loader.py, on the path via tools)

WEB_DIR = Path(__file__).with_name("web")
# Report photos. Never under WEB_DIR/static: only /council/photos/<id> serves them.
PHOTO_DIR = Path(__file__).with_name("photos")
PHOTO_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
               ".gif": "image/gif"}
STEPS = (
    ("new", "Received", "We have your report."),
    ("in_review", "In review", "A council officer is looking at it."),
    ("resolved", "Resolved", "The council has closed this report."),
)
SYNTHETIC_PREFIX = "Synthetic example: "

site = Blueprint(
    "website",
    __name__,
    template_folder=str(WEB_DIR / "templates"),
    static_folder=str(WEB_DIR / "static"),
    static_url_path="/assets",
)


@site.record_once
def _init_db(state):
    reports_db.init_db(state.app.config.get("KERBSIDE_DB"))


@site.app_template_filter("ukdate")
def _ukdate(iso_day):
    """'2026-10-17' -> '17 Oct 2026', as the prototype shows it."""
    day = datetime.strptime(iso_day, "%Y-%m-%d")
    return f"{day.day} {day:%b %Y}"


_GROUPS = {cid: c["group"] for cid, c in loader.load(tools.AGENT_DIR)[0].items()}


def _with_priority(reports):
    """Adds the priority score and its four factors to each report, on read."""
    scores = priority.score_all(reports, _GROUPS)
    for report in reports:
        report["priority"] = scores[report["id"]]
    return reports


def _connect():
    return closing(reports_db.connect(current_app.config.get("KERBSIDE_DB")))


@site.after_request
def _private_headers(response):
    # A resident's token is the only key to their report: keep it out of
    # caches, Referer headers and search engines.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# ---------------------------------------------------------------------------
# Council
# ---------------------------------------------------------------------------
def _council_password():
    return (current_app.config.get("COUNCIL_PASSWORD") or os.getenv("COUNCIL_PASSWORD") or "").strip()


def _council_denied():
    """None if the request may see /council, else the response to send."""
    password = _council_password()
    if not password:
        return Response("The council view is off. Set COUNCIL_PASSWORD in code/.env.", 503,
                        mimetype="text/plain")
    auth = request.authorization
    given = (auth.password or "") if auth and auth.type == "basic" else ""
    if hmac.compare_digest(given.encode(), password.encode()):
        return None
    return Response("Council staff only.", 401, {"WWW-Authenticate": 'Basic realm="council"'},
                    mimetype="text/plain")


@site.get("/council")
def council():
    denied = _council_denied()
    if denied:
        return denied
    with _connect() as conn:
        reports = _with_priority(reports_db.council_reports(conn))
        stats = reports_db.summary_stats(conn)
    return render_template("council.html", reports=reports, stats=stats, labels=tools.category_labels())


@site.get("/council/reports.json")
def council_reports_json():
    """Polled every 15 seconds by /council. Same columns as the page: no reporter_ref."""
    denied = _council_denied()
    if denied:
        return denied
    with _connect() as conn:
        return jsonify({"ok": True, "reports": _with_priority(reports_db.council_reports(conn)),
                        "stats": reports_db.summary_stats(conn)})


@site.get("/council/stats.csv")
def council_stats_csv():
    """The same figures as the strip on /council, one per row, for NUMBERS.md."""
    denied = _council_denied()
    if denied:
        return denied
    with _connect() as conn:
        stats = reports_db.summary_stats(conn)
    labels = tools.category_labels()
    rows = [
        ("generated_at", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("total_reports", stats["total"]),
        ("synthetic_reports", stats["synthetic"]),
        ("open_reports", stats["open"]),
        *((f"open_severity_{level.replace(' ', '_')}", n) for level, n in stats["open_by_severity"].items()),
        *((f"open_category_{cid}", n) for cid, n in stats["open_by_category"].items()),
        ("reports_with_photo", stats["with_photo"]),
        ("duplicates_caught", stats["duplicates_caught"]),
        ("reports_with_a_status_change", stats["first_change_count"]),
        ("avg_hours_to_first_status_change", "" if stats["first_change_avg_hours"] is None
         else stats["first_change_avg_hours"]),
    ]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(("metric", "value", "label"))
    for metric, value in rows:
        label = labels.get(metric[len("open_category_"):], "") if metric.startswith("open_category_") else ""
        writer.writerow((metric, value, label))
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="council-stats.csv"'})


@site.get("/council/photos/<report_id>")
def council_photo(report_id):
    """A report's photo, for council staff only."""
    denied = _council_denied()
    if denied:
        return denied
    with _connect() as conn:
        relative = reports_db.photo_path(conn, report_id)
    root = Path(current_app.config.get("PHOTO_DIR") or PHOTO_DIR).resolve()
    path = (root / relative).resolve() if relative else None
    # Only image files inside the photo folder, whatever the database says.
    if (not path or root not in path.parents or not path.is_file()
            or path.suffix.lower() not in PHOTO_TYPES):
        return Response("No photo for this report.", 404, mimetype="text/plain")
    response = send_file(path, mimetype=PHOTO_TYPES[path.suffix.lower()])
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


@site.post("/council/reports/<report_id>/status")
def set_status(report_id):
    denied = _council_denied()
    if denied:
        return denied
    # A cross-site form cannot send JSON with a custom header, so this blocks
    # CSRF even though the browser caches the Basic credentials.
    if not request.is_json or request.headers.get("X-Requested-With") != "kerbside":
        return jsonify({"ok": False, "error": "send JSON from the council page"}), 400
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in reports_db.STATUSES:
        return jsonify({"ok": False, "error": f"status must be one of {', '.join(reports_db.STATUSES)}"}), 400
    with _connect() as conn:
        if not reports_db.set_status(conn, report_id, status):
            return jsonify({"ok": False, "error": "no such report"}), 404
    return jsonify({"ok": True, "id": report_id, "status": status})


# ---------------------------------------------------------------------------
# Resident
# ---------------------------------------------------------------------------
@site.get("/r/<token>")
def resident(token):
    with _connect() as conn:
        # get_report_status returns only this report's own fields, never the
        # id or reporter_ref, so the page cannot show anything else.
        report = tools.get_report_status(token, conn=conn)
    if not report["ok"]:
        return render_template("resident.html", report=None), 404

    reached = [key for key, _, _ in STEPS].index(report["status"]) if report["status"] in reports_db.STATUSES else 0
    steps = [{"title": title, "text": text, "done": i <= reached} for i, (_, title, text) in enumerate(STEPS)]
    description = report["description"] or ""
    if description.startswith(SYNTHETIC_PREFIX):
        description = description[len(SYNTHETIC_PREFIX):]
    return render_template("resident.html", report=report, steps=steps, description=description,
                           status_label=dict((k, t) for k, t, _ in STEPS).get(report["status"], report["status"]))


def create_app(db_path=None, council_password=None, photo_dir=None):
    app = Flask(__name__, static_folder=None)
    app.config["KERBSIDE_DB"] = db_path
    app.config["COUNCIL_PASSWORD"] = council_password
    app.config["PHOTO_DIR"] = photo_dir
    app.register_blueprint(site)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("WEB_PORT") or "5006"), threaded=True)
