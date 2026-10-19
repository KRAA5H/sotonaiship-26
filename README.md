# Saint

Saint is an iMessage bot that lets Southampton residents report street problems by text, and gives council officers a clean, de-duplicated queue with a forecast of what to fix before residents have to ask.

Built for SotonShip 2026, track: Southampton City.

**Made by Anirudh, Krish, Sid and Aadil.**

**Read the PowerPoint first:** the pitch deck is `deck/SotonShip-pitch.pptx`.

## The user and the problem

- **Users:** a Southampton resident who sees a pothole, fly-tipping or broken glass and does not want to fill in a council form, and the council officer who has to work through the reports.
- **Problem:** the report is often incomplete (no street, no photo), the same problem is reported several times, and residents then ring the council to ask whether it was fixed.
- **Evidence:** Southampton recorded 10,948 fly-tipping and waste incidents in the year to March 2024 (Southampton open data, Open Government Licence, accessed 2026-10-17, recorded in `code/data/raw/MANIFEST.json`). Our own evaluation on 60 real FixMyStreet reports is in `NUMBERS.md`.

## What it does

A resident texts a message or a photo. The bot works out what it is, asks where it is, and saves one report.
- **No street yet:** it asks where, and sends a link to a mobile map page. The resident taps a pin, searches a street or a postcode, or replies with the street name. They can also share their location from iMessage.
- **Street known:** it saves the report, checks for a duplicate, and sends a private tracking link.
- **Officers** see every report on a password-protected dashboard, with a priority and a photo if there is one. They set a status, and the resident is told.
- **Forecast:** a Forecast section on the same dashboard predicts next week's hotspots, flags a sudden burst of reports, and turns both into preventive jobs an officer can approve. **The forecast runs on synthetic data and is labelled that way everywhere.**

The bot never claims the council has received a report. Reports are saved locally for officers to review, and the replies say so.

## Architecture

```
code/
  blue_bubbles.py    iMessage webhook (BlueBubbles), also serves the dashboard and the map page
  simulator.py       the same bot in a browser chat, no Mac needed
  channel.py         one contract for both channels
  graph/             the conversation, as one LangGraph graph: hydrate, precheck, capture,
                     decide, validate, execute, compose, lint, enqueue
  agents/            safety, triage, category, location, duplicate, records, reply, status
  services/          one generated playbook per category
  pin_service.py     the drop-a-pin map page and its privacy controls
  website.py         council dashboard (/council) and resident page (/r/<token>)
  predict/           the Forecast section: hotspot forecast, surge alerts, preventive jobs
  geo/               Southampton boundary and street list, used offline
  eval/              evaluation on real FixMyStreet reports
tickets/             MCP server and tickets database, synced with the website
agent/               the rulebook (categories.json) and the dated council-facts sheet
dashboard/           reports schema and the synthetic reports
```

### Application flow

1. **Safety first.** An emergency (gas smell, fire, injury) gets a fixed "call 999" reply before anything else, from rules, with no model involved.
2. **Capture first.** A real complaint is always saved, even if the category is unsure. A wrong category never loses a report.
3. **Decide.** One model call reads the message and the conversation and proposes a plan. Code checks it against the rulebook and the playbook for that category, and repairs or refuses anything it does not allow.
4. **Location.** If the street is missing, the resident gets the question and the map link together. The tracking link follows once the street is known.
5. **Duplicates.** The same person reporting the same problem again saves nothing new. A different person is linked to the first report.
6. **Reply.** The text is checked against the facts and the copy rules (short, one link, no promises, no unconfirmed team names). If it fails, a fixed template is sent.
7. **Status.** When an officer changes a status on the dashboard, the resident is texted.

## Setup

