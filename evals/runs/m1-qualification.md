# T6 — Authenticated qualification review desk

24 October 2026. Local development slice on feat/m1-foundation, continuing sequentially from T5 (64cd0c9). No deployment, GitHub push or customer pilot is claimed.

The UI now implements the agreed workflow: real sign-in → company reference/upload → cited assessment → owner-confirmed named review task → attributed reviewer answer → automatic reassessment → authorised human decision/export → amendment invalidation and explicit reconciliation. Chat is optional. The original D1 answered-stage pursuit expectation still does not match the live model's hold; that mismatch is retained.

## What was implemented

- Work inbox with buyer, Singapore closing time, assessment/decision currency and next action.
- Side-by-side protected source review and findings; exact page/paragraph excerpts, extracted PDF page text, native original PDF/download, DOCX paragraph highlighting/scrolling.
- Findings and fact corrections with source support/reason; explicit amendment mappings can cite every affected original/replacement clause.
- Named review-task confirmation, typed assigned answers, answer scope, original-assessment inspection and persisted job progress.
- Approver controls, attestation/reason, current/non-current decisions, polled assessment/decision history and exact-snapshot Markdown export.
- Accepted company-reference settings/download and an optional grounded assistant with human confirmation for drafts.
- Real Supabase password sessions. Server-derived memberships/roles; account changes clear client caches. No public signup, role switch or test-login endpoint.
- Concrete authenticated read models/endpoints and reproducibly generated OpenAPI/TypeScript types. Existing schema_version is preserved.

House components, TanStack routing/query and the upstream test setup were reused. Unrelated demo routes are unreachable; their licensed sources/tests were retained. PDF.js was not added: this slice uses protected native PDF viewing plus source text. Native PDF pixels are not established by the automated Chromium screenshots; extracted page text, exact quotes and original downloads were inspected.

## Verification

Final backend suite: **153 passed in 1,054.03 seconds (17m34s)**. Frontend/browser suite: **144 passed in 20.53 seconds**, including 14 qualification checks. Production TypeScript/Vite build passed (21.64 seconds). Targeted ESLint has zero errors and five existing-style Fast Refresh export warnings; targeted Ruff F checks pass. OpenAPI generation is reproducible, the frozen frontend lock is consistent, and the client build contains none of the three configured server secret values.

The initial backend suite passed 147 tests in 994.80 seconds before the final review additions. New meaningful regressions were observed failing before fixes:

| Case | Verified behaviour |
|---|---|
| Revoked assignee role | Answer control disappears; server authority remains decisive |
| Early Singapore closing time | UI preserves +08:00 and expiry policy uses the workspace calendar date |
| Ambiguous mutation outcome | Explicit retry reuses the same request identity/body |
| Amendment mapping across documents | UI collects multiple citations; server accepts supported mappings and rejects incomplete ones |
| Background amendment/decision change | History refreshes alongside tender detail |
| Provisioning DB/output/write failure | Preflight precedes Auth; protected recovery credentials survive interrupted updates |
| DOCX download | Parsed text is labelled and downloaded as JSON, preserving the PDF filename behaviour |
| Selection-field names | Separate explicit labels give exact accessible names |
| Failed refresh | Cached readiness cannot keep decision controls enabled |
| Unreadable source | Needs-input state, no validated assessment and no model request |

The single fresh review found three Important issues (mapping citations, stale history, provisioning recovery), all addressed in one fix pass. Three Minor findings (schema version preservation, DOCX scrolling, original task context) were also addressed. No second review was performed.

## Actual UI run

Four temporary real Auth accounts represented owner/admin, reviewer, approver and a foreign-workspace viewer. All business writes used visible UI controls in [t6-live.mjs](../../apps/web/scripts/t6-live.mjs); only read-only snapshots used the browser's session. The API, production queue worker, Docling parser, private Storage, PostgreSQL and configured OpenAI model were real. Credentials, raw snapshots and personal-account screenshots remain ignored locally.

The run used the actual 24 October Singapore clock, rather than overriding production time with the answer key's later fixture clocks. Only the fixture answer text was submitted; its claimed actor/timestamp fields were not trusted. Answer keys were read only after provider work had finished.

| Stage | Observed result |
|---|---|
| Initial, revision 2 | Hold; two-person Saturday staffing unconfirmed; three additional delivery scope gaps |
| Answer pending, revision 3 | Old assessment explicitly non-current while the answer-created job was queued |
| Answer completed, revision 3 | Two-person staffing met with attributed answer evidence; hold for three scope gaps |
| Human decision, revision 3 | Real approver recorded an attested hold; downloaded brief labelled current human decision |
| Addendum upload, revision 4 | Prior human hold immediately non-current |
| Addendum assessed, revision 4 | Closing 27 November 2026 at 16:00 +08:00; three-person staffing unconfirmed; old two-person obligation retained for reconciliation |
| Human mapping, revision 5 | Original staffing obligation mapped to its addendum replacement; three-person finding remains unconfirmed; hold and other reconciliation blockers remain |
| Separate unreadable PDF | Needs input / SOURCE_INCOMPLETE; no assessment and zero provider requests |

