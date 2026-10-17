# Southampton resident reporting agent: data pack
Checked against Southampton City Council pages on 17 Oct 2026. Public data only. Nothing was submitted to any council form.

## agent/  (give these to the agent)
- categories.json: the rulebook (22 categories, outcomes, questions to ask, location rule, official form links).
- confirmed_with_websites.csv: the fact sheet (53 facts, each with source URL and date). The agent may only state facts from here.
- loader.py: joins the two files on category_id (some fact rows list several ids separated by ;).
Only fully confirmed items are included. Anything else goes to council_service_other (point to the council forms page).

## dashboard/
- schema.sql and SCHEMA.md: the report table (11 columns, no map coordinates, includes link_token for the resident's private link). Agree this between agent and dashboard, change only together.
- fake_reports.csv / .json: 68 SYNTHETIC reports (60 originals + 8 duplicates). Label them as synthetic on screen.
- make_fake_reports.py: regenerates the fake data from categories.json.

## Website plan
One website, two views: /council (staff dashboard) and /r/<link_token> (the resident's own report only). The agent's last message includes the resident link.

## reference/  (for the team and the judges, NOT for the agent)
- scope_checks.csv: verified council-scope checks.
- council_forms.csv: the council's own forms and the questions we could read (many only partly).
- confirmed_categories.csv: the 15 confirmed categories with what the council controls and what is out of scope.

## Still to check by hand
- Council out-of-hours number appears as 023 8023 3344 and 023 8083 3344. Check before quoting.
- A36 / A33 National Highways status is not confirmed, so no road names are used.
- Most multi-step forms were only read as far as the first steps.
- Facts can change: show the date checked.

## Demo and privacy
- Use only team or synthetic phone numbers. Store a hashed or fake reporter_ref, never a real number.
- FixMyStreet counts (mySociety, ODC-BY) are optional; credit mySociety if used and do not rank areas.

## Pages
- /council: dashboard for council staff (all reports, filters, duplicate grouping, status buttons).
- /r/<link_token>: resident page, one report only. The agent sends this link in its last message. Never put the report id in a public link.
- dashboard/prototype/index.html: clickable prototype of both views (synthetic data). Open it in a browser.
