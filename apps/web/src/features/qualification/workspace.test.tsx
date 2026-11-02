import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppSidebar } from '@/circle/components/layout/sidebar/app-sidebar'
import { SidebarProvider } from '@/circle/components/ui/sidebar'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { createApi, type Actor, type Tender, type Task } from './api'
import { tenderFixture, taskFixture } from './test-fixtures/review'
import {
  reviewCase as screeningCase,
  boundedTender,
  owner as screeningOwner,
  members as screeningMembers,
} from './test-fixtures/screening'
import { WorkspaceInbox, ReviewWork } from './workspace-activity'

const session = vi.hoisted(() => ({
  signOut: vi.fn(async () => {}),
  actor: {
    user_id: 'reviewer',
    workspace_id: 'workspace',
    roles: ['service_reviewer'],
  },
  session: {
    user: {
      email: 'warren.lee@example.com',
      user_metadata: { full_name: 'Warren Lee' },
    },
  },
}))
vi.mock('@/features/qualification/session', () => ({
  useSession: () => session,
}))
vi.mock('next/navigation', () => ({
  usePathname: () => '/inbox',
  useRouter: () => ({ push: vi.fn() }),
}))
const responsive = vi.hoisted(() => ({ mobile: false }))
vi.mock('@/circle/hooks/use-mobile', () => ({
  useIsMobile: () => responsive.mobile,
}))
let cache: QueryClient
const api = createApi(async () => 'test-token')
let failDetail = false
let tenders: Tender[]
let commands: Array<{ path: string; body: Record<string, unknown> }>
function decision(tender: Tender, choice: 'pursue' | 'hold' | 'decline') {
  return {
    schema_version: 'm1.v1' as const,
    id: 'decision-' + tender.id,
    tender_id: tender.id,
    actor_id: 'approver',
    assessment_version_id: tender.assessment!.id,
    input_revision: tender.input_revision,
    decision: choice,
    reason: 'Reviewed the evidence.',
    review_complete: true,
    is_current: true,
    currency_reason: null,
    created_at: '2026-10-26T01:00:00Z',
    manifest: {},
  }
}
function answer(): NonNullable<Task['answer']> {
  return {
    id: 'answer',
    evidence_version_id: 'answer-evidence',
    actor_id: 'reviewer',
    created_at: '2026-10-26T01:00:00Z',
    text: 'Confirmed from the staffing roster.',
    response_kind: 'confirmed',
    basis: null,
    reassessment_job_id: 'reassessment',
    reassessment_status: 'queued',
  }
}
beforeEach(() => {
  responsive.mobile = false
  failDetail = false
  commands = []
  session.signOut.mockClear()
  Object.assign(session, { api })
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const one = structuredClone(tenderFixture) as unknown as Tender
  one.id = 'one'
  one.title = 'Campus maintenance'
  one.assessment!.candidate.key_facts.title.value = one.title
  one.assessment!.id = 'assessment-one'
  one.review_tasks = [
    {
      ...structuredClone(taskFixture),
      id: 'assigned',
      tender_id: 'one',
      created_by: 'reviewer',
      assessment_version_id: 'assessment-one',
      assignee_id: 'reviewer',
      question: 'Can Saturday staffing be confirmed?',
      is_current: false,
    },
    {
      ...structuredClone(taskFixture),
      id: 'second',
      tender_id: 'one',
      created_by: 'reviewer',
      assessment_version_id: 'assessment-one',
      assignee_id: 'reviewer',
      question: 'Can mobilisation be confirmed?',
      is_current: true,
    },
    {
      ...structuredClone(taskFixture),
      id: 'other',
      tender_id: 'one',
      created_by: 'owner',
      assessment_version_id: 'assessment-one',
      assignee_id: 'other',
      question: 'Question for another reviewer',
      is_current: true,
    },
  ] as Task[]
  const two = structuredClone(one)
  two.id = 'two'
  two.title = 'Completed tender'
  two.assessment!.id = 'assessment-two'
  two.assessment!.candidate.key_facts.title.value = two.title
  two.review_tasks = [
    {
      ...two.review_tasks[0],
      id: 'answered',
      tender_id: 'two',
      status: 'answered',
      created_by: 'owner',
      answer: answer(),
    },
  ]
  two.decision = decision(two, 'hold')
  const three = structuredClone(one)
  three.id = 'three'
  three.title = 'Closed tender'
  three.assessment!.id = 'assessment-three'
  three.assessment!.candidate.key_facts.title.value = three.title
  three.review_tasks = [
    {
      ...three.review_tasks[0],
      id: 'cancelled',
      tender_id: 'three',
      status: 'cancelled',
      created_by: 'owner',
    },
  ]
  three.decision = decision(three, 'decline')
  const four = structuredClone(one)
  four.id = 'four'
  four.title = 'Unanalysed tender'
  four.assessment = null
  four.assessment_status = 'not_ready'
  four.review_tasks = []
  tenders = [one, two, three, four]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (init?.method && init.method !== 'GET') {
        const body = JSON.parse(String(init.body))
        commands.push({ path, body })
        if (path.endsWith('/answers')) {
          const task = tenders
            .flatMap((t) => t.review_tasks)
            .find((t) => path.includes('/' + t.id + '/'))!
          task.status = 'answered'
          task.answer = { ...answer(), text: body.text }
        }
        if (path.endsWith('/decisions')) {
          const tender = tenders.find((t) =>
            path.endsWith('/' + t.id + '/decisions')
          )!
          tender.decision = {
            ...decision(tender, body.decision),
            reason: body.reason,
          }
        }
        return Response.json({ id: 'saved' })
      }
      if (path.endsWith('/members'))
        return Response.json({
          schema_version: 'm1.v1',
          items: [
            {
              user_id: 'reviewer',
              display_name: 'Warren Lee',
              roles: ['service_reviewer'],
            },
            {
              user_id: 'owner',
              display_name: 'Tender owner',
              roles: ['bid_owner'],
            },
          ],
        })
      if (path.endsWith('/tenders'))
        return Response.json({
          schema_version: 'm1.v1',
          items: tenders.map((t) => ({
            ...t,
            buyer: 'Campus buyer',
            closing_at: '2026-11-20T16:00:00+08:00',
            recommendation:
              t.assessment?.candidate.recommendation.decision || null,
            next_action: 'Confirm Saturday staffing',
          })),
        })
      if (path.endsWith('/sources'))
        return Response.json({
          schema_version: 'm1.v1',
          assessment_version_id: 'assessment-one',
          anchors: [],
        })
      if (path.endsWith('/history')) {
        const tender = tenders.find((t) =>
          path.endsWith('/' + t.id + '/history')
        )!
        return Response.json({
          schema_version: 'm1.v1',
          assessments: tender.assessment
            ? [
                {
                  id: tender.assessment.id,
                  input_revision: tender.input_revision,
                  created_at: '2026-10-26T02:00:00Z',
                  created_by: 'owner',
                  is_current: tender.assessment.is_current,
                },
              ]
            : [],
          decisions: tender.decision ? [tender.decision] : [],
        })
      }
      const tender = tenders.find((t) => path.endsWith('/tenders/' + t.id))
      if (tender) {
        if (failDetail)
          return Response.json(
            { code: 'UNAVAILABLE', message: 'Review is unavailable.' },
            { status: 503 }
          )
        return Response.json(tender)
      }
      return Response.json({})
    })
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
    .element(screen.getByRole('link', { name: 'Reviews', exact: true }))
    .toHaveAttribute('href', '/reviews')
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

