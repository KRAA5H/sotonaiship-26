# Track: Responsible AI

Full brief, from `live.sotonship.space/tracks/responsible-ai` and `briefs/responsible-ai-brief.pdf` (6 pages). Fetched 16 October 2026.

Not one of the two tracks being considered, kept here because the material and the papers transfer to any track's evaluation section.

**Stale note:** `www.sotonship.space/pillars/tracks` (last updated before the event) describes this track as "an AI Cyber Arena with Holistic AI — build a defence for a simulated AI agent and one attack against it, upload a Docker image up to 1 GB, a hidden benchmark scores every defence". The **live brief is a product-and-business brief** and supersedes it.

## The challenge

Build a product that makes AI useful and trustworthy for a specific person, and pitch it as a business. It can be a tool that helps others develop, test or govern AI, or an AI-powered product in any sector where responsible design is central to the value it delivers. There is no fixed problem, sector or technology.

RAi UK brings together technical and wider social perspectives on responsible AI, with research spanning health, law enforcement and financial services. The challenge is to turn a specific need into a working product, with evidence of benefit, a clear buyer and a credible way to grow.

A focused product that one customer could trial after the weekend is stronger than a broad promise to make all AI safe. Responsibility should change what the product does, how it is tested, or what its users can control.

The one-sentence test:

> We help **[a specific person]** to **[do or decide something]** using **[AI or an AI assurance tool]**, while reducing **[a specific risk to people]**.

Their example: *We help customer-support teams test whether their AI answers are supported by approved sources before a chatbot update reaches customers.*

## Who you build for and what fits the track

Choose **one main user and one potential buyer**; they may be different people. The user might be a developer, a service worker, a teacher, an AI procurement team, a small business, or someone affected by an AI decision. Design around one workflow and identify who benefits, who could be harmed, and who can put mistakes right.

Any sector fits. Possible themes: fairness, privacy, security, reliability, transparency, accessibility, human oversight, participation and environmental impact. You do not have to address every theme: choose the risks that matter for the user and make the improvement testable.

**Does not fit:**

- a generic chatbot, ethics checklist or dashboard with no specific user, decision or action
- claims that a system is fair, safe or compliant without a defined scope and supporting evidence
- an earlier project resubmitted as new work, or a demo depending on restricted systems or real sensitive personal data

## What every project must show

1. **A real problem and people affected.** Who has it, how often, what they do today, supported by research, published evidence or a conversation with someone affected. A concrete benefit or harm, not a general concern about AI.
2. **AI at the core.** Show the AI capability the product uses or improves. An assurance tool qualifies by testing or governing a running AI system; it does not need an LLM added to its checker. Compare the important step against a simple baseline, such as rules, manual review, or the same model without the safeguard.
3. **A product that works.** A user completes the main task from start to finish, on public or openly licensed material with reproducible test cases, sources and dates visible. Label synthetic inputs. Keep test cases separate from examples used to tune the system, and report sample sizes as well as results.
4. **A business case**, not only a research idea: user, paying customer or funder, problem cost, proposed price or funding model, route to a first pilot, estimated AI/hosting/human-review cost per use, why a buyer would choose this over existing tools, and what changes for a second customer.
5. **Evidence of responsibility and honest limits.** One measurable improvement and its trade-off (for example fewer unsupported answers at the cost of more handoffs), one demonstrated failure and what happens next, who can review or override the output, and what evidence is still needed before real deployment.

## Directions the organisers want to see

Optional, research-informed starting points. The papers support the methods or concerns; the products and business models are proposals to validate.

1. **A release check for customer-support AI.** RAGAs proposes ways to evaluate retrieval-augmented answers, including faithfulness to retrieved material. Build a tool that runs test questions against a support chatbot, highlights unsupported claims and creates a review queue. A software company or support agency could pay per bot or test run. Compare against the same bot without the check; measure missed errors and false alarms against human-labelled answers. Automated evaluation is evidence for a reviewer, not proof that every answer is true.
2. **A fairness check before an AI update.** Gender Shades found substantial differences in error rates across gender and skin-type groups in three commercial gender classifiers, which motivates checking performance across relevant groups rather than relying on one average. Build a release-review tool for one classifier, such as routing customer requests. Compare versions and show subgroup error rates, sample sizes and trade-offs. Do not infer sensitive traits from names or faces. Synthetic results demonstrate the workflow, not fairness in a real population.
3. **An evidence assistant for buying AI.** Model Cards and Datasheets for Datasets propose structured documentation of intended uses, evaluations and data provenance. Build an assistant that compares a buyer's needs with supplier documentation, quotes supporting passages and flags missing evidence for a person to review. Test on public model cards plus clearly labelled fictional supplier packs with planted omissions. Compare against a manual checklist; measure missed gaps, invented claims and review time. Sell faster evidence review, not automatic certification or legal approval.
4. **A service tool that knows when to hand over.** SelectiveNet studies prediction with a reject option and the trade-off between error and coverage. Apply it to a narrow service workflow: AI routes maintenance requests when evidence is sufficient and sends uncertain cases to a worker. Report errors, the fraction handled automatically and the human queue, compared with routing everything automatically. Show what happens when the reviewer is unavailable.

## Track rules on top of the event rules

- Credit research, code, models and data, with dates and licences. Disclose AI-generated work, prior components and outside help in the README.
- Label cached and synthetic data. Show uncertainty and avoid safety, fairness or compliance claims beyond what the tests support.
- Do not use private customer records or sensitive personal data in the demo, and do not send confidential information to external AI services. Test only systems you own or are authorised to test.
- Use a sandbox, with no real consequential decisions about people. For health, safety, legal or financial uses, show qualified human review and link to official guidance.

## Research and references

Sources checked by the organisers on 15 October 2026. Research examples inform the challenge and do not imply endorsement of a team or product.

1. RAi UK, research overview.
2. Es, S., James, J., Espinosa Anke, L. & Schockaert, S. (2024). *RAGAs: Automated Evaluation of Retrieval Augmented Generation*. EACL System Demonstrations, 150–158.
3. Buolamwini, J. & Gebru, T. (2018). *Gender Shades: Intersectional Accuracy Disparities in Commercial Gender Classification*. PMLR 81, 77–91.
4. Mitchell, M. et al. (2019). *Model Cards for Model Reporting*. FAT*. arXiv:1810.03993.
5. Gebru, T. et al. (2021). *Datasheets for Datasets*. Communications of the ACM. arXiv:1803.09010.
6. Geifman, Y. & El-Yaniv, R. (2019). *SelectiveNet: A Deep Neural Network with an Integrated Reject Option*. PMLR 97, 2151–2159.

## The three questions the pitch must answer for this track

1. What problem and AI-related risk has been evidenced?
2. Who would adopt and pay for the product, and why?
3. What would it take to serve a second customer responsibly?
