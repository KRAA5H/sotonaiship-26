# Prediction: preventive jobs before residents have to report

The Forecast section of the council dashboard (`/council/forecast`) predicts where street problems are likely next week. It spots streets with a sudden burst of reports, and turns both into preventive jobs an officer can approve.

> **Everything shown today is SYNTHETIC DEMO DATA.** The model is trained and tested on a made-up two-year history with planted patterns. That proves the method works end to end. It does **not** show that these patterns exist in Southampton. The page says this wherever a number appears.

## What it does

| Part | What it does | Compared with |
|---|---|---|
| Hotspot forecast | Distinct problems per street and category for next week, with a likely range and a confidence level | Baseline: the average of the last 4 weeks |
| Surge detection | Flags a street whose last 24 to 72 hours are far above its own normal rate | A fixed rule: 3 problems in 24 hours |
| Event and season effects | Extra problems that tend to follow match days, cruise calls, student move-out and leaf fall, with how many past events each figure rests on | Comparable days without the event |
| Action planner | Turns each risk into a job with a do-by date, steps, a suggested team and a score shown with its parts. Officers approve, schedule, complete or dismiss it, and every change is recorded | Rules from `predict/data/preventive_actions.json`, no AI |

## How to run

From `code/`, after `pip install -r requirements.txt`:

```
python -m predict.run                 # nightly batch, about 3 minutes; writes code/predict.db
python -m predict.surge_job --loop    # surge check on live reports every 5 minutes
python test_predict.py                # tests, no network
```

Open `/council/forecast` with the council password. The page reads only `predict.db`, so it never retrains during a page load. If the last run failed or is more than 24 hours old, a warning banner says so.

## How it works

1. **Live link, read-only.** The bot's `kerbside.db` is opened with `mode=ro`, so the forecast can never block or change the bot. Only these columns are read: category, location, area, severity, status, time, duplicate link and photo features. Complaint text, sender references and links are never read. If the database is locked or missing, the last saved run is shown with a warning.
2. **Distinct problems.** A root report plus its duplicates counts as one problem. The number of people who reported it is kept separately. Free-text locations become one street through the city gazetteer (`code/geo`), so "weston ln" and "Weston Lane" match.
3. **Weather.** Daily rain, minimum temperature and wind for the city centre come from Open-Meteo, cached with the fetch time. Cached weather is never shown as live. If the fetch fails, the model runs without weather and the page says so.
4. **Features.** Every row uses data up to the end of its own week only, plus calendar facts known in advance:
   - problems in the last 1, 4, 13 and 52 weeks, and weeks since the last one
   - a smoothed rate: empirical Bayes, pulling quiet streets toward the city average for the category
   - rain and frost in the last 7 and 14 days
   - week of year, the leaf-fall window, and scheduled events
5. **Model.** `HistGradientBoostingRegressor(loss="poisson")`, pooled across categories with the category as a feature.
6. **Testing.** A rolling time-based backtest over 12 finished weeks: each week is predicted using only earlier weeks. There is never a random split, and the in-progress week is never scored.
7. **Confidence.** Fewer than 3 problems in 13 weeks is **low** confidence. It is shown as "not enough history" and creates no job. 3 to 9 is medium, 10 or more is high. Each forecast shows an 80% Poisson range.
8. **Priority.**
   - `score = expected problems x harm x urgency x confidence x 10`
   - `do_by = expected date - lead time`
   - Jobs are sorted by do-by, then score, with overdue jobs first.
   - Jobs on the same area, action and date merge into one.

## Results (synthetic, held-out weeks 20 July to 5 October 2026, 12 weeks)

| Measure | Model | Baseline | Random | Best possible |
|---|---|---|---|---|
| Share of next week's problems on our top 10 streets | 6.5% | 6.1% | 2.0% | 9.5% |
| Average error per street and week | 0.292 | 0.300 | | |
| Poisson deviance (lower is better) | 0.58 | 1.85 | | |

- **Ranking.** The model's lead over the baseline on top-10 capture is **+0.3 points, 95% interval 0.0 to +0.6**. That is barely above the baseline. The large gain is in deviance, mostly because the baseline predicts zero for quiet streets and is then badly wrong when a problem appears.
- **Surges, over 84 days.** The model raised 163 alerts, 95 of them followed by another problem within 7 days. The fixed rule raised 52, 46 followed. The model catches bursts on quiet streets that the fixed rule misses, at the cost of more alerts. The threshold (`SURGE_P`) is the dial for that trade-off.

## Honest limits

- **Synthetic history.** The effects found are the effects planted (`config.PLANTED`). Real performance is unknown until the bot has months of real reports, or real FixMyStreet history is collected under its reuse terms.
- **Reports are not the problem.** Complaints show where people report, not only where the damage is. Council cleansing job logs would be a better ground truth.
- **Street level only.** There are no coordinates. The heat view is by area, so no individual home can be picked out.
- **Weather is city-wide** from one point.
- **Events.** The match, cruise and move-out dates are **synthetic**. `predict/data/events.csv` holds real events only when each row has a public source and a collection date. Today it holds one illustrative row for the Utilita Bowl, used as the out-of-area case: it is in West End, outside the city boundary, so it creates no job and the page points to the right council. The Bowl's coordinates come from Wikipedia, fetched 2026-10-18. Its date is illustrative.
- **Assumptions to confirm with the council.** Lead times, teams and harm weights.
- **Time to fix can't be measured.** The reports table records only the first status change.
- **No congestion claim.** There is no traffic data.
- **"Did prevention help"** will be shown as an association between done jobs and later problems, never as cause. No forecast week has ended yet.
- **Not built in time:** the LLM event scout, the officer events review queue, the street map, and LLM-written plan wording (off by default).
