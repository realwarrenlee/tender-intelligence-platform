# Tender Intelligence Platform

A tender qualification workspace for the CBM challenge. The prototype combines a Next.js frontend, a FastAPI application and worker, and Supabase authentication, PostgreSQL and private source storage.

## Current state

The authenticated workspace supports tender intake, source review, company evidence, assigned review tasks, decisions and history. The newer bounded screening workflow adds source-backed preparation briefs, team Reviews, Human and Agent Inbox views, and preparation decisions. It is controlled by `QUALIFICATION_WORKFLOW_ENABLED`, which defaults to `false`; the configured value determines which workflow is available. Existing legacy assessments and history remain readable.

All the tasks of the qualification workspace plan have been implemented and checked. Task 6 included one authorised real PUB screening: its recovered and reviewed draft contains 12 unconfirmed findings, and total settled provider usage was US$0.0803868. The trial's spending authority is closed and paused. Follow-up transport and output-contract fixes were verified offline. Independent assessment of screening quality, representative acceptance and equivalent manual versus assisted effort remain open; this is not evidence of pilot readiness. See the reliability result (local only) and [validation record](VALIDATION.md).

## Get started

Work in WSL. Follow [setup](SETUP.md), then the [API and worker guide](apps/api/README.md) and [frontend guide](apps/web/README.md). The frontend runs at http://127.0.0.1:3000 and redirects to the authenticated tender workspace. The API defaults to port 8765.

## Repository layout

| Folder | Contents |
| --- | --- |
| `apps/` | Frontend, API, worker and their tests |
| `contracts/` | Output schemas and generated API contract |
| `supabase/migrations/` | Applied database history; retain existing migrations |
| `evals/` | Fixtures, answer keys, checks and run records |

## Project reference

- [Product direction](PRODUCT.md) and [challenge brief](BRIEF.md)
- [Architecture and runtime rules](ARCHITECTURE.md)
- [Validation and outstanding gates](VALIDATION.md)
- [Company reference](COMPANY.md)
