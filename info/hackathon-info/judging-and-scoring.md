# Judging and how to win

Source: `live.sotonship.space/judging` plus the judging sections of the three live track briefs. Fetched 16 October 2026. This page is the single most worth memorising.

## The Ship test

The winning project is the one a real customer would start using next month, and that could still be growing in a year. Five plain questions are asked of every team:

1. **Would someone actually use this?** A named user with a painful problem, not "everyone".
2. **Is AI the reason it works?** Remove the AI and the product should stop doing its core job.
3. **Does it really work?** A live, end-to-end demo on real data, including what happens when it fails.
4. **Could it become a business?** Someone pays, or benefits enough to fund it, and it can grow beyond the first customer.
5. **Can people trust it?** It uses data it has the right to use, protects privacy, and is honest about its limits.

Stated plainly by the organisers: they do not reward slides without a product, the number of features, or how advanced the model is. A simple tool that works with a clear customer beats an impressive prototype nobody would buy.

## The five criteria, same for every track

Each scored 1–10 and weighted.

| | Criterion | Weight | What the judges want |
|---|---|---|---|
| C1 | Problem and user | 20% | Who exactly has this problem? How painful and how frequent? What evidence shows it is real (data, a regulation, a conversation with a real user)? What do they do today instead? |
| C2 | AI at the core | 20% | Could this be done without AI? Is AI the right tool, or would a rule, a form or a spreadsheet do? Is the AI used well: sensible model choice, grounded outputs, a comparison against a simple baseline? |
| C3 | Working product | 25% | Does the core task run end to end, live? Real data, not mock-ups? What happens with a bad input or missing data? Is there evidence it works (test cases, accuracy vs baseline, known failures)? |
| C4 | Business and scale | 20% | Who pays, and why? What does it cost to run per user including AI inference? Who are the first three customers? What stops a big player copying it? What changes at 10x or 100x users? Can it work beyond its first market? |
| C5 | Responsibility and trust | 15% | Does it have the right to use its data? Is personal data minimised and protected? What harm happens when it is wrong, and who catches it? Are limits and uncertainty shown to the user? Any obvious legal or regulatory blocker? |

`weighted score = 0.20×C1 + 0.20×C2 + 0.25×C3 + 0.20×C4 + 0.15×C5`

### What the scores mean

| Score | Meaning |
|---|---|
| 1–2 | Missing or not shown |
| 3–4 | Claimed, but weak evidence |
| 5–6 | Solid for a hackathon |
| 7–8 | Convincing, with few gaps |
| 9–10 | Would hold up in front of a real customer or investor |

## How to win, in the organisers' words

- Pick one user and one task. Depth beats breadth.
- The impact of the idea matters.
- Try to talk to a real potential user during the weekend (mentors, partners, other participants) and quote them.
- Get the core task working end to end by Saturday evening, then polish.
- Measure it: a few test cases, a baseline, the failures found.
- Put a number on the business: what someone would pay and what it costs to run.
- Record the video before the deadline. Don't spend the last hour building features nobody will see.
- Show a failure honestly. Judges trust teams that know their limits.

## Track lenses: the extra questions per track

### Southampton City (Council)

| Criterion | Extra questions |
|---|---|
| Problem and user | What is the impact on Southampton, and on whom (residents, council officers, businesses, visitors)? What local evidence shows the problem exists here? |
| AI at the core | What does AI do that a council webpage or form cannot? |
| Working product | Does it run on genuine Southampton data, dated and sourced? What happens outside the area it covers? |
| Business and scale | Who would own and fund it: the council, a service provider, residents, local businesses? Is it niche to Southampton, or could it work in other UK cities and councils? What would it need to move to a second city? What outcome would a council measure (time saved, reports resolved, emissions cut)? |
| Responsibility and trust | Does it work for people who are less digital, older or have access needs? Does it avoid sending non-public council information to external AI services? If it gives safety information, does it point to official sources? |

The brief adds that the pitch must answer three questions clearly: **what local evidence shows the problem is real in Southampton, who would own and pay for the product, and what it would take to run it in a second city.**

### FinTech

