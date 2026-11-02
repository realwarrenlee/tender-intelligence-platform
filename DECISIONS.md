# Decisions and open questions

## Current direction

- Build an approachable business workspace for tender qualification and coordination, with human review at consequential decisions. The wider product hypothesis covers discovery, qualification, quotations and costing, proposal preparation and coordination; later capabilities remain subject to evidence and scope decisions. See [PRODUCT.md](PRODUCT.md) and [BRIEF.md](BRIEF.md).
- Keep a shared tender record and current evidence, tasks and decision history. The newer workflow separates source-backed screening and authorisation of bid preparation from a later final offer or release decision.
- In the enabled bounded workflow, Inbox separates personal Human actions from Agent opportunity suggestions; Reviews shows the team's cases without granting extra authority. A named authorised person answers a scoped request, and a delegated approver makes the preparation decision.
- Use the existing Next.js frontend with its retained Circle shell, FastAPI/Pydantic API and worker, and Supabase PostgreSQL, Auth and private Storage. The original Circle demo features were pruned; retain [source and licence notices](apps/web/licenses/README.md). Desktop is the current validation scope.
- Use OpenAI as the initial model provider. Models, prices and spending authority are explicit server-side inputs; no feature flag, preparation approval or suggestion grants paid-call authority. Unknown provider outcomes must not be silently retried.
- `QUALIFICATION_WORKFLOW_ENABLED` defaults to `false`. The configured API and worker value determines the active entry path. Enabled screening uses bounded source retrieval and shared budgets; legacy assessments and history remain readable. A case that has entered screening cannot return to broad analysis on rollback. No configured value or rollout is implied by the default.
- Keep external source claims limited to the verified public notice route or labelled controlled imports. A notice does not imply attachment access. Further integrations and external communications require authorised access and a defined human handoff.
- Keep exact source provenance and coverage gaps visible. Missing, partial, stale or conflicting evidence remains unresolved; citation presence does not establish semantic correctness. Approvals and source-dependent work become non-current when their supporting inputs or authority change.
- The supplied challenge brief remains the source for challenge requirements. Do not read the challenge terms under the existing user instruction, and do not contact people without authorisation. No private CBM dataset has been supplied for this work.

## Evidence and current gate

The later qualification plan's Tasks 1-5 are implemented; Task 6's authorised PUB trial and source review are complete. The earlier T0-T6 work refers to the legacy review-desk implementation, not the later trial. The recovered draft has 12 unconfirmed findings; usage-derived trial cost was US$0.0803868, and its spending authority is closed and paused. Offline reliability fixes do not prove model accuracy. Independent quality, representative acceptance and human-effort comparison remain open. See [VALIDATION.md](VALIDATION.md) and the reliability result (local only).

## Open decisions

| Question | What it determines |
|---|---|
| Which tasks cause the most delay or rework, and does a configured agent or existing product solve them adequately? | Whether to build, configure, integrate or narrow the product. |
| Which service lines, real examples and outcome rubric should be included in representative UAT? | Supported scope and whether accuracy and effort targets are met. |
| Who owns current Company and bidding-entity evidence, and who can review and approve preparation? | Reliable qualification and actual customer delegation. |
| Which public and private sources, amendments and attachments are authorised and accessible? | Discovery coverage and required human access handoffs. |
| What are the customer's hosting, model-processing, retention, identity and access requirements? | Pilot deployment and provider suitability. |
| What workbook behavior, supplier quote bases and approval rules must commercial work preserve? | The scope and feasibility of later costing integration. |
| Who authorises recipients and content, and what starts or stops follow-ups? | Any future email or reminder automation. |
| Are complete, comparable pursuit and outcome records available? | Whether later learning or predictive evaluation is justified. |

Representative independent quality checks, business evidence, actual delegation and a measured manual-versus-assisted comparison are prerequisites to a pilot. The 30-50% effort-reduction and at least 70% selected-output accuracy figures are targets, not achieved results. More detail and evidence are in [VALIDATION.md](VALIDATION.md).
