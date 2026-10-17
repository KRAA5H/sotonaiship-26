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
| duplicate_of | id, or empty | R-0004 |
| reporter_ref | anonymous text | synthetic-2408 |
| link_token | random text (unique) | k3Jx9Qw2mZpV7tRb |
| area | named Southampton area, or empty | Portswood |
| status_changed_at | text (ISO date), or empty: when the status first changed | 2026-10-18T09:30:00+00:00 |
| photo_path | path under `code/photos/`, or empty. Never sent to a page; served only at `/council/photos/<id>` | synthetic/pothole.png |

## Pages
- `/council`: all reports, filters, duplicate grouping, status buttons (login or private).
- `/r/<link_token>`: one resident's own report and status only. The agent sends this link in its last message.

Never use `id` in the resident link. Only the random `link_token` opens a report.
