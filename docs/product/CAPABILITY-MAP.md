# CBM requirement coverage map

As of 23 October 2026. Read alongside the [market research](../research/RESEARCH.md). This is a map of documented coverage and validation needs, not a product test or numerical vendor ranking.

A named product means a relevant feature is documented. It does not establish complete CBM compatibility. "Not established" means the inspected public material did not answer the question; it does not mean the capability is absent.

| CBM requirement | Existing coverage found | Gap assessment | Evidence needed before custom development |
|---|---|---|---|
| Multi-source discovery and alerts | Official GeBIZ RSS; TenderBoard aggregation; SESAMi listings | Crowded capability; source access/configuration may still require work | Coverage of all CBM accounts, invitation-only events, document access, update latency and export rights |
| Relevant opportunity categorisation | BidPilot profile/rule matching; BidWright and AI bid platforms advertise screening | Generic categorisation is feasible; CBM's criteria are unavailable | Labelled examples plus current capability and commercial rules |
| Tender scope/date/eligibility extraction | Inventive, Altura, Tendermeister, Microsoft RFP agent, Docling plus an LLM | No general feature gap established | Requirement recall, source citations, scanned tables, multi-file packs, site briefings and conflicting dates |
| Marketing and customer intelligence | Some bid products advertise competitive intelligence; public award histories support buyer research | Campaign attribution/customer engagement integration not established in the reviewed shortlist | What marketing data exists and which actual decision depends on it |
| Bid/no-bid recommendation | Inventive, Bidhive, Altura, BidWright, BidPilot and generic agents | Feature exists; decision calibration and hard eligibility rules are CBM-specific | Capacity/certification sources, explicit thresholds, historical pursuit decisions and expert review |
| Initial costing and cost-benefit | CleanBid, Aspire, CATS, ConWize; BidWright advertises cost/margin modelling | Existing estimating market; multi-service local fit remains unknown | Actual workload model, wage/relief assumptions, service design, supplier rates, risk and margin policy |
| Win probability | Historical analytics advertised in category; award data available | Data problem is more established than software gap | Pursued/lost bids, comparable features and proper held-out calibration; public awards alone are insufficient |
| Vendor RFQ question responses | Generic document-grounded agents; TenderAI partner briefs; procurement portals support RFQs | Basic assistance feasible; exact workflow and responsibilities need clarification | Representative supplier questions with authoritative tender clauses and approved responses |
| RFQ issue, reminders and status | ERPNext structured RFQs; ConWize invitations/response tracking; existing workflow tools | Mostly integration and process configuration | Supplier contact records, email/thread association, owner and response status |
| Vendor quote comparison | ConWize qualitative/quantitative BOQ comparison; ERPNext supplier comparison; CATS | Capability exists; unstructured FM scope reconciliation may require adaptation | Different units, periods, exclusions, optional items, taxes, escalation, quote validity and scope coverage |
| Excel formula/costing verification | Excel Inquire analysis/compare; estimating systems; general agents with calculation tools | Formula inspection is already supplied; business correctness is separate | Formula support, macros, external links, recalculation, inserted rows, unit consistency and hidden assumptions |
| Cost summary to customer schedule mapping | CATS Excel links and estimating structures; generic agents can propose mappings | CBM/client-specific compatibility hypothesis | Actual templates, named ranges, grouping rules, rounding and traceability to source costs |
| Historical vendor price estimates | Estimate/rate libraries in Aspire/CATS; knowledge stores; vendor pricing features in some tender projects | Requires comparable, dated and scope-normalised inputs | Scope, unit, location, contract term, quote date, inclusions and uncertainty; no unsupported point estimate |
| Internal routing and approvals | Responsive, Loopio, Altura, Bidhive; generic workflow/agent infrastructure | Strong existing coverage | Current owners/delegations, required decision gates, overdue handling and the exact version approved |
| Proposal retrieval and drafting | Responsive, Loopio, AutogenAI, Inventive, Altura, Microsoft RFP agent, RAGFlow | Very crowded; weak standalone differentiation | Factual support, current approved evidence, mandatory coverage, output format and correction effort |
| Corrigendum comparison | Tendermeister advertises comparison of uploaded amendments; broader workflow products support document/risk processes | Comparison itself is available; full downstream impact remains unverified | Changes linked to supplier scope, quantities, price, narrative commitments and approval versions |
| Mobilisation planning | BidWright advertises discovery-to-delivery; general task/project tooling can support plans | Specific award-to-operations handover not established for CBM | Mobilisation templates, asset/site data, staffing, dependencies and acceptance criteria |
| Enterprise integration | Multiple commercial platforms advertise repository/CRM integration; ERPNext and workflow components supply APIs | Capability exists; exact systems/permissions unknown | CBM's systems, authoritative data, interface access, identity and deployment constraints |
| Vendor engagement analytics | ConWize supplier metrics; procurement records provide response data | Strong component coverage, conditional on complete event records | Correct vendor identity, invited/received timestamps, comparable scope and actual performance data |
| Post-bid review and reuse | Bidhive debrief and outcomes; Altura evaluation; agent memory and structured records | Recording and retrieval exist; improvement has not been demonstrated | Explicit lesson validation, feedback provenance, correct later application and measurable changes in work |
| Secure/configurable multi-team operation | Commercial enterprise platforms advertise controls; generic frameworks require configuration | Customer requirements and product fit unknown | Role boundaries, audit expectations, hosting, approved AI processing, retention and operating ownership |
| Prototype measurement | General evaluation tooling and controlled test packs; brief allows sandbox data | Feasible before private data, with limited conclusions | Known correct answers, reviewer scoring and a later CBM validation phase |

