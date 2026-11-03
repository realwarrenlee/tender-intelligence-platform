import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/app/globals.css'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent, page } from 'vitest/browser'
import { createApi } from './api'
import { opportunity, owner } from './test-fixtures/screening'
import { WorkspaceInbox } from './workspace-activity'

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  search: '',
}))
vi.mock('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(navigation.search),
}))
const responsive = vi.hoisted(() => ({ mobile: false }))
vi.mock('@/hooks/use-mobile', () => ({
  useIsMobile: () => responsive.mobile,
}))
let cache: QueryClient
let commands: Array<{ path: string; body: Record<string, unknown> }>
let failOnce: boolean
let suggestions: ReturnType<typeof opportunity>[]
let scanEnabled: boolean
beforeEach(() => {
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  document.documentElement.classList.add('dark')
  commands = []
  failOnce = false
  responsive.mobile = false
  suggestions = [opportunity()]
  scanEnabled = true
  navigation.search = 'tab=agent'
  navigation.push.mockReset()
  navigation.replace.mockReset()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path.endsWith('/opportunity-discovery')) {
        if (init?.method === 'PUT') {
          const body = JSON.parse(String(init.body))
          commands.push({ path, body })
          scanEnabled = body.enabled
        }
        return Response.json({
          configured: true,
          enabled: scanEnabled,
          can_edit: true,
        })
      }
      if (path.endsWith('/members'))
        return Response.json({
          items: [
            {
              user_id: 'teammate',
              display_name: 'Teammate',
              roles: ['member'],
            },
          ],
        })
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        commands.push({ path, body })
        if (failOnce) {
          failOnce = false
          throw new TypeError('Interrupted')
        }
        return Response.json({
          ...opportunity(),
          state: 'activated',
          tender_id: 'tender-1',
        })
      }
      if (path.includes('/opportunity-suggestions'))
        return Response.json({ items: suggestions, next_cursor: null })
      if (path.includes('/inbox-actions') || path.endsWith('/tenders'))
        return Response.json({ items: [], next_cursor: null })
      return Response.json({ items: [] })
    })
  )
})
afterEach(() => {
  cache.clear()
  document.documentElement.classList.remove('dark')
  vi.unstubAllGlobals()
})
async function mount() {
  return render(
    <QueryClientProvider client={cache}>
      <div
        className='h-dvh bg-container'
        style={{ fontFamily: 'Arial, sans-serif' }}
      >
        <WorkspaceInbox actor={owner} api={createApi(async () => 'test')} />
      </div>
    </QueryClientProvider>
  )
}
it('opens the selected Agent suggestion beside its list', async () => {
  const second = opportunity()
  second.id = 'second'
  second.notice.title = 'Office cleaning'
  second.notice.evidence_text = 'Cleaning notice evidence'
  suggestions.push(second)
  const screen = await mount()
  const list = screen.getByRole('region', { name: 'Opportunity suggestions' })
  const detail = screen.getByRole('article', { name: 'Campus maintenance' })
  await expect.element(detail).toBeVisible()
  await userEvent.click(list.getByRole('button', { name: 'Office cleaning' }))
  await expect.element(detail).not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('article', { name: 'Office cleaning' }))
    .toBeVisible()
})

it('shows an Agent list on mobile and returns to it from a suggestion', async () => {
  responsive.mobile = true
  const screen = await mount()
  await expect
    .element(screen.getByRole('article', { name: 'Campus maintenance' }))
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Campus maintenance' })
  )
  await expect
    .element(screen.getByRole('article', { name: 'Campus maintenance' }))
    .toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Back to list' }))
  await expect
    .element(screen.getByRole('button', { name: 'Campus maintenance' }))
    .toBeVisible()
})

it('shows the Agent empty queue with an empty detail prompt', async () => {
  suggestions = []
  const screen = await mount()
  await expect
    .element(screen.getByText('No suggested opportunities assigned to you.'))
    .toBeVisible()
  await expect
    .element(screen.getByText('Select a suggestion to view its details.'))
    .toBeVisible()
})

it('shows the Agent queue without a status filter, like the Human inbox', async () => {
  const screen = await mount()
  await expect
    .element(screen.getByRole('button', { name: 'Campus maintenance' }))
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Suggestion status'))
    .not.toBeInTheDocument()
})
it('shows sourced Agent suggestions and uses one activation identity after an interrupted result', async () => {
  failOnce = true
  suggestions[0].budget_status = 'not_approved'
  suggestions[0].budget_id = null
  const screen = await mount()
  await expect
    .element(screen.getByRole('tab', { name: 'Agent', exact: true }))
    .toHaveAttribute('data-state', 'active')
  await expect
    .element(screen.getByText('Attachments not obtained', { exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByText('Controlled import', { exact: true }))
    .toBeVisible()
  await page.screenshot({
    path: '../../../../../output/implementation/bid-qualification-2026-11-01/task-5-agent-desktop.png',
  })
  await userEvent.click(
    screen.getByRole('button', { name: 'Start assessment', exact: true })
  )
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('outcome is unknown')
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same request', exact: true })
  )
  await expect
    .poll(() => navigation.push.mock.calls[0]?.[0])
    .toBe('/tenders/tender-1')
  expect(commands).toHaveLength(2)
  expect(commands[0].body).toEqual(commands[1].body)
  expect(commands[0].body).toMatchObject({
    action: 'start_assessment',
    expected_revision: 1,
  })
  expect(commands.some((c) => /analyses|screenings/.test(c.path))).toBe(false)
})
it('turns off the daily GeBIZ scan from the Agent Inbox', async () => {
  const screen = await mount()
  const toggle = screen.getByRole('switch', { name: 'Daily GeBIZ scan' })
  await expect.element(toggle).toHaveAttribute('aria-checked', 'true')
  await userEvent.click(toggle)
  await expect.element(toggle).toHaveAttribute('aria-checked', 'false')
  expect(commands[0]).toMatchObject({ body: { enabled: false } })
})

it('forwards a notice and a question to a teammate without starting an assessment', async () => {
  const screen = await mount()
  await userEvent.click(screen.getByRole('button', { name: 'Ask for input' }))
  await userEvent.selectOptions(screen.getByLabelText('Teammate'), 'teammate')
  await userEvent.fill(
    screen.getByLabelText('Question'),
    'Have we worked with this buyer?'
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))
  await expect
    .element(screen.getByText('Request sent to your teammate’s Human Inbox.'))
    .toBeVisible()
  expect(commands).toHaveLength(1)
  expect(commands[0].path).toMatch(
    /\/opportunity-suggestions\/[^/]+\/feedback$/
  )
  expect(commands[0].body).toMatchObject({
    recipient_id: 'teammate',
    question: 'Have we worked with this buyer?',
    expected_revision: 1,
  })
  expect(navigation.push).not.toHaveBeenCalled()
})

it('keeps Human and Agent tab choice in a local shareable URL', async () => {
  const screen = await mount()
  await userEvent.click(screen.getByRole('tab', { name: 'Human', exact: true }))
  expect(navigation.replace).toHaveBeenCalledWith('/inbox?tab=human', {
    scroll: false,
  })
  await expect
    .element(screen.getByText('No actions assigned to you.', { exact: true }))
    .toBeVisible()
})
