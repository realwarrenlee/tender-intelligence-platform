# T0 queue and T1 foundation execution

24 October 2026, Asia/Singapore. Branch: `feat/m1-foundation`. No GitHub push or public deployment.

## Real queue verification

[Queue evidence](m1-queue.json): PostgreSQL 17.11 via the supplied persistent session-pooler connection; PgQueuer 1.6.0. One child worker exited with code 23 during a picked job, without graceful acknowledgement. A second process recovered that job through heartbeat expiry. A separate job raised a database-level transient retry and completed on its next attempt.

Both jobs executed twice but produced one recorded effect each. An identical queued request was skipped by the queue's dedupe key. There were two successful logs, one retry log and no jobs left. Runtime: 15.422 seconds. Application uniqueness/transactions enforce effect idempotency; this is not an exactly-once-delivery guarantee. A uniquely named private probe schema is retained for inspection; existing managed/application tables were not modified.

The real integration check failed before the experiment existed, then passed. Reproduce deliberately (creates a fresh private probe schema):

```powershell
$env:M1_RUN_DATABASE_TESTS='1'
uv run --project spikes/m1-adoption pytest spikes/m1-adoption/tests/test_queue_live.py -q
```

## T1 implemented behaviour

The FastAPI backend now creates and retrieves durable tender records. Role checks are enforced in database transactions: viewers cannot write, admin does not imply approver, foreign-workspace direct IDs return 404, and forged client roles/workspace fields are rejected. Commands re-read actual database membership rather than trusting a stale context role list.

Client request identity/hash and result are stored transactionally. Concurrent identical requests create one tender; changed content under the same identity returns 409. Source registration increments the input revision, stores immutable document versions plus an explicit source-set manifest, and rejects stale writes. Company evidence cannot be promoted through ordinary bid-owner source registration. Source/artifact/answer/decision/audit updates are rejected by immutable-history triggers.

The schema supports versioned evidence/assessments, review records, decision snapshots and business jobs for later tasks; their workflows are not implemented. Analysis/decision routes fail with explicit not-ready states instead of simulating success. The frontend template is still unconnected.

Authentication calls Supabase Auth's user endpoint to verify a bearer token and then loads workspace membership from PostgreSQL. Tests of valid/invalid provider responses are controlled boundary tests; no actual human sign-in session or customer onboarding was executed. No test bypass exists in production routes.

## Verification

Initial record/access checks failed before implementation. Additional tests exposed missing source-set manifests, malformed-session classification and company-evidence authority gaps; each failed before its fix. The first complete foundation suite passed 14 tests. After the final review fixes, **20 tests passed in 74.94 seconds** against the development PostgreSQL database. Coverage includes duplicate concurrency, restart persistence/replay, stale updates, tenant isolation, role enforcement, forged user metadata, private-schema grants/RLS, immutable source versions, Windows migration line endings, concurrent aggregate snapshots and sanitised database-outage errors.

One test-client deprecation warning remains: the installed Starlette still supports the pinned httpx client but recommends httpx2. This does not fail the tests; changing client libraries is deferred until required by an upgrade.

Migration SQL was generated with Supabase CLI 2.122.0, inspected against the initially absent `m1_app` schema and applied through an explicit hash-tracked application runner. Running it again applied no changes. Source fixtures, existing Supabase schemas and local credentials were preserved. See [API setup](../../apps/api/README.md).

T0's earlier model requirement drift and intermittent native parser failure remain open for T2/T3. The queue success and API foundation do not resolve those findings or establish full M1 readiness.

## Final review

One independent read-only review found three important issues. Regressions reproduced changed migration hashes after CRLF conversion, a mixed-revision tender/document response during a coordinated write, and unsanitised database availability exceptions. Those five failing cases were fixed in one pass: migration SQL uses LF attributes and normalised hashing; detail reads use repeatable-read isolation; known connection/time-out errors use the JSON retry contract. An integrity-error check confirms programmer/data-integrity failures are not falsely labelled transient. The full 20-test suite passed; the revised API starts and returns /health 200 and unauthenticated tender access 401.

Scope decisions: use the current checkout's feature branch to preserve local runtime setup (weaker file isolation than a separate worktree); keep the two command orchestrations in the repository (split if later workflows become hard to review); use explicit application-owned migration history (reconcile before switching to Supabase CLI push). No actual sign-in/onboarding, upload/storage/AI/review/decision flow or production role/deletion policy is claimed. Future workflow commands must enforce assessment type and cross-tender linkage constraints. A crash after effect commit but before acknowledgement was not exercised by the queue probe and remains a T2 idempotency test. The test-client deprecation warning is deferred; the current pinned client works.