## Representative public inputs

- [Government award dataset](https://data.gov.sg/datasets/d_acde1106003906a75c3fa052592f2fcb/view): historical awards, including CBM rows. It is not a lost-bid dataset or pricing workbook.
- [GeBIZ alerts](https://www.gebiz.gov.sg/business-alerts.html) and [SESAMi listing](https://sesami.online/BO/businessOpportunities.aspx): realistic discovery metadata and source routes.
- [NEA cleaning tender evaluation guide](https://www.nea.gov.sg/docs/default-source/itm/obc-guides/guide-on-tender-evaluation-for-outcome-based-cleaning-contracts-2021.pdf): outcome/quality evaluation context.
- [Police security contract template](https://www.police.gov.sg/-/media/SPF/Knowledge-Hub/Security-Contracting/Outcome-based-Contract-Template_Final.pdf): realistic service outcomes, instructions and performance structure.
- Fictional company/quote/costing fixtures can supply deliberately known errors and changes. They should be labelled and assessed as controlled demonstrations.

## Product evidence used for the map

- [TenderBoard supplier offering](https://www.tenderboard.biz/vendor/)
- [BidWright](https://www.catalystsolutions.sg/bidwright)
- [Responsive](https://www.responsive.io/platform-overview)
- [Loopio](https://loopio.com/platform/)
- [AutogenAI](https://autogenai.com/)
- [Inventive](https://www.inventive.ai/)
- [Altura](https://altura.io/en/bid-companion)
- [Bidhive lifecycle](https://bidhive.com/features/end-to-end-0/)
- [Tendermeister Singapore](https://tendermeister.com/sg_en/gebiz-tender-analysis-software/)
- [ConWize](https://conwize.io/bidding/)
- [CleanBid](https://www.cleanguru.com/cleanbid/features)
- [Aspire](https://www.youraspire.com/features/estimating)
- [CATS](https://www.iddtech.com.au/products/cats-estimating)
- [ERPNext RFQ](https://docs.frappe.io/erpnext/request-for-quotation) and [quotations](https://docs.frappe.io/erpnext/supplier-quotation)
- [Excel workbook analysis](https://support.microsoft.com/en-us/excel/analyze-a-workbook-with-spreadsheet-inquire)
- [Microsoft RFP template](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/agent-template-rfp-assistant)
- [BidPilot](https://github.com/GiorgosPanagopoulos/bidpilot)
- [TenderAI MCP Server](https://github.com/dbugom/tenderai-mcp-server)
- [Docling](https://github.com/docling-project/docling), [RAGFlow](https://github.com/infiniflow/ragflow) and [LangGraph](https://github.com/langchain-ai/langgraph)

## Selection posture

Evaluate the same realistic pack against existing products and a configured general agent. Missing public documentation should trigger a demo question. A custom capability becomes more compelling when a material, repeatable failure is observed and the customer values fixing it.

