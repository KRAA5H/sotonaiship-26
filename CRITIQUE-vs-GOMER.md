# Critical review: our plan against Dr Richard Gomer

Written Sat 17 Oct 2026, evening. Reviewed against `PLAN.md`, `VIDEO.md`, the working code in `code/`, and the notes in `info/richard gomer talk on using ai in the council.md`.

**Advisory only, and partly overruled.** `DECISIONS.md` is the record of what we actually adopted. D1 keeps the volume-based problem statement, D2 keeps the agent-executes-every-step framing, and D5 removes human-to-human chat. The accepted recommendations are D3, D4 and D6 to D10. Do not re-open the rejected ones.

---

## 0. Who he is, and why his objection is the one that matters

Dr Richard Gomer is a Lecturer in Computer Science at Southampton, in the Web, AI and Society group, HCI and agency-oriented design, and a director of several organisations. He led the AI City Innovation Sandpit and the Participatory Envisioning for the AI City of Excellence project, and hosted the University's first Civic AI workshop with Solent local authorities in 2024. He has been a councillor for West End North on Eastleigh Borough Council since 2018 and was made Mayor of Eastleigh in 2026.

Two things follow from that, and they are why his critique is worth the next hour:

1. **He is a service designer who studies agency and values, not an AI enthusiast.** His published line is that civic AI "can't just be a lift-and-shift of products designed for commercial organisations". He will not be impressed by a model. He will ask what relationship the system creates between a resident and their council.
2. **He has to answer to residents for a living.** His questions about accountability, "who makes the decision to use this", and "what reassurance will different groups want" are the questions an elected member gets asked at a surgery, not a rubric. Answering them is the same as answering C5 well.

He is also the single most valuable person in the building for our C1 evidence, because the judging page explicitly rewards quoting a real potential user. He is not our customer, but he is a credible local government voice who has already told us what he thinks is missing.

His public sources, for citation:
- Staff page, University of Southampton: `southampton.ac.uk/people/5xg7qv/doctor-richard-gomer`
- AI City Innovation Sandpit and Participatory Envisioning for the AI City of Excellence project pages
- Civic AI workshop post, August 2024 (the lift-and-shift quote)
- Eastleigh Borough Council, Mayor making 2026

**One warning before anyone quotes him.** The notes in `info/` are your notes from a talk, not a transcript. Do not put quotation marks around them on a slide, and do not attribute a paraphrase in his name. If we want a direct quote, use the published LinkedIn line, which is verifiable, or ask him. Misquoting a sitting mayor in front of a panel that may include him is an avoidable own goal.

Also: the note says "coastal authority, 150,000 approx residents". Southampton is around 250,000. Either that figure refers to another authority, or it was misheard, or it was about Eastleigh. Do not put a resident count on a slide until it is checked against the ONS or the council's own page.

---

## 1. His position, distilled into six claims

| # | His claim, from the notes | What it really attacks |
|---|---|---|
| G1 | "Everyone was pitching chatbots but they said no", and he does not want to roll one out because he "doesn't want to go through many stages for a simple thing". "You should be able to use good web design to solve solution asap" | Our intake agent, and the whole chat-first framing |
| G2 | "If you see the problem, the council sees it too, so it's still important" | Our C1 evidence, which is built on volume of reports |
| G3 | Dangers: overselling AI, "not magic, hard problems are still hard"; "incremental improvements won't solve congestion" | Our "the AI does ALL the steps" line |
| G4 | Civic value *connecting*: AI should enhance connection between people and communities; the danger of "a loss of human connection and people who are isolated"; a chatbot "not letting you do what you need, missing that crucial option" | The resident-to-machine relationship we are building |
| G5 | "Underestimating councils": they are sophisticated, with specialist expertise and multi-million pound budgets; AI must beat what exists | Our integration and business story, which quietly assumes the council is behind |
| G6 | His forward ideas: be more predictive, especially event-driven ("a festival happened and the bins needed collecting"); make council decisions easier to understand; consultation comment analysis is "very human and labour intensive" | Our predictive module (weather-only) and our bounded explainer |

He also concedes one thing that is our opening: some residents, particularly those with low literacy or limited understanding of what councils do, would benefit from a very specific, solution-oriented conversational service. That is the only door he leaves open for a chat interface, and it is the door we should walk through.

---

## 2. Verdict up front

**Three things we got right, and should say louder.**

