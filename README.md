# Tender Intelligence Platform

A development prototype for facilities management bid teams, built for the CBM tender intelligence challenge. It connects tender documents, bid decisions, technical and pricing work, and submission records in one shared workspace.

## How the workflow works

| Stage | What the team can do today |
| --- | --- |
| **Find and import** | Create a tender manually or review GeBIZ matches in **Inbox → Agent**. The team downloads the tender pack from the portal and uploads them to the tender record. |
| **Qualify** | Review a source-linked brief with key facts, requirements and blockers. Assign questions when information is missing, then record a human decision on whether to start preparing the bid. |
| **Prepare** | Assign an owner, a separate reviewer and an internal deadline to the technical response and pricing workbook. Track working versions and review the specific file submitted for acceptance. |
| **Compare quotes and cost the work** | Compare supplier quotes for one service package using the supported workbook layout. Check missing items, exclusions, quantities and units. Calculate a scenario from comparable rates and any explicitly selected, documented estimates, then save a complete working workbook for review. |
| **Draft the technical response** | Map selected requirements to approved company wording for the confirmed bidding entity. Generate a Word draft, request evidence for gaps and have the reviewer confirm requirement coverage before accepting it. |
| **Release and record submission** | Seal the accepted file versions and have a separate approver clear the release. The bid owner submits on the portal, then records the reference, submission time and PDF receipt in the workspace. |

New addenda or changes to approved inputs can make affected reviews and approvals out of date. Earlier versions and decisions stay in the tender history.

### From a GeBIZ match to a tender case

1. **Find matches.** Once configured, the worker checks up to 10 pages of public GeBIZ listings every day at **8:00 a.m. Singapore time**. It checks tender titles and categories for facilities management matches and adds them to the designated intake owner's **Inbox → Agent**. The intake owner or a workspace admin can switch the daily scan on or off there. [Discovery setup](SETUP.md#environment)
2. **Decide what to do.** Open a suggestion to see the public notice and why it matched. Choose **Ask for input** to send the notice and a question to a teammate. They can reply in **Inbox → Human → Tender feedback**, where you can see their answer. Choose **Dismiss** to remove the suggestion from the active queue.
3. **Start an assessment.** Choose **Start assessment** to create and open a case under **Tenders**. Upload the tender pack and any addenda to add detail beyond the public notice. AI screening runs separately from case creation and requires an approved screening budget.

### Track team work in Oversight

With the qualification workflow enabled, use **Inbox → Human** for your own assignments and **Oversight** for the team's next actions across active tenders. **Overdue** opens first. Switch to **Upcoming** to see the remaining work.

Each row shows the next qualification or preparation action, who needs to act, the internal deadline, and when the tender closes, where those details are available. Oversight uses the earlier of the internal deadline and tender closing time to sort the work. Select a row to open the relevant section or task in **Tenders**.

## Prototype status

The workflow has been exercised with controlled examples. Quote comparison supports one service package, and proposal drafting covers selected sections using approved wording. Preparation and Submission currently cover two deliverables. On a live bid, the team must verify the latest addenda, closing time, and every form, declaration, signature and attachment the buyer requires.

The full challenge brief also calls for broader portal coverage, RFQ follow-up, general costing workbook checks, and learning from past bids. The live PUB qualification case still needs reassessment. The brief’s targets of **30–50% less time** on selected tasks and **at least 70% accuracy** on selected AI outputs remain unverified. See the [validation record](docs/engineering/VALIDATION.md) for test evidence and pilot gates.

## Run locally

Follow [development setup](SETUP.md) to configure and start the API, worker and frontend.

To try the newer workflow, follow the [controlled setup instructions](SETUP.md#controlled-preparation-tracking). Qualification, Preparation writes and Submission writes each have a flag that defaults to off. Paid model calls require separate spending approval. In **Preparation → Pricing workbook**, use **Load fictional example** to try quote comparison with the included HVAC data.

## Repository guide

| Path | Contents |
| --- | --- |
| `apps/web/` | Next.js workspace and frontend tests |
| `apps/api/` | FastAPI service, Python worker and API tests |
| `contracts/` | Output schemas and generated API contract |
| `supabase/migrations/` | Database migration history |
| [`docs/`](docs/README.md) | Engineering, product, and research documentation |
| [`evals/`](evals/README.md) | Evaluation fixtures, answer keys and run records |

- [Challenge brief](docs/product/BRIEF.md) for CBM’s requirements and success measures
- [Product direction](docs/product/PRODUCT.md) for workflow details, roles and rollout scope
- [Architecture](docs/engineering/ARCHITECTURE.md) for system components and runtime rules
- [Company reference](docs/research/COMPANY.md) for the background used to develop company evidence
