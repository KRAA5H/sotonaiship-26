# Prediction plan: predictive prevention for Kerbside

Stage 0. No feature code yet. Branch: `anirudh/predict` (from `main` at `f11b047`).

**Time box.** Written Sunday 18 October 2026 at 06:40. Submissions lock at 13:00, so there are about 6 hours. The plan below is sized for that, with a hard freeze at 12:30 and a clear list of what is cut first.

---

## 1. What I found in the repo

### The live complaints are in `code/kerbside.db`, not `tickets.db`

This is the biggest difference from the brief.

| Brief assumed | What is real |
|---|---|
| `tickets.db`, written by the Records agent | The bot, the Records agent, the dashboard and the graph store all write `code/kerbside.db` (path from `DB_PATH`), table `reports`. `tickets/tickets.db` is my separate MCP copy, synced from it |
| A street field and an area field | `location` is free text as the resident said it, `area` is a named area from the location service (may be empty) |
| `created_at`, `severity`, `duplicate_of`, `status` | All present. Severity is `high`, `medium`, `low` or null. Status is `new`, `in_review`, `resolved` |
| `audit_log` timestamping every status change | Not in `kerbside.db`. There is only `status_changed_at`, the **first** change. So time to first action is measurable, time to fix is not |

Other columns we will use:
- `has_photo` and `photo_features`, which hold JSON with `hazard` and `estimated_size`
- `capture_state` and `routing_status`

Columns we will never read for prediction: `description`, `reporter_ref`, `link_token`, `photo_guid`.

### The data is too short to train on

- `dashboard/fake_reports.json`: 68 synthetic reports covering **17 September to 17 October 2026, about 4 weeks**. 8 are duplicates.
- Locations cluster on a few streets: Old Northam Road and Bevois Valley (12 each), Bitterne Road (12), Shirley High Street (10).
- Four weeks is not enough for a weekly model with a time-based split, or for any seasonal or event effect.
- FixMyStreet: `code/data/sources.md` records that the JSON API path returns 404 and says to use the public pages with a collection date. Collecting and labelling a real history would take most of the day. See question 1.

### Locations

`code/geo/southampton.py` has what we need:
- `normalise` and `street_in_text`, to turn free text into one street
- `in_city(lat, lng)` against the city boundary
- `names_outside_place`
- `southampton_streets.json`: about 2,800 streets with area and a public centroid, from OpenStreetMap via Overpass, ODbL, fetched 2026-10-17

We will count by normalised street, then by area. Public street centroids allow an optional map, credited to OpenStreetMap.

### The dashboard

- **Framework:** Flask 3.1. All council and resident views live on one Blueprint, `site`, in `code/website.py`. It is registered by `create_app` (tests), `code/blue_bubbles.py:108` (the live bot) and `code/simulator.py:40`.
- **Templates:** `code/web/templates/base.html` (top bar, synthetic-data banner) and `council.html`, which renders the report list in the browser from `/council/reports.json`.
- **Styles:** one stylesheet, `code/web/static/kerbside.css`.
- **Navigation:** there is no nav menu, only a `{% block topbar_extra %}` slot in `base.html`.
- **Authentication:** HTTP Basic, checked by `website._council_denied()`. The view is off unless `COUNCIL_PASSWORD` is set.
- **Data access:** `reports_db.connect()` with WAL and a busy timeout. It sets the journal mode, so it is a writing connection, and the forecast will not use it (see section 3).
- **Priority:** `code/priority.py` scores open reports for the card list, with severity, exposure, cluster and age. It will be reused for the harm weights only, by import, unchanged.

### Libraries

`pandas`, `numpy`, `scipy` and `scikit-learn` are **not** in `code/requirements.txt`, and `sklearn` is not installed here. The brief allows them. They must also be installed on the demo Mac (question 3).

---

## 2. File layout (all new unless marked)