1. **We do not replace the council's systems.** We are the join between the resident's words and the work order. That is service design, which is his language, not model worship.
2. **Human control is designed in.** An autonomy dial, low confidence to a human, every action audited, every override logged.
3. **We keep the number small.** No name, no account, no ID. That is an inclusion and privacy argument, and it is the sort of thing he would defend.

**Four things he would reject, in decreasing order of danger.**

1. **The chat-first framing.** His strongest objection. "Everyone was pitching chatbots but they said no" is almost a direct instruction. If our pitch opens with "an AI conversational agent", we lose the room he is in. Note the conditionality though: he did license one kind of chat, and section 2.5 is built on it.
2. **The volume-based problem statement.** 10,948 fly-tipping incidents proves the problem is real, not that reporting is the bottleneck. He will say the council already knew.
3. **"The AI does all the steps."** That is overselling, in his exact warning. It also invites the question "so a machine books work orders with public money?" which we do not want to answer in a Q&A minute.
4. **Talking to a machine as the relationship.** We currently improve the resident's contact with the council by removing the humans from it. That is the opposite of his *connecting* value.

**The one sentence that changes.** Our pitch should not be "we built a chatbot that triages reports". It should be:

> The council already sees the problem. The resident cannot see the council. We close that loop, and we do it in the one place they already are, with one text and one question at most.

That sentence is compatible with everything he said, it is still true to the product, and it is a better opening for a public vote than a fly-tipping statistic.

---

## 2.5 The concession is the licence, not the footnote

This is the most important paragraph in the notes, and I gave it too little weight in the first draft:

> Some residents with low literacy rates, or specific residents who have limited interaction and understanding about councils, could benefit from a very specific chatbot solution orientated towards them.

Read carefully, that sentence licenses the project and constrains it at the same time.

| His words | What they license | What they forbid |
|---|---|---|
| "very specific" | One job, one end state, a narrow scope | A general assistant, a directory bot, "ask me anything about Southampton" |
| "solution orientated" | It must actually solve the thing and end in a reference and a next step | Conversation as the deliverable, a chat that answers questions but changes nothing |
| "towards them" | Designed for a named group who currently fail | Designed for the median resident, then claimed to be inclusive |
| "some residents" | An addition to the channel mix | A replacement for the form, the phone line or the surgery |

So the correct position is neither "we built a chatbot" nor "we reject chatbots". It is:

> We built one very narrow reply service for the residents who fall out of the form entirely, and it ends in a work order rather than a conversation.

**This flips the primary user.** `PLAN.md` names the street-scene officer as the target user and the council as the buyer. That is defensible for C4 and weak for C1, because an officer's saved minutes are a cost line, not a story. His concession points at a stronger primary user: the resident who currently cannot get through at all. The officer stays as the operational beneficiary, the council stays as the buyer, and C1 becomes an equity claim with a measurable test.

It also makes C2 easier to argue than it was. For this user, the AI is not decoration: a form cannot read a photo with no words attached, cannot read a voice note, and cannot map "someone's dumped a mattress on the corner" to the council's category called *Flytipping*. Remove the model and the product stops existing for exactly the people it was built for.

### What "specific" has to mean in the build

| Constraint | What it means concretely | Cost |
|---|---|---|
| Photo-first, words optional | The happy path works with an image and no text at all. Test: send only a photo, expect one reply with a reference | 30 min |
| One line out | Maximum two short sentences. No jargon, no service names, no internal codes except the reference | 30 min of prompt and copy work |
| Confirm-back, not interrogation | When the report is ambiguous, read it back in the resident's own words in one sentence and ask yes or no. This is not the same as a clarifying question: it prevents a wrong job rather than adding a stage | 45 min |
| Plain-English taxonomy | Store *Flytipping*, speak "dumped rubbish". Store *carriageway defect*, speak "hole in the road" | 30 min |
| Voice notes | Accept audio, transcribe, treat as text. Only worth it if the channel supports MMS | 1h, optional |
| No dead ends | If it is not the council's, name the owner and give one link. Never "we cannot help", never a phone tree | 30 min |
| Reading age 9 to 11 | A readability score for every resident-facing string, recorded in the README | 20 min |
| Existing channels untouched | The form, the phone line and the councillor surgery stay, and we say so on the slide | copy |

### This refines the one-shot rule

The earlier draft said zero questions, one question, never a second form. With this user in mind, the rule is subtler: a **clarifying question adds a stage and should be rare**, but a **confirm-back is a safety net and should be routine** when the input is ambiguous. "So there's a hole in the road outside number 42, and it's been there about a month. Have I got that right?" is one tap to answer, it catches a wrong job before a crew drives, and it is exactly the affordance that a low-literacy resident needs and a form cannot offer.

