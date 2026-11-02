# CBM tender intelligence: market coverage, gaps and possible entry points

Research date: 23 October 2026, Singapore time. This is a research assessment, not a selected solution or implementation specification.

## Findings that matter

1. **A large part of the brief is already a software category.** Discovery alerts, tender extraction, bid qualification, content retrieval, drafting, reviewer assignments and outcome tracking have multiple commercial suppliers. A generic AI tender assistant would enter a crowded market.
2. **Even the broader combination has direct competitors.** Singapore-based Catalyst Solutions advertises BidWright across discovery, subcontractor quotations, cost/margin modelling, proposals, approval gates and post-award learning. This is published positioning, not independently tested delivery evidence. [BidWright](https://www.catalystsolutions.sg/bidwright)
3. **Facilities management is already being targeted.** AutogenAI has an APAC real-estate/FM offering, while service-estimating products already model cleaning work, labour, supplies and margins. Sector specificity alone would be a weak differentiation claim. [AutogenAI](https://autogenai.com/apac/sectors/real-estate/), [CleanBid](https://www.cleanguru.com/cleanbid/features), [Aspire](https://www.youraspire.com/features/estimating)
4. **CBM plays two commercial roles.** It responds to its customer's tender and obtains quotations from its own suppliers. The connection between those activities, the costing workbook and the final commitments is more promising to investigate than another proposal writer.
5. **The strongest possible gap is currently a hypothesis about fit and integration.** Public documentation does not establish which product can process CBM's actual tender packs, quotations, workbooks and amendments with acceptable review effort. It also does not establish that existing products fail.
6. **Lack of private data limits validation, rather than all research.** Public Singapore award data contains genuine CBM records, and official cleaning/security procurement documents provide realistic examples. These cannot establish CBM's current capacity, cost rates, margins, lost bids or decision criteria.
7. **No final product concept is selected.** There are credible paths through implementation services, adapting generic agents, a focused commercial checking capability, or partnering with an existing vendor. A buy/configure outcome remains viable.

## Research basis and limits

I screened 125 search results from 19 targeted queries, representing 123 unique result URLs. I examined 43 successfully retrieved web pages and 13 GitHub file/directory resources, plus repository metadata and selected rows from the official government procurement dataset. The source register records searches, inspected pages and failed fetches.

The supplied BRIEF.md and PROPOSAL.md informed the assessment. The challenge terms were left unread. No private CBM data, paid product trial, customer interview or vendor demonstration was available. No product or repository was installed or executed.

Evidence labels throughout:

- **Documented:** a vendor or project explicitly describes the feature. This establishes a claim, not its measured accuracy or fit.
- **Inspected:** selected source code or source data was read.
- **Inference:** a reasoned implication of the evidence.
- **Unknown:** the evidence needed to decide is unavailable.

Customer success percentages published by vendors were not used as comparable performance measurements. Regional landing pages were not treated as proof of working Singapore connectors.

## What the problem actually contains

The brief combines opportunity intelligence, proposal response management, supplier procurement, commercial estimating and organisational knowledge. Those activities have different information needs.

| Activity | Principal information needed | Consequence for research |
|---|---|---|
| Find work | Listings, categories, source access, dates and amendments | Existing alerts/aggregators should be evaluated before developing collection |
| Qualify | Mandatory requirements, capabilities, certificates, capacity and commercial rules | Historical memory helps; current facts and explicit rules remain necessary |
| Obtain inputs | Supplier scope, exclusions, quantities, units, rates and response status | CBM becomes a buyer while remaining a bidder to its customer |
| Price delivery | Workload, service design, labour, equipment, subcontractors, overhead and risk | Correct arithmetic alone does not establish a viable price |
| Prepare and approve | Evidence, methods, commitments, attachments, owners and versions | Review must apply to an identifiable version of the submission and price |
| Learn | Pursuit decisions, outcomes, feedback and delivery experience | Stored records become useful when later decisions retrieve and apply them |

For FM, service design matters as much as document generation. NEA's cleaning tender guide discusses outcome-based contracts and evaluation of price alongside quality. The Singapore Police Force's security contracting template includes service outcomes, performance management and practical requirements such as compulsory site briefings. These are examples of domain complexity, not a universal rule for every CBM tender. [NEA guide](https://www.nea.gov.sg/docs/default-source/itm/obc-guides/guide-on-tender-evaluation-for-outcome-based-cleaning-contracts-2021.pdf), [security template](https://www.police.gov.sg/-/media/SPF/Knowledge-Hub/Security-Contracting/Outcome-based-Contract-Template_Final.pdf)

CBM already publicly presents digiHUB as a smart property management system. That is evidence of an operational technology offering; it does not tell us what CBM uses for business development, estimating or approvals. The challenge should not be read as evidence that CBM has no digital systems. [CBM digiHUB](https://www.cbm.com.sg/digihub)

## Existing market coverage

### Singapore discovery and procurement access

| Option | Documented capability | Relevance and remaining question |
|---|---|---|
| GeBIZ | Government opportunity search, document access/submission and RSS alerts for registered trading partners | Basic monitoring has an existing official route. The alerts page says the former GoBusiness email alert service ended in February 2025; an integration plan should use current access methods. [Alerts](https://www.gebiz.gov.sg/business-alerts.html), [portal overview](https://www.gebiz.gov.sg/about-us.html) |
| TenderBoard | Aggregation of over 40 open tender sites, including GeBIZ and Ariba, with notifications and historical information | Strong evidence that multi-source discovery is already sold locally. Exact coverage of private/invitation-only events, source freshness and export/integration access need checking. [Supplier product](https://www.tenderboard.biz/vendor/) |
| SESAMi | Public business opportunities plus sourcing, quotation analysis and buyer/supplier procurement workflows | It is both a source and an existing procurement product. Registration and access depend on the relevant buyer/portal; public listings do not imply unrestricted access to every document. [Live listing](https://sesami.online/BO/businessOpportunities.aspx), [supplier access FAQ](https://sesami.com/login/), [product](https://sesami.com/e-procurement/) |

SAP publishes supplier APIs, but its supplier API FAQ directs users to the authenticated developer portal for the current catalogue. The FAQ's enumerated list is dated January 2024. It cannot establish what sourcing-event access CBM has today. Buyer-side sourcing APIs should not be assumed to be supplier entitlements. [SAP supplier API guidance](https://support.ariba.com/item/view/KB0402633?HelpCenter=1)

**Assessment:** scheduling is a small part of discovery. Source coverage, credentials, full-document access, changes and a record of successful collection are the practical implementation work. None of this establishes a novel market gap.

### Proposal and full lifecycle platforms

| Product | Documented overlap | What remains unverified for CBM |
|---|---|---|
| Responsive | AI drafting, approved content, collaborative response projects, governance and source validation | Singapore source collection, subcontractor commercial workflows and CBM workbook compatibility. [Platform](https://www.responsive.io/platform-overview) |
| Loopio | Retrieval from its content library and connected repositories, response drafting and team workflows | FM costing, supplier quotation normalisation and source access. Its pricing page also lists multi-step reviews and business-unit options by tier. [Platform](https://loopio.com/platform/), [plans](https://loopio.com/pricing/) |
| AutogenAI | Qualification-to-submission positioning, evidence sourcing, drafting, compliance and an APAC FM offering | Actual integration with CBM's pricing and supplier processes. A published Serco partnership is adoption evidence in large outsourced services; the associated savings remain reported pilot results. [Product](https://autogenai.com/), [FM](https://autogenai.com/apac/sectors/real-estate/), [Serco partnership](https://autogenai.com/uk/blog/serco-agrees-partnership-with-innovative-uk-tech-start-up-autogenai-after-pilot-shows-up-to-85-time-saving-in-knowledge-management-using-ai/) |
| Inventive AI | Cited answers, synchronised company knowledge, go/no-go agents, compliance checks and stale/conflicting content detection | FM commercial calculations, live Singapore source access and acceptable extraction accuracy. [Product](https://www.inventive.ai/) |
| Altura | Structured requirement/risk/deadline tables, company knowledge retrieval, drafting, qualification, evaluation and workflows | Regional discovery coverage, detailed quote-to-costing linkage and workbook behaviour. [Bid Companion](https://altura.io/en/bid-companion), [plans](https://altura.io/en/prijzen) |
| Bidhive | Pre-bid capture and qualification, bid management, debriefs and win/loss records | The quality of analysis possible from CBM's data and the commercial estimating interface. [Lifecycle](https://bidhive.com/features/end-to-end-0/) |
| BidWright, Catalyst Solutions | Advertises discovery, requirements, subcontractor quotes, cost/margin models, proposals, approval gates, ERP integration and post-award learning | Public page does not establish operational performance, customers, connector details or workbook fidelity. It is nevertheless a close competitor in stated scope. [Product](https://www.catalystsolutions.sg/bidwright) |
| Tendermeister | Markets GeBIZ document analysis, eligibility/compliance extraction and comparison of uploaded amendments | The inspected page describes uploading downloaded documents; this does not demonstrate live portal integration. Performance and local fit were not tested. [Singapore offering](https://tendermeister.com/sg_en/gebiz-tender-analysis-software/) |

Additional Singapore-facing vendors appeared in search, including Bidovate and IntelliBidz. They strengthen the evidence of category competition, but their marketing was not enough to establish deployment quality. This report does not rank them as proven alternatives.

Altura's founder also describes why its earlier analytics-led approach depended on people manually feeding bid data, and why the company shifted towards executing document and expert-input workflows. This is one supplier's account, but it directly challenges the idea that adding a dashboard and memory automatically creates a useful learning system. [Founder account](https://altura.io/en/blog/from-managing-to-doing-the-bid)

### Costing and supplier quotation products

| Product | Documented capability | Fit boundary |
|---|---|---|
| ConWize | Supplier invitations and response tracking, line-by-line quantity/scope comparison, missing-price detection, supplier metrics and transfer to estimates | Construction/BOQ orientation. Recurring FM contracts and CBM workbooks require validation. [Bidding](https://conwize.io/bidding/) |
| CleanBid / CleanGuru | Cleaning task workloading, time estimates, wage assumptions, consumables and price recommendations | Strong cleaning-specific overlap; Singapore assumptions and integrated security/engineering scope are not established. [Features](https://www.cleanguru.com/cleanbid/features) |
| Aspire | Service estimating kits combining production factors and labour/supply costs, markups/margins, approvals and estimate status | A reusable model still requires the customer's own rates, templates and service assumptions. Multi-service CBM suitability remains unknown. [Estimating](https://www.youraspire.com/features/estimating) |
| CATS, IDD Tech | Multi-user estimating, direct costs/overheads, supplier quote comparison, Excel linking, scenarios and FM use | Adjacent evidence against claiming that estimating plus spreadsheets is an empty market. Tender document intelligence and Singapore discovery were not established. [Product](https://www.iddtech.com.au/products/cats-estimating) |
| ERPNext | RFQ distribution, linked supplier quotations and structured comparison of rates and commercial terms | A reusable procurement component; it is not demonstrated as a turnkey response platform for CBM's customer tenders. [RFQ](https://docs.frappe.io/erpnext/request-for-quotation), [quotation comparison](https://docs.frappe.io/erpnext/supplier-quotation) |

Microsoft also already provides Spreadsheet Inquire for workbook structure/error analysis and cell-by-cell workbook comparison, including formula and VBA changes. Availability depends on the Excel edition. These features reduce the novelty of a general Excel checker. They do not determine whether a staffing assumption or supplier exclusion is commercially acceptable. [Workbook analysis](https://support.microsoft.com/en-us/excel/analyze-a-workbook-with-spreadsheet-inquire), [comparison](https://support.microsoft.com/en-us/excel/compare-workbooks-using-spreadsheet-inquire)

## How far can general agents already go?

The user's proposed decomposition is technically credible. Codex supports scheduled tasks using skills/plugins; Claude Code supports cloud scheduled tasks with connectors. These can support collection, extraction, retrieval, drafting and follow-up when tools and permissions are configured. The research did not benchmark them on CBM material. [Codex](https://learn.chatgpt.com/docs/automations), [Claude Code](https://code.claude.com/docs/en/routines)

Microsoft supplies an RFP response agent template that draws on proposal content and templates, with use cases for reuse and internal review routing. Its Copilot Studio scenario also describes requirement extraction and historical pricing analysis. The latter is a scenario, not proof of FM pricing accuracy. CBM's Microsoft environment and entitlements are unknown. [Agent template](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/agent-template-rfp-assistant), [scenario](https://adoption.microsoft.com/en-us/scenario-library/sales/respond-to-an-rfp-agent/)

A practical baseline therefore exists before a bespoke product is considered:

- Give the agent a controlled document pack and an explicit company profile.
- Give it access to a structured tender/task record and a calculation tool.
- Specify the outputs and human decisions.
- Compare its results and reviewer effort with a manual run and shortlisted specialist products.

This is an evaluation baseline, not a selected architecture. A competent operator may manage a useful workflow with an existing agent. A shared business process may require configuration for simultaneous users, current state, permissions, review versions and recovery. Those needs can also be met by existing workflow products.

### Memory and learning

Persistent instructions, retrieved company documents, current bid records and outcome history serve different purposes. Claude's documented memory consists of persistent instructions and notes supplied as context. Saving an outcome does not automatically update model weights. [Memory](https://code.claude.com/docs/en/memory)

Operational learning can happen when an approved lesson is retrieved on a later tender and changes the assessment, service design or proposal. Improvement still needs evaluation. A recorded loss does not reveal its cause by itself.

Public award data is especially limited: awards won divided by awards in a dataset describes award share. Wins divided by tenders actually pursued describes bid win rate. Estimating win probability also needs appropriate features, losses and validation. One inspected BidPilot test explicitly calculates award share despite broader win-rate terminology in the project. [Inspected test](https://github.com/GiorgosPanagopoulos/bidpilot/blob/main/tests/test_win_rates.py)

## Open-source and publicly available components

| Component | Inspected/documented contribution | Maturity or reuse consideration |
|---|---|---|
| Docling | Document parsing, OCR, layout/table handling and structured exports; MIT codebase | Useful extraction infrastructure. Model licences are separate, and parser output still needs evaluation. [Repository](https://github.com/docling-project/docling) |
| RAGFlow | Document retrieval, knowledge organisation and source citations; Apache-2.0 | Supports the knowledge portion. Retrieval does not establish cost correctness or complete compliance coverage. [Repository](https://github.com/infiniflow/ragflow) |
| LangGraph | Persistent workflows, resumption, human review and memory; MIT | General orchestration infrastructure rather than a tender product. [Repository](https://github.com/langchain-ai/langgraph) |
| ERPNext | RFQ, supplier and commercial records; GPL-3.0 repository | Existing operational workflows may save more effort than inventing them. Integration and software distribution choices need review. [Repository](https://github.com/frappe/erpnext) |
| n8n | Workflow automation available under its Sustainable Use License, with separate enterprise portions | Classify it as source-available rather than assuming an unrestricted open-source product foundation. [Licence](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) |
| Dify | Agent/application platform with a modified Apache licence | The inspected licence includes additional multi-tenant and frontend conditions. Its label should not be flattened into plain Apache-2.0. [Licence](https://github.com/langgenius/dify/blob/main/LICENSE) |

### Tender-specific repositories examined more closely

**BidPilot** is an MIT-licensed supplier-side example with TED ingestion, rule-based eligibility, cited drafting and review status. It also contains a test directory and CI configuration. The inspected extraction tests mock the LLM response: they establish test intent around handling results, not real-world extraction accuracy. Its source connectors target TED/Greek public data, so Singapore support is adaptation work. No tests were run in this research. [Repository](https://github.com/GiorgosPanagopoulos/bidpilot), [extraction test](https://github.com/GiorgosPanagopoulos/bidpilot/blob/main/tests/test_requirement_extraction.py)

**TenderAI MCP Server** describes parsing, technical proposals, vendor quote ingestion, pricing, DOCX/XLSX generation and a SQLite-backed knowledge base. Its root listing and README were inspected; no root licence file was present and GitHub metadata did not identify one. Treat it as publicly inspectable source with reuse permission unresolved. The README's production-readiness claim was not validated. [Repository](https://github.com/dbugom/tenderai-mcp-server)

**rfp-requirements-mcp** exposes extraction, qualification and compliance tools. The implementation calls BidCraft's hosted analysis/generation endpoints, including free/pro limits. It is an integration example rather than a self-contained replacement for the underlying commercial service. Its README says MIT, while the inspected root lacked a standalone licence file. [Repository](https://github.com/crawde/rfp-requirements-mcp), [implementation](https://github.com/crawde/rfp-requirements-mcp/blob/main/index.ts)

**Assessment:** reusable technology is plentiful. The inspected tender repositories do not establish a maintained, validated, turnkey Singapore/FM platform. Their existence supports feasibility and offers reference patterns; it does not remove the need to verify software quality, permissions and business fit.

## The gaps: what is established and what is hypothetical?

| Candidate gap | Evidence-based status | What would establish a real opportunity? | What would weaken it? |
|---|---|---|---|
| Cross-portal collection | Access/configuration work is real; the feature is already supplied | Important CBM sources or invitation flows are unsupported by affordable existing options | Existing alerts/aggregator exports cover the required inputs |
| Requirements linked to supplier scope and costing | Plausible compatibility gap; adjacent products and BidWright already claim overlap | A real pack shows costly manual reconciliation that shortlisted products cannot handle | A vendor demonstrates the same pack with acceptable review effort |
| Amendments propagated through quotes, price and approvals | Valuable control, but novelty unproven | Changes cannot currently be traced to affected quantities, assumptions, commitments and approval versions | Existing bid/estimating tools perform the propagation satisfactorily |
| Singapore/FM commercial assumptions | Domain adaptation need is plausible; FM software already exists | Explicit local service rules, costing structures and work practices require material adaptation | Configuration of existing service estimators is sufficient |
| Knowledge upkeep and staff adoption | Organisational problem supported by the brief; tools already offer content and review functions | Teams need an implementer to make those tools usable and maintain current content | CBM already has effective ownership and a product mainly needs procurement |
| Private deployment, residency or permissions | Unknown customer constraint | CBM states a requirement that suitable vendors cannot meet economically | Existing vendors meet the requirement or no such constraint applies |
| Historical price and win prediction | Data dependency is established; unmet software capability is unproven | CBM has sufficiently comparable, labelled historical cases and a decision the model improves | Data is absent, biased, incomparable or offers no predictive advantage |
| End-to-end learning | Records and feedback products exist; improvement is unproven | Validated lessons repeatedly change decisions and reduce measurable rework | A memory store grows without improving the work |

The most defensible current statement is: **fit between existing software and CBM's exact commercial workflow has not been established.** That is narrower than claiming that no suitable product exists.

For change management, even a conventional addendum log can record receipt, scope, price impact and notification status. The distinctive test would concern whether the full impact is carried through the working documents and decisions. [Industry practice from ConstructConnect](https://www.constructconnect.com/blog/how-to-track-addenda-without-losing-a-bid-to-a-missed-revision)

## Where we could come in, without selecting a solution

| Route | What the customer would buy | Possible advantage | Condition for pursuing it |
|---|---|---|---|
| Configure/integrate existing products | Working source access, cleaned knowledge, configured rules, templates and trained users | Delivery capability and knowledge of the customer's actual work | CBM needs implementation ownership and products cover the core capabilities |
| Adapt generic agents | Reusable procedures and tools around an existing agent, with appropriate shared records | Faster adaptation and less application development where the baseline performs well | The agent meets quality/review needs and CBM accepts its operating model |
| Build one focused commercial capability | A demonstrably better way to reconcile requirements, supplier quotes, costing and changes | Domain-specific checks, mappings and evaluation evidence | Existing tools fail an important task on representative data |
| Partner with a close vendor | A local implementation, domain configuration or extension | Existing product maturity with a narrower delivery role | Partnership terms and extension access are workable |
| Recommend purchase/configuration | A justified selection and implementation plan | An honest answer to the customer's need | An existing option already achieves the required outcomes |

An implementation business can be valuable without strong proprietary software differentiation. A product business needs a repeatable problem beyond one company's templates and a reason that agents or incumbents do not readily absorb it. Research has not established that repeatable advantage yet.

The challenge's published assessment allocates 30% to solution fit, 30% to readiness/scalability, 20% to innovation and 20% to company/team profile. It does not require a newly trained foundational model. Existing capability and credible adaptation may help; this research does not establish our team's traction or experience.

## What can be investigated without private CBM data?

**Government award data:** the MOF dataset contains tender identifiers, descriptions, agencies, award dates/status, supplier names and awarded amounts. I downloaded the official CSV and confirmed CBM rows, including:

- LTA000ETT21000010 — Integrated Facilities Management Services.
- CDVHQ0ETT22000006 — FM services for MSF standalone social facilities.
- HDB000ETT23000053 — managing agent services and maintenance works.

These are historical award examples, not a complete CBM portfolio or current pipeline. The inspected dataset page covers April 2021 to March 2026 and displays an April 2026 update. Records can represent item awards or multiple suppliers; totals should not be combined casually. [Official dataset](https://data.gov.sg/datasets/d_acde1106003906a75c3fa052592f2fcb/view)

**Public opportunity listings:** GeBIZ and SESAMi establish realistic metadata and source flows. Full documents, private events and change notifications still depend on access.

**Official FM examples:** the NEA guide and police security template support representative requirements, scoring concepts, service outcomes and briefing obligations.

**Controlled fixtures:** fictional supplier quotations, a fictional company profile and an auditable costing workbook can support tests with known missing items, unit differences, exclusions and amendments. They demonstrate behaviour on the fixtures, without establishing CBM's actual financial or operational fit.

The available public material cannot reveal CBM's losing bids, unpursued opportunities, staff availability, negotiated supplier rates, margin rules, actual execution costs or internal approval authority.

## Validation priorities before choosing an entry point

A useful comparison would put a manual process, a configured general agent and a shortlist of existing products through the same document pack. Keep the inputs and expected outputs fixed.

| Question | Measurement worth collecting |
|---|---|
| Does it miss mandatory requirements? | Requirement-level recall and source location correctness |
| Does it invent company capabilities? | Unsupported-claim count and correct handling of missing evidence |
| Does it understand quotations? | Correct scope/units, exclusions, omitted items and price basis |
| Does it check the workbook? | Detection of planted formula, quantity and mapping errors; independent recalculation |
| Does it handle an amendment? | Correctly identified affected requirements, costs, proposal statements and review status |
| Does it help the team? | Human review/correction time and total elapsed effort, including setup |
| Is the result reproducible? | Consistency across repeated runs and successful recovery from a failed step |
| Does memory improve later work? | Whether a recorded, approved lesson is applied correctly to a subsequent case |

One vendor-published procurement benchmark, ProcureBench, uses a school renovation tender in two languages with fixed answer keys and measures requirement extraction and planted-defect detection. Its narrow corpus and vendor-run judging do not establish CBM performance. It is useful as an example of transparent test construction, rather than as a ranking to adopt. [Methodology](https://tendergate.ai/benchmark)

The brief's 70% AI accuracy target needs a task-specific definition. A single percentage should not obscure a missed deadline, invented qualification or incorrect price. Mandatory-field coverage, factual support and commercial calculations should be evaluated separately from writing quality.

### Questions with the highest information value for CBM

1. Which tender task consumes the most person-hours today, and where do errors or late decisions actually occur?
2. Which existing products, internal tools or general agents have been tried, and what specific results were inadequate?
3. Can CBM provide a sanitised linked pack: original tender, amendment, supplier quotes, costing workbook, submitted proposal and review history?
4. What must be preserved in its workbooks: formulas, macros, named ranges, external links and customer submission formats?
5. Which source accounts, notifications, exports and enterprise-system interfaces can the prototype use?
6. Which records are current and authoritative for certifications, capacity, rates, company evidence and approval powers?
7. Are there genuine hosting, access-control or deployment constraints that would exclude otherwise suitable products?
8. Who will judge outputs, and can the prototype measure actual manual time and correction effort?
9. Which data and integrations will be available only after selection?
10. What continuing deployment and support budget exists beyond the prototype award?

## Commercial considerations

Published pricing is uneven. Responsive displays a starting price of $10,000 and describes an annual platform fee with user licensing. That is not a complete CBM quote, and the captured page did not establish the currency unambiguously. Loopio and Altura direct buyers towards tailored quotes. Altura's listed onboarding packages include six weeks, illustrating that implementation and adoption are part of the offering. [Responsive pricing](https://www.responsive.io/pricing), [Loopio pricing](https://loopio.com/pricing/), [Altura pricing](https://altura.io/en/prijzen)

A fair cost comparison includes licensing or model usage, setup, connectors, content preparation, hosting, review effort, maintenance and support. Self-hosting does not eliminate those costs.

The supplied brief offers S$50,000 for a working prototype with scope to be agreed. That is not a disclosed full deployment or recurring software budget. The proposal form explicitly asks whether a solution requires adaptation, which is compatible with reusing existing technology.

## Decision position

Technical feasibility for many individual tasks is well supported by existing products and components. A broad product whitespace is not supported by the research.

The most useful next evidence is a demonstrated failure or costly workaround on a representative commercial workflow. Until that exists, implementation, adaptation, partnership and a focused product capability should all remain live options.

