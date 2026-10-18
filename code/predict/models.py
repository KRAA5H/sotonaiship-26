"""Hotspot forecast (model 4): distinct problems per street and category next week.

The panel is street x category x week. Every feature on a row uses only data up
to the end of that week, or calendar facts known in advance (week of year,
leaf-fall window, scheduled events). The target is the next week. Forecast rain
is NOT a feature: we have no archive of past forecasts, and using the rain that
actually fell would leak the future into the test.

  baseline   mean of the last 4 weeks (always shown, every model is compared to it)
  shrunk     empirical Bayes rate pulled toward the city average for the category,
             so a street with 2 reports in 2 weeks does not look hot by luck
  model      HistGradientBoostingRegressor(loss="poisson"), one pooled model with
             the category as a feature
"""

import os
from datetime import timedelta

# One thread: parallel OpenMP in the gradient booster has stalled on Windows
# runs here, and the whole batch takes about a minute single-threaded anyway.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd
from scipy.stats import poisson
from sklearn.ensemble import HistGradientBoostingRegressor

from . import config, events as ev, weather

FEATURES = ["y", "r4", "r13", "r52", "since_last", "shrunk", "rain7", "frost7", "rain14", "frost14",
            "woy", "leaf", "ev_match", "ev_cruise", "ev_moveout", "ev_other", "cat_code"]


def build_panel(problems, weather_days, events, last_week):
    """DataFrame, one row per (street, category, week) for every pair ever seen."""
    located = [p for p in problems if p.get("street")]
    if not located:
        return pd.DataFrame()
    df = pd.DataFrame({"street": [p["street"] for p in located], "area": [p["area"] for p in located],
                       "category": [p["category"] for p in located],
                       "week": [p["day"] - timedelta(days=p["day"].weekday()) for p in located],
                       "synthetic": [p["synthetic"] for p in located]})
    area = df.groupby("street")["area"].agg(lambda s: s.dropna().mode().iat[0] if s.notna().any() else None)
    synthetic = df.groupby(["street", "category"])["synthetic"].max()
    counts = df.groupby(["street", "category", "week"]).size()
    first = df["week"].min()
    weeks = pd.date_range(first, last_week, freq="7D").date
    pairs = counts.index.droplevel("week").unique()
    index = pd.MultiIndex.from_tuples([(s, c, w) for s, c in pairs for w in weeks],
                                      names=["street", "category", "week"])
    panel = counts.reindex(index, fill_value=0).rename("y").reset_index()
    panel["area"] = panel["street"].map(area)
    panel["synthetic"] = [synthetic.get((s, c), 1) for s, c in zip(panel["street"], panel["category"])]

    g = panel.groupby(["street", "category"], sort=False)["y"]
    panel["r4"] = g.transform(lambda s: s.rolling(config.BASELINE_WEEKS, min_periods=1).mean())
    panel["r13"] = g.transform(lambda s: s.rolling(config.HISTORY_WEEKS, min_periods=1).sum())
    panel["r52"] = g.transform(lambda s: s.rolling(52, min_periods=1).mean())
    panel["since_last"] = g.transform(_weeks_since_last)
    panel["target"] = g.shift(-1)
    panel["target_week"] = [w + timedelta(days=7) for w in panel["week"]]
    panel["shrunk"] = _shrink(panel)

    # Weather up to the day before the target week starts: known at forecast time.
    wk = {}
    for w in set(panel["target_week"]):
        r7, f7 = weather.window(weather_days, w, 7)
        r14, f14 = weather.window(weather_days, w, 14)
        wk[w] = (r7, f7, r14, f14)
    for i, name in enumerate(("rain7", "frost7", "rain14", "frost14")):
        panel[name] = [wk[w][i] for w in panel["target_week"]]

    panel["woy"] = [w.isocalendar()[1] for w in panel["target_week"]]
    panel["leaf"] = panel["woy"].isin(list(config.LEAF_WEEKS)).astype(int)
    _event_flags(panel, events)
    panel["cat_code"] = panel["category"].astype("category").cat.codes
    return panel


def _weeks_since_last(series):
    out, gap = [], 99
    for value in series:
        gap = 0 if value > 0 else min(gap + 1, 99)
        out.append(gap)
    return pd.Series(out, index=series.index)


