# PUB screening review set

These are **unlabelled review candidates**, selected deterministically from the saved native PUB sources. They are not gold answers, model-quality evidence, or the earlier 488 generated requirements.

There are 24 development examples and 24 held-out examples. Every example has an exact native source reference and quote. Candidate source hashes are separated across splits; a human must still check for repeated clause families across different files. No domain reviewer is assigned. The workspace user is not required to label tender examples. Codex has prepared a separate, source-grounded provisional review of the 24 development candidates; it is development material, not independent validation. See research and self-review (local only).

The following labels are for internal evaluation, not an app onboarding task. An appropriately qualified reviewer can later review development examples and establish an independent evaluation set. For each excerpt, record:
- **Kind:** entry/eligibility condition, scored criterion, bid document/artifact, delivery commitment, information, or unsure.
- **Due:** submission, award, mobilisation, delivery, or unsure.
- **Material now:** does this establish a material gate/risk for the preparation decision now? Yes, no, or unsure.

“Unsure” maps to `unknown`. Do not turn a future delivery obligation into proof that work must already be complete. An inaccessible or partial source is a gap, rather than a proven failure.

The benchmark labels remain null until independent review. Agent proposals stay in a separate artifact. The research inspected the evaluation document used by PUB-29; if this informs tuning, re-establish an independent evaluation set before claiming held-out quality. Do not tune questions on held-out answers. Before a live evaluation, a reviewer must confirm separate clause families and at least eight critical, eight benign/scored/delivery, and eight ambiguous examples in each split; candidates may need replacing to achieve that balance.

Offline check (no provider calls):

```bash
UV_PROJECT_ENVIRONMENT=/home/warren/.cache/tender-api-t3-venv uv run --no-sync --project apps/api python evals/run_decisions_screening.py
```

Live mode additionally requires the explicit flag, a real actor/workspace scope and an already-approved persisted budget capped at US$1 and 60 cumulative requests. The harness grants no budget, retries no uncertain call and stops on a missed critical gate.

## Task 6 source audit

[task-6-scenario.json](task-6-scenario.json) adds 18 agent-provisional known-source checks, including 11 critical checks sharing four native pages. It leaves all 48 original benchmark labels null.

The audit uses the actual bounded context/retrieval/Company code and saved immutable native index. Only index creation is replaced with that existing index. Database work is rolled back; no job, business decision, model client or paid authority is created. A separate public-notice check concerns PA, never PUB.

Run from the repository root: `UV_PROJECT_ENVIRONMENT=/home/warren/.cache/tender-api-t3-venv uv run --no-sync --project apps/api python evals/run_pub_source_audit.py --output output/implementation/bid-qualification-2026-11-01/task-6-retrieval-audit.json`.

Exact expected text supplied to the reasoner measures evidence delivery, not model critical-gate recall. Oracle-informed searches are a diagnostic, not a default-product/held-out result. Model accuracy, unsupported-claim and human-effort measures stay null. The original offline benchmark's zero critical-miss counter with zero evaluated examples does not mean zero model misses.

See Task 6 result (local only) and [comparison protocol](../../../../VALIDATION.md). Task 6 remains in progress; improve default evidence selection before a paid trial/pilot.

Retrieval repair (local only) raises the declared development critical-span delivery from 0/11 to 11/11 without changing coverage/approval/spending limits. The evaluator also preflights the real reasoner byte guard with no model configured; no inference/client/reservation follows. Original baseline artifacts are preserved. This remains development evidence, not model or human-outcome validation.