```
code/predict/
  __init__.py
  config.py            thresholds, lead times, harm weights (marked "assumed, confirm")
  data.py              read-only loader, street normalising, distinct-problem weekly table
  synth.py             synthetic history generator (labelled synthetic everywhere)
  weather.py           Open-Meteo history and forecast, cached to file with fetch date
  events.py            events.csv loader, coverage check, uplift table
  models.py            baseline, shrinkage, HistGradientBoosting Poisson, intervals
  evaluate.py          time-based backtest: top-10 capture, MAE, lead over baseline with 95% interval
  surge.py             Poisson tail surge alerts with cooldown, and fixed-threshold comparison
  actions.py           rules-based action planner, merge, do_by, priority parts, CSV
  store.py             predict.db: pred_runs, pred_forecasts, pred_surges, pred_actions,
                       pred_action_audit, pred_outcomes, pred_events (CREATE IF NOT EXISTS)
  run.py               python -m predict.run          (nightly batch)
  surge_job.py         python -m predict.surge_job    (every few minutes)
  web.py               Blueprint "forecast": /council/forecast and its JSON/CSV/POST routes
  templates/forecast.html
  static/forecast.css  only what kerbside.css lacks
  data/events.csv
  data/preventive_actions.json
  data/weather_cache.json
code/test_predict.py   (one test file, the repo's style: python code/test_predict.py)
PREDICTION.md          how it works, how to run, honest limits
```

**Why a separate `code/predict.db`:** the forecast never writes to the bot's database. `kerbside.db` is opened read-only with a SQLite URI (`file:...?mode=ro`, short retry, then the last saved run with a warning). Officer actions on plans write only to `predict.db`.

---

## 3. Data flow and the live link

```
kerbside.db (bot writes) --read-only--> data.load_reports()
   -> normalise street (geo) -> distinct problems (root + duplicates counted once,
      duplicates kept as "people noticed") -> street x category x week table
   -> + weather (cached) + events.csv + season (week of year, leaf-fall window)
   -> models -> predict.db (pred_*) -> /council/forecast reads only predict.db
```

- **Nightly batch:** `run.py` rebuilds everything from all history and records a run row: id, created_at, sources, synthetic flag, status.
- **Surge job:** `surge_job.py` reads reports newer than the last surge run, in the same read-only way, and writes `pred_surges`. It runs every few minutes from a loop or cron. It is not wired into the bot.
- **Records agent trigger:** proposed in `DECISIONS.md` only. After a successful save, call `predict.surge_job.check_street(street, category)` in a background thread. I do not edit the Records agent.
- **Outcomes:** `pred_outcomes` records, at the end of each forecast week, the actual distinct problems per street and category. The accuracy panel and the "did prevention help" view read only that.
- **Synthetic labelling:** every run, forecast, action and outcome row stores `synthetic` 1 or 0. The page shows "SYNTHETIC DEMO DATA" whenever any input row is synthetic.

### The synthetic history (because 4 weeks cannot train or test anything)

`synth.py` builds about 104 weeks of synthetic reports.
- **Sampling:** they are sampled from the real street list and the 16 council categories.
- **Planted effects:** each street gets a base rate, plus known effects: leaf fall raising litter in October and November, frost plus rain raising potholes two weeks later, move-out raising fly-tipping and missed bins in student areas, match days and cruise days raising litter near the venue.
- **Weather:** the planted weather effects use **real cached Open-Meteo history**, so the weather join is genuine even though the complaints are not.
- **Where it lives:** only in `predict.db`, never in `kerbside.db`.
- **Honest limit:** a model that recovers effects we planted proves the method runs end to end, not that it works on Southampton. `PREDICTION.md` and the page say exactly that.

---

## 4. Models

