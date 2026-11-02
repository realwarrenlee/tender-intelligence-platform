# Product direction

Help a facilities management bid team decide which tenders deserve preparation effort by connecting source evidence, company knowledge, specialist input and accountable decisions. The challenge requirements are in [BRIEF.md](BRIEF.md).

The current prototype covers qualification and internal coordination. Engineering checks and a reviewed PUB case demonstrate controlled behaviour; independent usefulness, customer acceptance and time savings remain unproven. See [VALIDATION.md](VALIDATION.md).

## What is implemented

The Next.js workspace has Tenders, Inbox, Reviews, Company, Members and Settings. Existing assessments, assigned questions, pursuit decisions, source readers, history and the contextual assistant remain supported.

The newer workflow is implemented behind `QUALIFICATION_WORKFLOW_ENABLED`, which defaults to `false`. When enabled, it adds a public-notice collector and labelled controlled imports, Human and Agent Inbox tabs, bounded source-backed screening, shared review cases, scoped input requests and preparation decisions. Enabling it grants neither model-spending authority nor business approval.

| Surface | Purpose |
| --- | --- |
| Inbox / Human | Personal requests, updates and preparation approvals |
| Inbox / Agent | Opportunity suggestions with source, matching reasons and uncertainties; start, defer or dismiss |
| Tenders | Shared case, owner, deadline, sources, current review and history |
| Reviews | Team progress, outstanding inputs, next actor and decision readiness; opens the same tender review |
| Company | Accepted, dated company evidence and its source/version history |

The [product workflow](PRODUCT.md#preparation-journey) defines detailed behaviour. [DESIGN.md](DESIGN.md) records the desktop design rules.

## Users and authority

These are product roles, not a confirmed CBM organisation chart. A member may hold several roles.

- **Bid owner:** register an opportunity, start an authorised assessment, confirm named input requests and assemble a preparation recommendation.
- **Service reviewer or estimator:** answer assigned questions about capability, availability and delivery assumptions, recording the basis.
- **Approver:** approve specified preparation scope and budget, request information or decline.
- **Administrator:** manage memberships and accept shared company evidence. Administration alone grants no commercial approval.
- **Viewer:** read permitted workspace records.

Team visibility does not grant authority to answer someone else's request or approve a decision. The app asks people for scoped business facts; routine users are not required to label evaluation datasets.

## Preparation journey

1. Start from a sourced suggestion or manual intake. A notice link does not establish attachment access.
2. Preserve the supplied pack, inventory extraction coverage and retrieve bounded evidence for material gates.
3. Prepare cited findings that distinguish eligibility, scoring, submission artifacts and later delivery duties.
4. Confirm named requests for missing information. Responses in Inbox and the shared review update the same attributed task.
5. Consolidate feasibility, risks, uncertainty and outstanding work in the tender review.
6. A delegated approver records a preparation decision against the exact reviewed versions. This is separate from provider spending, a commercial commitment and final offer release.
7. Changed documents, company evidence or answers make affected work and approvals non-current.

Missing company evidence means **unconfirmed**. A supported failure must be explicit. Conditional award or delivery obligations retain their timing; they are not proof that the bidder must already have fulfilled them.

The current PUB development brief remains `needs_information`: bidding-entity evidence, the current closing date/amendments and material source gaps are unresolved. All 12 findings remain unconfirmed. The single authorised trial is closed; its cost and limits are recorded in [validation](VALIDATION.md).

## Wider product scope

| Capability | Direction after qualification validation |
| --- | --- |
| Discovery | Add verified source routes and authorised private access; no claim of four working portal connectors |
| Quotations and costing | One agreed service scope, supplier quote set and supported workbook; compare missing scope and price basis before proposing mappings |
| Proposal preparation | A requirement-to-response matrix and a small set of grounded draft sections using approved evidence |
| Coordination | Extend the existing task/version model into authorised notifications and delegation |
| Learning | Record outcomes, attributed feedback and approved contextual lessons; show their use on later work |

For costing, people must supply or approve workloads, staffing/relief, rates, overheads, risk and margin. AI may propose interpretation or mappings; deterministic tools must calculate supported scenarios. An absent quote stays missing. Historical estimates, if later supported, need source dates, comparability assumptions and approval status.

Outbound messages remain drafts until a user approves the message version, recipients and configured delivery route. Automatic bid submission, general spreadsheet verification, predictive win probabilities, marketing analytics, vendor scoring, mobilisation management and a public agent interface are outside the current prototype. Draft export does not establish release readiness.

## Delivery gates

1. **Validate qualification:** resolve material evidence gaps, establish representative acceptance criteria and compare equivalent manual and assisted work.
2. **Add one commercial slice:** only after that gate, connect a narrow supplier scope and supported costing workbook.
3. **Add proposal/release review:** use current accepted facts and commitments, with amendments invalidating affected approvals.
4. **Pilot:** confirm customer roles, access, operating boundaries and measured benefit before deployment.

The challenge's 30–50% effort reduction and at least 70% selected-output accuracy are targets, not achieved results. Review and correction count toward effort. Critical dates, mandatory gates, claim support and arithmetic need separate checks.

Custom development is justified only if this workflow shows a repeatable advantage over suitable products or a configured general agent. Configuration, integration and partnership remain valid outcomes; willingness to use and pay is still unknown. Earlier competitor/reuse research is retained in the [research archive](RESEARCH.md); it is not evidence of current product superiority.
