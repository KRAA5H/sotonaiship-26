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
from flask import Blueprint, Flask, Response, current_app, jsonify, render_template, request

load_dotenv(Path(__file__).with_name(".env"))

import bb
import photo_features
import dashboard_categories
import priority
import reports_db
import tools
from graph.store import TaskStore

import loader  # noqa: E402  (agent/loader.py, on the path via tools)

WEB_DIR = Path(__file__).with_name("web")
# Same whitelist as photos.py: BlueBubbles converts on download, so only these two.
IMAGE_MIMES = ("image/jpeg", "image/png")
PHOTO_WIDTH = 1024
STEPS = (
    ("new", "Logged", "We have your report here. It has not gone to the council yet."),
    ("in_review", "In review", "It is being looked at on this dashboard."),
    ("resolved", "Resolved", "It is marked as resolved here."),
)

# Called with (report_id, status) after the council saves a status: the status
# agent texts the resident. Hooks run after the response is decided and must
# never fail the click.
STATUS_HOOKS = []

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


_GROUPS = {**{cid: c["group"] for cid, c in loader.load(tools.AGENT_DIR)[0].items()},
           **dashboard_categories.groups()}


def _labels():
    """Rulebook labels plus the dashboard-only ones for imported reports (D70)."""
    return {**tools.category_labels(), **dashboard_categories.labels()}


def _with_priority(reports):
    """Adds the priority score and its four factors to each report, on read.

    Photo features are validated again here, so the page only ever receives the
    fixed shape (or nothing), never raw model text and never a location.
    """
    for report in reports:
        report["photo_features"] = photo_features.from_stored(report.get("photo_features"))
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


@site.get("/t/<token>")
def task_page(token):
    task = TaskStore().get_by_token(token)
    if not task:
        return Response("No task found.", 404, mimetype="text/plain")
    fields = "".join(
        f"<li><b>{key}</b>: {value}</li>"
        for key, value in (task.get("fields") or {}).items())
    return Response(f"""<!doctype html><meta name="viewport" content="width=device-width">
    <title>Your task</title><body style="font:17px system-ui;max-width:36rem;margin:2rem auto;padding:0 1rem">
    <p>Southampton City Council</p><h1>{task['kind']} task</h1>
    <p>Status: <b>{task['status']}</b></p>
    <p>Reference: <b>{task.get('external_ref') or 'not created yet'}</b></p>
    <ul>{fields}</ul><p>This is a prepared case in the council sandbox. Nothing was submitted unless a reference says so.</p>
    </body>""", mimetype="text/html")


@site.get("/council/tasks")
def council_tasks():
    denied = _council_denied()
    if denied:
        return denied
    rows = TaskStore().all()
    body = "".join(
        f"<tr><td>{task['task_id']}</td><td>{task['kind']}</td><td>{task['status']}</td>"
        f"<td>{task.get('external_ref') or ''}</td><td>{task.get('fields') or {}}</td></tr>"
        for task in rows)
    return Response(f"""<!doctype html><title>Council tasks</title>
    <body style="font:16px system-ui;margin:2rem"><h1>Council tasks</h1>
    <p><a href="/council">Back to reports</a></p>
    <table border="1" cellpadding="6" cellspacing="0"><thead><tr>
    <th>Task</th><th>Kind</th><th>Status</th><th>Reference</th><th>Fields</th>
    </tr></thead><tbody>{body or '<tr><td colspan=5>No tasks yet.</td></tr>'}</tbody></table>
    </body>""", mimetype="text/html")


@site.get("/council")
def council():
    denied = _council_denied()
    if denied:
        return denied
    with _connect() as conn:
        reports = _with_priority(reports_db.council_reports(conn))
        stats = reports_db.summary_stats(conn)
    return render_template("council.html", reports=reports, stats=stats, labels=_labels())


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
    labels = _labels()
    rows = [
        ("generated_at", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("total_reports", stats["total"]),
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
        source = reports_db.council_photo_source(conn, report_id)
    not_found = Response("No photo for this report.", 404, mimetype="text/plain")
    if not source:
        return not_found

    if source["photo_guid"]:
        # The resident's real photo, fetched from BlueBubbles as photos.py does for
        # /r/<token>/photo. The guid never leaves the server.
        fetched = bb.download_attachment(source["photo_guid"], width=PHOTO_WIDTH)
        if not fetched:
            return not_found
        body, fetched_mime = fetched
        mime = next((m for m in ((source["photo_mime"] or "").split(";")[0].strip().lower(),
                                 (fetched_mime or "").split(";")[0].strip().lower())
                     if m in IMAGE_MIMES), None)
        if mime is None:
            return not_found
        response = Response(body, mimetype=mime)
    else:
        return not_found
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["Content-Disposition"] = "inline"
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
    for hook in STATUS_HOOKS:
        try:
            hook(report_id, status)
        except Exception as error:  # noqa: BLE001 - the status is saved either way
            print(f"[status] hook failed for {report_id}: {error}")
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
    return render_template("resident.html", report=report, steps=steps, description=description,
                           status_label=dict((k, t) for k, t, _ in STEPS).get(report["status"], report["status"]))


from predict.web import forecast  # noqa: E402  Forecast section, /council/forecast (code/predict/)
site.register_blueprint(forecast)


def create_app(db_path=None, council_password=None):
    app = Flask(__name__, static_folder=None)
    app.config["KERBSIDE_DB"] = db_path
    app.config["COUNCIL_PASSWORD"] = council_password
    app.register_blueprint(site)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("WEB_PORT") or "5006"), threaded=True)
