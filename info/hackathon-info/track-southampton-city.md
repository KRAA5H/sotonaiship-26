# Track: Southampton City

Full brief, from `live.sotonship.space/tracks/southampton-city` and `briefs/southampton-city-brief.pdf` (5 pages). Fetched 16 October 2026.

**In collaboration with Southampton City Council.**

## The challenge

Build an AI-powered product that solves a real problem for someone who lives, works or visits in Southampton, and that could realistically be put in front of that person after the weekend.

Southampton is a port city of around 250,000 people, shaped by its docks, its coastline and two rivers. Its council runs hundreds of services on a tight budget, and its residents, businesses and visitors deal with traffic, air quality, flood risk, housing and access to services every day. There is no fixed list of projects: you choose the problem, as long as you can show it matters here.

Judges look past technical ambition and ask whether the product has a clear user, a working core and a plausible way to be paid for. A simple tool that one council team or one group of residents would start using next month beats an impressive prototype nobody would adopt.

The one-sentence test:

> We help **[a specific person]** to **[do or decide something]** in **[part of Southampton]** using **[AI and the data behind it]**.

Their example: *We help council street-scene officers clear fly-tipping faster across the city by classifying, merging and routing residents' photo reports.*

## Who you build for and what fits the track

Choose **one main user** and design, test and pitch from their point of view. Options:

- a resident (a student, a family, an older person, someone with access needs, a tenant or a small landlord)
- a council officer (planning, highways, street scene, environmental health, housing or customer services)
- a local business or worker (retail, hospitality, the port or logistics)
- a visitor, such as a cruise passenger or a new student

Working well for one neighbourhood, one service or one kind of journey is enough, and is usually stronger than covering the whole city.

Any problem connected to life in Southampton fits: the port and coast, transport, environment and climate, housing and planning, streets and public spaces, and access to council services.

**Does not fit:**

- a general chatbot about Southampton, or a map or prediction that does not lead to a decision
- an existing product with an AI feature added on top
- anything that needs restricted council systems, real personal data, access to port facilities or physical hardware, unless an organiser has agreed it in advance

## What every project must show

1. **A real local problem.** Who has it, how often, what they do about it today, backed by local evidence such as data, a council document or a conversation with someone affected. Putting "Southampton" on a generic app does not count.
2. **AI that the product depends on.** If the product would still do its main job without the AI, AI is not at its core. Where the AI classifies, predicts or extracts, compare it against a simple baseline.
3. **A product that works on real data.** The main task completes start to finish, live, on genuine Southampton data with source and date visible. Synthetic data is fine for testing if labelled as synthetic.
4. **A business case.** Who would pay or fund it (the council, a service provider, local businesses, residents), roughly what it costs to run per user including AI costs, and what it would take to work in a second city.
5. **Honesty about limits.** What the product does not know, how old its data is, and what happens when data is missing, a source is out of date or a location is outside coverage. Show at least one of these failure cases in the demo.

## Directions the organisers want to see

These are starting points; original ideas are judged on exactly the same terms and following an example earns no extra credit.

1. **Triage for street reports.** Residents report fly-tipping, potholes and broken street lights as photos and free text, often several times for the same problem. A tool that classifies each report, merges duplicates, estimates urgency and routes it to the right team would save officers hours a week. The council is the customer, and because every UK council handles the same kind of reports, a product that works in Southampton has an obvious path to other cities. Starting point: public FixMyStreet reports for Southampton.
2. **A pre-check for planning applications.** Many householder applications are returned as invalid because a document or detail is missing, delaying the applicant and costing the council staff time. A tool that reads a draft application and checks it against the council's validation checklist and Local Plan policies before submission could be sold per check to homeowners and small architects, or licensed by the council to cut invalid submissions. The public planning register and published policies are enough to build and test it.
3. **Licensing support for HMO landlords.** Southampton runs a licensing scheme for houses in multiple occupation, which matters in a city with a large student population. A tool that reads a landlord's property details and documents, checks them against the published licence conditions and lists what is missing before an inspection would help letting agents and small landlords and reduce failed inspections for the council. Many other UK councils run similar schemes, so it could grow beyond Southampton.
4. **Cruise-day planning for local businesses.** Cruise calls bring large numbers of visitors into the city on specific days, but cafés, shops and taxi firms often staff by guesswork. A tool that forecasts demand for a particular business from the cruise schedule, the weather and local events, and turns it into staffing and stock advice, could be sold as a subscription to businesses or to the city-centre business improvement district on their behalf, and later to other cruise ports. Compare against a simple baseline such as assuming the same demand as the last comparable cruise day.

## Track rules on top of the event rules

- Build the entry during the event and create the repository after hacking opens. Open-source libraries, templates and pre-trained models are fine; your own earlier projects are not.
- State in the README which parts were AI-generated, what existed before the event, and who helped.
- Show where each number comes from and when it was collected. Never present cached data as live or synthetic data as real.
- Do not collect personal data you do not need, and do not send non-public council information to an external AI service.
- If the product deals with safety, health or emergencies, link to official guidance rather than writing your own instructions.

## Key times stated in the brief

| When | What |
|---|---|
| Friday 16 October, afternoon and evening | Doors open, talks, track introductions and a visit and Q&A with the Lord Mayor; **hacking opens at 20:00** |
| Saturday 17 October | Hacking all day and through the night; Eagle Labs stays open Friday and Saturday nights |
| Sunday 18 October, 13:00 | Hacking stops and **submissions lock** |
| Sunday afternoon | VC for a Day pitches, the final panel and awards |

## Data sources the brief lists

See `data-sources.md` for the full table with access limits. The brief's own advice: there is no compulsory dataset, choose sources that fit the problem, and **check early that they cover Southampton and that you are allowed to use them**.

## The three questions the pitch must answer for this track

1. What local evidence shows the problem is real in Southampton?
2. Who would own and pay for the product?
3. What would it take to run it in a second city?
