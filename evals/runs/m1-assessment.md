# T3 — cited qualification assessment

24 October 2026. Backend slice complete; T4–T6 remain open.

T3 connects the existing document pipeline to bounded OpenAI Responses requests and strict independent validation. It adds admin acceptance of dated company evidence, source-bound requirement identities, conservative reconciliation, immutable human corrections, historical assessment reads and durable model-call accounting. A valid recommendation is never a human decision.

## Evidence

- Before review: 82 tests passed on Windows (466.20 seconds) and WSL (396.77 seconds). WSL is now the required development runtime; the Windows environment was preserved.
- Six review regressions failed before the fixes, including reconciliation reset, persisted incomplete/refused output replay, unsafe correction serialization, duplicate in-flight reservations and unrelated replacement mappings. One failed-test shutdown also produced a TestClient portal teardown error.
- Post-fix focused checks: 39 passed in 247.87 seconds. Full final WSL suite: **90 passed in 533.95 seconds**, including the real parser worker crash/commit-before-ack recovery regression.
- One independent read-only review; all six Important findings addressed in one fix pass. No second reviewer. Existing T2 Storage error classification remains a deferred Minor.
- Applied migration `20261024041316_m1_assessment.sql` using the explicit application runner; locked dependencies in `apps/api/uv.lock`. JSON Schema 4.26.0 and OpenAI SDK 3.37.0.

The [Linux live run](m1-t3-live.json) used actual parser, model, development database, private Storage and transactional queue dispatch, with fictional seeded actors. The harness called the business handler directly and inserted attributed review evidence itself. It did not test actual sign-in, T4 answer authorization or model-worker process-crash recovery.

| Stage | Observed result | Provider calls | Reported tokens |
|---|---|---:|---:|
| Initial | Hold; Saturday staffing and three service-scope findings unconfirmed; targeted questions | 2 | 13,419 |
| Staffing answer | Staffing met; scope findings retained; hold | 2 | 19,777 |
| Supplemental scope clarification | All seven mandatory qualification findings met; pursue | 2 | 20,347 |
| Addendum | New closing date 27 November 2026, three technicians unconfirmed; hold and reconciliation required | 2 | 22,360 |
| Untrusted-note variant | Hold; instruction flagged; no decision created | 2 | 13,674 |

Total: **10 provider calls / 89,577 reported tokens**. Each stage used its permitted schema repair: offline inspection of the first responses reproduced duplicate source-clause identities. The conservative identity scheme increases repair/correction effort and is not a general extraction-consistency result. Token totals are observed usage, not a cost estimate. There were zero human decisions. Initial/answered/scope-clarified runs retained 12 requirement identities; amended output retained the old staffing clause as history alongside the new one (13 records); the independent injection variant extracted 10 records.

**The original D1 answered expectation remains a mismatch:** the key expects pursue after the staffing answer. The real model kept planned maintenance, reactive fault response and service reporting unresolved. Those requirements and questions remained visible. The additional scope clarification is a separately labelled fictional event, not CBM evidence and not a rewrite of the original key.

Semantic inspection found that staffing changed only with its attributed confirmation; the scope clarification supported those separate delivery findings; the addendum did not turn two confirmed technicians into three or into an asserted inability to comply. All five closing timestamps matched their applicable expected dates. Exact quote checks establish source location, not general semantic accuracy.

The live run predates the review fixes. [Offline revalidation](m1-t3-revalidation.json) reran its saved final candidates through the corrected validator using reconstructed anchors from the unchanged fictional PDFs/answer texts, with no new provider calls. All five candidates validated: 151 candidate citations; the amended state now retains two unresolved reconciliation records, including the new clause addition. This is not a second integrated live run.

The earlier [Windows run](m1-t3-live-windows.json) used 5 calls / 35,513 reported tokens across four stages. Its amended parser child failed before any provider call; stale earlier assessment stayed non-current. The WSL amendment run completed. One Linux run does not establish broad parser reliability.

## Review fixes and operating rulings

- Preserve unresolved reconciliation and the original obligation across identical reruns and unrelated corrections. Additions require explicit review when there is a prior assessment.
- Human edits create a new attributed assessment with hold pending reassessment. This permits safe downgrades and clearing a fact to explicit null without weakening source/schema rules.
- Select the highest input revision before creation time everywhere: late old results remain historical and cannot hide a newer human correction.
- Persisted provider refusal/incompletion remains terminal during recovery. Actual refusal content is recognized even when the provider marks the response completed.
- Replacement mappings must address outstanding changes and cite affected original/replacement clauses. They require a shared clause or a registered amendment relationship, retain mandatory qualification, and cannot silently replace an unresolved finding with met. Humans must still judge whether the replacement is semantically correct.
- Model reservations serialize under the job lock, refuse an outstanding unknown call and check the owning attempt before another paid request. At most three reservations, one schema repair, 120 seconds per provider call, 12,000 output tokens, 600 seconds total.
- Ruling: fail safely when a provider outcome is unknown; require conscious new analysis rather than assuming exactly-once external execution. Cost if wrong: a recoverable valid response may require human-triggered reanalysis.
- Ruling: accept company evidence through a separate admin workflow and invalidate all workspace tender revisions. Cost if wrong: conservative invalidation causes extra reassessment.
- Ruling: source identity uses exact normalized clauses, with no fuzzy automatic reconciliation. Cost if wrong: harmless quote/wording changes need human review.

The WSL API is running at localhost:8765; [smoke checks](m1-t3-smoke.json) passed. The worker was restarted after the suite against an empty queue. [Check summary](m1-t3-checks.json).

## Limits and next step

T4 will create confirmed review tasks and accept authorized answers while enqueueing reassessment atomically. T5 implements the assistant, human decision policy and export; T6 connects the frontend and real authentication.

No OCR/complex-document, deployment, customer capability, held-out accuracy or productivity claim. T2's conservative image/DOCX restrictions remain. All terminal work now runs in WSL. The user-created AGENTS.md and unrelated line-ending differences are excluded from the T3 commit. API/worker setup and request shapes are in the [API guide](../../apps/api/README.md).
