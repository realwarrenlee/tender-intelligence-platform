# Web workspace

The frontend uses Next.js App Router, React, the retained Circle desktop shell, Supabase browser sessions and TanStack Query. It connects to the FastAPI backend; the original Circle demo data and screens have been removed.

## Run in WSL

Use Node 24 and pnpm 10.34.8 from the repository root:

```bash
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web dev
```

Open http://127.0.0.1:3000. The root redirects to `/tenders`, where sign-in is required. Start the [API and worker](../api/README.md) separately.

The frontend reads the root `.env`. `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` configure sign-in; older `VITE_` equivalents are supported as migration aliases. `API_ORIGIN` sets the server-side API proxy target, which defaults to http://127.0.0.1:8765. See [setup](../../SETUP.md).

## Navigation and behavior

Workspace routes are `/tenders`, `/tenders/[tenderId]`, `/inbox`, `/reviews`, `/members`, `/company` and `/settings`. Existing legacy assessments, sources, decisions and history remain accessible.

The server's `QUALIFICATION_WORKFLOW_ENABLED` flag defaults to false. When enabled, Inbox provides Human and Agent tabs; Reviews shows bounded team cases; and the shared review includes the screening brief, sources and preparation decision. With the flag off, legacy list, review and assessment behavior remains available. The frontend reads the flag from the API; it does not grant roles, budgets or model-spending authority.

## Verify

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
pnpm --dir apps/web knip
pnpm --dir apps/web format:check
pnpm --dir apps/web build
```

Browser tests use controlled responses. On the existing WSL Ubuntu 26 setup, the installed Chromium may require `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64`.

For route and proxy checks:

```bash
pnpm --dir apps/web start
pnpm --dir apps/web check:routes
pnpm --dir apps/web check:proxy
```

`start` requires a production build; run the route check in a separate terminal with the frontend and API running. The proxy check starts its own isolated frontend and mock API, with no model calls. For contract changes, regenerate the OpenAPI file and browser types using the [API guide](../api/README.md).

## Attribution

See the [Circle adaptation record](licenses/README.md), [Circle notice](licenses/circle-MIT.txt), [shadcn-admin notice](LICENSE), [notice index](licenses/README.md) and [dependency inventory](licenses/README.md).