### How to prove it by 13:00 without recruiting users at 2am

1. **The photo-only test.** A photo, no text. If the reply is one line and a reference, the core inclusivity claim holds.
2. **The confirm-back test.** Send a deliberately ambiguous message and check that it asks one yes or no question rather than guessing.
3. **A ten point low-literacy heuristic audit**, scored pass or fail and pasted into the README. Cheap, honest, and it shows the work.
4. **Two quotes beat all three.** The judging page rewards a real conversation. If any mentor, volunteer or community contact is in the building tomorrow, ask them to try the photo-only path and write down what they said.

### The language trap

Do not say "for illiterate people" on stage. It is patronising, it is unverifiable, and it turns a design choice into a label. Say **"for residents who currently cannot use the form"**, and quote the council's own digital strategy language back at them: services that are "digitally inclusive, designed around their needs". Mention the Equality Act duty to make reasonable adjustments, because that is the mechanism a council actually recognises and it is the argument for funding this rather than a nicer form.

### What this changes in the demo

The first beat of the video should be a photo with no words, not a typed paragraph. One change, and it proves the inclusivity claim in seven seconds. That is a better opening than any statistic, and it is the single most Gomer-compatible frame we could shoot.

---

## 3. Claim by claim

| Claim | Our plan today | Verdict | What must change |
|---|---|---|---|
| G1 Chatbots rejected | Intake agent with up to 5 turns as the front door | **Conditional, not fatal** | He licensed a "very specific" bot for a defined group (section 2.5), so the fix is specificity plus one-shot-first, not deletion. Flip the default: photo and text in, one acknowledgement plus reference out, zero questions when the message is complete, one confirm-back when it is ambiguous. Rename it in the pitch: not a chatbot, a **reply**. Cost: one system prompt rewrite, 30 minutes |
| G2 Council already knows | C1 leans on incident volume and 755 open FixMyStreet cases | **Partial** | Reframe from discovery to **asymmetric information**. The harm is that residents report into a void and stop reporting, so the council loses its demand signal and its early warning. Keep the numbers as context, not as the argument. Cost: 20 minutes of copy |
| G3 Overselling | "Agent does steps 1 to 10 without a human" | **Conflict with wording** | Change to **"one human decision, ten machine steps"**. State plainly: we cut handling time and duplicate visits, we do not claim to reduce fly-tipping. Add one honest line: if the backlog is three weeks, it is still three weeks, but the resident now knows. Cost: wording |
| G4 Connecting | Resident to machine, officer sees the dashboard | **Partly conflict** | D5 settles it: there is no human chat. Keep the two cheap features that do not need staffing: (a) "3 of your neighbours reported this", collective visibility with no personal data; (b) an escalation route, "not good enough", to the statutory complaints process and the ward councillor, with the official link. Cost: about 2 hours |
| G5 Underestimating councils | We talk as if we are teaching them their own systems | **Partial** | Add the procurement reality: DPIA, data processing agreement, records retention, FOI, automated decision-making under UK GDPR Article 22, and the fact that **Balfour Beatty, not the council, is the gatekeeper for the crew's today list**. Say that our model does not know more than their highways engineer, it just reads faster. Cost: copy, 20 minutes |
| G6 Predictive, event-driven | Weather, tide, leaf and growth index | **Partial** | Add **event-driven demand**: fixtures at St Mary's, cruise calls from VTS, festivals, freshers' week, school terms. Predict report and waste volume by area and hour, pre-position crews. Baseline: last comparable event, which is the brief's own suggested baseline. This is closer to his festival example than soil temperature is. Cost: a hand-collected events CSV plus a spike analysis, about 2 hours |
| G6 Decision explainability | A bounded "what does the council do" answer door | **Too weak, wrong target** | Explain the **resident's own decision**, not the council's governance. Every message shows what happened and why: matched with 4 others, assigned to Highways crew 2, due Tuesday, because it is on a school route. That is decision transparency at the point of maximum relevance, and it is what he is actually asking for. Cost: UI only |
| G6 Duty to consult | Absent | **Gap, correctly out of scope** | Do not build it. Put it on the roadmap slide as the second function of the same engine: comment in, structured objection out, themes clustered, and **overlooked issues surfaced**, which is exactly what the traffic engineer reads for. Same 11 steps, one box changed. Cost: one diagram, 30 minutes |
| Multi-tier government | Ownership resolver assumes one council | **Gap with a real bug inside** | Our second-city story says "swap the routing table". In Hampshire that is not a table, it is a **tier decision**: county for highways, district for waste, parish for verges, National Highways for the A27, the EA for coastal defences. Make the resolver (function x location) to (authority, team). This is also a much better demo failure case than the private car park. Cost: 90 minutes |
| Inclusion | No app, no account, voice notes, SMS fallback | **Aligned, under-proven** | Add a measurable target: every resident-facing message at reading age 9 to 11, checked with a readability score, and plain English category names. Add the freephone or shortcode point, because a paid shortcode is an exclusion. State the gap honestly: non-English languages are not covered this weekend |
| Accountability | Audit log and overrides | **Aligned** | Make the audit readable by a councillor, not an engineer: one paragraph export, "why did the machine do that", plus a named service manager. He is an elected member, so the elected route has to exist |

