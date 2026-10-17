# Decisions

The short record of what we decided and what we rejected, so nobody re-opens a settled question at 2am.

**Rules.** Every contract change, scope change or feature removal gets one line here. One line each: what, why, who. `PLAN.md` is the source of truth; this file explains how it got that way.

---

## The identity decisions

| # | Decision | Why | Decided by |
|---|---|---|---|
| D1 | The problem statement stays **volume and money**: 10,948 incidents, the rising rate, 755 open cases, £830,000 on potholes | It is the strongest evidence in the brief, it is local, and a public audience feels it immediately. The "asymmetric information" reframe is a supporting line, not the headline | Team |
| D2 | The pitch leads with **the agent executing every step**. We do not open with "one human decision, ten machine steps" | That is the ambition, and it is what the demo shows. The autonomy dial and the approvals stay as safety features, described when asked, not as the headline | Team |
| D3 | **One-shot first.** Photo and words in, one line and a reference out. Zero questions when the message is complete, one confirm-back when it is ambiguous, never a second form | It answers the "not another chatbot" objection structurally, and it makes the demo faster | Team |
| D4 | The **primary user is the resident who falls out of the portal**, the officer is the operational beneficiary, the council is the buyer | It gives C1 a named user with a measurable inclusion claim, and it uses the one case where conversational intake is clearly justified | Team |
| D5 | **The only counterpart is the model.** No human-to-human chat, no shared inbox for conversations, no DM product. An officer can send a **one-way status update**, and anything the resident sends back is read by the agent | We are not building a messaging service. Staffing a human chat is out of scope and it is not the product. Escalation to the complaints process covers the case where a person is genuinely needed | Team |

## What we kept from the Gomer review

| # | Decision | Why |
|---|---|---|
| D6 | **Neighbour count** on the acknowledgement and the officer card ("3 other people nearby reported this") | Cheap, and it turns a private report into visible collective action without exposing anyone's data |
| D7 | **Escalation route**: "not fixed" or "I disagree" routes to the council's formal complaints process and the ward councillor, with official links | The machine must never be a wall. This is two hours of work and it protects the weakest moment in the product |
| D8 | **Tier-aware ownership resolver**: function x location to (authority, team) | In Hampshire the same defect belongs to county, district or parish depending on the function. A single routing table would be wrong one mile outside the city, and it is also our best failure case |
| D9 | **Plain English** everywhere resident-facing: "hole in the road", not pothole. Reading age 9 to 11, measured | It is the inclusion claim made real, and it takes an afternoon |
| D10 | **Photo-only opening** in the video | It proves the inclusion claim in seven seconds, better than any statistic |

## What we rejected

| # | Rejected | Why |
|---|---|---|
| D11 | Reframing the problem statement around "the council cannot see the problem" | The council can see it. The volume and cost evidence is stronger and less arguable |
| D12 | "One human decision, ten machine steps" as the headline | Honest, but it under-sells what the system does and it is not what the judges are asking about |
| D13 | Officer free-text chat with the resident | Out of scope, needs staffing, and it turns the product into a messaging service |
| D14 | Consultation comment analysis | Good second product, different user, different week. Roadmap only |
| D15 | Satellite imagery | Five day revisit, October cloud, no ground truth. Cannot be demonstrated live |
| D16 | Building an auth system, billing, or multi-tenancy | Not this weekend |

## Engineering decisions

