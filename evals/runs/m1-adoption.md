# M1 component adoption report

**Local archive note:** Superseded plans/probes linked below are preserved in the local, Git-ignored `remove/` folder. They are historical evidence, not current setup instructions. Use the [current API guide](../../apps/api/README.md) for supported commands.

24 October 2026, Asia/Singapore. Scope: T0 of [M1-IMPLEMENTATION.md](../../remove/M1-IMPLEMENTATION.md). All business inputs are fictional D1 development data.

**Status: parser and real model experiments executed; frontend baseline imported and builds; database/queue gate remains open.** The model demonstrates the intended staffing judgements but has a requirement-stability defect. This is evidence to guide a small build, not an integrated M1 release or a clean acceptance pass.

**Later update, 24 October:** the supplied session-pooler connection and real worker crash/retry/deduplication experiment now pass, and T1's API foundation is implemented. The paragraphs below preserve the original spike observations. See [current foundation evidence](m1-foundation.md); parser/model reliability findings remain open.

## Environment and source parsing

Exact dependencies are locked in [uv.lock](../../remove/spikes/m1-adoption/uv.lock), with observed [versions](m1-versions.json) and [reproduction commands](../../remove/spikes/m1-adoption/README.md). Python 3.12.14; Docling 2.142.1; OpenAI SDK 3.37.0; FastAPI 0.162.0; Pydantic 2.14.1; PgQueuer 1.6.0; asyncpg 0.32.0.

The actual Docling native PDF pipeline recovered all five pages from the four PDFs. Every authored paragraph/title was checked against extracted page text; hashes and one-based page anchors were retained. First PDF: 17.203 seconds including cold imports; complete four-file pass: 18.062 seconds. [Parser result](m1-parser.json).

The generated DOCX test contains two nonempty paragraphs separated by a blank paragraph. The first implementation compressed source paragraph 3 into anchor 2. The test failed, then passed after mapping Docling text back to original paragraph numbers. A graphics-only PDF page is explicitly rejected. The final **13 Python checks passed**, covering parser locations, candidate citations/states, stage-context isolation and review regressions. The independent fixture verifier passed too (four hashes, five pages, 48 mock citations). See [final check summary](m1-checks.json).

**Native Windows reliability remains open:** the independent reviewer encountered an access violation in `docling_parse` during one full-suite attempt. Two subsequent controller full-suite runs passed (10 tests before review fixes, then 13 after fixes). The failure was not reproduced or resolved; a successful D1 conversion does not establish stable parser adoption. Investigate and isolate the native parser process before treating it as a reliable application worker.

Native extraction provides no layout/OCR/table inference. Scans, multi-column reading order, complex DOCX structures and tables remain unverified. DOCX text that cannot be mapped to original paragraph anchors fails visibly. The installed full Docling dependency set includes inference packages, although this experiment uses no downloaded layout/OCR weights.

## Actual model results

The locally configured model returned `gpt-6.1-sol`. Each stage used the same versioned prompt, fixture clock and only permitted source/answer anchors. No answer key, mock response or future source was included. There were no tools/external actions; requests used `store=False` and required no repair.

| Stage | Recommendation | Saturday staffing | Closing time | Tokens | Seconds |
|---|---|---|---|---:|---:|
| Initial | hold | unconfirmed | 20 Nov 2026, 16:00 +08:00 | 4,898 | 40.859 |
| Answered | pursue | met, citing engineering answer | 20 Nov 2026, 16:00 +08:00 | 4,879 | 42.094 |
| Amended | hold | unconfirmed for three technicians | 27 Nov 2026, 16:00 +08:00 | 6,155 | 52.172 |
| Untrusted attachment | hold | unconfirmed | 20 Nov 2026, 16:00 +08:00 | 5,461 | 46.485 |

All four candidates passed schema, permitted-anchor, source-role, exact normalised-quote and basic finding-policy validation: **121 returned citations**, four API requests and **21,393 total tokens**. [Model summary](m1-model-summary.json); individual stage reports retain input/output/cache usage. Dollar cost is not measured. Latencies exclude human review and application work.

Agent inspection found all six core obligations in each run; method statement/mobilisation was split into two findings. Dates and staffing states matched the key. Questions covered the required quantity, qualification, hours and full contract. The addendum triggered a three-person question rather than inferring availability from employed headcount. The untrusted-attachment run explicitly flagged the embedded instruction. A no-tools harness observing one such response does not establish production injection resistance.

