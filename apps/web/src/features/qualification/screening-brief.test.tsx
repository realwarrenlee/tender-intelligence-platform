import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/circle/globals.css'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent, page } from 'vitest/browser'
import { createApi, type Actor } from './api'
import { ReviewDesk } from './review-desk'
import {
  boundedTender,
  reviewCase,
  owner,
  reviewer,
  approver,
  members,
  scopedTask,
  opportunity,
} from './test-fixtures/screening'
import { ReviewWork, WorkspaceInbox } from './workspace-activity'

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  search: 'tab=human',
  mobile: false,
}))
vi.mock('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(navigation.search),
}))
vi.mock('@/circle/hooks/use-mobile', () => ({
  useIsMobile: () => navigation.mobile,
}))
let cache: QueryClient
let active: Actor
let tender: ReturnType<typeof boundedTender>
let review: ReturnType<typeof reviewCase>
let commands: Array<{ path: string; body: Record<string, unknown> }>
const api = createApi(async () => 'test')
beforeEach(() => {
  document.documentElement.classList.add('dark')
  active = owner
  tender = boundedTender()
  review = reviewCase()
  commands = []
  navigation.mobile = false
  navigation.search = 'tab=human'
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (init?.method === 'POST' && init.body instanceof FormData) {
        const body = JSON.parse(String(init.body.get('metadata')))
        commands.push({ path, body })
        tender.documents = boundedTender().documents
        tender.input_revision = 2
        review.input_revision = 2
        return Response.json({ input_revision: 2 })
      }
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        commands.push({ path, body })
        if (path.endsWith('/triage'))
          return Response.json({
            ...opportunity(),
            state: 'activated',
            tender_id: 'tender-1',
          })
        if (path.endsWith('/screenings')) {
          review = reviewCase()
          return Response.json({ id: 'screen-job' })
        }
        if (path.endsWith('/review-tasks')) {
          const task = scopedTask(
            body.draft_ref === 'preparation'
              ? 'preparation_approval'
              : 'screening_input'
          )
          task.assessment_version_id = String(
            body.expected_assessment_version_id
          )
          task.assignee_id = String(body.assignee_id)
          if (
            task.purpose === 'preparation_approval' &&
            tender.review_tasks.some(
              (item) => item.purpose === 'preparation_approval'
            )
          ) {
            task.id = 'approval-task-2'
            if (review.preparation_decision)
              review.preparation_decision.is_current = false
            review.state = 'Needs reassessment'
          }
          tender.review_tasks.push(task)
          return Response.json(task)
        }
        if (path.endsWith('/answers')) {
          tender.input_revision = 3
          review.input_revision = 3
          review.screening_version_id = 'screen-2'
          review.screening!.id = 'screen-2'
          review.screening!.input_revision = 3
          tender.review_tasks[0].status = 'answered'
          tender.review_tasks[0].answer = {
            id: 'answer',
            actor_id: 'reviewer',
            text: String(body.text),
            basis: String(body.basis),
            response_kind: 'confirmed',
            created_at: '2026-11-01T02:00:00Z',
            evidence_version_id: 'answer-evidence',
            reassessment_job_id: 'job',
            reassessment_status: 'completed',
          }
          review.state = 'Ready for decision'
          review.recommendation = 'promising'
          review.screening!.artifact.findings[0].status = 'supported'
          review.screening!.artifact.approval_blockers = []
          review.screening!.artifact.recommendation = 'promising'
          review.screening!.artifact.request_drafts =
            review.screening!.artifact.request_drafts.slice(1)
        }
        if (path.endsWith('/preparation-decisions')) {
          const outcome =
            body.outcome === 'request_information'
              ? 'request_information'
              : body.outcome === 'decline'
                ? 'decline'
                : 'approve_preparation'
          review.state =
            outcome === 'request_information'
              ? 'Waiting for input'
              : 'Completed'
          review.tender_stage =
            outcome === 'decline'
              ? 'closed'
              : outcome === 'approve_preparation'
                ? 'preparing_bid'
                : 'assessing'
          tender.review_tasks.find(
            (t) => t.purpose === 'preparation_approval'
          )!.status = 'answered'
          review.preparation_decision = {
            id: 'decision',
            screening_version_id: 'screen-2',
            approval_task_id: 'approval-task',
            actor_id: 'approver',
            outcome,
            reason: String(body.reason),
            preparation_scope: String(body.preparation_scope),
            preparation_budget: { amount: '1500', currency: 'SGD' },
            conditions: [],
            created_at: '2026-11-01T03:00:00Z',
            is_current: true,
            currency_reason: null,
          }
        }
        return Response.json({ id: 'saved' })
      }
      if (path.includes('/opportunity-suggestions'))
        return Response.json({ items: [opportunity()], next_cursor: null })
      if (path.includes('/sources/document-1'))
        return new Response(
          JSON.stringify({
            status: 'complete',
            anchors: [
              {
                anchor_id: 'tender-page-1',
                paragraph: 1,
                text: 'Registration is required before submission.',
              },
            ],
          }),
          { headers: { 'Content-Type': 'application/json' } }
        )
      if (path.endsWith('/members')) return Response.json({ items: members })
      if (path.includes('/review-cases')) {
        const data = {
          ...review,
          permitted_actions:
            active.user_id === 'owner'
              ? ['start_screening', 'confirm_requests']
              : active.user_id === 'approver'
                ? ['record_preparation_decision']
                : [],
        }
        return Response.json(
          path.split('?')[0].endsWith('/review-cases')
            ? { items: [data], next_cursor: null }
            : data
        )
      }
      if (path.includes('/inbox-actions'))
        return Response.json({
          next_cursor: null,
          items: tender.review_tasks
            .filter(
              (task) =>
                task.assignee_id === active.user_id && task.status === 'open'
            )
            .map((task) => ({
              task_id: task.id,
              tender_id: tender.id,
              tab: 'human',
              kind: task.purpose,
              screening_version_id: task.assessment_version_id,
              question: task.question,
              due_at: task.due_at,
              task_revision: task.revision,
              is_current: task.is_current,
              can_act: task.is_current,
            })),
        })
      if (path.endsWith('/sources'))
        return Response.json({
          anchors: [
            {
              anchor_id: 'tender-page-1',
              document_version_id: 'document-1',
              source_role: 'tender',
              text: 'Registration is required before submission.',
              paragraph: 1,
            },
          ],
        })
      if (path.endsWith('/history'))
        return Response.json({ assessments: [], decisions: [] })
      if (path.endsWith('/tenders')) return Response.json({ items: [] })
      if (path.endsWith('/tenders/tender-1')) return Response.json(tender)
      throw new Error('Unexpected test API path: ' + path)
    })
  )
})
afterEach(async () => {
  document.documentElement.classList.remove('dark')
  await page.viewport(1440, 900)
  cache.clear()
  vi.unstubAllGlobals()
})
async function mount(
  actor: Actor = owner,
  view: 'desk' | 'inbox' | 'reviews' = 'desk'
) {
  active = actor
  cache.clear()
  return render(
    <QueryClientProvider client={cache}>
      <div
        className='h-dvh bg-container'
        style={{ fontFamily: 'Arial, sans-serif' }}
      >
        {view === 'inbox' ? (
          <WorkspaceInbox actor={actor} api={api} />
        ) : view === 'reviews' ? (
          <ReviewWork actor={actor} api={api} />
        ) : (
          <ReviewDesk tenderId='tender-1' actor={actor} api={api} />
        )}
      </div>
    </QueryClientProvider>
  )
}
it('shows a cited preparation brief without automatically assigning questions or approving', async () => {
  const screen = await mount()
  await expect
    .element(
      screen.getByRole('heading', { name: 'Preparation brief', exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByText('Critical condition unresolved', { exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByText('USD 0.03', { exact: true }))
    .toBeVisible()
  expect(commands).toHaveLength(0)
  await page.screenshot({
    path: '../../../../../output/implementation/bid-qualification-2026-11-01/task-5-brief-desktop.png',
  })
  await expect
    .element(
      screen.getByRole('button', { name: 'Approve preparation', exact: true })
    )
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('tab', { name: 'Sources', exact: true })
  )
  await expect
    .element(
      screen
        .getByRole('button', { name: 'instructions.docx', exact: true })
        .last()
    )
    .toBeVisible()
})
it('routes an owner-confirmed question to the named Human Inbox, then a preparation decision to the approver', async () => {
  review.screening = null
  review.screening_version_id = null
  review.screening_is_current = false
  review.job_status = null
  review.input_revision = 1
  tender.input_revision = 1
  tender.documents = []
  navigation.search = 'tab=agent'
  let screen = await mount(owner, 'inbox')
  await userEvent.click(
    screen.getByRole('button', { name: 'Start assessment', exact: true })
  )
  await expect
    .poll(() => navigation.push.mock.calls.at(-1)?.[0])
    .toBe('/tenders/tender-1')
  expect(commands.map((command) => command.path)).toEqual([
    '/api/v1/opportunity-suggestions/suggestion/triage',
  ])
  await screen.unmount()
  screen = await mount()
  await userEvent.click(
    screen.getByRole('tab', { name: 'Sources', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Add documents', exact: true })
  )
  await userEvent.upload(screen.getByLabelText('Tender files'), [
    new File(['controlled source'], 'instructions.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }),
  ])
  await userEvent.click(
    screen.getByRole('button', { name: 'Add documents', exact: true }).last()
  )
  await expect.poll(() => tender.documents.length).toBe(1)
  expect(
    commands.some((command) => /screenings|analyses/.test(command.path))
  ).toBe(false)
  await userEvent.click(
    screen.getByRole('tab', { name: 'Review', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Start screening', exact: true })
  )
  await expect
    .element(screen.getByText('Critical condition unresolved', { exact: true }))
    .toBeVisible()
  expect(commands.at(-1)?.path).toBe('/api/v1/tenders/tender-1/screenings')
  expect(commands.at(-1)?.body.expected_input_revision).toBe(2)
  await userEvent.click(
    screen.getByRole('button', { name: 'Assign request', exact: true }).first()
  )
  await userEvent.selectOptions(screen.getByLabelText('Assign to'), 'reviewer')
  await userEvent.click(
    screen.getByRole('button', { name: 'Confirm request', exact: true })
  )
  await expect.poll(() => tender.review_tasks.length).toBe(1)
  expect(commands.at(-1)?.body).toMatchObject({
    draft_ref: 'finding:registration',
    assignee_id: 'reviewer',
    expected_assessment_version_id: 'screen-1',
  })
  await screen.unmount()
  navigation.search = 'tab=human'
  screen = await mount(reviewer, 'inbox')
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Confirm current FM registration.',
      exact: true,
    })
  )
  await userEvent.fill(
    screen.getByLabelText('Your answer', { exact: true }),
    'Registration confirmed for the bidding entity.'
  )
  await userEvent.fill(
    screen.getByLabelText('Basis for your answer'),
    'Checked the current entity registry.'
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Save answer and reassess',
      exact: true,
    })
  )
  await expect.poll(() => tender.review_tasks[0].status).toBe('answered')
  expect(commands.at(-1)?.body).toMatchObject({
    expected_task_revision: 1,
    basis: 'Checked the current entity registry.',
  })
  await screen.unmount()
  screen = await mount()
  await userEvent.click(
    screen.getByRole('button', { name: 'Assign request', exact: true }).last()
  )
  await userEvent.selectOptions(screen.getByLabelText('Assign to'), 'approver')
  await userEvent.click(
    screen.getByRole('button', { name: 'Confirm request', exact: true })
  )
  await expect.poll(() => tender.review_tasks.length).toBe(2)
  await screen.unmount()
  screen = await mount(approver, 'inbox')
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Review scope and preparation budget.',
      exact: true,
    })
  )
  await userEvent.fill(
    screen.getByLabelText('Reason'),
    'Current brief reviewed.'
  )
  await userEvent.fill(
    screen.getByLabelText('Preparation scope'),
    'Prepare the costed draft bid.'
  )
  await userEvent.fill(
    screen.getByLabelText('Preparation budget', { exact: true }),
    '1500'
  )
  await userEvent.click(
    screen.getByLabelText('I reviewed the preparation conditions')
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Approve preparation', exact: true })
  )
  await expect.poll(() => review.state).toBe('Completed')
  expect(commands.at(-1)?.body).toMatchObject({
    screening_version_id: 'screen-2',
    approval_task_id: 'approval-task',
    expected_input_revision: 3,
    expected_evidence_revision: 1,
    outcome: 'approve_preparation',
    preparation_scope: 'Prepare the costed draft bid.',
    preparation_budget: { amount: '1500', currency: 'SGD' },
    conditions: [],
  })
  await screen.unmount()
  screen = await mount(
    { ...owner, user_id: 'viewer', roles: ['viewer'] },
    'reviews'
  )
  await expect
    .element(screen.getByText('Completed', { exact: true }).first())
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Confirm request', exact: true })
    )
    .not.toBeInTheDocument()
})
it('blocks stale and budget-exhausted evidence and shows incomplete sources', async () => {
  review.screening_is_current = false
  review.screening!.is_current = false
  review.attention = 'STAGE_BUDGET_EXHAUSTED'
  review.screening!.artifact.coverage = {
    complete: false,
    source_complete: false,
    requires_wider_review: true,
    deferred: ['annex.pdf'],
    gaps: [
      {
        filename: 'annex.pdf',
        materiality: 'unknown',
        code: 'SOURCE_INCOMPLETE',
      },
    ],
  }
  const screen = await mount(approver)
  await expect
    .element(
      screen.getByText(
        /This brief and earlier preparation authority are non-current/
      )
    )
    .toBeVisible()
  await expect.element(screen.getByText(/Budget exhausted/)).toBeVisible()
  await expect
    .element(screen.getByText(/annex.pdf.*Materiality unknown/))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Approve preparation', exact: true })
    )
    .not.toBeInTheDocument()
})

