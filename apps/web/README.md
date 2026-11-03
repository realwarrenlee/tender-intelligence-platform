# Web workspace

The frontend uses Next.js App Router, React, the retained Circle desktop shell, Supabase browser sessions and TanStack Query. It connects to the FastAPI backend; the original Circle demo data and screens have been removed.

## Run locally

Use Node 24 and pnpm 10.34.8 from the repository root:

```bash
pnpm --dir apps/web install --frozen-lockfile
cd apps/web
npm run dev
```

Open http://127.0.0.1:3000. The root redirects to `/tenders`, where sign-in is required. Start the [API and worker](../api/README.md) separately.

The frontend reads the root `.env`. `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` configure sign-in; older `VITE_` equivalents are supported as migration aliases. `API_ORIGIN` sets the server-side API proxy target, which defaults to http://127.0.0.1:8765. See [setup](../../SETUP.md).

If an existing WSL checkout links `node_modules` outside the project, Turbopack cannot resolve those dependencies with the default configuration. Use the [Webpack start command](../../SETUP.md#run-locally) for that layout. [Turbopack root directory](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack#root-directory)

## Navigation and behavior

Workspace routes are `/tenders`, `/tenders/[tenderId]`, `/inbox`, `/reviews`, `/members`, `/company` and `/settings`. Existing legacy assessments, sources, decisions and history remain accessible.

The server's `QUALIFICATION_WORKFLOW_ENABLED` flag defaults to false. When enabled, Inbox provides Human and Agent tabs; Reviews shows bounded team cases; and the shared tender provides Qualification and Sources views, with grouped requirements, review requests and the existing preparation decision. The qualification overview leads with the recommendation, blockers and next actor; exact coverage gaps and usage are expandable. Buyer, reference, scope, contract period and sites show cited exact extracts labelled `Extracted · verify against sources`, or explicit unknowns for missing values and older briefs. Links open the existing source pane and preserve decision drafts. Generated API types describe this optional persisted summary; legacy analysis/notice values are not used to fill it. With the flag off, legacy list, review and assessment behavior remains available. The frontend reads the flag from the API; it does not grant roles, budgets or model-spending authority.

New Qualification briefs show source-linked questions for missing or conflicting context, with confirmed reviewer/deadline or a suggested team explicitly marked unassigned. Stage-aware work rows distinguish conditional preparation work and future duties; the decision form uses server-derived required condition IDs, retaining the conservative legacy fallback. Extraction counts and status remain in the existing expandable diagnostics. These additions use the current theme, components, confirmation dialog and source pane; rendering does not assign, enqueue or approve work.

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