| Model | What | Compared with |
|---|---|---|
| Baseline | mean of the last 4 weeks per street and category | always shown |
| Hotspot forecast (model 4) | `HistGradientBoostingRegressor(loss="poisson")`, features: last 1, 4, 13 weeks, weeks since last, shrunk rate, rain and frost in the last 7 and 14 days, forecast rain, week of year, event flags. One model per category with at least 100 nonzero street-weeks, otherwise pooled with a category feature | baseline, random, best possible |
| Shrinkage | Gamma-Poisson empirical Bayes toward the city rate for that category | raw rate |
| Uncertainty | Poisson 80% interval around the mean. Confidence is **low** if under 3 distinct problems in 13 weeks, which shows "not enough history" and creates no job; **medium** if 3 to 9; **high** if 10 or more | |
| Surge (model 7) | last 24, 48, 72 hours vs the street's shrunk weekly rate, `scipy.stats.poisson.sf`, alert if p < 0.01 and count is at least 3, 72-hour cooldown | fixed "3 in 24 hours" rule |
| Event and season uplift | table: mean distinct problems in affected streets over days 0 to 3 after the driver, minus matched non-event days. Shows n events; under 5 is marked low confidence | none (descriptive) |

### Evaluation

- **Time-based backtest:** train on weeks whose outcome was known before each test week, rolling over the last 12 synthetic weeks. No random split. No feature uses data after the forecast date (a test checks this).
- **What is reported:**
  - the share of next week's problems falling on our top 10 streets, for the model, the baseline, random and best possible
  - MAE per street-week
  - the lead over the baseline with a 95% bootstrap interval across test weeks
- **Surge backtest:** alerts raised, how many were planted surges, and the lead time in days vs the fixed rule.

### Priority (in `actions.py`, never named priority.py)

- **Score:** `score = expected_volume x harm_weight x urgency x confidence`.
- **Harm weight:** from severity and hazard, reusing `priority.SEVERITY` by import.
- **Urgency:** rises as do_by approaches.
- **Sorting:** by do_by, then by score. Overdue items go first and are marked overdue.

---

## 5. Action planner (rules first)

- **Config:** `preventive_actions.json` maps each driver and category to an action type, a lead time in days, a suggested team marked "confirm" and checklist steps. Every value is marked "assumed, confirm with the council".
- **Deadline:** `do_by = expected problem date - lead time`.
- **Merging:** plans with the same street, same action type and overlapping window merge into one job with several reasons.
- **Status flow:** proposed, then approved, scheduled, done, or dismissed with a reason. Each change is written to `pred_action_audit` with a timestamp.
- **Export:** a CSV work order of approved plans, sorted by do_by.
- **Wording:** template only. LLM wording is off by default and noted in `DECISIONS.md`. It is only built if time remains, and then it only sends aggregated fields (street, category, date, counts, driver).
- **Measure:** after each period, record whether the problem still happened, and show "after a done action" vs "after none" as an association, never a cause.

---

## 6. Plugging into the dashboard (additive, listed exactly)

| Existing file | Owner (please confirm) | Exact change |
|---|---|---|
| `code/website.py` | Section 3 (Aadil) | **2 lines**, just before the existing `create_app`, at about line 275: `from predict.web import forecast` and `site.register_blueprint(forecast)`. Registering on `site` nests it, so it appears everywhere `site` is already registered (bot, simulator, tests) with no edit to `blue_bubbles.py` or `simulator.py` |
| `code/web/templates/council.html` | Section 3 (Aadil) | **1 line** in `{% block topbar_extra %}`: a "Forecast" link to `url_for('website.forecast.page')`, using existing `kerbside.css` classes |
| `code/requirements.txt` | shared | **4 lines**: `scikit-learn`, `pandas`, `numpy`, `scipy`, version-pinned |
| `DECISIONS.md` | shared | one new entry: lines changed, the proposed Records-agent trigger, LLM wording off by default, the ranking terms to check before any ranked list |
| `.gitignore` | shared | none needed, `*.db` is already ignored |

- **Not touched:** `reports_db.py`, `priority.py` (import only), `NUMBERS.md`, `blue_bubbles.py`, the Records agent, every existing table and function.
- **Auth:** `forecast` routes call the existing `website._council_denied()`, so it is the same login.
- **Click-through:** each risk links to `/council?q=<street>`. If `council.html` has no such filter, the link opens `/council` and I note it, without editing their filter code.

