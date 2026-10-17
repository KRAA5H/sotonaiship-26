# Source index

Every page pulled, when, and what it held. All fetched **16 October 2026, 18:30–18:45 BST** by direct HTTP request with `curl`, because the live portal is a Next.js app whose server-rendered HTML carries the content but whose client-side shell returns nothing to a page extractor.

Raw copies live in `raw/` (HTML plus a text extract per page). The three track brief PDFs and their text extracts live in `briefs/`.

## live.sotonship.space — the live event portal

| URL | Raw file | What it held |
|---|---|---|
| `/` | `live.sotonship.space_.html` | Hub landing: "the weekend hub: teams, schedule, submissions and voting", log in, links to schedule, judging and help |
| `/schedule` | `live.sotonship.space_schedule.html` | The full three-day schedule with real times, the lock at 13:00 Sunday, and the Sunday pitch and panel slots |
| `/tracks` | `live.sotonship.space_tracks.html` | The three tracks in summary, with the partner names and links to the full briefs and PDFs |
| `/tracks/southampton-city` | `live_tracks_southampton-city.html` | Full Southampton City brief |
| `/tracks/fintech` | `live_tracks_fintech.html` | Full FinTech brief |
| `/tracks/responsible-ai` | `live_tracks_responsible-ai.html` | Full Responsible AI brief, with the cited papers |
| `/judging` | `live_judging.html` | The Ship test, five weighted criteria, score bands, track lenses, submission requirements, pitch structure, VC for a Day maths, Stage 2 panel |
| `/qa` | `live.sotonship.space_qa.html` | Live Q&A board. **0 questions at fetch time**; needs a login to ask or upvote |
| `/help` | `live.sotonship.space_help.html` | Committee roles and what each handles, plus emergencies. Footer links to privacy and code of conduct on the `www` site |
| `/login` | `live_login.html` | Two login routes: emailed 6-digit code to the Luma email, or the badge access code |
| `/briefs/southampton-city-brief.pdf` | `briefs/southampton-city-brief.pdf` | 5-page PDF brief. Content matches the live track page |
| `/briefs/fintech-brief.pdf` | `briefs/fintech-brief.pdf` | 5-page PDF brief. Content matches the live track page |
| `/briefs/responsible-ai-brief.pdf` | `briefs/responsible-ai-brief.pdf` | 6-page PDF brief. Content matches the live track page |

Other routes that exist in the app but were not pulled: team pages, the submission form and the voting interface, all behind the login.

## www.sotonship.space — the pre-event site

| URL | Raw file | What it held | Freshness |
|---|---|---|---|
| `/` | `www.sotonship.space_.html` | Pitch, 120 builders, free, overnight, the four pillars, the backers, applications closed | Front page, current on status |
| `/mission` | `www_mission.html` | Why the event exists: universities teach AI theory, not entrepreneurship | Stable |
| `/pillars` | `www_pillars.html` | The four strands: tracks, workshops, talks, VC for a Day | Stable |
| `/pillars/tracks` | `www_pillars_tracks.html` | Track summaries plus the rules, criteria and prize structure as they stood earlier. **Describes Responsible AI as the AI Cyber Arena — superseded** | Stale |
| `/pillars/workshops` | `www_pillars_workshops.html` | Saturday workshop: Dr Gomer, how local authorities use technology and AI, listed as Sat 16:00–18:00 | Partly stale; the live schedule places that talk at 18:00–19:00 Sunday |
| `/pillars/talks` | `www_pillars_talks.html` | Talk programme by day: Friday Mayor and VIPs, Saturday JPMorganChase then Responsible AI with Prof Gopal, Prof Aled, Prof Ivan, Sunday Hackathons UK | Partly stale |
| `/pillars/vc-for-a-day` | `www_pillars_vc_for_a_day.html` | VC for a Day in four steps: get funded, due diligence, back your picks, People's Choice | Stable, but the live judging page has the real rules |
| `/manifest` | `www_manifest.html` | Pre-event Friday manifest and venue travel details. **Says the venue closes at night; contradicts the FAQ and the live schedule, both of which say overnight is allowed** | Stale on the overnight point |
| `/manifest` (venue block) | same file | Getting there: train, bus, bike, parking, access | Current |
| `/sponsors` | `www_sponsors.html` | Partner and sponsor list, grouped | Current |
| `/leaderboard` | `www_leaderboard.html` | "To be announced after the event ends" | Placeholder |
| `/logbook` | `www_logbook.html` | Photo-gallery captions from last year, no text of substance | Marketing |
| `/boarding-pass` | `www_boarding_pass.html` | Participant info, eligibility bullets, three-step boarding process | Current on status |
| `/faq` | `www_faq.html` | Cost, who can attend, IP ownership, teams, venue, overnight, what to bring, conduct. Confirms overnight and 20:30 Sunday close | Current |
| `/prizes` | `www_prizes.html` | Prize structure, Hackiest Hack, eligibility, how winners are chosen, how money is paid, judge feedback. Last updated 12 September 2026 | Mostly current; the live judging page has the detailed VC for a Day rules |
| `/code-of-conduct` | `www_code-of-conduct.html` | Hackathons UK code plus the event's own articles, fair play rules, five reporting routes, welfare | Current. Last updated 12 September 2026 |
| `/privacy` | `www_privacy.html` | What registration data is collected, who sees it, retention, rights. Luma is the registration platform | Current. Last updated 12 September 2026 |

## External links referenced by the pages, not fetched

- Hackathons UK code of conduct: `https://hackathons.org.uk` (the event runs under it in full, and it is the authority if the two disagree)
- Hackathons UK incidents: `incidents@hackathons.org.uk`, `+44 300 131 3331`
- Hackathons UK privacy policy
- Luma registration page: `https://luma.com/t9fj4gbf` (closed)
- RAi UK research overview, and the papers cited in the Responsible AI brief (in `track-responsible-ai.md`)

## What changed between the pre-event site and the live portal

1. **Overnight is allowed.** The pre-event manifest said the venue closes at 20:30 on Friday night and there was no sleeping on the floor. The FAQ and the live schedule both say the opposite: open Friday 17:00 to Sunday evening, sleep on site, bring a sleeping bag.
2. **Responsible AI changed from a cyber-arena to a product brief.** The pre-event site described an AI Cyber Arena with Holistic AI, Docker images up to 1 GB, an offline-only rule and a hidden benchmark. The live brief is a product, evidence and business case brief with no Docker or leaderboard.
3. **Finalists per track: three, not two.** The pre-event tracks page said the top two per track pitch on the main stage; the live judging page says the top three go to the panel and Sunday's schedule allots 9 finalists.
4. **Submission lock is 13:00 Sunday.** Some earlier summaries circulated with 12:00; the live judging page, the schedule and all three briefs say 13:00, with a "final countdown" hour from 12:00.
5. **Team size wording conflicts** between the judging page ("exactly 2 members") and everything else (two to five). Worth one question at the desk.
