# Product direction

Help a facilities management bid team decide which tenders deserve preparation effort by connecting source evidence, company knowledge, specialist input and accountable decisions. The challenge requirements are in [BRIEF.md](BRIEF.md).

The current prototype covers qualification and internal coordination. Engineering checks and a reviewed PUB case demonstrate controlled behaviour; independent usefulness, customer acceptance and time savings remain unproven. See [VALIDATION.md](../engineering/VALIDATION.md).

## What is implemented

The Next.js workspace has Tenders, Inbox, Oversight, Company, Members and Settings. Tender detail brings together screening, assigned questions, preparation decisions and source readers.

The tender detail presents a Qualification brief with the current recommendation, material blockers, known facts, next actor and requirements grouped by obligation type. Review requests are grouped by suggested function; exact source gaps and processing usage remain available in expandable details. New screenings can include buyer, reference, scope, contract period and sites as cited verbatim extracts, labelled `Extracted · verify against sources`. Missing fields and older briefs show unknowns. Citation validation checks source support, not whether a passage answers the intended field correctly; independent semantic review remains required.

Qualification includes a configurable public-notice collector, labelled controlled imports, Human and Agent Inbox tabs, bounded source-backed screening, shared review cases, scoped input requests and preparation decisions. Model spending and business approval require explicit authority.

| Surface | Purpose |
| --- | --- |
| Inbox / Human | Personal requests, updates and preparation approvals |
| Inbox / Agent | Review opportunity suggestions, check the source and matching reasons, ask for input, start an assessment or dismiss |
| Tenders | Shared case, owner, deadline, sources, current review and history |
| Oversight | Team-wide overdue and upcoming work, with the next action, assignee and deadlines. Each row opens the relevant section in Tenders. |
| Company | Accepted, dated company evidence and its source/version history |

The [product workflow](PRODUCT.md#preparation-journey) defines detailed behaviour. [DESIGN.md](DESIGN.md) records the desktop design rules.

## Users and authority

The MVP has three workspace access levels, each member holding exactly one:

- **Admin:** all Member actions, plus membership administration and acceptance of shared company evidence.
- **Member:** create and work on tenders, answer assigned requests and record assigned preparation decisions.
- **Viewer:** read workspace records without changing business records or recording decisions.

Bid owner, service reviewer and preparation decision-maker are responsibilities assigned per tender or request, not permanent workspace roles. Any Member or Admin can be assigned. Only the named assignee may answer a request or decide its preparation approval; ownership still controls screening and request confirmation. All decisions retain actor and version attribution.

This is an MVP trust model. Confirm actual customer delegation before a pilot. Preparation decisions grant neither provider spending authority nor final offer release. Temporary development accounts are documented locally in MEMBERS.md.

## Preparation journey

1. Start from a sourced suggestion or manual intake. A notice link does not establish attachment access.
2. Preserve the supplied pack, inventory extraction coverage and retrieve bounded evidence for material gates.
3. Prepare cited findings that distinguish eligibility, scoring, submission artifacts and later delivery duties.
4. Confirm named requests for missing information. Responses in Inbox and the shared review update the same attributed task.
5. Consolidate feasibility, risks, uncertainty and outstanding work in the tender review.
6. A delegated approver records a preparation decision against the exact reviewed versions. This is separate from provider spending, a commercial commitment and final offer release.
7. Changed documents, company evidence or answers make affected work and approvals non-current.

Missing company evidence means **unconfirmed**. A supported failure must be explicit. Conditional award or delivery obligations retain their timing; they are not proof that the bidder must already have fulfilled them.

New screenings add a bounded overview evidence set alongside the six critical excerpts. Missing facts and conflicting terms become source-linked draft questions with a suggested function. The bid owner confirms a named reviewer and deadline; the brief shows that assignment. Ordinary unfinished submission outputs and future duties can remain unconfirmed during Qualification only under the conservative preparation-role rules, with exact timing support and an explicit human approval condition. Eligibility, scored thresholds, present material risk, unknown timing and evidenced failures cannot use that exception. Older unclassified findings remain conservative. Model labels and exact quotes still require domain review; they do not establish semantic accuracy.

The current PUB case needs reassessment: bidding-entity evidence, the closing date/amendments and material source gaps remain unresolved. The first rerun's uncited site extract was rejected; its fallback retained twelve earlier findings with a null summary. The repaired producer subsequently returned a source-supported overview, including site-transition qualifiers, but the full response hit its output cap. Offline repairs now support references to unchanged validated findings and reserve bounded input-count headroom. The one-token usage discrepancy was settled through an audited operation, preserving the original limits and receipt. No new qualification artifact was created; earlier artifacts remain in history and are non-current under the latest-job fence. Spending is paused. Live outcomes and offline engineering evidence are recorded separately in [validation](../engineering/VALIDATION.md); live output quality and representative acceptance remain open.

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

Increment 3 implements a controlled Preparation tab for a technical response and pricing workbook. The bid owner sets the internal deadline, assigns a deliverable owner and a separate reviewer, and can link requirements from the approved screening. The deliverable owner uploads working versions and requests a scoped review. Inbox and Oversight show the same work. Acceptance covers the reviewed file and plan only. Amendments require fresh preparation approval and reconfirmation; earlier plans, files and reviews remain available.

Preparation writes require current preparation approval for the tender.

The controlled Submission tab seals the accepted technical and commercial file versions, their hashes and review records. The bid owner names a separate release approver. After that approver clears the release checks and approves the package, the bid owner can record the portal reference, submission time and PDF receipt. Changes to qualification evidence, accepted files or plans can make a package non-current. Earlier packages, decisions and receipts remain available.

The controlled costing feature lives under the Pricing workbook deliverable. It compares supplier quotes against one service package and flags missing, excluded, partial and non-comparable lines. It calculates a selected scenario in SGD before tax using comparable rates and any explicitly selected estimates with approval references. A complete working workbook for the current tender can be saved as a new pricing version for the existing review and release workflow. The fictional HVAC example is available for practice. Pilot use requires representative quotes and approved company workbook rules.

Proposal drafting lives under the Technical response deliverable. The bid owner confirms the bidding legal entity, links tender requirements and can assign input requests for evidence gaps. The assigned owner matches each requirement to approved wording from the current Company evidence. The app assembles the chosen wording and evidence references into a DOCX. A generated draft with gaps or an outdated plan stays out of review, and the named reviewer must confirm requirement coverage before acceptance.

1. **Validate qualification:** resolve material evidence gaps, establish representative acceptance criteria and compare equivalent manual and assisted work.
2. **Add one commercial slice:** only after that gate, connect a narrow supplier scope and supported costing workbook.
3. **Add proposal/release review:** use current accepted facts and commitments, with amendments invalidating affected approvals.
4. **Pilot:** confirm customer roles, access, operating boundaries and measured benefit before deployment.

The challenge's 30–50% effort reduction and at least 70% selected-output accuracy are targets, not achieved results. Review and correction count toward effort. Critical dates, mandatory gates, claim support and arithmetic need separate checks.

Custom development is justified only if this workflow shows a repeatable advantage over suitable products or a configured general agent. Configuration, integration and partnership remain valid outcomes; willingness to use and pay is still unknown. Earlier competitor/reuse research is retained in the [research archive](../research/RESEARCH.md); it is not evidence of current product superiority.
