# --- The only function that needs changing in tools.py ---
# Add this import near the top, alongside "import reports_db":
#
#     from location import LocationService
#     _location_service = LocationService()
#
# Then replace save_report() with this version:

def save_report(category_id, location, description, severity=None, has_photo=False,
                reporter=None, conn=None):
    categories = _rulebook()[0]
    if category_id not in categories:
        return {"ok": False, "error": f"unknown category_id: {category_id}"}
    outcome = categories[category_id]["outcome"]
    if outcome != "council_report":
        return {"ok": False, "error": f"{category_id} is {outcome}: nothing is saved, "
                                      "point the resident to official guidance instead"}
    if not (location or "").strip():
        return {"ok": False, "error": "location is required: ask where the problem is"}
    if not (description or "").strip():
        return {"ok": False, "error": "description is required"}
    if severity is not None and severity not in SEVERITIES:
        return {"ok": False, "error": f"severity must be one of {', '.join(SEVERITIES)}"}

    # Geocode BEFORE opening the transaction - this is a network call, and
    # holding BEGIN IMMEDIATE (a write lock on the whole file) while waiting
    # on Nominatim would block every other writer for no reason. If the
    # lookup fails or finds nothing, area stays None - never block saving
    # the report itself on a geocoding miss.
    area = None
    try:
        geocoded = _location_service.forward_geocode(location)
        if geocoded:
            area = geocoded.get("area")
    except Exception as error:  # noqa: BLE001 - geocoding must never block a save
        print(f"[geocode] forward_geocode failed for {location!r}: {error}")

    def work(c):
        # IMMEDIATE takes the write lock now, so two webhooks cannot pick the same id.
        c.execute("BEGIN IMMEDIATE")
        try:
            duplicate = check_duplicate(category_id, location, conn=c)
            last = c.execute(
                "SELECT MAX(CAST(SUBSTR(id, 3) AS INTEGER)) FROM reports WHERE id LIKE 'R-%'"
            ).fetchone()[0]
            report_id = f"R-{(last or 0) + 1:04d}"
            link_token = secrets.token_urlsafe(12)
            c.execute(
                "INSERT INTO reports (id, created_at, category_id, status, severity, location, "
                "area, description, has_photo, duplicate_of, reporter_ref, link_token) "
                "VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report_id,
                    _now().isoformat(timespec="seconds"),
                    category_id,
                    severity,
                    location.strip(),
                    area,
                    description.strip(),
                    int(bool(has_photo)),
                    duplicate["duplicate_of"],
                    _reporter_ref(reporter),
                    link_token,
                ),
            )
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        return {
            "ok": True,
            "report_id": report_id,  # internal: never put this in a resident link
            "link_token": link_token,
            "link": f"{SITE_URL}/r/{link_token}",
            "area": area,
            "duplicate_of": duplicate["duplicate_of"],
            "matching_reports": duplicate["matching_reports"],
        }

    return _with_conn(conn, work)
