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

import hmac
import os
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, current_app, jsonify, render_template, request

load_dotenv(Path(__file__).with_name(".env"))

import reports_db
import tools

WEB_DIR = Path(__file__).with_name("web")
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
        reports = reports_db.council_reports(conn)
    return render_template("council.html", reports=reports, labels=tools.category_labels())


@site.get("/council/reports.json")
def council_reports_json():
    """Polled every 15 seconds by /council. Same columns as the page: no reporter_ref."""
    denied = _council_denied()
    if denied:
        return denied
    with _connect() as conn:
        return jsonify({"ok": True, "reports": reports_db.council_reports(conn)})


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


def create_app(db_path=None, council_password=None):
    app = Flask(__name__, static_folder=None)
    app.config["KERBSIDE_DB"] = db_path
    app.config["COUNCIL_PASSWORD"] = council_password
    app.register_blueprint(site)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("WEB_PORT") or "5006"), threaded=True)