---

## 4. The three hard conflicts, argued properly

### 4.1 The chatbot conflict: flip the default

His objection is not that machines cannot read text. It is that a chat interface adds stages to something that should be one step. He said good web design solves it faster, and he is right about the design most councils ship. But he also named the one case where a chat genuinely helps, and section 2.5 is the answer: aim at that case, not at everyone.

Our answer cannot be "but ours is different", because everyone says that. It has to be structural:

**One-shot is the default. Conversation is the fallback. The machine only speaks when it is missing something it cannot get elsewhere.**

If the resident sends a photo with the text "pothole outside 42 Shirley Road", the correct behaviour is a single message back: "Logged, KB-1042, Highways, due Tuesday." No questions. The photo's metadata, the text, and the geocoder do the work. That is one fewer stage than any form, and it is what a good service would do.

The agent asks a question only when the report is genuinely unusable without one, and then only one, and never for something the phone already told us. That yields a hard product rule worth putting on a slide:

> Zero questions when the report is complete. One question when it is not. Never a second form.

Measured against the council's own portal, this is a service design claim we can test in half an hour: submit a pothole on the Empro portal and count the interactions. We will report the number, whatever it is. If the portal takes 11 interactions and ours takes 2, that is his own argument settled with evidence rather than assertion, and it costs us 30 minutes tonight.

**What we should stop saying:** "conversational agent" as the headline noun. Say "reply", "intake", "the council in your messages". Keep the word agent for the orchestration behind the scenes, where it is accurate.

### 4.2 The "council already sees it" conflict: move the argument

He is right, and our C1 currently walks into it. 10,948 incidents is evidence that the problem exists, not that discovery is the constraint.

The constraint is the loop. The resident reports, hears nothing, assumes nothing happened, and stops reporting. The council fixes some of it and cannot show that it did. Two harms follow, and both are measurable: residents lose trust, and the council loses a free, high-resolution demand signal.

This reframe also upgrades the product's value:

- **For the resident**: certainty. Logged, owned, scheduled, done.
- **For the officer**: one decision per report instead of six handoffs.
- **For the council**: a demand dataset it did not have, and a public "we fixed this" record it can defend.

That third one is the one to lead C4 with, because it is the thing that makes number-of-reports prioritisation matter.

### 4.3 The overselling conflict: one human decision, ten machine steps

His warning is specific: not magic, hard problems stay hard. Our step table reads like a boast. Rewrite it as a ratio, because a ratio is both more modest and more impressive:

| Today | With Kerbside |
|---|---|
| 6 handoffs, 2.5 minutes of officer reading per report, no feedback to the resident, duplicates attended twice | 1 human decision per report (approve or override), 10 machine steps, feedback at every stage, duplicates merged before a crew moves |

And the honesty line, said out loud in the video: "We do not claim to reduce fly-tipping. We claim to halve the time between a resident caring and a crew knowing."

---

## 5. His six civic values as the pitch scaffold

This is the most directly usable thing in the notes. He gave a checklist. Use his checklist, in his order, and the pitch becomes legible to a civic audience in a way that C1 to C5 is not.