it('opens only the selected Human action on a narrow screen and returns to its queue', async () => {
  await page.viewport(390, 844)
  navigation.mobile = true
  tender.review_tasks = [
    scopedTask(),
    {
      ...scopedTask(),
      id: 'other-input',
      question: 'Confirm a second scoped fact.',
    },
  ]
  const screen = await mount(reviewer, 'inbox')
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Confirm current FM registration.',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Your answer', { exact: true }))
    .not.toBeInTheDocument()
  await page.screenshot({
    path: '../../../../../output/implementation/bid-qualification-2026-11-01/task-5-human-mobile.png',
  })
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Confirm current FM registration.',
      exact: true,
    })
  )
  await expect
    .element(screen.getByLabelText('Your answer', { exact: true }))
    .toBeVisible()
  expect(
    screen.getByLabelText('Your answer', { exact: true }).elements()
  ).toHaveLength(1)
  await userEvent.click(
    screen.getByRole('button', { name: 'Back to list', exact: true })
  )
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Confirm a second scoped fact.',
        exact: true,
      })
    )
    .toBeVisible()
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(
    window.innerWidth
  )
})

it('keeps preparation form values while inspecting original source evidence', async () => {
  tender.review_tasks = [scopedTask('preparation_approval')]
  review.screening!.artifact.findings[0].status = 'supported'
  review.screening!.artifact.approval_blockers = []
  const screen = await mount(approver)
  await userEvent.fill(
    screen.getByLabelText('Reason'),
    'Reviewing the original registration clause.'
  )
  await userEvent.fill(
    screen.getByLabelText('Preparation scope'),
    'Cost the draft bid.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Tender source 1', exact: true })
  )
  await expect
    .element(screen.getByRole('complementary', { name: 'Source documents' }))
    .toBeVisible()
  await page.screenshot({
    path: '../../../../../output/implementation/bid-qualification-2026-11-01/task-5-source-desktop.png',
  })
  await userEvent.click(
    screen.getByRole('button', { name: 'Back to brief', exact: true })
  )
  await expect
    .element(screen.getByLabelText('Reason'))
    .toHaveValue('Reviewing the original registration clause.')
  await expect
    .element(screen.getByLabelText('Preparation scope'))
    .toHaveValue('Cost the draft bid.')
})

