# reports

| column | type | example |
|---|---|---|
| id | text | R-0001 |
| created_at | text (ISO date) | 2026-10-17T12:00:00Z |
| category_id | text | pothole |
| status | new / in_review / resolved | new |
| severity | high / medium / low | medium |
| location | text | 12 Portswood Road |
| description | text | Deep pothole outside the shop |
| has_photo | 0 or 1 | 1 |
| photo_guid | BlueBubbles attachment guid, or empty | iMessage;-;at-0-1A2B3C |
| photo_mime | image/jpeg / image/png, or empty | image/jpeg |
| duplicate_of | id, or empty | R-0004 |
| reporter_ref | anonymous text | synthetic-2408 |
| link_token | random text (unique) | k3Jx9Qw2mZpV7tRb |

## Pages
- `/council`: all reports, filters, duplicate grouping, status buttons (login or private).
- `/r/<link_token>`: one resident's own report and status only. The agent sends this link in its last message.

Never use `id` in the resident link. Only the random `link_token` opens a report.

## Photos
The bytes stay in BlueBubbles; `photo_guid` and `photo_mime` are a reference to them.
`/r/<link_token>/photo` fetches the attachment for the resident's own page. The guid
never appears in a URL, a header or a page, and the council views never select it.
Older rows can have `has_photo = 1` with no `photo_guid`: every display path says
"You sent a photo" and shows no image rather than a broken one.
