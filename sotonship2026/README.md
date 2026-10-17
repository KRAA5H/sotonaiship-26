# SotonShip 2026 — working repo

Everything pulled from the organisers' own sites on **16 October 2026**, plus the build folder.

| Folder | What is in it |
|---|---|
| `hackathon-info/` | The event as published: schedule, rules, judging, per-track briefs, data sources, submission requirements, contacts. Read-only context. |
| `code/` | Where the entry gets built. Repo skeleton, submission README template, data-fetch script. |

## Read this first

- `hackathon-info/README.md` — index of the docs, and what is stale.
- `hackathon-info/judging-and-scoring.md` — the five criteria and weights, and the VC for a Day maths. This is what the weekend is scored on.
- `hackathon-info/submission-requirements.md` — exactly what has to be on the team page before the lock.
- `code/README.md` — build rules that carry a disqualification risk if missed.

## The two things that matter most

1. **Submissions lock at 13:00 on Sunday 18 October.** The organiser's wording: no extensions, and a team whose submission is incomplete at the lock is not shown in Stage 1.
2. **Working product is the heaviest criterion at 25%**, and every track includes it. A demo that does not run cannot score on it, and ties break on it first.

## Two candidate tracks

`hackathon-info/track-southampton-city.md` and `hackathon-info/track-fintech.md` are the full briefs for the two being considered. `hackathon-info/tracks-overview.md` compares all three.

## Pushing this

```
cd sotonship2026
git init
git add .
git commit -m "SotonShip 2026: event docs and build folder"
git remote add origin <your repo url>
git push -u origin main
```

The event's own rule: the project repository is created **after hacking opens** (Fri 16 Oct, 20:00). `code/` is a skeleton, not the entry's repo. Point the entry's repo at the track partner's requirements, and keep this one as the notes repo.