| Value | His question | Our answer | The artefact that proves it |
|---|---|---|---|
| **Effective** | What does it do, who uses it, what evidence shows it beats the status quo | Turns a message into a scheduled work order; used by the street-scene officer; measured against the keyword baseline and against the council's own form, with the numbers shown | The eval table and the steps-to-report count |
| **Inclusive** | Who benefits, how are benefits shared, how do we avoid new exclusions | Reaches residents who bounce off a 22-field portal, including low literacy and older residents; voice notes, no app, no account, SMS as well as iMessage; every message at reading age 9 to 11; the phone line and the walk-in stay | The readability score, the SMS path, the channel list |
| **Connecting** | Which relationships change, who still needs to talk to a human and how | The relationship changes from silence to a loop. Neighbours see each other's reports. A person is one word away through escalation, and the existing channels are untouched. The counterpart stays the model (D5) | The neighbour count, the escalation button, the channel list |
| **Transparent** | How are people informed, how do they understand the impact | Every step is narrated to the resident in their own thread, and every decision shows its reason on the officer card | The thread, and the audit paragraph |
| **Accountable** | Who decides to use it, who monitors and shapes it | A named service manager owns it, the autonomy dial is theirs, overrides are logged and reviewed monthly, and the public record of resolved reports is publishable | The audit log, the monthly review, the public digest |
| **Acceptable** | What will different groups think, what reassurance do they want | Tested with residents, not just with us; no dark patterns; opt out in one word; data minimisation sold as a choice, not a limitation | Two real reactions, quoted, plus the STOP behaviour |

If we only do one thing from this review, do this table. It costs an afternoon of copy and it re-frames everything we already built.

---

## 6. Prioritisation by report count

Your note says "we need to add prioritisation based on number of reports". It is already in `PLAN.md` at step 7, but it is buried and it is not visible. Make it three things:

1. **A visible factor, not a hidden score.** The officer card shows the three inputs: severity, exposure, and **reports in the cluster**. No magic number.
2. **A threshold that changes the kind of work.** 1 to 2 reports is a job. 5 or more at one location in 30 days is a **defect, not an incident**: it escalates from a repair to an inspection, and it enters a capital programme candidate list. 20 or more is a service failure with a named owner. This is the insight that makes resident reports matter beyond triage: volume is evidence for investment, and councils currently have no cheap way to assemble it.
3. **A public version.** "This street has been reported 23 times since January" is the single most powerful transparency artefact we could ship, it needs no AI, and it is exactly the sort of thing that reduces conspiracy thinking, which he specifically hopes better communication would do.

Formula for tonight, deliberately simple and auditable:

```
priority = severity (1-4) x exposure (1-3) x report_factor (1 + log10(1 + reports_30d))
```

Show it in the README, show the factors on the card, and never let it become a black box.

---

## 7. What the code actually does, versus the plan

The loop does not exist yet. `conversational_ai.py` and `database.py` cover intake and storage. There is no triage, no dedupe, no priority, no work order, no scheduler, no console, and the Plan's own Gate 2 ("ugly but complete loop by 19:30") has already slipped. Re-baseline the schedule in the next ten minutes rather than pretending.

Three implementation bugs worth fixing before anything else is built:

1. **The BlueBubbles send payload uses `"message"`, the docs' sample uses `"text"`.** One of them is wrong for your server version. Print the error body on the first send and fix it, or the demo's first beat fails in front of the room. This is a two minute risk to retire.
2. **The 5 exchange cap throws away what the AI already extracted.** The check runs before the model call, so the fifth message force-completes with the raw text as the description and `location: None`, discarding three turns of good extraction. Fix: on the cap, make one final call instructing "complete now with what you have", and only fall back to raw text if that call fails.
3. **The phone number is stored in plaintext** in `phone TEXT`, while `PLAN.md` promises hashing. Fix before any device other than our own touches it: store a salted hash, keep the raw handle only in the in-memory session, and add a `DELETE` path. It is a one line change and a whole slide of trust.

Also, root level duplicates of `blue_bubbles.py`, `conversational_ai.py` and `database.py` sit next to their `code/` copies. Pick one home before the judged repo exists, or a judge will read two versions of the truth.

One more: the system prompt is a good start but has no guardrail for safety content. The rules require official links for anything touching safety, health or emergencies. Add to the prompt: never give safety instructions, always link the Environment Agency flood warnings and 999, and never promise a repair time we cannot keep.

---

## 8. Patch list for PLAN.md

Apply these, in this order, and the plan becomes Gomer-compatible without losing the build.