| Criterion | Extra questions |
|---|---|
| Problem and user | Which user in a bank, fintech, business or household has this problem? What does it cost them today in money, time or risk? |
| AI at the core | Why does this need AI rather than fixed rules? How does it cope when fraudsters or markets adapt? |
| Working product | How often is it wrong, and what does each error cost (false alarms vs missed cases)? Was it tested against a simple baseline? |
| Business and scale | Who pays: a bank, a merchant, a consumer? How would it plug into existing systems (APIs, payment standards)? Could one of the partner banks (Deutsche Bank, JPMorganChase, TrueMoney) realistically adopt it? |
| Responsibility and trust | Can it explain a decision to a customer or a regulator? Which rules apply (for example FCA Consumer Duty, anti-money-laundering, data protection)? Is customer data handled lawfully? |

The brief adds: the pitch must answer **what evidence shows the problem is real and costly, who would deploy and pay for it, and what it would take to roll it out to a second bank or market.**

### Responsible AI

| Criterion | Weight | What judges should see |
|---|---|---|
| Problem and user | 20% | A specific need, credible evidence and an understanding of affected people |
| AI at the core | 20% | A demonstrated AI capability or assurance function, tested against a sensible baseline |
| Working product | 25% | An end-to-end task, reproducible tests and a demonstrated failure or handoff |
| Business and scale | 20% | A buyer, value proposition, realistic costs, differentiation and a second-customer plan |
| Responsibility and trust | 15% | Measured risk reduction, honest trade-offs, provenance and meaningful human control |

Responsible AI shapes the evidence across all five criteria, not just the last one.

## Stage 1: VC for a Day

Every team pitches on the Sunday afternoon, track by track, in a **random order**.

### Each slot

Up to **3:00 of pitch** (the video plus any live pitch) followed by **1:00 of Q&A**. While a team pitches, anyone can post and upvote questions on its team page; the moderator reads the top ones, judges' questions first.

### Investment rules

- **£10,000 per person per track.** It can only be spent in that track. Unspent money is lost.
- You cannot invest in your own team, but you can invest in other teams in your track.
- **Back at least 3 teams**, and put **no more than £4,000 in any one team**.
- Change the allocation as often as you like while the track is open; the **last save counts**. Investing closes a few minutes after the last pitch.
- Judges invest only in their assigned track, under the same rules, and their money is counted separately.

### The maths

Each side becomes a share of its own pot first, within the track:

```
public_share = public £ in the team / all public £ in the track
judge_share  = judge £ in the team  / all judge £ in the track
stage1_score = 0.7 × public_share + 0.3 × judge_share
```

Ties go to the higher judge share, then the higher average judge score. Results stay hidden until all three tracks are done.

**Reading it:** the public pot is 70% of the Stage 1 score, so a demo that lands in 30 seconds and gets voted for by the room is worth more than impressing three judges. The £4,000 cap per team also means a team needs breadth of support, not one rich backer.

### People's Choice

A symbolic prize for the team that raised the most money from the public across the whole event, whether or not it reached the final panel.

## Stage 2: the panel

- Judges see the finalists and score only teams in their assigned track.
- Each finalist gets about **10 minutes: a 2:00 live demo** (the panel gives it one input of its own choosing) **and 5 minutes of panel Q&A**.
- **Every finalist starts level.** The Stage 1 ranking carries no weight.
- The panel decides 1st, 2nd and 3rd in each track, then picks the overall winner from the three track winners.

**The number to design against:** the panel supplies its own input to the live demo. The demo has to survive an unseen input from a judge, which is a different requirement from a rehearsed screen recording.

## Overall winner and prizes

- One winner per track, one overall winner from the track winners, partner prizes, and People's Choice.
- The overall winner is chosen on a single question: **which project would we most want to see exist in six months.**
- Partner prizes are opt-in at submission, for example best use of a partner's tool or best responsible-AI practice, decided by that partner's own judge from the teams that opted in.
- Non-cash prizes may include follow-on support and conversations with partners about internships.
- Prize amounts are being confirmed with partners and will be announced before the event. The structure is fixed. Prize money is paid by bank transfer to one nominated team member within 30 days; the team splits it.
- Hackiest Hack, presented by Hackathons UK, is open to any team in any track and judged separately by Hackathons UK. The prize description was still a placeholder on the prize terms page.
- **Every judge leaves a one-line note for every team they score**, emailed within a week of the event. Free feedback from people who screen internship applications.

## Contradictions worth clearing up with an organiser

| Where | What it says |
|---|---|
| Judging page | "every team must have exactly 2 members" |
| Track briefs and every other page | Teams of two to five; briefs add "teams of four (two or three fine, solo with an organiser's approval)" |
| Live judging page | Top **3** teams per track go to the panel; Stage 2 says 9 finalists |
| `www` tracks page (dated) | Top **two** teams per track pitch on the main stage |
