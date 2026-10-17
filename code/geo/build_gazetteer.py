"""Build Southampton's boundary and street list from OpenStreetMap. Run once.

  southampton_boundary.json   the city council's boundary (GSS E06000045), simplified
  southampton_streets.json    every named street, one entry per stretch, with its area

Both come from the Overpass API in one polite request each (named user agent,
the query asks for nothing else). The data is OpenStreetMap, (c) OpenStreetMap
contributors, under the Open Database Licence; credit is on the map page and in
the README. Nothing personal is in either file.

Run: python code/geo/build_gazetteer.py                  both files
     python code/geo/build_gazetteer.py --streets-only  street list only
"""

import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Kerbside/1.0 (SotonShip 2026 hackathon; +https://github.com/KRAA5H/sotonaiship-26)"
GSS = "E06000045"  # Southampton, unitary authority

CLUSTER_METRES = 700     # two stretches of one name further apart are two streets
SIMPLIFY_DEGREES = 0.00012  # about 10 m: plenty for "is this pin in the city"
AREA_PLACES = ("suburb", "quarter", "neighbourhood", "village")


def overpass(query, tries=4):
    """One query, retried with a growing pause when the shared server is busy."""
    for attempt in range(1, tries + 1):
        request = urllib.request.Request(
            OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 502, 503, 504) or attempt == tries:
                raise
            pause = 20 * attempt
            print(f"overpass busy ({error.code}), waiting {pause}s")
            time.sleep(pause)


def metres(a, b):
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians((a[0] + b[0]) / 2))
    dy = (a[0] - b[0]) * 110540
    return math.hypot(dx, dy)


# ---------------------------------------------------------------------------
# Boundary: join the relation's outer ways into closed rings
# ---------------------------------------------------------------------------
def rings(members, role):
    pieces = [[(round(p["lat"], 6), round(p["lon"], 6)) for p in m["geometry"]]
              for m in members if m.get("type") == "way" and m.get("role") == role and m.get("geometry")]
    out = []
    while pieces:
        ring = pieces.pop(0)
        grew = True
        while ring[0] != ring[-1] and grew:
            grew = False
            for i, piece in enumerate(pieces):
                if piece[0] == ring[-1]:
                    ring += piece[1:]
                elif piece[-1] == ring[-1]:
                    ring += piece[-2::-1]
                elif piece[-1] == ring[0]:
                    ring = piece[:-1] + ring
                elif piece[0] == ring[0]:
                    ring = piece[:0:-1] + ring
                else:
                    continue
                pieces.pop(i)
                grew = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            out.append(ring)
    return out


def simplify(points, tolerance):
    """Douglas-Peucker on (lat, lng) pairs."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    best, index = 0.0, 0
    for i in range(1, len(points) - 1):
        p = points[i]
        if start == end:
            d = math.hypot(p[0] - start[0], p[1] - start[1])
        else:
            num = abs((end[0] - start[0]) * (start[1] - p[1]) - (start[0] - p[0]) * (end[1] - start[1]))
            d = num / math.hypot(end[0] - start[0], end[1] - start[1])
        if d > best:
            best, index = d, i
    if best <= tolerance:
        return [start, end]
    return simplify(points[:index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def build_boundary():
    data = overpass(f'[out:json][timeout:90];relation["boundary"="administrative"]["ref:gss"="{GSS}"];out geom;')
    relation = next(e for e in data["elements"] if e["type"] == "relation")
    outer = [simplify(r, SIMPLIFY_DEGREES) for r in rings(relation["members"], "outer")]
    inner = [simplify(r, SIMPLIFY_DEGREES) for r in rings(relation["members"], "inner")]
    if not outer:
        raise SystemExit("no closed outer ring in the boundary relation")
    return {
        "name": relation["tags"].get("name"),
        "gss": GSS,
        "osm_relation": relation["id"],
        "source": "OpenStreetMap via Overpass API, (c) OpenStreetMap contributors, ODbL",
        "fetched": time.strftime("%Y-%m-%d"),
        "outer": [[[round(a, 5), round(b, 5)] for a, b in r] for r in outer],
        "inner": [[[round(a, 5), round(b, 5)] for a, b in r] for r in inner],
    }


# ---------------------------------------------------------------------------
# Streets: every named highway inside the city, clustered by name
# ---------------------------------------------------------------------------
def build_streets():
    query = (
        "[out:json][timeout:180];"
        f'relation["boundary"="administrative"]["ref:gss"="{GSS}"];map_to_area->.a;'
        '(way(area.a)["highway"]["name"];)->.roads;'
        f'(node(area.a)["place"~"^({"|".join(AREA_PLACES)})$"]["name"];)->.places;'
        ".roads out tags center qt;.places out qt;"
    )
    data = overpass(query)
    places = [(e["lat"], e["lon"], e["tags"]["name"], e["tags"].get("place"))
              for e in data["elements"] if e["type"] == "node"]
    stretches = {}
    for e in data["elements"]:
        if e["type"] != "way" or "center" not in e:
            continue
        tags = e.get("tags") or {}
        if tags.get("highway") in ("platform", "construction", "proposed", "bus_stop", "elevator"):
            continue
        name = " ".join(tags["name"].split())
        stretches.setdefault(name, []).append((e["center"]["lat"], e["center"]["lon"]))

    def area_for(point):
        best = None
        for lat, lng, name, kind in places:
            d = metres(point, (lat, lng))
            # A suburb label reaches further than a neighbourhood one.
            reach = 2500 if kind == "suburb" else 1200
            if d <= reach and (best is None or d < best[0]):
                best = (d, name)
        return best[1] if best else ""

    streets = []
    for name, points in stretches.items():
        clusters = []
        for p in points:
            for c in clusters:
                if metres(p, c["mean"]) <= CLUSTER_METRES:
                    c["points"].append(p)
                    n = len(c["points"])
                    c["mean"] = (sum(q[0] for q in c["points"]) / n, sum(q[1] for q in c["points"]) / n)
                    break
            else:
                clusters.append({"points": [p], "mean": p})
        for c in clusters:
            # The stretch closest to the cluster's middle, so the pin lands on the road itself.
            anchor = min(c["points"], key=lambda q: metres(q, c["mean"]))
            streets.append([name, area_for(anchor), round(anchor[0], 5), round(anchor[1], 5)])
    streets.sort(key=lambda s: (s[0].lower(), s[1]))
    return streets


def main():
    if "--streets-only" not in sys.argv:
        boundary = build_boundary()
        (HERE / "southampton_boundary.json").write_text(json.dumps(boundary, separators=(",", ":")),
                                                        encoding="utf-8")
        print(f"boundary: {boundary['name']}, {sum(len(r) for r in boundary['outer'])} points in "
              f"{len(boundary['outer'])} outer ring(s)")
        time.sleep(5)  # be kind to the shared Overpass server
    streets = build_streets()
    payload = {
        "source": "OpenStreetMap via Overpass API, (c) OpenStreetMap contributors, ODbL",
        "fetched": time.strftime("%Y-%m-%d"),
        "fields": ["name", "area", "lat", "lng"],
        "streets": streets,
    }
    (HERE / "southampton_streets.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"streets: {len(streets)} stretches, {len({s[0] for s in streets})} names")


if __name__ == "__main__":
    main()
