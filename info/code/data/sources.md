# Data sources: keys, endpoints and limits

The briefs' own tables are in `../../hackathon-info/data-sources.md`. This file is the build-side view: what actually needs a key, where the key comes from, and what the limits are, so nothing blocks a build at 02:00.

Verified by request from this machine on 16 October 2026. `fetch_sources.py` pulls the keyless ones.

## No key needed, safe to fetch right now

| Source | Endpoint used | Notes |
|---|---|---|
| Environment Agency flood monitoring | `https://environment.data.gov.uk/flood-monitoring/id/...` | Open API, no registration. `floods`, `floodAreas`, `stations`, `stations?type=TideGauge`, then `/id/measures/{id}/readings?_sorted&_limit=1` for the latest reading. Open Government Licence v3. It is a beta service, so check timestamps rather than trusting "live" |
| OFSI consolidated sanctions list | `https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv` | Direct CSV download, open data. Good for name-matching and screening demos. 200 on 16 Oct 2026 |
| postcodes.io | `https://api.postcodes.io/postcodes/{postcode}` | Free geocoding and postcode lookup, no key, no registration. Useful for anything address or location shaped |

## Key needed, free registration

| Source | Where the key comes from | What to watch |
|---|---|---|
| Companies House API | Developer account at `developer.company-information.service.gov.uk`. HTTP Basic with the key as the username, blank password. `https://api.company-information.service.gov.uk/search/companies?q=` returns 401 without it | Free. Also has bulk files: large, take a slice rather than the whole product file |
| Bus Open Data Service | `data.bus-data.dft.gov.uk`, free account, then the API key from the account page | Check which Southampton operators publish and which fields are populated. Timetables, vehicle locations and fares are separate datasets |
| Met Office Weather DataHub | `datahub.metoffice.gov.uk`, free tier | Check the current product list and the call allowance: the free tier is small |
| UKHO Admiralty Tidal API | `admiralty.co.uk` developer portal | Tides are the point of a lot of coastal ideas. Check the tier, forecast horizon and quota before designing around it |
| FCA Register API | `register.fca.org.uk` / FCA developer portal | Free but rate-limited. Check terms before bulk collection |
| Kaggle datasets (PaySim, IBM AMLworld, Elliptic) | Kaggle account and API token | Free and no cost, but the licence differs per dataset: check each one, and note that PaySim and AMLworld are widely used so originality has to come from the product, not the model |

## No key, but no API either

| Source | How to use it |
|---|---|
| Southampton VTS | Public web pages for cruise schedules and vessel movements. **Do not assume an API or permission to redistribute.** A hand-collected CSV with the date noted is honest; presenting a scraped page as a live feed is not |
| Southampton City Council | Planning register, Local Plan, HMO licensing conditions, service pages. Public documents. Check terms before reusing content, and cite the document and its date |
| Southampton Data Observatory | Council statistics and reports. Public. Check the date and the geographic granularity before joining it to anything |
| Defra UK-AIR | Public downloads of air-quality measurements at Southampton sites. Check which pollutants, and whether the record is provisional or ratified |
| DfT road traffic statistics | Public downloads of counts and annual average flows. These are historical averages, **not live traffic**. Do not label them as live |
| FixMyStreet | The Southampton City brief names public FixMyStreet reports as a starting point. The JSON API path commonly cited (`/api/v1.0/reports`) returns 404, so use the public pages and record the date of collection rather than assuming a feed |

## Practical rules that come straight from the briefs

- Keep keys and passwords out of the repository. `.env` is git-ignored; commit `.env.example` with blank values.
- Show where each number came from and when it was collected. `raw/MANIFEST.json` exists for exactly that: it records the URL, UTC timestamp, byte count and sha256 of every fetch.
- Never present cached data as live, and never present synthetic data as real. Human-readable dates come from the manifest, so a demo can say "collected 14 minutes ago".
- Do not send non-public council information, confidential material or real customer data to an external AI service.