| # | Decision | Why |
|---|---|---|
| D17 | **One home for code: `code/`.** The duplicate `.py` files at the repo root are frozen, and are deleted before the judged repo is created | Two copies of the truth is the fastest way to lose an hour. Do not edit the root copies |
| D18 | **The brain must run with no API key**, falling back to a deterministic stub, and every response says whether it came from the model or the stub | Unblocks everyone tonight, and the stub is also our C2 baseline. Never present stub output as AI output |
| D19 | **Contracts are frozen**: vocabulary, report JSON, endpoints, tables, interfaces, as written in `PLAN.md` section 4 | Four people cannot merge against moving shapes |
| D20 | **`main` is always runnable**, `python code/smoke.py` passes before any merge | Demo risk is the biggest risk we have |
| D21 | **Every quoted number comes from `NUMBERS.md`** | The video, the pitch and the README must not drift apart |
| D22 | Video is a **trailer with a real product spine**, 2:40 plus a 20 second live call to action, declared at submission | The submission page requires real product footage, so the trailer can never carry it alone |
| D23 | Model access is **OpenAI-compatible over HTTP**, not the Anthropic SDK. `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free` | Keys are unsettled. The `openrouter/free` router returned "User Safety: safe" instead of an answer, so a specific free model is pinned. It answered correctly in 3.8 to 8.0 seconds. Swapping provider is two env vars |
| D24 | BlueBubbles sends with `method=apple-script` | `private_api` is false on server 1.9.9, so `private-api` would fail every send |
| D25 | Plans stay short and the todo list carries **only live development work** | A plan nobody reads is worse than no plan |
| D26 | **Reports follow `CLAUDE.md` and `dashboard/schema.sql`, replacing `PLAN.md` section 4.** One 11-column `reports` table, `R-0001` ids, statuses `new` / `in_review` / `resolved`, no coordinates, no channel, residents see only `/r/<link_token>`. Duplicates: same category, same location text, open (not resolved), within 30 days, as in `agent/categories.json`. The KB-xxxx report object, its statuses and the 80 m / 14 day rule are retired | The newer design is what the dashboard, the fake data and the agent tools are built on; two report shapes would split the team. Signed: Aadil |
| D31 | **Grounded answers use the full fact sheet, not a vector database and not keyword retrieval.** All 53 dated facts fit in one prompt (about 2,940 tokens). The model returns the fact numbers it used, and we append the citation. It answered 12 of 12 evaluation questions correctly and refused 2 of 2 unanswerable ones | A keyword list failed on natural language ("gas leak" matched nothing) and was hand-maintained. An embedding model would mean a second provider and key for no measurable gain on 50 documents. Trigger to revisit: if answer citation accuracy falls below 10 of 12 |
| D32 | **Act first, ask second.** A council report with no street is saved with location "Not given", and the resident's next short message fills that row in rather than creating a second report | A missing location used to throw the report away. An incomplete card is the truthful state and the officer can see it |
| D33 | **One module owns every resident-facing string**, with the copy rules enforced as tests: three lines, one link, no markdown, no unconfirmed team names, no search links, no em dashes, silence for thanks | Copy written in three places drifts. The bot used to answer "thanks" with a refusal |
| D34 | **The emergency guard runs before the model.** Gas, fire, trapped, live cable and collapse are recognised locally and get "Call 999 now", never a report | Safety cannot depend on a model call that might fail, and a gas leak is not a litter report |
| D27 | **`deepseek-flash` is DeepSeek V4.1 Flash and handles text and images, so it is the only provider we need.** Effort pinned to `low`, and every DeepSeek request carries `reasoning` | Cheaper on both sides of the token count and faster than V4 Pro on the same prompt. Without the `reasoning` key an image request returns HTTP 200 with empty content, reproduced twice |
| D28 | **The model proposes and `code/triage.py` decides.** Unknown category, no location, `info_only` and `not_council` are refused before `save_report` is called | A wrong row in the database is worse than a question back to the resident, and validation is testable without the network |
| D29 | **Duplicate matching allows extra words at the same place.** "Weston Lane" matches "Weston Lane outside the school". A directional suffix (north, south, east, west, upper, lower) still means a different road | Exact text matching missed a real repeat during the live check; the suffix guard keeps one street from swallowing its neighbours |
| D30 | **The bot remembers a location question for 10 minutes** and joins a short reply to the earlier message | Without it, "there is a pothole near my house" followed by "Alma Road" lost the report. A proper session store is deferred |

## How to change something

1. Write the line in this file first: what, why, who.
2. If it touches a contract, message the file owner and let them merge it.
3. If it adds scope, say what is being dropped to pay for it.