it('shows separate assigned-question updates with one contextual answer in Inbox', async () => {
  const screen = await wrap(
    <WorkspaceInbox api={api} actor={session.actor as Actor} />
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Question assigned · Campus maintenance · Can Saturday staffing be confirmed?',
      exact: true,
    })
  )
  await expect
    .element(
      screen.getByRole('heading', {
        name: 'Can Saturday staffing be confirmed?',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('link', { name: 'Open review', exact: true }))
    .toHaveAttribute('href', '/tenders/one')
  expect(screen.getByLabelText('Your answer').elements()).toHaveLength(1)
  await expect
    .element(screen.getByRole('table', { name: 'Requirements and findings' }))
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Review source documents',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', { name: /Question for another reviewer/ })
    )
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Question assigned · Campus maintenance · Can mobilisation be confirmed?',
        exact: true,
      })
    )
    .toBeVisible()
  await userEvent.fill(
    screen.getByLabelText('Your answer'),
    'Confirmed from the staffing roster.'
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Save answer and reassess',
      exact: true,
    })
  )
  expect(commands[0].path).toBe('/api/v1/review-tasks/assigned/answers')
  expect(commands[0].body).toMatchObject({
    expected_task_revision: 1,
    response_kind: 'confirmed',
    text: 'Confirmed from the staffing roster.',
  })
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Question assigned · Campus maintenance · Can Saturday staffing be confirmed?',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
})

