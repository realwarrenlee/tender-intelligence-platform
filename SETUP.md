# Development setup

Run commands from the repository root in WSL. The application needs Node 24, pnpm 10.34.8, Python 3.12, `uv`, and a Supabase project with PostgreSQL, Auth and private Storage. The API and worker use the same database and server configuration.

## Environment

For a fresh checkout, copy [.env.example](.env.example) to `.env` and fill it locally. Preserve an existing configured `.env`; do not overwrite it. The API, worker and frontend load the root file.

- `SUPABASE_URL` and `SUPABASE_SECRET_KEY` configure server access. `DATABASE_URL` is the PostgreSQL session-pooler connection; queue jobs require a persistent connection.
- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` configure browser sign-in. The older `VITE_` names are supported as migration aliases.
- `OPENAI_API_KEY`, `OPENAI_MODEL` and explicit `OPENAI_PRICES` are needed for authorised paid model work. Decisions classification also needs `OPENAI_DECISIONS_MODEL` and the additional price field described in `.env.example`.
- `QUALIFICATION_WORKFLOW_ENABLED` defaults to `false`. When enabled in the API and worker, new work uses bounded screening; legacy history remains readable. Changing the flag does not provision a budget or grant roles.
- `NOTICE_SOURCE_JOBS` defaults to an empty list. `API_ORIGIN` optionally changes the frontend's server-side API proxy target.

Keep server secrets out of browser variables and version control. A publishable key is intended for the browser; a Supabase secret key is not. If `OPENAI_API_KEY` is already exported in your shell, remove its blank entry from `.env`.

## Run locally

Follow the [API guide](apps/api/README.md) to install dependencies, prepare a development database and private bucket, and start the API and worker. Follow the [frontend guide](apps/web/README.md) to install and start Next.js. The setup commands for migrations and storage change the configured development project.

| Service | Address |
|---|---|
| Frontend | http://127.0.0.1:3000 |
| API | http://127.0.0.1:8765 |
| Interactive API schema | http://127.0.0.1:8765/docs |

A provisioned workspace membership and Supabase password account are required for sign-in. If a local development account has already been provisioned, its credentials may be stored in the ignored `evals/runs/local/development-sign-in.json`; keep that file private. The API guide documents the provisioning command for a new development account.
