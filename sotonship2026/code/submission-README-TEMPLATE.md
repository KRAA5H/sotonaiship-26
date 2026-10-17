# Submission README template

The judged repository's README. The organisers' requirement: it must cover **setup, data sources with dates and licences, what the AI does, what was AI-generated or pre-existing, test results, and known limits**. Fill the angle brackets, delete what does not apply, and do not leave a placeholder in the pushed version.

---

# <Project name>

<One line: what it does and for whom.>

<Build for: SotonShip 2026, Track: Southampton City | FinTech | Responsible AI. Team: names.>

## The user and the problem

- **User:** <a named kind of person, not "everyone">.
- **Problem:** <what they do today, how often it costs them, what it costs them>.
- **Evidence:** <dataset, council document, regulation, or a quote from someone talked to at the event, with the date>.

## What it does

<Three or four sentences. The core task, start to finish. Then a screenshot turned into an image file in the repo.>

## Setup

```
git clone <url> && cd <repo>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in the keys listed below
<the single command that runs the demo>
```

Keys needed: <provider>, free tier, sign up at <url>. None are committed.

## What the AI does

- **Model or method:** <model, version, or algorithm>.
- **Where it sits:** <which step of the pipeline, on which input, producing which output>.
- **Why AI is required:** <what breaks if the AI is removed>.
- **Grounding:** <retrieval, rules, constraints that keep the output tied to the data>.

## Baseline comparison

The AI step compared against the simplest thing that could work: <keyword list | pattern-matching rules | last comparable day | manual checklist | average accuracy | routing everything automatically>.

| | Baseline | This system |
|---|---|---|
| <metric 1: accuracy / precision / recall / MAE> | <n> | <n> |
| <metric 2> | <n> | <n> |
| Test set size | <n> | <n> |

## Test results and failures

- Test cases: <how many, how they were built, and that they are held out from any tuning>.
- Known failure: <the case the demo deliberately shows, and what the product does when it hits it>.
- Error cost: <what a false positive costs vs a false negative, and which way the system is tuned, if relevant>.

## Data sources

Every source, with the date it was collected and its licence. `data/raw/MANIFEST.json` holds the URL, UTC timestamp and sha256 of each fetched file.

| Source | What it provides | Collected | Licence | Key needed |
|---|---|---|---|---|
| <Environment Agency flood monitoring> | <flood warnings, river and tide gauges> | <YYYY-MM-DD> | Open Government Licence v3 | No |
| <next source> | | | | |
| <synthetic dataset, if used> | <labelled synthetic> | <YYYY-MM-DD> | <licence> | No |

Attribution lines required by licence, for example: "Contains Environment Agency data © Crown copyright and database right, OGL v3." / "© OpenStreetMap contributors, ODbL."

Synthetic data is labelled synthetic wherever it appears in the product.

## What was AI-generated, and what existed before

- Written by the team: <files or modules>.
- Generated with AI tools: <which tool, which parts>.
- Pre-existing outside the event: <open-source libraries, templates, pre-trained models — by name and licence>.
- Help received: <mentors, other teams, partners, and what they helped with>.

## Known limits

- <what the product does not know>
- <how old the data can be, and what happens if it is stale>
- <what happens outside the covered area, market or input range>
- <what has not been tested, and what evidence would be needed before real deployment>

## Responsible use

- <who can review, override or challenge the output>
- <what personal data is handled, how it is minimised, and what is never collected>
- <official guidance linked to, if the product touches safety, health, legal or financial decisions>

## Business

- **Who pays:** <the buyer>.
- **Price or funding model:** <per check, per bot, subscription, licence>.
- **Cost to run per use:** <including AI inference and hosting>.
- **First three customers:** <names or clear categories>.
- **Second market or customer:** <what changes to serve them>.
- **What stops a big player copying it:** <the moat: data, workflow, integration, distribution>.
