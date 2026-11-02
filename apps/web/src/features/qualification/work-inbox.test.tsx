import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { createApi, type Actor, type Inbox } from './api'
import { WorkInbox } from './work-inbox'

const navigation = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => navigation }))

const item: Inbox['items'][number] = {
  schema_version: 'm1.v1',
  workspace_id: 'workspace',
  owner_user_id: 'owner',
  input_revision: 1,
  created_at: '2026-10-24T01:00:00Z',
  id: 'tender-1',
  title: 'Campus maintenance',
  buyer: 'Campus buyer',
  source_label: 'Reference A',
  closing_at: '2026-11-20T16:00:00+08:00',
  assessment_status: 'current',
  recommendation: 'hold',
  decision: null,
  next_action: 'Confirm Saturday staffing',
}
let cache: QueryClient
let commands: Array<Record<string, unknown>>
let fail: boolean
let networkFailures = 0
let interruptedSuffix: string | undefined
let removed: string[]
let deleteStatus: number
beforeEach(() => {
  fail = false
  networkFailures = 0
  interruptedSuffix = undefined
  commands = []
  removed = []
  deleteStatus = 200
  navigation.push.mockReset()
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        const path = String(_input)
        const body = JSON.parse(String(init.body))
        commands.push({ path, ...body })
        if (deleteStatus !== 200)
          return Response.json(
            {
              code: 'STALE_INPUT',
              message: 'Tender changed. Refresh and try again.',
            },
            { status: deleteStatus }
          )
        const id = path.split('/').at(-1)!
        removed.push(id)
        if (interruptedSuffix && networkFailures-- > 0)
          throw new TypeError('Interrupted deletion response')
        return Response.json({ schema_version: 'm1.v1', id, deleted: true })
      }
      if (init?.method === 'POST') {
        const path = String(_input)
        const body =
          init.body instanceof FormData
            ? {
                ...JSON.parse(String(init.body.get('metadata'))),
                filenames: init.body
                  .getAll('files')
                  .map((file) => (file as File).name),
              }
            : JSON.parse(String(init.body))
        commands.push({ path, ...body })
        if (
          interruptedSuffix &&
          path.endsWith(interruptedSuffix) &&
          networkFailures-- > 0
        )
          throw new TypeError('Interrupted analysis response')
        return Response.json({
          id: 'created-tender',
          input_revision: path.endsWith('/documents') ? 2 : 1,
        })
      }
      if (fail)
        return Response.json(
          { code: 'UNAVAILABLE', message: 'Inbox is unavailable.' },
          { status: 503 }
        )
      return Response.json({
        schema_version: 'm1.v1',
        items: [
          item,
          {
            ...item,
            id: 'tender-2',
            title: 'Office cleaning',
            source_label: 'Reference B',
          },
        ].filter((t) => !removed.includes(t.id)),
      } as Inbox)
    })
  )
})
afterEach(() => {
  cache.clear()
  vi.unstubAllGlobals()
})

function open(roles = ['bid_owner']) {
  return render(
    <QueryClientProvider client={cache}>
      <WorkInbox
        actor={{ user_id: 'owner', workspace_id: 'workspace', roles } as Actor}
        api={createApi(async () => 'test-token')}
      />
    </QueryClientProvider>
  )
}

it('filters real inbox rows by title or reference and retains detail links', async () => {
  const screen = await open()
  const campus = screen.getByRole('link', { name: /Campus maintenance/ })
  await expect.element(campus).toHaveAttribute('href', '/tenders/tender-1')
  await userEvent.fill(
    screen.getByRole('textbox', {
      name: 'Filter tenders by name or reference',
    }),
    'reference b'
  )
  await expect
    .element(screen.getByRole('link', { name: /Office cleaning/ }))
    .toBeVisible()
  await expect.element(campus).not.toBeInTheDocument()
})

it('creates, uploads and analyses a pack without asking for tender details', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'Create tender', exact: true })
  )
  await expect
    .element(screen.getByText('Drag files here to add them'))
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Tender title'))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByText('manual_upload', { exact: true }))
    .not.toBeInTheDocument()
  await userEvent.upload(screen.getByLabelText('Tender files'), [
    new File(['pack'], 'Campus maintenance.pdf', { type: 'application/pdf' }),
  ])
  await userEvent.click(
    screen.getByRole('button', { name: 'Analyse tender', exact: true })
  )
  await expect
    .poll(() => navigation.push.mock.calls[0]?.[0])
    .toBe('/tenders/created-tender')
  expect(commands.map((command) => command.path)).toEqual([
    '/api/v1/tenders',
    '/api/v1/tenders/created-tender/documents',
    '/api/v1/tenders/created-tender/analyses',
  ])
  expect(commands[0]).toMatchObject({
    title: 'Campus maintenance',
    source_label: 'manual_upload',
  })
  expect(commands[1]).toMatchObject({
    expected_input_revision: 1,
    filenames: ['Campus maintenance.pdf'],
  })
  expect(commands[2]).toMatchObject({ expected_input_revision: 2 })
  await expect
    .element(
      screen.getByRole('button', { name: 'Analyse tender', exact: true })
    )
    .toBeDisabled()
})

