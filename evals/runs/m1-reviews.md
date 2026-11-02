# T4 — confirmed review tasks and answer-driven reassessment

**Local archive note:** Superseded plans/probes linked below are preserved in the local, Git-ignored `remove/` folder. They are historical evidence, not current setup instructions. Use the [current API guide](../../apps/api/README.md) for supported commands.

24 October 2026. T4 backend complete; T5–T6 remain open.

T4 adds the two specified HTTP commands and includes tasks/answers in tender detail. A bid owner confirms an actual current question draft and chooses an authorized assignee. The assignee records a typed answer. Evidence, task status, tender revision, reassessment job and PgQueuer dispatch commit together; enqueue failure rolls everything back.

## Verification

- The first 12 checks failed for missing T4 commands and due calculation.
- Three answer-kind regressions failed before the guard was added, then 34 analysis/policy checks passed in 3.12 seconds.
- Focused review/analysis/policy suite: 49 passed in 171.27 seconds. This includes real parser → answer HTTP endpoint → reassessment using controlled model output, authorization, attribution, task idempotency, rollback and concurrent submissions.
- Snapshot regression: failed with embedded prior assessment data, then passed in 14.07 seconds after preserving only version references/hashes.
- First implemented run also exposed fixture cleanup ordering and a test call typo. Cleanup now removes only the fixture's own tasks before its workspace; four exact workspace IDs from failed cleanup traces were verified as fictional and cleaned.
- One independent read-only review found two Important gaps: answer scope could confirm unrelated/changed requirements, and carried-forward local references could pollute current task scope/deduplication. Nine regressions failed first; a tenth reproduced preserved human corrections bypassing the scope check. Both findings were fixed in one pass; no second reviewer.
- Pre-review full API suite: 109 passed in 666.70 seconds. Post-fix focused suite: **60 passed in 202.39 seconds**. Final full WSL suite: **119 passed in 692.62 seconds**, including real parser worker commit-before-ack recovery and the review concurrency/rollback checks.

## Actual model workflow

The [live T4 report](m1-t4-live.json) uses the real parser/model/DB/Storage and confirmed T4 business commands with seeded fictional actors. The answer-created job is processed directly. Separate HTTP integration tests cover the endpoints, roles and rollback; this is not actual user sign-in or a production worker process recovery test.

| Stage | Result | Calls | Reported tokens |
|---|---|---:|---:|
| Initial | Hold; 10 requirement records; staffing and service scope unconfirmed | 2 | 13,818 |
| Attributed staffing answer | Staffing met; 11 requirement records; hold/needs_input for scope and a new submission-deadline reconciliation item | 1 | 9,858 |

Total **3 provider calls / 23,676 reported tokens**, including the initial schema repair. Answer replay, task answered before reassessment, old-assessment invalidation, queued reassessment and author attribution all passed. Both closing timestamps matched; zero decisions were recorded.

The additional requirement was “Submit by 20 November 2026 at 16:00 Singapore time (UTC+08:00).” The closing fact was already present, but the model added a separate requirement on reassessment. The conservative identity policy keeps that addition visible for human reconciliation. General delivery scope also remains unresolved. The original D1 answered-pursue expectation is still a mismatch; no key or prompt was changed to hide it.

The live run predates the review fixes. [Post-fix offline validation](m1-t4-revalidation.json) accepted both saved final candidates using their actual parsed anchors and scoped answer metadata, restoring the previous snapshot from the saved initial payload. It made no new provider call. Staffing remains unconfirmed→met and the hold/reconciliation state remains.

## Behavior and rulings

- Confirming requires bid-owner authority and the current assessment version. AI drafts alone create nothing. A configured engineering_lead suggestion routes to service_reviewer; an assigned bid owner must record a basis when answering.
- Open tasks deduplicate on the exact sorted requirement identity set, assignee and qualification-review purpose. Different client keys still reuse an equivalent task; same-key replay returns its original response.
- Default due time uses the exact UTC formula in M1-SPEC. Unknown/past closing needs an explicit future deadline within 48 hours; a known future closing permits only an earlier future time than its default. The original due time is preserved on deduplication.
- Both explicit analysis and answers use one transaction-aware enqueue helper. Each caller enforces its own authority; the reviewer is never impersonated as the bid owner.
- A task stays bound to its original question/source versions. Answers after a source change retain that scope while reassessment pins all current inputs. This is human evidence, not automatic compliance with amended requirements.
- Answer scope must match the exact requirement identity for a definite finding. Missing/malformed scope/kind metadata fails validation, including preserved human corrections. A current draft is resolved through current candidate requirements, excluding carried-forward records that reuse a local ref.
- Answer types are confirmed, denied or unable_to_confirm. Denial/unable cannot be cited to support met; unable cannot support unmet. The task's answered status does not change qualification by itself.
- Source snapshots contain version IDs and hashes rather than recursively embedding old assessment payloads. This keeps answer history/model context from growing through nested snapshots.
- Ruling: retain the initial engineering_lead to service_reviewer mapping and allow an assigned bid owner with a basis — follows the existing authority model — cost if wrong: wider routing needs later configuration.
- Ruling: retain source/version references instead of nested prior payloads — bounds history growth — cost if wrong: text must be retrieved through immutable references.
- Ruling: reuse the enqueue helper across authority paths — preserves one atomic manifest/dispatch implementation — cost if wrong: both paths depend on that helper retaining its currency checks.
- Ruling: preserve answers to old open questions as explicitly bound evidence — avoids discarding useful human input across amendments — cost if wrong: semantic relevance still needs review.
- Ruling: allow an explicit deadline within 48 hours when closing is unresolved — permits asking for missing information — cost if wrong: manual timing needs bid-owner judgement.

- Ruling: reconciliation cannot expand an answer to a changed capacity requirement — prevents extending a two-person confirmation to three — cost if wrong: harmless quote changes can require a new scoped answer or other evidence.

The live D1 answer key remains unchanged. T3's extra scope questions are an existing documented mismatch; T4 does not remove them to manufacture pursue.

The WSL API was restarted with T4 routes. [Smoke checks](m1-t4-smoke.json) passed: health/docs/OpenAPI 200 and anonymous task/answer commands 401.

Worker restarted after final verification with zero pending queue messages. [Check summary](m1-t4-checks.json).

## Limits

No external messages are sent. Actual user sign-in, the frontend, human decisions, assistant tools and export remain T5–T6. Live tests seed fictional actors; model-worker process crash recovery remains untested, while the existing parser recovery test remains in the full suite. T2's input restrictions and deferred Storage 401/403 classification still apply.

See [API commands](../../apps/api/README.md), [implementation checklist](../../remove/M1-IMPLEMENTATION.md) and [progress ledger](m1-progress.md).