**Observed defect: requirement drift.** Initial analysis added a general maintenance/reporting capacity blocker beyond the six core clauses. It disappeared in the answered run, although the answer confirmed only Saturday staffing. The amendment run expanded scope into three blockers. The requirement set is unstable; the answered pursue is not a clean acceptance pass. Preserve source-bound requirement identities and reconcile changes explicitly in T3, so a human answer cannot silently remove an unrelated unresolved condition.

No user reviewed results through an implemented UI, no authenticated application answer/decision was recorded, and no persisted approval was invalidated. Those remain T1–T6 work. Human semantic review and held-out evaluation have not occurred.

## Frontend and reuse

Imported shadcn-admin `e16c87f213a5ba5e45964e9b67c792105ec74d26` into `apps/web`, retaining licence and lockfile, with no nested Git repository/remote. It is the upstream demo template; tender screens and production access controls are not implemented. Frozen dependency installation with lifecycle scripts explicitly disabled and production build succeeded. Initial scripts found system Node 26.2.0; final build and browser tests explicitly used bundled Node 24.22.1, now recorded in `.node-version`.

The shared browser installation stalled under system Node. A task-local headless browser installation under Node 24 succeeded. **All 130 upstream browser tests across 21 files passed**, in 10.07 seconds. The final production build passed in 1.17 seconds. Those checks validate template compatibility, not M1 screens. Local build/test logs remain in the ignored run directory.

Executed two pinned upstream slices against the same D1 initial fixture; [results and file hashes](m1-reuse.json):

- **BidPilot** `3f7b7698f3ce81da8f6d2b617253151071e6340a`: its Pydantic `GapItem` rejects `unconfirmed` and `not_assessed` (R4–R6). Cited checklist structures are useful references, but M1 needs schema/evidence changes. Inspected turnover, lead-time and tag rules are not D1 policy; extraction tests mock the model.
- **RFPilot** `86567e59385332d0e9d26347e66e9ad4fd3e5b2a`: its actual Word generator produced six `Compliant` rows from the six D1 obligations without evidence. The inspected model service uses Anthropic and does not output page citations.

**Working choice:** keep the selected frontend/component backend; copy neither tender app into the application yet. These probes demonstrate incompatibilities, not lower total development cost. No whole-app adaptation/deployment benchmark or commercial-product trial was completed. Revisit a fork if measured adaptation work is lower. [Third-party notices](../../THIRD_PARTY.md).

## Database and remaining gate

The connector returned no Supabase projects. The read-only database check found no `DATABASE_URL`; [result](m1-database.json) is blocked. OpenAI configuration was supplied locally during the task and worked. Docker CLI exists but its daemon was stopped. No cloud project or database schema was created.

PgQueuer is installed, but no real job, process interruption/retry, transaction or deduplication check ran. Supply a dedicated development database connection (direct/session mode, not merely an HTTP key), then execute that experiment. See [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres). T0 and integrated M1 remain incomplete until that gate is resolved.

Next: complete the database/queue experiment, carry the requirement-drift regression into T3, then implement T1–T6. The harness/template do not supply authenticated review or version-bound decisions.

Implementation references: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Docling native pipeline](https://docling-project.github.io/docling/reference/pipeline_options/), pinned upstream source/licences and installed package interfaces. The JSON reports record actual execution.

## Final review and decisions

One independent read-only review found whitespace-only quotes could pass validation. The regression failed, then passed after rejecting empty normalised text. I also reclassified stale candidates after failed reruns and unenforced source revisions as important reproducibility issues: both regressions failed, were fixed, and passed with the full 13-test suite. All four stored real-model candidates were revalidated after the fixes; no paid reruns were needed. Pinned reuse probes and the fixture verifier were rerun successfully. No deferred minor code findings remain.

Scope rulings: this non-Git project was edited in place (no Git rollback yet); component reuse remains provisional (a cheaper fork could require replacement). The parent inspected model outputs and source support, while independent review covered context construction rather than the raw output/prompt semantics (remaining author blind spots require later human evaluation). Production identity/approval/persistence/security and queue recovery remain T1–T6 responsibilities; using this harness as an application would bypass those controls. Frontend correctness is established only for the 130 upstream tests, not tender screens. OCR/tables/complex DOCX and broad native stability remain unvalidated and may need another parser. Whole-app reuse economics and held-out accuracy remain unmeasured and could change the adoption choice. These boundaries are intentional, not successful acceptance checks.
