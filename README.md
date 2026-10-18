# sotonaiship-26
sotonaiship hackathon submission

## Data credits

- Report data: mySociety FixMyStreet (ODC-BY). The dashboard shows the most recent public Southampton reports from [FixMyStreet](https://www.fixmystreet.com), fetched through its Open311 API (see below and `DECISIONS.md` D67).
- Evaluation data: real Southampton reports from [FixMyStreet](https://www.fixmystreet.com) (mySociety / SocietyWorks), fetched through its Open311 API on 2026-10-17. Used by the evaluation in `code/eval/fms/`. The evaluation's report text is not stored in this repository. Results and method: `NUMBERS.md`.
- Road names: (c) OpenStreetMap contributors, via Nominatim, under the Open Database Licence.
- Southampton's boundary and street list (`code/geo/`): (c) OpenStreetMap contributors, fetched through the Overpass API on 2026-10-17, under the Open Database Licence. Used offline to check a location is inside the city and to suggest streets.

## Loading the reports

```
python code/import_fixmystreet.py           # fetch what is not cached yet, add new reports to code/kerbside.db
python code/import_fixmystreet.py --reset   # rebuild code/kerbside.db from the local cache only, no network
```

The first command makes one Open311 request for the 150 most recent reports and looks up each street on
Nominatim (one request a second). Both are cached in `code/data/fixmystreet_cache/`, which is gitignored,
so nothing is fetched twice. `kerbside.db` is never committed. Reports from the agent are added to the same
database as residents send them.
