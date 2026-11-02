# T5 — Bounded assistant, human decisions and qualification export

24 October 2026. Backend implementation verified; **143 API tests passed**. T6 UI/sign-in is separate.

## Implemented

The assessment assistant exposes only get_assessment, search_evidence and prepare_review_request. The server pins actor/workspace/tender/assessment and rejects injected identity fields or other tools. An in-scope answer requires exact source quotes; unknown or conflicting evidence still needs explicit explanation and human review. Review-answer search preserves the original question, assessment, source manifest and recorded basis.

Each turn has at most three provider requests, six tool calls, one schema repair and a 360-second total deadline. Duplicate tool arguments reuse the result. Private assistant_runs reserves each request before spending and retains outcomes/usage. Completed command replay spends nothing; running/unknown outcomes require a conscious new request identity. Provider calls hold no tender lock. A changed snapshot is explicitly historical. Drafts only become tasks through the bid owner's existing T4 confirmation command.

Human decisions require the approver role and exact current assessment/input/company-evidence versions. Pursue additionally requires review attestation and live source, qualification, reconciliation, closing-time and evidence-date checks. Hold/decline preserve the human reason and review flag. Immutable old decisions become non-current after changed inputs, answers, company evidence, corrections/new assessments or time-dependent pursuit blockers. A later decision supersedes an earlier decision even if the assessment is unchanged.

The protected Markdown download contains the exact assessment, source references, outstanding conditions and human actor/reason/time. It distinguishes DRAFT, CURRENT HUMAN DECISION and NON-CURRENT. Historical exports remain available; a current hold is not a pursuit approval. Untrusted document/reason text is inside JSON code fences, and no public export object is created.

## Verification and review

Focused T5 tests: **21 passed in 198.21 seconds** before the final review fixes. After the review fixes, the complete suite passed **143 tests in 927.05 seconds**; see [T5 checks](m1-t5-checks.json).

Tests use the configured development PostgreSQL and private Storage with unique fictional workspaces and controlled model responses. They cover tool/identity boundaries, citation validation, repair and request limits, same-ID concurrency, durable replay, separate human draft confirmation, current approval, missing attestation, closing/expiry, safe export and an amendment racing the decision lock.

The controlled end-to-end case runs real uploads, native parsing, T4 confirmation/answer, queued reassessment, human pursue, real addendum upload and amended reassessment. The old pursuit becomes non-current; the new closing date is recognised and staffing returns to unconfirmed/hold. Controlled candidates establish policy behavior, not extraction accuracy.

One fresh read-only review found two Important issues, each reproduced before one fix pass: a superseded pursuit replay remained current; retrieved short review answers lost their original question/scope. Regression tests now cover both. No second review was requested.

Practical testing also exposed an SDK serialization defect: stateless tool continuation sent Python's async_ field rather than the API's wire field. A minimal request reproduced API 400. The adapter now uses wire aliases and omits null fields, with a failing-then-passing SDK-object regression. Invalid tool batches now acknowledge every call before repair; simultaneous reservations reuse the existing read-committed claim with short snapshot locks. The unchanged T1 access test additionally caught a stale-input error-precedence regression, which was corrected.

[Smoke checks](m1-t5-smoke.json) confirm the restarted local API serves health/docs/OpenAPI and advertises the three T5 routes. Anonymous assistant/decision/export requests return 401. [Table access checks](m1-t5-access.json) confirm RLS and no browser anon/authenticated access to assistant_runs.

## Live fictional D1 results

The explicit [live run](m1-t5-live.json) uses the real parser/provider/database/Storage, seeded actors and actual T4/T5 business commands. It makes no real user session or external communication. Six analysis requests reported 55,368 tokens:

| Stage | Outcome | Staffing | Closing |
|---|---|---|---|
| Initial | hold | Two-person Saturday availability unconfirmed | 20 November 2026, 16:00 Singapore |
| Answered | hold | Two-person Saturday availability met | 20 November 2026, 16:00 Singapore |
| Amended | hold / needs input | New three-person obligation unconfirmed; older two-person met record retained pending reconciliation | 27 November 2026, 16:00 Singapore |

The original D1 answered key expects pursue. The observed hold remains a visible mismatch: the live extractor separately identified unresolved maintenance/reactive/reporting scope, and requirement identity changes still require reconciliation. The key was not weakened and no pursuit was forced.

The fictional approver recorded **hold**. Its exact snapshot exported as CURRENT HUMAN DECISION; the addendum immediately made that hold and its historical export NON-CURRENT. Live positive pursue was not demonstrated; the controlled HTTP/parser case proves that path.

The initial grounded assistant exposed the wire-format error after one successful tool response. [Failure evidence](m1-t5-assistant-initial-failure.json) preserves the two-request outcome. The out-of-scope approve/email/submit request returned the fixed explanation with zero citations/drafts and no mutation.

After the fix, a conscious new [bounded assistant turn](m1-t5-assistant-after-fix.json) reused the saved real parsed initial snapshot: three provider requests, two tool calls, four validated citations and one review draft, with an explicit historical notice. This targeted rerun used the direct tool loop; durable HTTP behavior is covered separately. It did not repeat the entire paid parser/analysis run.

[Usage](m1-t5-usage.json): 12 run requests and 72,402 provider-reported tokens across analysis, failed assistant turn, out-of-scope response and targeted successful rerun. A separate rejected diagnostic request reproduced the wire error. These are observed usage figures, not a monetary cost estimate.

## Remaining limits and next step

- Source-valid quotes do not establish semantic support; extraction drift and requirement reconciliation remain visible human work. No broad document-accuracy claim.
- Two review Minors are deferred: a distant normalized whitespace/NFKC search match can fall outside its excerpt; repair feedback is generic instead of listing exact errors and the failed final answer. These affect usefulness and bounded repair success, not authority.
- The earlier Storage 401/403 classification Minor, operating-system parser sandboxing, unknown provider cost on interrupted requests and model-worker crash recovery remain unverified/deferred. Parser commit-before-ack recovery was demonstrated earlier.
- Real user/membership provisioning, browser sign-in and the usable review desk remain **T6**. No shared deployment or GitHub push was performed. M1 release completion is not claimed.