def _shrink(panel):
    """Gamma-Poisson shrinkage of the 13-week rate toward the category's city mean, per week."""
    rate = panel["r13"] / config.HISTORY_WEEKS
    out = pd.Series(index=panel.index, dtype=float)
    for _, idx in panel.groupby(["category", "week"]).groups.items():
        r = rate.loc[idx]
        m, v = r.mean(), r.var(ddof=0)
        excess = v - m / config.HISTORY_WEEKS
        k = float(np.clip(m / excess, 1, 52)) if excess > 0 else 52.0   # prior strength in weeks
        out.loc[idx] = (panel.loc[idx, "r13"] + k * m) / (config.HISTORY_WEEKS + k)
    return out


def _event_flags(panel, events):
    by_area = {}
    for e in events:
        if e["coverage"] != "inside" or not e["areas"]:
            continue
        for day in ev.event_days(e):
            wk = day - timedelta(days=day.weekday())
            for a in e["areas"]:
                key = (a, wk)
                cur = by_area.setdefault(key, {"match_day": 0.0, "cruise_call": 0.0,
                                               "university_move_out": 0.0, "other": 0.0})
                kind = e["type"] if e["type"] in cur else "other"
                cur[kind] = max(cur[kind], ev.weight(e))
    empty = {"match_day": 0.0, "cruise_call": 0.0, "university_move_out": 0.0, "other": 0.0}
    flags = [by_area.get((a, w), empty) for a, w in zip(panel["area"], panel["target_week"])]
    panel["ev_match"] = [f["match_day"] for f in flags]
    panel["ev_cruise"] = [f["cruise_call"] for f in flags]
    panel["ev_moveout"] = [f["university_move_out"] for f in flags]
    panel["ev_other"] = [f["other"] for f in flags]