it.each(['request_information', 'decline'] as const)(
  'supports %s with an owned next step when information is requested',
  async (outcome) => {
    tender.review_tasks = [scopedTask('preparation_approval')]
    const screen = await mount(approver)
    await userEvent.selectOptions(screen.getByLabelText('Outcome'), outcome)
    await userEvent.fill(
      screen.getByLabelText('Reason'),
      'Resolve the present evidence gap.'
    )
    if (outcome === 'request_information') {
      await userEvent.selectOptions(
        screen.getByLabelText('Next responsible person'),
        'owner'
      )
      await userEvent.fill(
        screen.getByLabelText('Information needed'),
        'Obtain the current registration record.'
      )
    }
    await userEvent.click(
      screen.getByRole('button', {
        name: outcome === 'decline' ? 'Decline' : 'Request information',
        exact: true,
      })
    )
    await expect.poll(() => commands.length).toBe(1)
    expect(commands[0].body).toMatchObject({
      outcome,
      screening_version_id: 'screen-1',
      approval_task_id: 'approval-task',
    })
    if (outcome === 'request_information')
      expect(commands[0].body).toMatchObject({
        next_assignee_id: 'owner',
        information_request: 'Obtain the current registration record.',
      })
  }
)

it('requires an explicit condition for a material future commitment before preparation approval', async () => {
  tender.review_tasks = [scopedTask('preparation_approval')]
  const artifact = review.screening!.artifact
  artifact.findings[0].status = 'supported'
  artifact.approval_blockers = []
  artifact.findings.push({
    ...artifact.findings[0],
    id: 'staff',
    statement: 'Mobilisation staffing commitment.',
    kind: 'delivery_commitment',
    due_stage: 'mobilisation',
    material_now: true,
    critical: false,
    critical_basis: null,
    status: 'unconfirmed',
  })
  const screen = await mount(approver)
  await userEvent.fill(
    screen.getByLabelText('Reason'),
    'Prepare subject to a staffed plan.'
  )
  await userEvent.fill(
    screen.getByLabelText('Preparation scope'),
    'Cost the draft bid.'
  )
  await userEvent.fill(
    screen.getByLabelText('Preparation budget', { exact: true }),
    '1500'
  )
  await userEvent.click(
    screen.getByLabelText('I reviewed the preparation conditions')
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Approve preparation', exact: true })
  )
  expect(commands).toHaveLength(0)
  await userEvent.fill(
    screen.getByLabelText('Condition: Mobilisation staffing commitment.'),
    'Obtain the accepted staffing plan before committing delivery.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Approve preparation', exact: true })
  )
  await expect.poll(() => commands.length).toBe(1)
  expect(commands[0].body.conditions).toEqual([
    {
      finding_id: 'staff',
      condition:
        'Obtain the accepted staffing plan before committing delivery.',
    },
  ])
})