it.each(['/tenders', '/documents', '/analyses'])(
  'resumes an interrupted %s request without duplicating completed stages',
  async (suffix) => {
    interruptedSuffix = suffix
    networkFailures = 1
    const screen = await open()
    await userEvent.click(
      screen.getByRole('button', { name: 'Create tender', exact: true })
    )
    await userEvent.upload(screen.getByLabelText('Tender files'), [
      new File(['pack'], 'Campus.pdf', { type: 'application/pdf' }),
    ])
    await userEvent.click(
      screen.getByRole('button', { name: 'Analyse tender', exact: true })
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Retry same request' })
    )
    await expect
      .poll(() => navigation.push.mock.calls[0]?.[0])
      .toBe('/tenders/created-tender')
    expect(commands).toHaveLength(4)
    const retries = commands.filter((command) =>
      String(command.path).endsWith(suffix)
    )
    expect(retries).toHaveLength(2)
    expect(retries[0].client_request_id).toBe(retries[1].client_request_id)
    expect(retries[0].expected_input_revision).toBe(
      retries[1].expected_input_revision
    )
  }
)

it('can cancel a selected pack before creating any business record', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'Create tender', exact: true })
  )
  await userEvent.upload(screen.getByLabelText('Tender files'), [
    new File(['pack'], 'Campus.pdf', { type: 'application/pdf' }),
  ])
  await userEvent.click(
    screen.getByRole('button', { name: 'Cancel', exact: true })
  )
  await expect
    .element(screen.getByRole('heading', { name: 'Tenders', exact: true }))
    .toBeVisible()
  expect(commands).toHaveLength(0)
})

it('keeps creation controls hidden for reviewers', async () => {
  const screen = await open(['reviewer'])
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'Create tender', exact: true }))
    .not.toBeInTheDocument()
})

it('shows a failed inbox without claiming there are no tenders', async () => {
  fail = true
  const screen = await open()
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('Inbox is unavailable.')
  await expect
    .element(screen.getByText(/No tenders yet/))
    .not.toBeInTheDocument()
})

it('shows real assessment states in a read-only tender board with detail links', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'Board', exact: true })
  )
  await expect
    .element(screen.getByRole('region', { name: 'Tender board' }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .toHaveAttribute('href', '/tenders/tender-1')
  await expect
    .element(screen.getByRole('button', { name: /Record pursue/ }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('heading', { name: /Current assessment/ }))
    .toBeVisible()
})

it('requires confirmation and removes only the selected tender', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Delete Campus maintenance',
      exact: true,
    })
  )
  const dialog = screen.getByRole('dialog', { name: 'Delete tender?' })
  await expect
    .element(dialog.getByText('Campus maintenance', { exact: true }))
    .toBeVisible()
  expect(commands).toHaveLength(0)
  await userEvent.click(
    dialog.getByRole('button', { name: 'Cancel', exact: true })
  )
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .toBeVisible()
  expect(commands).toHaveLength(0)
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Delete Campus maintenance',
      exact: true,
    })
  )
  await userEvent.click(
    screen
      .getByRole('dialog')
      .getByRole('button', { name: 'Delete tender', exact: true })
  )
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('link', { name: /Office cleaning/ }))
    .toBeVisible()
  expect(commands[0]).toMatchObject({
    path: '/api/v1/tenders/tender-1',
    expected_input_revision: 1,
  })
})

it('keeps a changed tender visible when deletion fails', async () => {
  deleteStatus = 409
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Delete Campus maintenance',
      exact: true,
    })
  )
  await userEvent.click(
    screen
      .getByRole('dialog')
      .getByRole('button', { name: 'Delete tender', exact: true })
  )
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('Tender changed. Refresh and try again.')
  await userEvent.click(
    screen
      .getByRole('dialog')
      .getByRole('button', { name: 'Cancel', exact: true })
  )
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .toBeVisible()
})

it('retries an interrupted deletion with the same request and supports board deletion', async () => {
  interruptedSuffix = '/tender-1'
  networkFailures = 1
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'Board', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Delete Campus maintenance',
      exact: true,
    })
  )
  await userEvent.click(
    screen
      .getByRole('dialog')
      .getByRole('button', { name: 'Delete tender', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same request' })
  )
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .not.toBeInTheDocument()
  expect(commands).toHaveLength(2)
  expect(commands[0]).toEqual(commands[1])
})

it('hides deletion controls from viewers', async () => {
  const screen = await open(['viewer'])
  await expect
    .element(screen.getByRole('link', { name: /Campus maintenance/ }))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Delete Campus maintenance',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
})

it('saves enabled-workflow intake sources without starting a model run', async () => {
  const previous = globalThis.fetch
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => {
    if (!init?.method && /\/review-cases|\/members/.test(String(input)))
      return Promise.resolve(Response.json({ items: [], next_cursor: null }))
    return previous(input, init)
  })
  const screen = await render(
    <QueryClientProvider client={cache}>
      <WorkInbox
        actor={{
          user_id: 'owner',
          workspace_id: 'workspace',
          roles: ['bid_owner'],
          qualification_workflow_enabled: true,
        }}
        api={createApi(async () => 'test-token')}
      />
    </QueryClientProvider>
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Create tender', exact: true })
  )
  await userEvent.upload(screen.getByLabelText('Tender files'), [
    new File(['pack'], 'Campus.pdf', { type: 'application/pdf' }),
  ])
  await userEvent.click(
    screen.getByRole('button', { name: 'Save sources', exact: true })
  )
  await expect
    .poll(() => navigation.push.mock.calls.at(-1)?.[0])
    .toBe('/tenders/created-tender')
  expect(commands.map((command) => command.path)).toEqual([
    '/api/v1/tenders',
    '/api/v1/tenders/created-tender/documents',
  ])
})
