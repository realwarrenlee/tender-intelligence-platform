import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { AppSidebar } from '@/components/layout/sidebar/app-sidebar'
import { SidebarProvider } from '@/components/ui/sidebar'
import { createApi } from './api'
import {
  reviewCase as screeningCase,
  owner as screeningOwner,
  members as screeningMembers,
} from './test-fixtures/screening'
import { Oversight } from './workspace-activity'

const session = vi.hoisted(() => ({
  signOut: vi.fn(async () => {}),
  actor: {
    user_id: 'reviewer',
    workspace_id: 'workspace',
    roles: ['member'],
  },
  session: {
    user: {
      email: 'warren.lee@example.com',
      user_metadata: { full_name: 'Warren Lee' },
    },
  },
}))
vi.mock('@/features/workspace/session', () => ({
  useSession: () => session,
}))
vi.mock('next/navigation', () => ({
  usePathname: () => '/inbox',
  useRouter: () => ({ push: vi.fn() }),
}))
const responsive = vi.hoisted(() => ({ mobile: false }))
vi.mock('@/hooks/use-mobile', () => ({
  useIsMobile: () => responsive.mobile,
}))
let cache: QueryClient
const api = createApi(async () => 'test-token')
beforeEach(() => {
  responsive.mobile = false
  session.signOut.mockClear()
  Object.assign(session, { api })
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Response.json({ items: screeningMembers }))
  )
})
afterEach(() => {
  cache.clear()
  vi.unstubAllGlobals()
})
function wrap(children: React.ReactNode) {
  return render(
    <QueryClientProvider client={cache}>{children}</QueryClientProvider>
  )
}
it('shows CBM branding, fixed navigation and a static name-only profile with real logout', async () => {
  const screen = await wrap(
    <SidebarProvider>
      <AppSidebar />
    </SidebarProvider>
  )
  await expect
    .element(screen.getByText('CBM Tender', { exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('link', { name: 'Oversight', exact: true }))
    .toHaveAttribute('href', '/oversight')
  await expect
    .element(screen.getByRole('link', { name: 'Settings', exact: true }))
    .toHaveAttribute('href', '/settings')
  await expect
    .element(screen.getByText('Warren Lee', { exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByText('warren.lee@example.com', { exact: true }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByText('More', { exact: true }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: /Warren Lee/ }))
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Log out', exact: true })
  )
  expect(session.signOut).toHaveBeenCalledOnce()
})

it('shows overdue and upcoming team work and links to the action without opening a second tender review', async () => {
  const first = screeningCase()
  first.permitted_actions = []
  first.next_action = {
    label: 'Review pricing workbook',
    assignee_id: 'owner',
    due_at: '2000-01-01T12:00:00+08:00',
    section: 'preparation',
    task_id: 'pricing',
  }
  const second = {
    ...screeningCase(),
    tender_id: 'tender-2',
    title: 'Another team case',
    permitted_actions: [],
    next_action: {
      label: 'Confirm staffing coverage',
      assignee_id: 'owner',
      due_at: null,
      section: 'questions',
      task_id: 'staffing',
    },
  }
  const reads: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      reads.push(path)
      if (path.includes('/review-cases?'))
        return Response.json(
          path.includes('after=')
            ? { items: [second], next_cursor: null }
            : { items: [first], next_cursor: 'tender-1' }
        )
      if (path.endsWith('/members'))
        return Response.json({ items: screeningMembers })
      throw new Error('Unexpected unbounded read: ' + path)
    })
  )
  const screen = await wrap(
    <Oversight
      api={api}
      actor={{ ...screeningOwner, user_id: 'viewer', roles: ['viewer'] }}
    />
  )
  await expect
    .element(
      screen.getByRole('link', {
        name: /Campus maintenance.*Review pricing workbook/,
      })
    )
    .toHaveAttribute(
      'href',
      '/tenders/tender-1?section=preparation&task=pricing'
    )
  await userEvent.click(
    screen.getByRole('tab', { name: 'Upcoming', exact: true })
  )
  await expect
    .element(
      screen.getByRole('link', {
        name: /Another team case.*No internal deadline/,
      })
    )
    .toHaveAttribute(
      'href',
      '/tenders/tender-2?section=questions&task=staffing'
    )
  expect(
    reads.some((path) => path.endsWith('/tenders') || path.endsWith('/history'))
  ).toBe(false)
  expect(reads.filter((path) => /\/tenders\/[^/]+$/.test(path))).toEqual([])
  await expect
    .element(
      screen.getByRole('button', { name: 'Assign request', exact: true })
    )
    .not.toBeInTheDocument()
})