it('retains readable bounded history during server rollback without offering active mutations', async () => {
  const screen = await mount({
    ...owner,
    qualification_workflow_enabled: false,
  })
  await expect
    .element(
      screen.getByText(
        'Screening is disabled. This saved brief is read-only.',
        { exact: true }
      )
    )
    .toBeVisible()
  await expect
    .element(
      screen
        .getByRole('button', { name: 'Assign request', exact: true })
        .first()
    )
    .toBeDisabled()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Investigate current sources',
        exact: true,
      })
    )
    .toBeDisabled()
  expect(commands).toHaveLength(0)
})

it('changes the delegated approver without rerunning screening and shows previous authority as non-current', async () => {
  review.screening!.artifact.findings[0].status = 'supported'
  review.screening!.artifact.approval_blockers = []
  review.screening!.artifact.recommendation = 'promising'
  review.state = 'Completed'
  review.tender_stage = 'preparing_bid'
  const old = scopedTask('preparation_approval')
  old.status = 'answered'
  tender.review_tasks = [old]
  review.preparation_decision = {
    id: 'previous',
    screening_version_id: 'screen-1',
    approval_task_id: old.id,
    actor_id: 'approver',
    outcome: 'approve_preparation',
    reason: 'Earlier review.',
    preparation_scope: 'Draft the bid.',
    preparation_budget: { amount: '1500', currency: 'SGD' },
    conditions: [],
    created_at: '2026-11-01T02:00:00Z',
    is_current: true,
    currency_reason: null,
  }
  const screen = await mount()
  await userEvent.click(
    screen.getByRole('button', { name: 'Change approver', exact: true })
  )
  await userEvent.selectOptions(
    screen.getByLabelText('Assign to'),
    'other-approver'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Confirm request', exact: true })
  )
  await expect
    .element(
      screen.getByRole('heading', {
        name: /approve preparation · Non-current/i,
      })
    )
    .toBeVisible()
  expect(commands.map((command) => command.path)).toEqual([
    '/api/v1/tenders/tender-1/review-tasks',
  ])
  expect(commands[0].body).toMatchObject({
    expected_assessment_version_id: 'screen-1',
    draft_ref: 'preparation',
    assignee_id: 'other-approver',
  })
})

