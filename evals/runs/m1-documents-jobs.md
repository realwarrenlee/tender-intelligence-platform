# T2 source processing and durable jobs

24 October 2026, Asia/Singapore. Branch `feat/m1-foundation`; local development only.

## Implemented

Bid owners can upload immutable born-digital PDF/simple DOCX sources through the authenticated API. Every accepted file has a server-generated content-addressed private Storage key, SHA-256, size, declared/validated type, source role and immutable document ID. Addenda explicitly reference an existing tender/addendum version in the same tender; they do not replace the original clauses. Upload transactions enforce membership, current input revision, pack limits and request idempotency.

Native Docling parsing accounts for every PDF page, including unreadable pages, and preserves original one-based DOCX paragraph indices across blank paragraphs. The original bytes remain unchanged. Unreadable/unmappable files leave the pack incomplete. File/MIME/page/character/ZIP checks occur before a future model call. Each conversion executes in a child process under the persisted 600-second analysis deadline, containing native process failures. This does not resolve the previously observed intermittent Windows parser failure or establish general OCR/table accuracy.

Analysis requests pin source metadata/versions and enqueue PgQueuer work in the same PostgreSQL transaction as the business request. Job states, attempt events, completed stages, per-source warnings and output version IDs are durable. Cancellation, a changed input revision and a newer attempt fence late publication. Transient storage/database failures have bounded retries. Earlier artifacts remain readable after later failure. A complete parse ends at **needs_input / ASSESSMENT_NOT_IMPLEMENTED**; no accepted AI assessment or decision is manufactured.

Private Storage bucket `m1-sources-v1` is created/verified through the Storage API. Queue tables/functions live in private `m1_queue`; application changes use CLI-created `20261024033342_m1_sources_jobs.sql` through the existing application migration runner. Browser roles have no application/queue schema privileges. [API setup and requests](../../apps/api/README.md).

## Verification

The original 20-test API baseline passed in 74.16 seconds. New tests were written before implementation. Missing document/job behaviour failed first. Real Storage revealed its missing-bucket response is HTTP 400 with `NoSuchBucket`, which was handled before proceeding. Race testing reproduced two artifacts from competing attempts; the attempt fence fixed this. Additional failing regressions covered cumulative DOCX character limits, multipart error shape and database-disconnect retry handling.

Pre-review combined T1/T2 suite: **44 passed in 266.24 seconds**. The independent review found four Important issues: omitted DOCX table content, unaccounted PDF bitmaps despite text on the page, failure to persist terminal database status, and a failed DOCX rerun masking earlier readable text. Seven regression cases reproduced these failures, then passed in one fix pass (39.58 seconds). The full post-review suite passed **51 tests in 287.27 seconds**, with the single existing TestClient deprecation warning.

The [D1 parser check](m1-t2-parser.json) recovered all four original fictional PDFs/five pages through the T2 isolated parser, verifying their known hashes and one-based page anchors. [Read-only access checks](m1-t2-access.json) confirmed both schemas deny browser roles and enable RLS on every table, the source bucket is private and no Storage policies grant browser access. [Restarted API smoke](m1-t2-smoke.json): health 200, unauthenticated job read 401, OpenAPI 200 with the T2 routes present. No frontend tests were rerun because no frontend code changed.

[Actual recovery evidence](m1-t2-recovery.json): a real worker parsed the fictional two-page PDF using private Storage/PostgreSQL and committed its output, then exited with `os._exit(23)` before queue acknowledgement. A replacement worker recovered/acknowledged the same queue message: **one business attempt, one parsed output, zero remaining queue messages**. The test uses an isolated queue entrypoint and a two-second heartbeat; the production worker uses a 60-second heartbeat. This demonstrates idempotent local effects, not exactly-once delivery.

Controlled parser barriers exercise cancellation/amendment/competing attempts while work is running; controlled timeout/disconnect cases exercise error/retry paths. These are separate from the real parser and process-interruption evidence. Tests use fictional workspace IDs and delete only their own objects/rows/messages. No actual Supabase user sign-in or paid AI call was made for T2.

## Limits and remaining work

- T3–T6: cited AI assessment, accepted company evidence integration, review/answers, human decisions, exports, UI and actual sign-in remain unimplemented. AI requirement drift remains open for T3.
- Supported inputs are born-digital PDF and simple DOCX body paragraphs. DOCX tables/drawings/header/footer/note/comment content, fields, tracked changes and external relationships fail visibly. Image-bearing PDF pages are partial even when they contain text; decorative logos also trigger this conservative rule. OCR and complex-document coverage remain unverified.
- Subprocesses contain parser crashes; deployment still needs a suitable worker security/runtime boundary.
- Storage and database commits cannot be atomic. Unreferenced uploaded objects after rollback need reconciliation before pilot retention/deletion obligations.
- The existing Starlette/httpx TestClient deprecation warning remains; the pinned client works.
- Storage 401/403 responses currently share the bounded retryable-unavailability classification. Distinguish permanent permissions/configuration failures before deployment; no additional credentials are needed for the verified local setup.

## Recorded decisions

- End complete parsing at needs_input until T3 validates an assessment; T3 must extend that transition.
- Retain application-owned migration history, a private PgQueuer schema and Storage API bucket creation; reconcile before adopting another migration/deployment tool.
- Reject unmappable DOCX and run conversion in a timed child; this narrows document support and contains crashes without providing an OS sandbox.
- Treat all bitmap-bearing PDF pages as partial; logo/image-heavy documents cannot yet produce complete coverage.
- Retain dispatch while terminal status cannot be saved, retrying only finalization; an unavailable business pool creates a recoverable backlog, without extra parsing/model calls.
- Keep T3–T6 and broad OCR/complex-document support outside T2; whole-workflow acceptance waits for those tasks.

One reviewer was used, with no re-review after fixes. The seven failing-then-passing regressions and full suite provide fix verification. Deferred minors are the Storage authorization classification and the existing test-client deprecation warning.
