# Location pin: data protection and safety

How the "drop a pin" feature (`code/pin_service.py`, `code/pin/static/`) handles personal data under UK GDPR, the Data Protection Act 2018 and PECR.

**This is not legal advice.** It is the team's own plain-English account of what the code does and why, written so that a council data protection officer can check it quickly. A real deployment needs the council's own review (see "Before anything real goes live").

## What the feature does

When a report arrives without a street, the bot texts the resident a short link. The link opens a map. The pin stays in the middle of the map; the resident moves the map under it (by touch, mouse or arrow keys), taps a spot, or searches for a postcode, street or place, then presses Confirm. Optionally they can press a button to use their phone's location once. We save the street, a nearby landmark, the area and the postcode against the report reference. The bot can then use that as the report's location.

## Who is responsible

| Setting | Controller | Processor |
|---|---|---|
| This hackathon prototype | The Kerbside team (set `CONTROLLER_NAME` and `CONTACT_EMAIL`; the privacy page shows a loud placeholder until they are set) | None |
| A real deployment | Southampton City Council, which decides why and how street reports are handled | The Kerbside team, under a written data processing agreement |

Sub-processors and recipients: OpenStreetMap Foundation (map tiles, and Nominatim street lookups) and postcodes.io (postcode lookups). See the table below for exactly what each one sees.

## What is collected, where it goes, how long it is kept

| Data | Where it comes from | Who receives it | Kept | Notes |
|---|---|---|---|---|
| Report reference (e.g. `R-0074`) | The bot | Our server only | With the saved location | Opaque. The pin service never sees a phone number, name or email |
| Link token | Our server | The resident, in the text | Never stored. Only its sha256 hash is | Hash row deleted 7 days after the link expires |
| Pin position (latitude, longitude) | Where the resident moves the map, a search result, or one phone reading | Our server; then postcodes.io and Nominatim, sent by our server | **Not stored** by default. With `STORE_COORDINATES=1`, rounded to 4 decimals (about 11 m) | Never logged. Kept in a short in-memory cache (rounded) to respect Nominatim's rate limit |
| Search text (street or place typed by the resident) | The resident | Our server; then Nominatim, sent by our server | **Not stored**. Never logged. Cached in memory only, so a repeated search does not hit Nominatim again | Residents may type their own address. Nominatim sees the text but never the resident's IP |
| Street, landmark, area, postcode | Derived from the pin by postcodes.io and Nominatim | Our database; the bot; the council dashboard once wired in | As long as the report it belongs to | This is the minimum the council needs to find the problem |
| Coverage (`inside` or `unverified`) and source (`map`, `gps`, `postcode`) | Our server | Our database | With the location | `unverified` flags it for an officer to check |
| IP address | The resident's browser | Our server (in memory, for rate limiting, about 60 seconds); OpenStreetMap tile server (when the map loads) | Not stored by us | The tile server sees the IP as with any website. Our server's access log redacts the link token |
| Cookies, analytics, browser storage | None | None | None | The page sets no cookies and uses no localStorage, sessionStorage or analytics |

## UK GDPR principles, mapped to the code