### The Forecast page

- **Banner:** sources, last updated, "SYNTHETIC DEMO DATA", and a stale warning if the last run failed or is over 24 hours old.
- **Risks:** cards with reason, confidence and driver.
- **Priority list:** sorted by do_by then score, with the score parts shown (as in example 1).
- **Hotspot heat strip:** streets by area for the next 7 days, with a category filter. Counts under 3 are shown as "fewer than 3".
- **Failure cases:**
  - a "not enough history" street
  - the Utilita Bowl as outside the council's area. It is checked with `geo.in_city` on the venue's public OSM coordinate and creates no job.
- **Accuracy panel:** model vs baseline, test period, number of weeks, and action plan counts.
- **Action plan board:** grouped by status, with approve and dismiss buttons, and the CSV export.
- **Events:** the confirmed events list from `events.csv`. The review queue appears only if the event scout is built.

**No league table of worst streets as a headline.** The page leads with preventive jobs.

---

## 7. Order of work and time box (freeze 12:30, submit before 13:00)

| Time | Stage | Done when |
|---|---|---|
| 07:00 to 08:00 | 1. Read-only loader, street normalising, distinct-problem table, synthetic history, weather cache, baseline | tests pass, baseline numbers printed |
| 08:00 to 09:15 | 2. Hotspot model, shrinkage, backtest, `predict.db`, `run.py` | accuracy table vs baseline |
| 09:15 to 10:30 | 3. Action planner and the Forecast page in the dashboard, with the 3 lines in existing files | page shows banner, risks, priority list, heat strip, failure cases, accuracy |
| 10:30 to 11:15 | 4. Surge detection and its backtest | surge card on the page |
| 11:15 to 11:45 | 5. `events.csv` with sourced rows, event and season uplift | uplift table with n events |
| 11:45 to 12:30 | 7. Polish: CSV export, `PREDICTION.md`, `DECISIONS.md`, all suites green | |
| 12:30 | Freeze: commit, push the branch, open a PR | |

**Cut order if short:**
1. Event scout (stage 6): planned as **cut now**, with manual `events.csv` instead.
2. The optional map.
3. The surge backtest (keep live surge alerts).
4. The action board's scheduled state.

**Never cut:** baseline comparison, synthetic labelling, the failure cases.

---

## 8. Assumptions

- **Synthetic history:** it is acceptable as the training and test data for the demo, clearly labelled (question 1).
- **Weather:** Open-Meteo is reachable from this machine. If not, the model runs without weather features and the page says so.
- **Events:** I fill `events.csv` only with rows whose dates I read on a public page today, each with `source_url` and `collected_on`. Any I cannot source are left out, not invented.
- **Placeholders:** lead times, team names and harm weights are placeholders marked "assumed, confirm with the council".
- **Coordinates:** public street centroids from OpenStreetMap are allowed for a map, since they are not resident locations.
- **Congestion is out of scope.** There is no traffic data, so it is not claimed.
- **Sensitive events:** protests or public gatherings are not added in this build. With the scout cut, there is no automated source for them.

---

## 9. Questions for you

1. **Training data.** Use a labelled two-year synthetic history (recommended, it fits the time), or spend time collecting real FixMyStreet Southampton reports? FMS would mean checking its reuse terms first, and would probably cost stages 4 and 5.
2. **Event scout.** OK to cut it and use a hand-sourced `events.csv`?
3. **Dependencies.** OK to add `scikit-learn`, `pandas`, `numpy` and `scipy` to `code/requirements.txt`? Whoever runs the demo Mac needs `pip install -r code/requirements.txt` after merging.
4. **Owners.** Is Aadil the right person to warn about the 2 lines in `website.py` and 1 line in `council.html`?
5. **Git.** At the end, push only `anirudh/predict` and open a PR into `main` (not a direct push), as before?