You need Python 3 (we ran 3.13). To use iMessage you also need a Mac running [BlueBubbles](https://bluebubbles.app). The browser simulator needs neither.

```
git clone https://github.com/KRAA5H/sotonaiship-26.git && cd sotonaiship-26
python -m venv .venv && source .venv/bin/activate
pip install -r code/requirements.txt
cp code/.env.example code/.env      # then fill in the keys below
python code/simulator.py            # chat in a browser at http://localhost:5007
```

- **iMessage bot:** `python code/blue_bubbles.py` (port 5005, set the BlueBubbles values in `code/.env`).
- **Council dashboard:** open `/council` on the same address. Set `COUNCIL_PASSWORD` in `code/.env`, otherwise the dashboard is off. The Forecast section is at `/council/forecast`. Build it first with `cd code && python -m predict.run`.
- **Phones:** set `SITE_URL` to an address your phone can open, for example the Mac's Wi-Fi address. The "use my phone's location" button on the map page also needs HTTPS (a tunnel is enough).
- **MCP server:** `cd tickets && pip install -r requirements.txt && python server.py` (see `tickets/README.md`).

Keys, all optional and none committed: `DEEPSEEK_API_KEY` for the language model (without it the bot answers from checked templates), an OpenRouter key as a fallback, and the BlueBubbles server URL and password. `.env` is git-ignored and `.env.example` has blank values.

## What the AI does

- **Model:** DeepSeek V4.1 Flash for text and images, with an OpenRouter model as a fallback and a fixed stub if neither answers (`code/llm.py`).
- **Where it sits:** it reads the resident's message and photo and proposes a plan (category, location, severity, what to ask). It writes the structured photo features. It phrases the reply. Everything else (safety, saving, duplicates, status) is ordinary code.
- **Why AI is required:** residents write "theres a mattress dumped by the bins on lawn rd" and send photos. A keyword list scored 42% on real reports (see below), and cannot read a photo.
- **Grounding:** the model never decides what is allowed. The rulebook (`agent/categories.json`) and playbooks define each category, a policy layer refuses claims the code cannot back up (for example that the council has the report), and the reply is linted before sending. Council facts are quoted only from a dated fact sheet with a source link.

## Baseline comparison

The simplest thing that could work is keyword matching on each category's label and example phrases, fixed before scoring. Full method, sample and sources are in `NUMBERS.md`.

| | Baseline | This system |
|---|---|---|
| Category accuracy on 60 real Southampton reports | 20 of 48 (42%) on the clear cases | **Not measured yet** |
| Real repeat reports caught (10 pairs) | n/a | 8 of 10 (duplicate rule) |
| Non-duplicates wrongly flagged (40 pairs) | n/a | 17 of 40 |
| Cost per report | n/a | **Not measured yet** |

The agent's own category accuracy and the cost per report are not measured, because they need the paid model key to run. We state that rather than quote a number we do not have. The losses are listed in `NUMBERS.md` too, for example the keyword baseline scored 0 of 17 on services we do not handle.

## Test results and failures

- **Test suite:** 709 tests in 26 files, all passing at the time of writing. Run each file with `python code/test_<name>.py`, and `python tickets/test_bridge.py`. They run offline.
- **Evaluation set:** 60 real reports for categories and 70 pairs for duplicates, labelled by one team member and not tuned on.
- **Failures we show:** the duplicate rule merges new problems at the same hotspot street (all 17 false positives are this), and it misses the same problem reported under two road names at a junction.
- **Forecast:** the model only slightly beats the 4-week-average baseline on how many next-week problems fall on its top 10 streets (6.5% against 6.1%, synthetic data). It is much better on a fair error measure for sparse counts. See `PREDICTION.md`.

## Data sources

Every source, with the date it was collected and its licence.

| Source | What it provides | Collected | Licence | Key needed |
|---|---|---|---|---|
| FixMyStreet Open311 API (mySociety and SocietyWorks) | 3000 Southampton reports, used only by the evaluation in `code/eval/fms/` | 2026-10-17 | No licence for reuse of report text found, so the text is not stored in this repository | No |
| OpenStreetMap via Overpass | Southampton boundary and about 2,200 street names (`code/geo/`) | 2026-10-17 | ODbL | No |
| OpenStreetMap via Nominatim | Street names for a map point or an Apple Maps pin, looked up when a resident gives a location | At run time | ODbL | No |
| OpenStreetMap map tiles | The map on the pin page, loaded by the resident's browser | At run time | ODbL | No |
| postcodes.io | Nearest postcode and council area for a pin | At run time | Contains OS and ONS data, Crown copyright, Open Government Licence v3 | No |
| Southampton City Council web pages | Short confirmed facts in `agent/confirmed_with_websites.csv`, each with its URL and date checked | 2026-10-17 | Quoted briefly with a source link | No |
| Southampton open data, waste statistics | Fly-tipping incident counts quoted above | 2026-10-17 | Open Government Licence | No |
| Open-Meteo | Daily rain, temperature and wind for the forecast, cached with its fetch time in `code/predict/data/weather_cache.json` | 2026-10-18 | CC BY 4.0 | No |
| Wikipedia, Areas of Southampton | Area names used to group reports | 2026-10-17 | CC BY-SA | No |
| Synthetic reports (`dashboard/fake_reports.json`) and the synthetic forecast history (`code/predict/synth.py`) | The demo dashboard and the forecast | Generated | n/a | No |

Attribution: (c) OpenStreetMap contributors, ODbL. Postcode data contains OS and ONS data, Crown copyright and database right, under the Open Government Licence v3. Report data from [FixMyStreet](https://www.fixmystreet.com), run by [mySociety](https://www.mysociety.org) and SocietyWorks, fetched through its [Open311 API](https://www.fixmystreet.com/open311). Open-Meteo data under CC BY 4.0.

**Synthetic data is labelled synthetic everywhere it appears:** the dashboard banner, the forecast page, `PREDICTION.md` and this README. The demo database and dashboard use synthetic reports only. Real FixMyStreet reports are used only by the offline evaluation and never in the product.

## What was AI-generated, and what existed before

- **Generated with AI tools:** most of the code and documents were drafted with Claude (Anthropic), mainly through Claude Code, during the event, then reviewed, tested and changed by the team. This includes the forecast section (`code/predict/`), the drop-a-pin page (`code/pin_service.py`), the MCP server (`tickets/`), and much of the test suite. The earlier disclosure in `code/data/raw/MANIFEST.json` covers only the first files and still names Claude as the run-time model, so it is out of date.
- **Designed and decided by the team:** the product and what it must never do, the rulebook (`agent/categories.json`), the choices recorded in `DECISIONS.md`, and the review of what the AI produced.
- **At run time:** the language model is DeepSeek V4.1 Flash.
- **Pre-existing, by name and licence:** Flask (BSD-3), requests (Apache-2.0), python-dotenv (BSD-3), LangGraph (MIT), scikit-learn and pandas (BSD-3), numpy and scipy (BSD-style), Leaflet 1.9.4 (BSD-2), and the MCP Python SDK (MIT).
- **Help received:** BlueBubbles, the open-source bridge that lets the bot send and receive iMessage.

## Known limits

- **Nothing is sent to the council.** Reports are saved for officers to review. The bot says so, and a rule in the code forbids it claiming otherwise.
- **The forecast is a demo of the method.** It is trained on a made-up two-year history with planted patterns, so it shows the pipeline works, not that the patterns hold in Southampton. Match, cruise and move-out dates in it are synthetic. See `PREDICTION.md`.
- **Small evaluation.** 60 reports and 70 pairs, one city, labelled by us, mostly older reports. See `NUMBERS.md`.
- **Agent accuracy and cost per report are not measured.**
- **Wording.** Some complaints worded "was not" or "wasn't" (for example "my bin was not collected") can be read as the resident correcting the bot.
- **Location is a street, not a point.** Coordinates are not kept. A pin on a private home can reveal an address, as set out in `COMPLIANCE_LOCATION.md`.
- **No congestion claims.** There is no traffic data.
- **Not built:** the event scout that would find events from the web, and a street-level map in the forecast.

## Responsible use

- **Officers decide.** Every report goes to a person to review, every preventive job needs an officer to approve it, and every status change is recorded.
- **Personal data:** the reports table holds a salted hash of the sender, never a phone number, and the resident page shows only that resident's own report. For this pilot the team decided (D65 in `DECISIONS.md`) that a separate `profiles` table may store a preferred name, address and phone, keyed by that hash, and kept out of the reports table, the resident page and the dashboard. All development and demo data is synthetic. Coordinates are discarded unless explicitly switched on.
- **Location privacy:** the map page never sees a phone number, sets no cookies, asks for the phone's location only when the resident presses the button, and does all postcode and street lookups on our server. Full notes, including a UK GDPR and PECR walkthrough and what must happen before real use, are in `COMPLIANCE_LOCATION.md`.
- **Safety:** emergencies get a fixed "call 999" reply, and safety guidance links to official sources, not text we wrote.
- **No secrets in the repository.** Keys live in a git-ignored `.env`.

## Future improvements

- Connect a real submission route to the council, so a report can honestly be marked as received.
- Measure the agent's category accuracy and cost per report on the held-out reports.
- Train the forecast on real history instead of synthetic data, and add the event scout with an officer review queue.
- Use officer corrections to improve category and duplicate decisions.

## Authors

Made by Anirudh, Krish, Sid and Aadil.