The first mapping attempt omitted an affected addendum quote and returned 422 without a mutation. Supplying all distinct affected quotes through the same visible form succeeded. This is one accepted human mapping in two submissions; no finding was forced to met and no pursuit was manufactured.

A browser read was interrupted during the initial provider run; the harness resumed the same persisted job without creating another analysis request. The first final model candidate needed one bounded repair. The first select automation attempts exposed the label defect, reproduced in a browser test and fixed. These setup/debugging interruptions are not a controlled business task-time measurement.

## Measured outcomes

The [live summary](m1-t6-live.json) and [scoped provider/input ledger](m1-t6-live-ledger.json) contain exact versions, source SHA-256 values, calls and reported usage.

- Four provider requests / **35,925 reported tokens**, using gpt-6.1-sol: initial plus repair, answered and amended. No paid call for the unreadable source. Request counts use durable model-call rows, not copied run metadata on corrected assessments.
- Five exposed key facts matched at each of three stages: **15/15**. The separate briefing timestamp is represented as a requirement, not a sixth key-fact field.
- Staffing status matched the answer key in **3/3** stages. Recommendation matched **2/3**; the answered pursue expectation remains a mismatch.
- Accepted candidates contained 14 extracted requirements at each stage; 31, 31 and 34 citation occurrences passed server source/quote validation (26, 26 and 29 distinct citations). This checks source membership/exact text, not semantic correctness.
- Manual inspection found all six keyed obligation groups at each stage, with the method statement/mobilisation plan split into separate requirements. Three initial eligibility positives were supported. Planned maintenance, reactive response and reporting were additional delivery gaps; staffing confirmation did not establish those capabilities. This is inspection of one fictional pack, not a general accuracy score.
- Anonymous protected access returned 401. Four direct foreign-workspace reads (tender, history, assessment sources, source bytes) returned 404. Viewer creation controls were absent. The real development account signed in successfully.
- The historical brief downloaded through the UI was labelled NON-CURRENT. Source text/citation selection and historical disabled decision controls were visually inspected.
- All four temporary Auth users, both fictional workspaces, their queued records and private source objects were removed using the saved run's IDs. The separate development user/workspace was retained. No email was sent.

The unchanged fixture verifier passed four PDF hashes, five pages, source text/event/schema and 48 mock citations. The untrusted-note file belongs to earlier T3/T5 checks; it was hash-verified here and was not an extra T6 provider input.

## Screenshots

[Source page, exact excerpt and unconfirmed three-person finding](m1-t6/t6-source-final.png) · [Historical decision and versions](m1-t6/t6-history-final.png) · [Current human hold](m1-t6/t6-human-decision.png) · [Immediate amendment invalidation](m1-t6/t6-amendment-stale.png) · [Unreadable file](m1-t6/t6-unreadable.png)

Only fictional-account captures are committed. The development user's sign-in capture remains local.

## Reproduction and remaining limits

See [frontend setup](../../apps/web/README.md) and [API/worker commands](../../apps/api/README.md). The actual development login is saved in ignored evals/runs/local/development-sign-in.json. Never put its password or server keys in browser code.

For an explicitly paid rerun, prepare fresh fictional accounts with python -m evals.t6_accounts prepare, then run the initial, answer, decision, amendment, reconcile, unreadable, source-final, export-history and access phases with Node against the running UI/API/worker. Inspect usage before scoped cleanup; generate the report from saved captures. A prior run record is deliberately retained locally after cleanup: archive both the accounts record and t6-ui-state.json locally before preparing another run. Do not run the production worker while the default backend suite is dispatching synthetic jobs. This host uses Playwright's published Ubuntu24 Chromium build via PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 under WSL Ubuntu26.

Supported intake remains born-digital PDF and simple DOCX body paragraphs. Image-bearing PDF pages are partial; OCR, complex DOCX and broad parser accuracy remain unsupported. Original PDF pixels require a capable browser/viewer; extracted page text remains available. DOCX text downloads are labelled as extracted text and use JSON filenames; original DOCX bytes remain retained privately. No model-worker exactly-once or general crash-recovery claim was added; earlier parser/queue recovery checks remain separate.

Deferred T5 Minors remain: distant NFKC/whitespace matches may yield an unhelpful retrieval excerpt; repair feedback is generic. The prior Storage401/403 retry-classification Minor remains deferred. General comments, live CBM integrations, D2/D3 and held-out/customer evaluation, deployment, retention/orphan-object reconciliation and measured business savings remain later work. No lifecycle milestone beyond the implemented engineering slice is declared complete.