| Principle | What the code does |
|---|---|
| **Lawful basis** | Public task (Article 6(1)(e)): the council must look after the highway and street scene, and needs a location to act on a report. For the prototype the team relies on the same purpose. Consent is not the basis for the report itself; it is used only for the optional phone location (see below) |
| **Transparency** | `/privacy` explains, in plain English, what is kept, who sees what, for how long, the controller, the contact, and how to complain to the ICO. A short "How we use your location" note sits on the page itself, collapsed, with a link |
| **Data minimisation** | Only street, landmark, area, postcode. Coordinates are discarded by default. No phone, name or email column exists in either table (a test checks this). The browser never contacts postcodes.io or Nominatim, so they never see the resident |
| **Purpose limitation** | The location is saved against one report reference and used only to locate that problem. A link can only write to its own report (a test checks this) |
| **Accuracy** | The resident sees the street before confirming and can move the map to adjust. Moving the map after a phone reading switches the source to `map` and removes the accuracy circle, because a hand-placed pin is the resident's own choice. Confirm stays disabled until the resident has chosen a spot, so the default view can never be confirmed by accident. Pins we cannot verify are saved as `unverified` for an officer |
| **Storage limitation** | Links live 2 hours, shrink to 10 minutes after a confirm, and are deleted 7 days after expiry (`purge_expired()` runs at start-up). Saved locations follow the report's own retention rule, which the council must set |
| **Integrity and confidentiality** | See "Security controls" |
| **Accountability** | This document, the tests in `code/test_pin.py`, and the decision log in `DECISIONS.md` |
| **Children** | The service does not ask for age and does not target children. It collects nothing that identifies a person, so the risk to a child using it is the same as for an adult: a pin placed on their own home. The privacy page uses plain language suitable for younger readers |
| **Rights** | Residents can ask to see, correct or delete their saved location, or object, through the contact on `/privacy`. Because we hold no identifier, the request needs the report link or reference. The page names the ICO (ico.org.uk) for complaints |

## Consent: the optional phone location

- The page **never** asks for the phone's location on load. `navigator.geolocation.getCurrentPosition` is called only inside the click handler of the "Use my phone's location (optional)" button. A test checks the source code, and the browser run checks no request is made on load.
- The phone's own permission prompt is the consent step. The line under the button says the phone will ask first and that we only use the reading to place the pin.
- One reading only. There is no `watchPosition` and no tracking.
- If the resident says no, the page says "No problem. Tap the map where the problem is instead." Nothing else changes.
- The reading is shown as an accuracy circle with "This is where you are now (within about N m). If the problem is somewhere else, move the map." This guards against logging where the resident stands instead of where the problem is.

**PECR.** The text carrying the link is a direct reply to a message the resident sent us about their own report. It is a service message, not marketing, so it needs no separate marketing consent. It must never be reused for anything promotional.

## Security controls