it('shows real assessment and answer updates for the owner without duplicating the full review', async () => {
  tenders[0].review_tasks[0].status = 'answered'
  tenders[0].review_tasks[0].answer = answer()
  tenders[0].review_tasks[0].created_by = 'owner'
  const screen = await wrap(
    <WorkspaceInbox
      api={api}
      actor={
        { ...session.actor, user_id: 'owner', roles: ['bid_owner'] } as Actor
      }
    />
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Assessment ready · Campus maintenance',
      exact: true,
    })
  )
  await expect
    .element(
      screen
        .getByRole('region', { name: 'Inbox update' })
        .getByText(tenders[0].assessment!.candidate.summary, {
          exact: true,
        })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('table', { name: 'Requirements and findings' }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('link', { name: 'Open review', exact: true }))
    .toHaveAttribute('href', '/tenders/one')
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Answer received · Campus maintenance · Can Saturday staffing be confirmed?',
      exact: true,
    })
  )
  await expect
    .element(
      screen.getByText('Confirmed from the staffing roster.', { exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Your answer'))
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Assessment ready · Completed tender',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: /Closed tender/ }))
    .not.toBeInTheDocument()
})

it('groups a single tender row containing all its review questions', async () => {
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Open reviews (1)', exact: true })
    )
    .toBeVisible()
  expect(
    screen
      .getByRole('button', { name: 'Campus maintenance', exact: true })
      .elements()
  ).toHaveLength(1)
  await userEvent.click(
    screen.getByRole('button', { name: 'Campus maintenance', exact: true })
  )
  await expect
    .element(
      screen.getByRole('heading', { name: 'Review questions', exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('article', {
        name: 'Can Saturday staffing be confirmed?',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('article', {
        name: 'Can mobilisation be confirmed?',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(screen.getByText('Original source snapshot', { exact: true }))
    .toBeVisible()
  expect(screen.getByLabelText('Your answer').elements()).toHaveLength(2)
  await expect
    .element(screen.getByRole('link', { name: 'Open review', exact: true }))
    .toHaveAttribute('href', '/tenders/one')
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Review source documents',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'For you', exact: true }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: 'Created', exact: true }))
    .not.toBeInTheDocument()
})

it('uses recorded decisions for completed and closed groups without scope tabs', async () => {
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Completed reviews (1)', exact: true })
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Completed tender', exact: true })
    )
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Closed reviews (1)', exact: true })
  )
  await expect
    .element(screen.getByRole('button', { name: 'Closed tender', exact: true }))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Unanalysed tender', exact: true })
    )
    .not.toBeInTheDocument()
})

it('reopens a non-current recorded review instead of treating an AI recommendation as completion', async () => {
  tenders[1].decision!.is_current = false
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Open reviews (2)', exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Completed tender', exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Completed reviews (0)', exact: true })
    )
    .toBeVisible()
})

it('saves an attributed answer from inside the selected tender without leaving Reviews', async () => {
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Campus maintenance', exact: true })
  )
  const question = screen.getByRole('article', {
    name: 'Can Saturday staffing be confirmed?',
    exact: true,
  })
  await userEvent.fill(
    question.getByLabelText('Your answer'),
    'Confirmed from the staffing roster.'
  )
  await userEvent.click(
    question.getByRole('button', {
      name: 'Save answer and reassess',
      exact: true,
    })
  )
  await expect
    .element(
      question.getByText('Confirmed from the staffing roster.', { exact: true })
    )
    .toBeVisible()
  expect(commands[0].path).toBe('/api/v1/review-tasks/assigned/answers')
  expect(commands[0].body).toMatchObject({
    expected_task_revision: 1,
    response_kind: 'confirmed',
    text: 'Confirmed from the staffing roster.',
  })
  await expect
    .element(screen.getByRole('table', { name: 'Qualification checks' }))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Campus maintenance', exact: true })
    )
    .toHaveAttribute('aria-pressed', 'true')
})

it('moves the tender review to Completed after the real decision command', async () => {
  tenders[0].review_tasks = []
  const actor = { ...session.actor, roles: ['approver'] }
  const screen = await wrap(<ReviewWork api={api} actor={actor as Actor} />)
  await userEvent.click(
    screen.getByRole('button', { name: 'Campus maintenance', exact: true })
  )
  await userEvent.click(
    screen.getByText('Decision and history', { exact: true })
  )
  await userEvent.fill(
    screen.getByLabelText('Decision reason'),
    'Hold pending company confirmation.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Hold', exact: true })
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Completed reviews (2)', exact: true })
    )
    .toBeVisible()
  expect(commands[0].path).toBe('/api/v1/tenders/one/decisions')
  expect(commands[0].body).toMatchObject({
    assessment_version_id: 'assessment-one',
    expected_input_revision: 2,
    decision: 'hold',
    reason: 'Hold pending company confirmation.',
  })
})