| # | Where | Change |
|---|---|---|
| P1 | Section 0, first paragraph | Replace the fly-tipping opening with the asymmetric-information opening: the council already sees the problem, the resident cannot see the council |
| P2 | Section 3.1 | Add the one-shot-first rule and the "zero questions, one question, never a second form" line |
| P3 | Section 3.3, intro | Replace "the agent does 1 to 10 without a human" with "one human decision, ten machine steps", and add the "we do not claim to reduce fly-tipping" line |
| P4 | Section 3.2 officer console | Add the officer reply into the resident thread, the neighbour count, and the escalation route |
| P5 | Section 3.3 table, step 4 | Make the ownership resolver tier-aware (function x location), and add the outside-boundary report as the primary failure case |
| P6 | Section 5.3 | Add event-driven demand prediction with the last-comparable-event baseline |
| P7 | Section 12 business case | Add procurement reality: DPIA, processor agreement, Article 22, records retention, and Balfour Beatty as the gatekeeper |
| P8 | New section | The six civic values table from section 5 of this document, placed immediately before the judging map, as the pitch scaffold |
| P9 | Section 7 data | Add the readability target and the freephone point |
| P10 | Section 16 | Add the 30 minute steps-to-report experiment against the Empro portal, tonight |
| P11 | Section 1, target user | Make the resident who currently fails at the form the primary user, and the officer the operational beneficiary. Add the eight low-literacy constraints from section 2.5 of this document as build requirements, with the photo-only and confirm-back tests as acceptance criteria |
| P12 | `VIDEO.md`, 0:20 beat | Change the first resident message from a typed paragraph to a photo with no words at all, and make the reply one line. This is the cheapest inclusivity proof in the project |

Time cost of P1 to P10: about 2 hours of writing and 90 minutes of engineering for the tier resolver. The events module (P6) is 2 hours and should be paid for by cutting the satellite discussion entirely and reducing the trailer's AI b-roll to three shots.

---

## 9. Revised schedule deltas

| When | Change |
|---|---|
| Now | Re-baseline the gates honestly. Fix the three code bugs. Run the steps-to-report count on the Empro portal, and write the number down whatever it is |
| Before midnight | Complete loop, one-shot path working, officer reply into the thread, neighbour count, escalation route. The tier resolver can wait until morning |
| Overnight | Event CSV and the spike analysis if the loop is green. If the loop is not green, nothing else starts |
| Morning | Civic values slide, readability pass on every string, the "why did the machine do that" paragraph export |
| 10:30 | Freeze, as before. The only addition permitted after freeze is copy |

Do not add the consultation module. Do not add full council governance explainers. Do not chase satellite imagery. Every one of those is a good idea that costs the loop.

---

## 10. If he is in the room

Rehearse these four answers, in this order, because he will ask one of them.

**"Isn't this just a chatbot?"** No. A chatbot is the fallback, not the product. If a resident sends one photo and one sentence, they get one reply and a reference, and no questions at all. The machine speaks only when the report is unusable, and never twice. The product is the work order and the closed loop.

**"The council already knows about the pothole."** Yes, and that is not the problem. The problem is that the resident does not know the council knows. We are not adding discovery, we are closing the loop, and the side effect is that the council gets a demand dataset it can defend.

**"Why not a better web form?"** We would support that too, and we can prove the difference rather than assert it: we submitted the same report through the council's own portal and through the message channel and counted the interactions. Here are both numbers, and here is the count for a resident who has a photo and no words, which is the case a form cannot serve at all.

**"Who is accountable when it books a crew to the wrong place?"** A named service manager, an autonomy dial that starts at suggest-only, and an append-only audit that a councillor can read in a paragraph. The machine never spends public money without a human pressing approve until the error rate on that category is measured and the council chooses otherwise.

---

## 11. Bottom line

The plan is strong on engineering and weak on the politics of the thing, and the notes are a map of exactly where. Three changes carry almost all of the value:

1. **One-shot first, conversation as fallback, and narrow by design.** This turns his strongest objection into a design principle, and it makes the demo faster. The qualifier matters as much as the rule: narrow, solution-oriented and aimed at the residents who currently cannot get through, which is the only kind of chat he said yes to.
2. **Close the loop, do not just speed the queue.** This moves C1 off contested ground and onto ground where we can win, and it makes the connecting value real rather than claimed.
3. **One human decision, ten machine steps.** Same work, honest framing, no overselling, and a better story for a public vote.

Everything else, including event prediction, consultation analysis and the tier resolver, is upside if the loop is green by midnight, and a distraction if it is not.

The most Gomer-compatible sentence we can say on stage, and the one I would build the video's last line around:

> The council already saw the problem. Now the resident can see the council.
