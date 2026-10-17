# Data sources

Consolidated from the "Data" sections of the three live track briefs, plus the "Directions" sections. Fetched 16 October 2026. **There is no compulsory dataset in any track.**

Two rules that apply everywhere: check early that the source covers the area or market chosen and that reuse is allowed, and **keep API keys and passwords out of the repository**.

## Southampton City sources

| Source | What it offers | Access and limits |
|---|---|---|
| Environment Agency flood monitoring | Flood warnings, warning areas, river and tide gauge readings | Open API, no registration. Check coverage and timestamps |
| UKHO Admiralty Tidal API | Predicted high and low tides | Free registration and key. Check the tier, forecast horizon and quota |
| Bus Open Data Service | Bus timetables, vehicle locations and fares | Free registration and key. Check which local operators and fields are available |
| Defra UK-AIR | Air-quality measurements from Southampton monitoring sites | Public downloads. Check which pollutants are covered and whether data is provisional or ratified |
| DfT road traffic statistics | Traffic counts and annual average flows at Southampton count points | Public downloads. These are historical averages, not live traffic |
| Met Office Weather DataHub | Site forecasts, including wind | Free account and key. Check current products and allowances |
| Southampton VTS | Cruise schedules and vessel movements | Public web pages. Do not assume an API or permission to redistribute |
| Southampton Data Observatory | Council statistics and reports on population, economy and services | Public. Check dates and the level of geographic detail |
| Southampton City Council | Planning register, Local Plan, HMO licensing conditions and service information | Public pages and documents. Check terms before reusing content |

Also named in the "directions" section: **public FixMyStreet reports for Southampton** as the starting point for street-report triage.

## FinTech sources

| Source | What it offers | Access and limits |
|---|---|---|
| Companies House API and bulk data | UK company records, officers, registered addresses, filing history and persons with significant control | Free; the API needs a key. Bulk files are large, so take a slice |
| UK sanctions list (OFSI / FCDO) | Names, aliases and identifiers of sanctioned people and entities | Free public download. Good for name-matching and screening |
| World Bank Remittance Prices Worldwide | Cost of sending money between country pairs, by provider type | Free download. Quarterly, not live prices |
| Bank of England and ECB exchange rates | Daily reference FX rates | Free. Historical reference rates, not live trading rates |
| FCA Register, and FCA / Bank of England publications | Authorised firms, warnings about unauthorised firms, policy statements and consultations | Public pages and downloads. Check terms before bulk collection |
| PaySim (Kaggle) | Synthetic mobile-money transactions with fraud labels | Openly available and widely used, so originality must come from the product |
| IBM AMLworld (Kaggle) | Synthetic transactions with money-laundering patterns labelled | Openly available; large, so sample it |
| Elliptic dataset (Kaggle) | Bitcoin transaction graph with licit and illicit labels | Openly available. Check the licence |
| Public blockchain explorers (Etherscan, Basescan) | On-chain token transfers, including stablecoins and deposit tokens | Free tiers need a key and have rate limits |
| OpenStreetMap | Structured address data | Open (ODbL). Credit OpenStreetMap contributors |

Also named in the "directions" section: **published scam scripts and public scam reports** (for the scam check), **public sample trade documents and generated sets with planted errors** (for the trade document checker).

## Responsible AI sources

| Source | What it offers | Access and limits |
|---|---|---|
| Ragas repository | Evaluation tools for language-model applications, linked to the RAGAs paper | Apache-2.0 code. Model or API use may cost money; validate automated scores with human checks |
| Fairlearn | Metrics and methods for assessing model performance across groups | MIT code. Dataset licences are separate; no single metric guarantees fairness |
| Hugging Face model cards | Public documentation of intended use, evaluation and limitations | Check each repository's terms. Public access alone does not grant reuse rights |
| Public manuals and help pages | Source material for grounded answers and evidence-review tasks | Choose content with permission to reuse; record owner, version, URL and date |
| Labelled synthetic test cases | Fictional records, planted errors, ambiguous inputs and controlled group comparisons | State how cases and labels were made. Keep a held-out test set; do not claim population-level validity |

## Verified from this machine, 16 October 2026

Checked with `curl` rather than assumed, because a brief's link is a claim about an endpoint:

| Endpoint | Result |
|---|---|
| `https://environment.data.gov.uk/flood-monitoring/id/floods?county=Hampshire` | 200, JSON, Open Government Licence, no key. Works |
| `https://environment.data.gov.uk/flood-monitoring/id/stations?type=TideGauge&lat=50.90&long=-1.40&dist=15` | 200, JSON. Works, and returns tide gauges near Southampton |
| `https://api.postcodes.io/postcodes/SO147SJ` | 200, JSON. Free, no key. Useful for geocoding the venue and any list of postcodes |
| `https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv` | 200, `text/csv`. The OFSI consolidated sanctions list downloads directly, no key |
| `https://api.company-information.service.gov.uk/search/companies?q=...` | 401 without a key. Needs a free Companies House account |
| `https://www.fixmystreet.com/api/v1.0/reports?...` | 404. Do not assume a FixMyStreet JSON API; the brief only claims public reports exist on the site |

`code/data/fetch_sources.py` runs the no-key sources and writes them to `code/data/raw/`.

### What an actual fetch returned, 16 October 2026 18:46 UTC

| Source | Result |
|---|---|
| Flood warnings, Hampshire | **0 items.** Nothing was flooding that evening, so a "live warnings" demo needs another live signal on a dry day |
| Tide gauges within 25 km of Southampton | **2, both Portsmouth** (station references E71839 and E71824). There is no Southampton tide gauge in the EA network within that radius, so a Southampton tide product either widens the radius or uses the UKHO predictions, which need a key |
| Flood monitoring stations within 10 km | Returned, with station reference and river name, ready to join to readings |
| OFSI consolidated sanctions list | 16.6 MB CSV, header row shows `Last Updated,03/06/2026`. That date is the one to quote in a README |
| postcodes.io, SO14 7SJ | Returns eastings/northings and lat/long for the venue: 50.905897, -1.405884 |


## Attribution that has to appear in the README

- Data sources **with dates** and **licences** for every number shown in the product.
- Environment Agency data is Open Government Licence v3.
- OpenStreetMap is ODbL, credit OpenStreetMap contributors.
- Synthetic datasets must be labelled synthetic in the product and the README.
