# Track: FinTech

Full brief, from `live.sotonship.space/tracks/fintech` and `briefs/fintech-brief.pdf` (5 pages). Fetched 16 October 2026.

**In collaboration with JPMorganChase, Deutsche Bank and TrueMoney.**

## The challenge

Build an AI-powered product that solves a real problem for someone who saves, spends, sends or manages money, and that could realistically be put in front of that person after the weekend.

Money now moves in seconds and across borders, and so do the people trying to steal it. Banks, fintechs and wallet providers spend heavily on fraud, compliance and payments operations, while small businesses, migrant workers and vulnerable customers are still poorly served by the financial system. There is no fixed list of projects: you choose the problem, as long as you can show it matters in finance.

Judges look past technical ambition and ask whether the product has a clear user, a working core and a plausible way to be paid for. A simple tool that one fraud team or one group of customers would start using next month beats an impressive prototype nobody would adopt.

The one-sentence test:

> We help **[a specific person]** to **[do or decide something]** in **[part of finance]** using **[AI and the data behind it]**.

Their example: *We help remittance users stop scam payments before they leave by spotting the warning signs in the messages that prompted them.*

## Who you build for and what fits the track

Choose **one main user** and design, test and pitch from their point of view. Options:

- a customer (a migrant worker sending money home, a student, an older person, someone recovering from a scam)
- a bank or fintech employee (fraud, payments operations, compliance and KYC, trade finance, customer services)
- a small business or sole trader
- a wallet agent or kiosk operator

Working well for one kind of customer, one team or one kind of payment is enough.

Any real problem in money fits: scams and fraud, money laundering, cross-border payments and remittance, payment data, trade and business verification, small-business cash flow, regulation and compliance, and digital money.

**Does not fit:**

- a general finance chatbot, or a trading bot or price prediction that does not lead to a decision
- an existing product with an AI feature added on top
- anything that needs real customer data, live bank credentials or moving real money, unless an organiser has agreed it in advance

## What every project must show

1. **A real financial problem.** Who has it, how often, what they do today, backed by evidence such as published data, a regulation or a conversation with someone affected. Putting "finance" on a generic app does not count.
2. **AI that the product depends on.** If removing the AI leaves the product doing its main job, AI is not at its core. Where the AI classifies, predicts or extracts, compare it against a simple baseline.
3. **A product that works on real data.** The main task completes start to finish, live, on public or openly licensed data with source and date visible. Real customer data is off limits; synthetic data is fine for testing and for anything personal, if labelled as synthetic.
4. **A business case.** Who would pay or fund it (a bank, fintech, wallet provider, businesses, customers), roughly what it costs per user including AI costs, and what it would take to serve a second bank or a second market.
5. **Honesty about limits.** What it does not know, how old its data is, and what happens when data is missing, a source is out of date or an input is outside what it was built for. Show at least one failure case in the demo.

## Directions the organisers want to see

Starting points only; original ideas are judged on exactly the same terms.

1. **A scam check for people sending money home.** Migrant workers sending money abroad are prime targets for scams, including deepfake calls from a "relative in distress", and UK reimbursement rules do not cover international payments. A tool that reads the message or call behind a transfer, spots the warning signs and warns the sender before the money leaves would protect people the system underserves. A wallet or remittance provider is the customer, because every prevented scam saves a refund, a complaint and a lost user. Compare it with a simple baseline such as a keyword list. Published scam scripts and public scam reports are a good starting point.
2. **A shell-company check for business onboarding.** Fraudsters open business accounts through shell companies with fake directors and mass-registration addresses. A tool that takes a new business customer's details, pulls their Companies House record and director network, and explains which risk signals it found would save onboarding teams hours per case. Banks and fintechs that open business accounts are the customer, and because every UK lender runs the same checks there is an obvious path to many buyers. Companies House's free API and bulk data are enough to build and test it.
3. **A payment address fixer.** Swift is moving cross-border payments to structured addresses split into fields such as street, town and country, and will stop accepting free-text addresses once the timing is agreed with the industry. Many banks still hold their customers' addresses as messy free text and every one of them will have to fix it. A tool that cleans and structures these addresses, flags the ones it is unsure about and explains why would save payments teams from rejected payments and manual repairs. Transaction banks are the customer, and the same rule applies to every bank on Swift worldwide. Compare accuracy with simple pattern-matching rules, using open address data such as OpenStreetMap.
4. **A trade document checker.** Before a bank pays out under a letter of credit, staff check by hand that the invoice, bill of lading and other documents match each other and the credit's terms. A tool that reads the documents, extracts the key fields and lists every discrepancy would speed up trade finance teams and catch forged or reused documents. Banks with trade finance businesses are the customer, and could license it per document checked. Public sample trade documents and generated sets with planted errors are enough to build and test it.

## Track rules on top of the event rules

- Build the entry during the event and create the repository after hacking opens. Open-source libraries, templates and pre-trained models are fine; your own earlier projects are not.
- State in the README which parts were AI-generated, what existed before the event, and who helped.
- Show where each number comes from and when it was collected.
- **No real customer data, no connecting to a real bank account, card or wallet, and never move real money.** Build tools that detect scams and fraud, not tools that create deepfakes, scam scripts or fake documents.
- If the product deals with investment, credit or borrowing, link to official guidance such as the FCA or MoneyHelper rather than giving your own advice.

## Key times stated in the brief

| When | What |
|---|---|
| Friday 16 October, afternoon and evening | Doors open, talks, track introductions and a visit and Q&A with the Lord Mayor; **hacking opens at 20:00** |
| Saturday 17 October | Hacking all day and through the night; Eagle Labs stays open Friday and Saturday nights |
| Sunday 18 October, 13:00 | Hacking stops and **submissions lock** |
| Sunday afternoon | VC for a Day pitches, the final panel and awards |

## Data sources the brief lists

See `data-sources.md` for the full table with access limits, including Companies House, the OFSI sanctions list, World Bank remittance prices, central bank FX rates, the FCA register, PaySim, IBM AMLworld, Elliptic, blockchain explorers and OpenStreetMap.

## The three questions the pitch must answer for this track

1. What evidence shows the problem is real and costly?
2. Who would deploy and pay for the product?
3. What would it take to roll it out to a second bank or market?
