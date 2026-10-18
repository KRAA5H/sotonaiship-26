"""Daily city-wide weather from Open-Meteo, cached to a file with the fetch time.

Open-Meteo is free for non-commercial use with no key; a council deployment
would need its commercial plan or the Met Office DataHub. If the network is
down the cache is used, and if there is no cache the model runs without
weather and the page says so. Cached data is never shown as live.
"""

import json
from datetime import date, datetime, timedelta, timezone

import requests

from . import config

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
FIELDS = "precipitation_sum,temperature_2m_min,wind_speed_10m_max"
SOURCE = "Open-Meteo (open-meteo.com), CC BY 4.0, city centre point"
HEADERS = {"User-Agent": "Kerbside-predict/1.0 (SotonShip 2026 hackathon prototype)"}


def _get(url, params):
    response = requests.get(url, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    daily = response.json()["daily"]
    return {day: {"rain": rain or 0.0, "tmin": tmin, "wind": wind}
            for day, rain, tmin, wind in zip(daily["time"], daily["precipitation_sum"],
                                             daily["temperature_2m_min"], daily["wind_speed_10m_max"])}


def load_cache():
    try:
        return json.loads(config.WEATHER_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def refresh(start, end, forecast_days=8):
    """Fetch history start..end plus the forecast, merge into the cache. Returns the cache."""
    lat, lng = config.CITY_CENTRE
    base = {"latitude": lat, "longitude": lng, "daily": FIELDS, "timezone": "Europe/London"}
    cache = load_cache() or {"source": SOURCE, "days": {}, "forecast": {}}
    try:
        cache["days"].update(_get(ARCHIVE, {**base, "start_date": start.isoformat(),
                                            "end_date": end.isoformat()}))
        cache["history_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cache["forecast"] = _get(FORECAST, {**base, "forecast_days": forecast_days})
        cache["forecast_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cache["source"] = SOURCE
        config.WEATHER_CACHE.parent.mkdir(parents=True, exist_ok=True)
        config.WEATHER_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except (requests.RequestException, KeyError, ValueError) as error:
        cache["last_error"] = str(error)[:200]
    return cache if cache["days"] else None


def daily(cache):
    """{date: {rain, tmin, wind}} for history and forecast together; forecast wins only for future days."""
    if not cache:
        return {}
    out = {date.fromisoformat(k): v for k, v in cache.get("days", {}).items()}
    for k, v in (cache.get("forecast") or {}).items():
        out.setdefault(date.fromisoformat(k), v)
    return out


def window(days, end, length):
    """Total rain and frost nights over the `length` days ending the day before `end`."""
    rain = frost = 0.0
    seen = 0
    for i in range(1, length + 1):
        d = days.get(end - timedelta(days=i))
        if not d:
            continue
        seen += 1
        rain += d["rain"] or 0.0
        frost += 1 if (d["tmin"] is not None and d["tmin"] <= config.FROST_C) else 0
    return (rain, frost) if seen else (None, None)