def _model(n_rows, features):
    # Small training sets (a new deployment, a test) need smaller leaves to fit at all.
    leaf = int(min(40, max(2, n_rows // 20)))
    return HistGradientBoostingRegressor(loss="poisson", max_iter=200, learning_rate=0.08,
                                         max_leaf_nodes=31, min_samples_leaf=leaf, early_stopping=False,
                                         categorical_features=[f == "cat_code" for f in features],
                                         random_state=config.SYNTH_SEED)


def fit(train):
    """Columns with no values at all (no weather when the fetch failed) are left out, not faked."""
    features = [f for f in FEATURES if train[f].notna().any()]
    model = _model(len(train), features)
    model.fit(train[features], train["target"])
    model.kerbside_features = features
    return model


def predict(model, rows):
    return model.predict(rows[model.kerbside_features])


def confidence(r13):
    if r13 < config.LOW_HISTORY:
        return "low"
    return "high" if r13 >= config.HIGH_HISTORY else "medium"


def interval(mu):
    tail = (1 - config.INTERVAL) / 2
    return int(poisson.ppf(tail, mu)), int(poisson.ppf(1 - tail, mu))


# ---------------------------------------------------------------------------
# Time-based backtest: rolling origin, never a random split
# ---------------------------------------------------------------------------
def backtest(panel, test_weeks=config.TEST_WEEKS, top_n=config.TOP_N, seed=config.SYNTH_SEED):
    known = panel.dropna(subset=["target"])
    # The latest week may still be in progress: never score a forecast against a half week.
    known = known[known["target_week"] < panel["week"].max()]
    targets = sorted(known["target_week"].unique())[-test_weeks:]
    rows, details = [], []
    for t in targets:
        train = known[known["target_week"] < t]
        test = known[known["target_week"] == t].copy()
        if train.empty or test.empty:
            continue
        test["pred"] = predict(fit(train), test)
        test["base"] = test["r4"]
        details.append(test[["street", "category", "target_week", "pred", "base", "target"]])
        street = test.groupby("street")[["target", "pred", "base"]].sum()
        total = street["target"].sum()
        if total == 0:
            continue
        cap = lambda col: street.nlargest(top_n, col)["target"].sum() / total  # noqa: E731
        rows.append({
            "week": t, "actual": float(total),
            "model": cap("pred"), "baseline": cap("base"), "best": cap("target"),
            "random": min(1.0, top_n / len(street)),
            "mae_model": float((test["pred"] - test["target"]).abs().mean()),
            "mae_baseline": float((test["base"] - test["target"]).abs().mean()),
            "dev_model": _deviance(test["target"], test["pred"]),
            "dev_baseline": _deviance(test["target"], test["base"]),
        })
    if not rows:
        return None
    res = pd.DataFrame(rows)
    lead = (res["model"] - res["baseline"]).to_numpy()
    rng = np.random.default_rng(seed)
    boots = [rng.choice(lead, size=len(lead), replace=True).mean() for _ in range(2000)]
    return {
        "test_from": str(res["week"].min()), "test_to": str(res["week"].max()), "weeks": len(res),
        "top_n": top_n,
        "capture": {k: round(float(res[k].mean()), 3) for k in ("model", "baseline", "random", "best")},
        "mae": {"model": round(float(res["mae_model"].mean()), 3),
                "baseline": round(float(res["mae_baseline"].mean()), 3)},
        "deviance": {"model": round(float(res["dev_model"].mean()), 3),
                     "baseline": round(float(res["dev_baseline"].mean()), 3)},
        "lead": {"mean": round(float(lead.mean()), 3),
                 "low": round(float(np.percentile(boots, 2.5)), 3),
                 "high": round(float(np.percentile(boots, 97.5)), 3)},
        "detail": pd.concat(details) if details else None,
        "per_week": [{k: (str(v) if k == "week" else round(float(v), 3)) for k, v in r.items()} for r in rows],
    }


def _deviance(y, mu):
    """Mean Poisson deviance: the fair error for sparse counts (MAE rewards always guessing 0)."""
    y = np.asarray(y, dtype=float)
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(np.mean(2 * (term - (y - mu))))


def forecast(panel, model, forecast_from):
    """One row per (street, category) for the week starting forecast_from."""
    rows = panel[panel["target_week"] == forecast_from].copy()
    if rows.empty:
        return []
    rows["pred"] = predict(model, rows)
    out = []
    for r in rows.itertuples(index=False):
        low, high = interval(r.pred)
        out.append({
            "street": r.street, "area": r.area, "category": r.category, "week": str(forecast_from),
            "expected": round(float(r.pred), 2), "low": low, "high": high, "baseline": round(float(r.r4), 2),
            "r13": int(r.r13), "rate": round(float(r.shrunk), 3),
            "confidence": confidence(r.r13), "synthetic": int(r.synthetic),
            "drivers": _drivers(r),
        })
    return out


def _drivers(r):
    """Plain reasons from the features this row actually had: (kind, key, text)."""
    out = []
    possible = lambda w: "" if w >= 1 else " (possible, not yet confirmed)"  # noqa: E731
    if r.ev_match and r.category in ("litter_street_cleaning", "illegal_parking"):
        out.append(("event", "match_day", "Match day nearby" + possible(r.ev_match)))
    if r.ev_cruise and r.category == "litter_street_cleaning":
        out.append(("event", "cruise_call", "Cruise ship call" + possible(r.ev_cruise)))
    if r.ev_moveout and r.category in ("fly_tipping", "missed_bin"):
        out.append(("event", "university_move_out", "Student move-out" + possible(r.ev_moveout)))
    if r.ev_other and r.category == "litter_street_cleaning":
        out.append(("event", "festival", "Large event nearby" + possible(r.ev_other)))
    if r.category == "pothole" and ((r.frost14 or 0) >= 3 or (r.rain14 or 0) >= 40):
        bits = []
        if (r.frost14 or 0) >= 3:
            bits.append(f"{int(r.frost14)} frost nights")
        if (r.rain14 or 0) >= 40:
            bits.append(f"{r.rain14:.0f} mm of rain")
        out.append(("weather", "frost_rain", " and ".join(bits) + " in the last 14 days"))
    if r.leaf and r.category == "litter_street_cleaning":
        out.append(("season", "leaf_fall", "Leaf-fall season"))
    if r.r13 >= config.HIGH_HISTORY:
        out.append(("history", "history", f"{int(r.r13)} problems here in the last 13 weeks"))
    return out
