# sotonaiship-26
sotonaiship hackathon submission

## Data credits
READ THE POWERPOINT
- Evaluation data: real Southampton reports from [FixMyStreet](https://www.fixmystreet.com) (mySociety / SocietyWorks), fetched through its Open311 API on 2026-10-17. Used only by the evaluation in `code/eval/fms/`, never in the demo or the dashboard. The report text is not stored in this repository. Results and method: `NUMBERS.md`.
- Road names: (c) OpenStreetMap contributors, via Nominatim, under the Open Database Licence.
- Southampton's boundary and street list (`code/geo/`): (c) OpenStreetMap contributors, fetched through the Overpass API on 2026-10-17, under the Open Database Licence. Used offline to check a location is inside the city and to suggest streets.
- The demo database and dashboard use synthetic reports only (`dashboard/fake_reports.json`).
