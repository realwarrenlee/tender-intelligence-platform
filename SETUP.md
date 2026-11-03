# Development setup

Use Node 24, pnpm 10.34.8, Python 3.12, `uv`, and a development Supabase project with PostgreSQL, Auth and private Storage. On Windows, the documented API and worker setup uses WSL. If you run the tools in WSL, keep the checkout under your Linux home directory (for example, `~/projects`). [WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems)

## Environment

For a fresh checkout, copy [`.env.example`](.env.example) to `.env` at the repository root. Keep an existing configured file. Fill in the Supabase server and browser values and the PostgreSQL session-pooler URL. The API, worker and frontend share this file. Keep server secrets private.

For optional GeBIZ discovery, enable Qualification and configure an enabled `NOTICE_SOURCE_JOBS` entry with an active intake owner for each workspace. The [environment template](.env.example) gives the fields and listing URL. The intake owner or a workspace admin can toggle scans in **Inbox → Agent**.

## Run locally

On Windows, use Ubuntu WSL for all three terminals. This checkout's frontend dependencies are installed in WSL.

For first-time setup, follow the [API and worker guide](apps/api/README.md#local-setup) to install dependencies, apply migrations, set up private storage and provision a sign-in. Install the frontend dependencies using the [frontend guide](apps/web/README.md#run-locally).

Open separate terminals for the API and worker. If you use the cached WSL environment, also run `export UV_PROJECT_ENVIRONMENT="$HOME/.cache/tender-api-venv"` in both terminals.

```bash
# API
cd apps/api
uv run uvicorn app.main:app --port 8765

# Worker
cd apps/api
uv run python -m app.tenders.jobs
```

In a third WSL terminal, run this from the repository root.

```bash
cd apps/web
npm run dev
```

If `node_modules` is linked outside the project, use `npm run dev -- --webpack` in `apps/web`.

Open the [workspace](http://127.0.0.1:3000) and sign in. The [API docs](http://127.0.0.1:8765/docs) are on port 8765.

## Controlled Preparation tracking

Use a disposable development database with all migrations applied through the API guide. Enable `QUALIFICATION_WORKFLOW_ENABLED=true` and `PREPARATION_TRACKING_ENABLED=true`, then open a tender with current preparation approval. To test Submission, also set `SUBMISSION_CONTROL_ENABLED=true` and accept both deliverables. Restart the API and worker after changing flags.

For proposal drafting, add a line in Company evidence in the form `Proposal reuse | Legal entity | Approved wording` and accept that version before screening. Set the same bidding entity and link requirements in the Technical response plan. The assigned owner can then generate a Word draft.

Paid model calls require approved spending and explicit model settings and prices in [`.env.example`](.env.example).
