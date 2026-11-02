import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/circle/globals.css'
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
vi.mock('@/circle/hooks/use-mobile', () => ({ useIsMobile: () => false }))
let cache: QueryClient
let commands: Array<{ path: string; body: Record<string, unknown> }>
let failOnce: boolean
beforeEach(() => {
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  document.documentElement.classList.add('dark')
  commands = []
  failOnce = false
  navigation.search = 'tab=agent'
  navigation.push.mockReset()
  navigation.replace.mockReset()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
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
        return Response.json({ items: [opportunity()], next_cursor: null })
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
it('shows sourced Agent suggestions and uses one activation identity after an interrupted result', async () => {
  failOnce = true
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
