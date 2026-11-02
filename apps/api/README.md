# API and worker

The FastAPI application serves authenticated, workspace-scoped tender data and commands. A Python worker processes source files and background jobs. Supabase provides authentication, PostgreSQL and private source storage. User identity and roles come from the authenticated session and workspace membership, not the request body.

## Local setup

Run these commands from the repository root in WSL. Use a Linux environment outside the Windows checkout and set the same environment variable in each API, worker and test terminal:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.cache/tender-api-venv"
uv sync --frozen --project apps/api --python 3.12
```

Configure the root `.env` as described in [setup](../../SETUP.md). For a new development project, initialise the application migrations and private bucket:

```bash
uv run --directory apps/api python -m app.db
uv run --directory apps/api python -m app.m1.storage
```

These commands modify the configured database and Storage project. The migration command also installs/verifies the PgQueuer schema and records application migration hashes; do not apply the same migrations through another tool without reconciling migration history. The bucket command refuses an existing public bucket. Neither command runs automatically when the API starts.

Start the API and, in a separate terminal, the worker:

```bash
uv run --directory apps/api uvicorn app.main:app --host 127.0.0.1 --port 8765
uv run --directory apps/api python -m app.m1.jobs
```

The worker needs the same root environment and workflow flag as the API. Local endpoints include `/health`, `/docs` and authenticated `/api/v1/*`.

A new development account can be provisioned explicitly:

```bash
uv run --directory apps/api python -m app.provision --email YOUR_EMAIL
```

This creates an Auth account and workspace records. It saves credentials in ignored `evals/runs/local/development-sign-in.json` and does not send email. Keep the credentials private.

## Workflow

The default legacy workflow supports uploaded sources, cited assessments, company evidence, review tasks and attributed answers, a bounded assistant, human pursuit decisions and Markdown exports. History and existing assessments remain readable.

`QUALIFICATION_WORKFLOW_ENABLED` defaults to `false`. When enabled, new work uses bounded screening, with source coverage, cited findings, named human requests and version-bound preparation decisions. Opportunity suggestions are sourced from controlled imports or configured public notices; they are not proof that attachments were obtained. The API exposes bounded `/api/v1/review-cases` and `/api/v1/inbox-actions` reads. Screening cases and history remain readable after rollback, and cases already in screening cannot fall back to broad analysis.

Model calls require explicit model prices and applicable approved spending authority; enabling the workflow does not grant either. Preparation approval is a business decision and does not authorise provider spend. A source citation identifies its location; a person must still assess semantic support.

Tender intake accepts PDF, DOCX, DOC, XLSX and PPTX, with limits of 100 files, 20 MiB per file, 100 MiB per pack, 2,000 PDF pages and 20 million extracted characters. Legacy DOC extraction requires `antiword`. Scans, drawings and other unsupported visual content remain visible coverage gaps; native extraction is not OCR. See the [runtime rules](../../ARCHITECTURE.md#model-and-human-authority) and [product workflow](../../PRODUCT.md#preparation-journey) for behavior and limits.

A bid owner can delete a tender from the active workspace; documents and history are retained for recovery. There is no restore screen.

## Checks and generated types

```bash
uv run --project apps/api pytest apps/api/tests -q
uv run --directory apps/api python -m evals.export_openapi --check
```

The API test suite uses the configured development database and Storage, creates and removes its own fictional test records, and runs migration/bucket setup. Stop a development worker before running it so it cannot consume test jobs. Ordinary tests use controlled model responses rather than paid calls.

After changing API models or routes, regenerate the contract and browser types:

```bash
uv run --directory apps/api python -m evals.export_openapi
pnpm --dir apps/web api:types
uv run --directory apps/api python -m evals.export_openapi --check
```

See the [validation record](../../VALIDATION.md) for actual trial results and remaining evidence gaps.
