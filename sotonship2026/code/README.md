# code

Where the SotonShip 2026 entry gets built. Not the event repo itself.

```
code/
  README.md                      this file
  .gitignore                     keeps keys, data dumps and venvs out
  submission-README-TEMPLATE.md  the README the judges read, section by section
  data/
    fetch_sources.py             pulls the no-key data sources listed in the briefs
    sources.md                   the key-gated sources, and where the key comes from
    raw/                         fetched data plus MANIFEST.json with URLs and timestamps
```

## Run the fetch first

```
cd code/data
python fetch_sources.py
```

Standard library only, no install. It writes each response to `data/raw/`, and `MANIFEST.json` records the exact URL, UTC timestamp, byte count and sha256 of every file. That manifest is the evidence behind the "data sources with dates" line the submission README has to carry.

## Rules that carry a disqualification risk

From `../hackathon-info/rules-and-fair-play.md`, condensed to the ones that get teams thrown out:

1. **No code before hacking opens, Friday 16 October 20:00.** Ideas are fine, code is not. The repository is created after hacking opens.
2. **No pre-existing projects.** Your own earlier work is not eligible, and publishing pre-written code as open source to use it at the event is against the spirit of the rules.
3. **No real customer, personal or partner data, ever.** No connection to a real bank account, card or wallet. No moving real money. No connecting an agent to a real email, calendar or bank: use the sandbox accounts provided.
4. **No API keys or secrets in the repository.** Use a local `.env` that `.gitignore` already excludes, and keep the `.env.example` keys blank.
5. **No scraping personal data, and no sending non-public council or confidential information to an external AI service.**
6. **Never present cached data as live, or synthetic data as real.** Label synthetic datasets as synthetic, in the product and in the README.
7. **Do not submit the same project to another hackathon.**
8. **Safety, health, legal or financial guidance must link to an official source** (council, EA, FCA, MoneyHelper, government) rather than being written by the product.

## Repo hygiene for the judged repository

- Public repository, created after hacking opens.
- README covers setup, data sources with dates and licences, what the AI does, what was AI-generated or pre-existing, test results, and known limits. Start from `submission-README-TEMPLATE.md`.
- Commit the data-fetch manifest, not the bulk data, if the bulk data is large or licence-restricted.
- `.env.example` with empty values so setup is reproducible without a secret.
- One command to run the demo, in the README, tested from a clean shell.

## Shape that scores

Working product is 25% and ties break on it, so the order of work is: core task end to end on real data first, then the baseline comparison, then the failure case, then polish. The pitch is a live demo, and in the final panel the judges supply their own input to a 2:00 live demo, so the core task needs to survive an unseen input.