it('reports review read failures without claiming there is no assigned work', async () => {
  failDetail = true
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('Review is unavailable.')
  await expect
    .element(screen.getByText('No reviews for you.', { exact: true }))
    .not.toBeInTheDocument()
})

it('keeps a tender review open while questions remain despite a recorded hold', async () => {
  tenders[0].decision = decision(tenders[0], 'hold')
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Open reviews (1)', exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Completed reviews (1)', exact: true })
    )
    .toBeVisible()
})

it('reports Inbox read failures instead of inventing updates or claiming an empty inbox', async () => {
  failDetail = true
  const screen = await wrap(
    <WorkspaceInbox api={api} actor={session.actor as Actor} />
  )
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('Review is unavailable.')
  await expect
    .element(screen.getByText('No updates need attention.', { exact: true }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('link', { name: 'Open review', exact: true }))
    .not.toBeInTheDocument()
})

it('pauses the contextual answer if a later Inbox refresh fails', async () => {
  const screen = await wrap(
    <WorkspaceInbox api={api} actor={session.actor as Actor} />
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Question assigned · Campus maintenance · Can Saturday staffing be confirmed?',
      exact: true,
    })
  )
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Save answer and reassess',
        exact: true,
      })
    )
    .toBeEnabled()
  failDetail = true
  await cache.invalidateQueries({ queryKey: ['tender'] })
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('Review is unavailable.')
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Save answer and reassess',
        exact: true,
      })
    )
    .toBeDisabled()
  expect(commands).toHaveLength(0)
})

it('keeps reviews created by the actor available after removing the scope tabs', async () => {
  tenders[0].review_tasks.forEach((task) => {
    task.assignee_id = 'other'
  })
  const screen = await wrap(
    <ReviewWork api={api} actor={session.actor as Actor} />
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Campus maintenance', exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'For you', exact: true }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: 'Created', exact: true }))
    .not.toBeInTheDocument()
})

it('pages team Reviews without loading every tender or history and preserves read-only visibility', async () => {
  const first = screeningCase()
  first.permitted_actions = []
  const second = {
    ...screeningCase(),
    tender_id: 'tender-2',
    title: 'Another team case',
    permitted_actions: [],
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
      if (path.endsWith('/review-cases/tender-1')) return Response.json(first)
      if (path.endsWith('/members'))
        return Response.json({ items: screeningMembers })
      if (path.endsWith('/sources')) return Response.json({ anchors: [] })
      if (path.endsWith('/tenders/tender-1'))
        return Response.json(boundedTender())
      throw new Error('Unexpected unbounded read: ' + path)
    })
  )
  const screen = await wrap(
    <ReviewWork
      api={api}
      actor={{ ...screeningOwner, user_id: 'viewer', roles: ['viewer'] }}
    />
  )
  await expect
    .element(screen.getByRole('button', { name: /Campus maintenance/ }))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Load more reviews', exact: true })
  )
  await expect
    .element(screen.getByRole('button', { name: /Another team case/ }))
    .toBeVisible()
  expect(
    reads.some((path) => path.endsWith('/tenders') || path.endsWith('/history'))
  ).toBe(false)
  expect(reads.filter((path) => /\/tenders\/[^/]+$/.test(path))).toEqual([
    '/api/v1/tenders/tender-1',
  ])
  await expect
    .element(
      screen.getByRole('button', { name: 'Assign request', exact: true })
    )
    .not.toBeInTheDocument()
})
