"""Location service.

Every resident goes through the same location link before their report
continues. This file turns real GPS coordinates into a street name,
postcode, and which of Southampton's named areas (Shirley, Bitterne,
Portswood-style neighbourhoods) the report falls into.

Uses OpenStreetMap's free Nominatim service - real, public, dated data,
no API key required.
"""

import time
from typing import Optional

import requests

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
# Nominatim's usage policy requires a real, descriptive User-Agent and asks
# for at most 1 request per second - both followed below.
HEADERS = {"User-Agent": "SotonShip26-StreetReportTriage/1.0 (hackathon demo)"}

# The 30 named areas of Southampton, used to match whatever OSM calls the
# neighbourhood against a recognisable, consistent list - so the dashboard
# groups reports by "Shirley" every time, not sometimes "Shirley" and
# sometimes "Shirley, Southampton".
SOUTHAMPTON_AREAS = [
    "Avenue Campus", "Bassett Green", "Bevois Valley", "Bitterne", "Bitterne Manor",
    "Boldrewood Innovation Campus", "Highfield Campus", "Highfield", "Holyrood",
    "Itchen Ferry", "Lordshill", "Lordswood", "Mansbridge", "Maybush", "Midanbury",
    "Millbrook", "Nicholstown", "Northam", "Ocean Village", "Peartree Green",
    "The Polygon", "Portswood", "Regents Park", "St Denys", "St Mary's", "Shirley",
    "Sholing", "Southampton City Centre", "Thornhill", "Townhill Park", "Weston",
    # Portswood is a real, well-known Southampton area that the original
    # 30-item Wikipedia category list happened to omit - added here so
    # real geocoded reports and the synthetic seed data use the same name.
]


def _match_area(candidate: Optional[str]) -> Optional[str]:
    """Matches whatever OSM calls the neighbourhood against the official
    list, case-insensitively. Falls back to the raw OSM name if it isn't
    one of the 30 (still a real area, just not on this particular list),
    or None if nothing came back at all."""
    if not candidate:
        return None
    candidate_lower = candidate.lower()
    for area in SOUTHAMPTON_AREAS:
        if area.lower() in candidate_lower or candidate_lower in area.lower():
            return area
    return candidate


class LocationService:
    def __init__(self):
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Nominatim's free tier asks for max 1 request/second - this just
        waits if we're calling it too fast, rather than risk getting
        temporarily blocked mid-demo."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def reverse_geocode(self, latitude: float, longitude: float) -> dict:
        """Turns real coordinates into a street name, postcode, and
        matched Southampton area."""
        self._rate_limit()
        params = {"lat": latitude, "lon": longitude, "format": "json"}
        response = requests.get(f"{NOMINATIM_BASE}/reverse", params=params, headers=HEADERS, timeout=10)
        data = response.json()
        address = data.get("address", {})

        street_name = address.get("road") or address.get("pedestrian") or address.get("neighbourhood")
        postcode = address.get("postcode")

        # OSM's hierarchy varies by location - try the most specific
        # neighbourhood-level fields first, falling back to broader ones.
        area_candidate = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("quarter")
            or address.get("city_district")
        )
        area = _match_area(area_candidate)

        return {
            "street_name": street_name,
            "postcode": postcode,
            "area": area,
            "latitude": latitude,
            "longitude": longitude,
        }

    def forward_geocode(self, description: str) -> Optional[dict]:
        """Turns a text description into coordinates, street name,
        postcode and area. Kept as a fallback for the rare case a
        resident's location permission is denied and they type an
        address instead."""
        self._rate_limit()
        params = {
            "q": f"{description}, Southampton, UK",
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
        }
        response = requests.get(f"{NOMINATIM_BASE}/search", params=params, headers=HEADERS, timeout=10)
        results = response.json()

        if not results:
            return None

        result = results[0]
        address = result.get("address", {})
        area_candidate = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("quarter")
            or address.get("city_district")
        )

        return {
            "street_name": address.get("road") or address.get("pedestrian"),
            "postcode": address.get("postcode"),
            "area": _match_area(area_candidate),
            "latitude": float(result["lat"]),
            "longitude": float(result["lon"]),
        }


if __name__ == "__main__":
    service = LocationService()
    print("Reverse geocoding a known Southampton point (50.9097, -1.4044):")
    print(service.reverse_geocode(50.9097, -1.4044))
