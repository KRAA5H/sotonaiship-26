"""The resident's own photo, served from the BlueBubbles attachment store.

  GET /r/<link_token>/photo   that report's photo, and only that one

The link token is the only key. The attachment guid never leaves this module: it
is not in a URL, not in a header and not in the page. An unknown token or a
report with no photo is a 404, never a 403, so the answer says nothing about
which tokens exist.

The photo bytes stay in BlueBubbles; reports_db keeps the guid and the mime type.
This module is a Blueprint nested inside website.site, so the webhook server
serves it on the same port under the same private headers, and website.py needs
no edit. Registering inside the parent blueprint at import time only works if
this module is imported before website.site is registered on an app, so
blue_bubbles.py imports it before create_app/register_blueprint runs.
"""

import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Blueprint, Response, current_app

import bb
import reports_db
from website import site

TOKEN_MIN, TOKEN_MAX = 8, 64
# BlueBubbles converts on download, so these two are the only types we will serve.
IMAGE_MIMES = ("image/jpeg", "image/png")
PHOTO_WIDTH = 1024

photo_site = Blueprint("photos", __name__)


def _not_found():
    """One answer for both a bad token and a missing photo: nothing to learn here."""
    return Response("No photo for that link.", 404, mimetype="text/plain")


def _image_mime(*candidates):
    """The first whitelisted image type, so nothing else can be served as an image."""
    for mime in candidates:
        mime = (mime or "").split(";")[0].strip().lower()
        if mime in IMAGE_MIMES:
            return mime
    return None


@photo_site.get("/r/<token>/photo")
def photo(token):
    if not TOKEN_MIN <= len(token) <= TOKEN_MAX:
        return _not_found()

    with closing(reports_db.connect(current_app.config.get("KERBSIDE_DB"))) as conn:
        row = conn.execute(
            "SELECT photo_guid, photo_mime FROM reports WHERE link_token = ?", (token,)
        ).fetchone()
    if row is None or not row["photo_guid"]:
        return _not_found()

    fetched = bb.download_attachment(row["photo_guid"], width=PHOTO_WIDTH)
    if not fetched:
        return _not_found()
    body, fetched_mime = fetched
    # The stored type is what the message carried; the download's type covers a
    # server that answers application/octet-stream instead.
    mime = _image_mime(row["photo_mime"], fetched_mime)
    if mime is None:
        return _not_found()

    response = Response(body, mimetype=mime)
    # Set here as well as in website._private_headers: this response is bytes from
    # someone's phone, so the private headers travel with it either way.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = "inline"
    return response


# Nested on the existing site blueprint: same port, same private headers, and the
# route appears wherever /r/<token> already does.
try:
    site.register_blueprint(photo_site)
except AssertionError as error:
    # website.site was registered on an app before this module was imported (a test
    # that builds an app first, then imports the webhook server), or this module was
    # imported twice. The route is then missing from that app only; say so, do not crash.
    if "already been registered" not in str(error):
        raise
    print("[photos] website.site was already registered: /r/<token>/photo not added")