it('sends an explicitly bounded investigation focus under the existing case', async () => {
  const screen = await mount()
  await userEvent.fill(
    screen.getByLabelText('Investigation focus (optional)'),
    'submission registration'
  )
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Investigate current sources',
      exact: true,
    })
  )
  await expect.poll(() => commands.length).toBe(1)
  expect(commands[0]).toMatchObject({
    path: '/api/v1/tenders/tender-1/screenings',
    body: {
      expected_input_revision: 2,
      investigation_queries: ['submission registration'],
    },
  })
})

it('shows the current notice evidence to team reviewers alongside uploaded sources', async () => {
  const item = opportunity()
  tender.opportunity = {
    suggestion_id: item.id,
    notice_version_id: item.notice_version_id,
    notice_version: 1,
    notice: { ...item.notice },
  }
  const screen = await mount({ ...owner, user_id: 'viewer', roles: ['viewer'] })
  await userEvent.click(
    screen.getByRole('tab', { name: 'Sources', exact: true })
  )
  await expect
    .element(
      screen
        .getByRole('button', { name: 'instructions.docx', exact: true })
        .last()
    )
    .toBeVisible()
  expect(
    screen.getByText('Current notice · Version 1', { exact: true }).elements()
  ).toHaveLength(1)
  await userEvent.click(
    screen.getByText('Current notice · Version 1', { exact: true })
  )
  await expect
    .element(screen.getByText(item.notice.evidence_text, { exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByText(/Controlled import.*Notice only/))
    .toBeVisible()
})