- **Unguessable links.** `secrets.token_urlsafe(9)` (72 bits), stored only as a sha256 hash. The token is in the path, never a query string, and is redacted from the access log.
- **Validation.** Report references must match `^[A-Za-z0-9_.-]{1,40}$` (full match). Coordinates must be finite JSON numbers in range; NaN, infinity, strings and booleans are refused. Postcodes are format-checked before any lookup.
- **Never trust the browser.** Confirm re-runs every check on the server: bounding box, council area, street lookup. The browser's verdict is ignored.
- **Cheap check first.** A pin outside the Southampton box (south 50.84, north 50.99, west -1.56, east -1.28) is refused with no third-party call at all.
- **Search is server-side and bounded.** The typed text (2 to 80 characters) is cleaned, sent to Nominatim by our server with a Southampton viewbox and `bounded=1`, and every result outside the city box is dropped anyway. Search shares the one-request-per-second lock with street lookups.
- **Untrusted third-party text.** Everything from postcodes.io and Nominatim is stripped of control characters and angle brackets and capped at 120 characters. The page writes all dynamic text with `textContent`, never `innerHTML`.
- **Rate limits** per IP, in memory and bounded: check 30, postcode 20, search 20, preview 40, confirm 10 per minute, returning 429. `TRUST_PROXY=1` makes this work behind a tunnel.
- **Headers on every response:** a strict Content-Security-Policy with no `unsafe-inline` (HTML, CSS and JS are separate files; Leaflet 1.9.4 is self-hosted, no CDN), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` allowing geolocation only for our own origin, `Cache-Control: no-store` on links and API calls, and HSTS when served over HTTPS.
- **Nominatim's usage policy** is respected: a real User-Agent (`SOTONFIX_USER_AGENT`), at most one request per second across all threads, results cached, and if the lock is busy for 2 seconds we skip the street rather than queue.
- **Bot endpoint** `GET /api/location/<ref>` is off unless `BOT_API_KEY` is set, and checks the key in constant time.
- **No debug mode**, no `/demo` unless `DEMO=1`, static files served from a fixed allowlist.

## Accessibility

- Mobile first, light and dark mode, tap targets at least 44 px, visible focus outlines, `prefers-reduced-motion` respected (map animations off).
- A live status line (`role="status"`, `aria-live="polite"`) announces every change, for example "Pin set: Windsor Terrace, near The Bargate, SO14 7BQ."
- The postcode box has a label (visually hidden). Errors are said in words, not only colour.
- **Keyboard.** The pin is fixed in the middle of the map, so nobody has to drag a small marker. A keyboard user selects the map (visible focus ring) and moves it under the pin with the arrow keys, zooms with + and -, and confirms with Enter. The browser run checks this keyboard-only path end to end. Searching for a postcode, street or place works fully by keyboard too, and the text reply remains for anyone who prefers it.
- **Remaining gap.** A screen reader user cannot see the map itself, so placing the pin by arrow keys still relies on the street read out after each move. Search, and the text reply, are the better routes for them, and the page says so.

## Risks that remain

| Risk | Why it matters | What we do | What is left |
|---|---|---|---|
| A pin on a private home | The street and postcode of someone's house can be personal data, especially if the problem is at the resident's own address | We store street level, not the house number; coordinates off by default | A postcode can cover only a few homes. Officers should treat locations as personal data |
| The phone shows the resident, not the problem | Logging the wrong place, and revealing where someone stands | Accuracy circle, explicit wording, moving the map switches source to `map`, warning above 100 m | Some residents will confirm without moving the pin |
| The council-area check uses the nearest postcode | Pins near the city boundary or over water can be judged wrongly | Nearest postcode within 1000 m; no result or a failed lookup is saved as `unverified` for an officer | A pin just inside the line can be refused if its nearest postcode is over the boundary. The text reply remains |
| OpenStreetMap tiles and Nominatim are free community services | Their usage policies forbid heavy production use | Light use, caching, one request per second, real User-Agent | A real deployment needs a paid or council-hosted tile and geocoding service |
| postcodes.io availability | Lookups can fail | Failure means `unverified`, never a lost report | None material |
| A forwarded link | Someone else could move the pin | Links expire in 2 hours and shrink to 10 minutes after confirm | A short window remains |

## Before anything real goes live

1. A Data Protection Impact Assessment (DPIA) with the council, covering location data and the third parties above.
2. A data processing agreement between the council (controller) and the team (processor), listing OpenStreetMap and postcodes.io as recipients.
3. Real controller details in `CONTROLLER_NAME` and `CONTACT_EMAIL`, and the council's own privacy notice linked from `/privacy`.
4. HTTPS hosting. Phones refuse location sharing on plain HTTP, and HSTS only applies over HTTPS.
5. A retention rule for saved locations that matches the council's retention schedule for street reports.
6. A decision on `STORE_COORDINATES`. Off is the default and matches the team's rule of never storing coordinates. Turn it on only if the DPIA finds officers need the 11 m position.
7. Production map tiles and geocoding that permit the expected volume.

## Paragraph for the README (responsibility criterion)

> **Location, safely.** When a report has no street, Kerbside texts a short link to a map. The resident taps where the problem is and confirms. We keep only the street, a nearby landmark, the area and the postcode, never a phone number, and by default not even the map coordinates. The page asks for the phone's location only if the resident presses the button, takes one reading, and never tracks. All street and postcode lookups run on our server, so third parties never see the resident. Links expire within hours, the page sets no cookies, and the code enforces a strict content security policy, rate limits and server-side checks on every pin. Our plain-English data protection notes are in `COMPLIANCE_LOCATION.md`.

## Suggested text for the message that carries the link

For Section 2 to own and adjust (`code/messages.py`). Three lines, one link, no markdown, no em dashes:

> Logged: fly-tipping.
> Where exactly is it? Drop a pin on this map: https://example/p/AbC123xyz
> Or just reply with the street name.

If the resident's first message already had a street, no link is sent.
