"""Every tunable number in one place. Values marked ASSUMED are placeholders a
council officer must confirm before any real use."""

import os
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# The bot's live database, opened read-only. Same variable the bot uses.
KERBSIDE_DB = Path(os.getenv("DB_PATH") or CODE / "kerbside.db")
# Everything the forecast writes lives here, never in the bot's database.
PREDICT_DB = Path(os.getenv("PREDICT_DB") or CODE / "predict.db")
FAKE_REPORTS = CODE.parent / "dashboard" / "fake_reports.json"

CITY_CENTRE = (50.9097, -1.4044)          # for city-wide weather only
WEATHER_CACHE = DATA / "weather_cache.json"
EVENTS_CSV = DATA / "events.csv"
ACTIONS_JSON = DATA / "preventive_actions.json"

# Synthetic history
SYNTH_WEEKS = 104
SYNTH_SEED = 2026

# Forecast
BASELINE_WEEKS = 4
HISTORY_WEEKS = 13
LOW_HISTORY = 3            # fewer distinct problems than this in 13 weeks: "not enough history"
HIGH_HISTORY = 10
MIN_SHOWN = 3              # counts below this are shown as "fewer than 3"
TOP_N = 10
TEST_WEEKS = 12
INTERVAL = 0.80            # Poisson prediction interval shown with each forecast
RISK_MIN_EXPECTED = 1.0    # expected problems next week before a risk card is raised

# Surge (model 7)
SURGE_WINDOWS_H = (24, 48, 72)
SURGE_P = 0.01
SURGE_MIN_COUNT = 3
SURGE_COOLDOWN_H = 72
FIXED_RULE = (3, 24)       # the simple comparison: 3 problems in 24 hours

# Seasons
LEAF_WEEKS = range(40, 49)          # roughly October and November
FROST_C = 0.0
STALE_HOURS = 24

# Priority parts. ASSUMED, confirm with the council.
HARM = {
    "glass_spillage_hazard": 1.6, "pothole": 1.5, "fly_tipping": 1.3, "dead_animal": 1.2,
    "illegal_parking": 1.1, "missed_bin": 1.0, "litter_street_cleaning": 1.0,
    "dog_fouling": 0.9, "graffiti_flyposting": 0.9,
}
HARM_DEFAULT = 1.0
CONFIDENCE_WEIGHT = {"high": 0.9, "medium": 0.7, "low": 0.0}

# Areas the synthetic history treats as student streets. ASSUMED.
STUDENT_AREAS = ("Portswood", "Portswood Park", "Highfield", "Swaythling", "Bevois Valley",
                 "St Denys", "The Polygon", "Glen Eyre")

# Which areas each kind of venue affects. ASSUMED, confirm with the council.
VENUE_AREAS = {
    "St Mary's Stadium": ("Northam", "Belvidere", "Chapel", "Bevois Valley"),
    "Cruise terminals": ("Eastern Docks", "Western Docks", "Ocean Village", "Old Town", "Below Bar"),
    "University halls and student streets": STUDENT_AREAS,
}

# Planted effects in the SYNTHETIC history (so the page can say what was planted).
PLANTED = {
    "leaf_fall": "litter x1.8 in October and November",
    "frost_rain": "potholes rise with frost nights and rain over the previous 14 days",
    "match_day": "litter x3 and parking x3 near the stadium on match day and the day after",
    "cruise_call": "litter x1.6 near the docks on cruise days",
    "university_move_out": "fly-tipping x4 and missed bins x3 in student areas for a week",
}
