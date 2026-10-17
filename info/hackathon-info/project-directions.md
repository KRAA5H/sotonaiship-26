# Project directions the organisers published

Every entry below is the organisers' own example, with the details they gave, indexed against the five criteria so the gaps are visible. Their words: "You can build one of them, change it, combine them or ignore them completely. Original ideas are judged on exactly the same terms, and following an example earns no extra credit."

Use this as a menu and as a checklist of what a scored entry needs, not as a plan.

## Southampton City directions

| Direction | Named user | Who pays | What the AI does | Named data | Baseline the brief suggests | Failure to show |
|---|---|---|---|---|---|---|
| Triage for street reports | Council street-scene officers clearing fly-tipping, potholes, broken street lights | The council; other UK councils later | Classifies each report, merges duplicates, estimates urgency, routes to the right team | Public FixMyStreet reports for Southampton | Not stated in the brief | Not stated; the track requires one |
| Pre-check for planning applications | Householders and small architects submitting applications; council validation staff | Homeowners/small architects per check, or licensed by the council | Reads a draft application and checks it against the validation checklist and Local Plan policies | Council public planning register and published policies | Not stated | Not stated |
| Licensing support for HMO landlords | Letting agents and small landlords; council licensing for HMOs | Letting agents and small landlords; council benefits from fewer failed inspections | Reads property details and documents, checks against published licence conditions, lists what is missing | Published HMO licence conditions | Not stated | Not stated |
| Cruise-day planning for local businesses | Cafés, shops and taxi firms staffing on cruise days | Businesses by subscription, or the city-centre business improvement district on their behalf, later other cruise ports | Forecasts demand from the cruise schedule, weather and local events, then turns it into staffing and stock advice | Southampton VTS cruise schedule, Met Office, local events | **Yes:** assume the same demand as the last comparable cruise day | Not stated |

Wider path in every case: the same problem exists at other UK councils or ports, which is the "second city" question the track's judges ask.

## FinTech directions

| Direction | Named user | Who pays | What the AI does | Named data | Baseline the brief suggests | Failure to show |
|---|---|---|---|---|---|---|
| Scam check for people sending money home | Migrant workers sending money abroad, targeted by scams including deepfake calls from a "relative in distress" | A wallet or remittance provider, because a prevented scam saves a refund, a complaint and a lost user | Reads the message or call behind a transfer, spots warning signs, warns the sender before the money leaves | Published scam scripts and public scam reports | **Yes:** a keyword list | Not stated |
| Shell-company check for business onboarding | Bank and fintech onboarding teams opening business accounts | Banks and fintechs that open business accounts, and every UK lender runs the same checks | Takes new business details, pulls the Companies House record and director network, explains the risk signals | Companies House free API and bulk data | Not stated | Not stated |
| Payment address fixer | Bank payments teams holding customer addresses as messy free text | Transaction banks; the same Swift rule applies to every bank worldwide | Cleans and structures addresses into Swift's fielded format, flags the uncertain ones and explains why | Open address data such as OpenStreetMap | **Yes:** simple pattern-matching rules | Not stated |
| Trade document checker | Trade finance staff checking letter-of-credit documents by hand | Banks with trade finance businesses, per document checked | Reads invoice, bill of lading and other documents, extracts key fields, lists every discrepancy, catches forged or reused documents | Public sample trade documents and generated sets with planted errors | Not stated | Not stated |

Every case has a stated rollout story: a second bank, a second market, or every bank on Swift. That is the C4 answer.

## Responsible AI directions

| Direction | Named user | Who pays | What the AI does | Baseline the brief suggests | Measured trade-off |
|---|---|---|---|---|---|
| Release check for customer-support AI | Customer-support teams running a RAG chatbot | Software company or support agency, per bot or per test run | Runs test questions against the bot, highlights unsupported claims, creates a review queue | **Yes:** the same bot without the check | Missed errors and false alarms against human-labelled answers; automated evaluation is evidence for a reviewer, not proof |
| Fairness check before an AI update | A product team shipping a classifier, such as request routing | Product team by subscription covering its models | Release-review checking subgroup error rates across versions | **Yes:** the single average accuracy figure | Subgroup error rates, sample sizes, trade-offs; synthetic results show the workflow, not real-population fairness |
| Evidence assistant for buying AI | An AI procurement team or small company buying a model | Small company, procurement team or consultancy, per supplier assessment | Compares buyer needs with supplier documentation, quotes supporting passages, flags missing evidence | **Yes:** a manual checklist | Missed gaps, invented claims and review time; sells faster evidence review, not certification |
| Service tool that knows when to hand over | Facilities/service teams routing maintenance requests | A facilities provider, per site or per request | Routes requests when evidence is sufficient, sends uncertain cases to a human | **Yes:** route every request automatically | Errors, the fraction handled automatically and the human queue; show what happens when the reviewer is unavailable |

## What these directions share

Reading across all twelve examples, the organisers' own idea of a strong entry has the same five parts every time:

1. **One named user with a job to do**, never "everyone".
2. **A published or open dataset that can be fetched today**, so the build is not blocked on getting access.
3. **An AI step with a stated dumb baseline** to beat: a keyword list, pattern-matching rules, the last comparable day, a manual checklist, average accuracy, route-everything.
4. **A buyer who already spends money on the problem**: a council team, a bank, a remittance provider, the business itself.
5. **A visible path to a second customer**: another council, another bank, another port.
