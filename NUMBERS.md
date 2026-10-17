# Numbers

Every number we quote comes from this table. Each row has a source and a date. Losses are listed with the wins.

| What | Result | Source | Date |
|---|---|---|---|
| Category accuracy, keyword baseline | **20 of 48 (42%)** on the clear cases; 12 more reports were too ambiguous to score | `code/eval/fms/score.py` on 60 real Southampton FixMyStreet reports, labels in `code/eval/fms/labels.json`, results in `code/eval/fms/results.json` | 2026-10-17 |
| Category accuracy, our agent (`code/triage.py`) | **Not measured yet.** Ready to run with `score.py --agent`; it sends the 60 real reports to the external text model, so it waits for a go-ahead | same | not run |
| Duplicate rule: real repeats caught | **8 of 10** | `score.py`, rule from `code/tools.py` `check_duplicate` (same category, same street text, open, 30 days) | 2026-10-17 |
| Duplicate rule: false positives | **17 of 40** non-duplicates wrongly flagged; 0 of 19 hard negatives flagged | same | 2026-10-17 |
| Cost per report | **Not measured yet.** No component logs model token usage today, so there is nothing measured to read | `code/llm.py` (no usage logging) | 2026-10-17 |

## Wins

- **Fly-tipping:** the baseline got 6 of 6 right.
- **Hard negatives:** the duplicate rule flagged none of the 19 pairs that were the same street with a different issue, or the same issue on a different street.
- **Exact resubmissions:** the rule caught both identical double submissions (the same pothole twice in one minute, and the same front-lawn parking report twice).

## Losses

- **Services we do not handle:** the baseline scored 0 of 17 on traffic lights, signs, trees and bollards. It has no keywords for them, so it guessed parking, graffiti ("lamp post") or nuisance.
- **Litter versus fly-tipping:** 4 of 6 litter reports were called fly-tipping, because both talk about rubbish.
- **Same street, new incident:** the duplicate rule merges new problems at a hotspot.
  - On Drummond Drive, separate fly-tips weeks apart are all flagged as one.
  - On Bath Street, potholes the resident numbered 1 to 7 are flagged as duplicates of each other.
  - All 17 false positives are this case. The rule has no way to tell "again, a new pile" from "the same pile".
- **Two names for one place:** the same overflowing bin, reported twice 10 m apart, falls on two road names at a junction (Sholing Road and Peartree Road). The rule misses it.
- **No street at all:** one real repeat (more trolleys added to ones already reported) had no road name from the geocoder, so the rule could not run.

## Limitations

- **Small sample, one city:** 60 reports for categories and 70 pairs for duplicates, all from Southampton.
- **Labels made by us:** one person on the team read each report against `agent/categories.json`, and nobody independently checked the labels.
- **Ambiguous reports excluded:** 12 of the 60 reports, and 10 of the 70 pairs, were marked ambiguous and are left out of the rates.
- **Mostly old reports:** most of the duplicate pairs date from 2017 to 2019, because that is where the dense same-street clusters are.
- **Location is a stand-in:** a resident types a street, but these reports were given the road OpenStreetMap returns for their map point. Residents' own wording would match differently.
- **The likely-repeats set leans easy:** it was chosen by closeness, timing and shared wording.

## How the evaluation was built

- **Source:** FixMyStreet's official Open311 API, with Southampton City Council as the recipient (MapIt area 2567).
  - Three requests, at least five seconds apart (`robots.txt` asks for three).
  - No photos fetched. A user agent naming this project and repo.
- **Coverage:** 3000 reports, from 2017-09-13 to 2026-10-06, fetched 2026-10-17 by `code/eval/fms/collect.py`.
- **Road names:** OpenStreetMap Nominatim, one request per second, cached (`select.py`).
- **Where the data lives:** the raw downloads and every file holding report text stay in `code/eval/fms/raw/`, which is gitignored. Committed files hold FixMyStreet ids, our labels and predictions only.
- **Not in the product:** real reports are used only by this evaluation, never in the demo database, the dashboard or the agent. Permission is recorded in `DECISIONS.md` (D35).
- **The sets:**
  - 60 reports for category accuracy: at most 6 per FixMyStreet category, from 2023 onwards.
  - 20 likely repeats.
  - 20 same-street pairs: same category, under 50 m, under 30 days.
  - 20 hard negatives: 10 on the same street with a different issue, 10 with the same issue more than 800 m apart.
- **The baseline:** keyword matching using only the words in each category's label and example phrases in `categories.json`. It was fixed before scoring and not tuned on these reports.

## Credit

Report data from [FixMyStreet](https://www.fixmystreet.com), run by [mySociety](https://www.mysociety.org) and SocietyWorks, fetched through its [Open311 API](https://www.fixmystreet.com/open311) on 2026-10-17. We could not find a stated licence for reusing report text on fixmystreet.com, so we keep the text out of this repository and credit the source here.

Road names © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, via Nominatim, available under the Open Database Licence.
