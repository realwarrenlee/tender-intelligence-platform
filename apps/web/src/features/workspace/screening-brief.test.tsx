import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/app/globals.css'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent, page } from 'vitest/browser'
import { createApi, type Actor, type OpportunityFeedback } from './api'
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
import { Oversight, WorkspaceInbox } from './workspace-activity'

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
vi.mock('@/hooks/use-mobile', () => ({
  useIsMobile: () => navigation.mobile,
}))
let cache: QueryClient
let active: Actor
let tender: ReturnType<typeof boundedTender>
let review: ReturnType<typeof reviewCase>
let feedback: OpportunityFeedback[]
let commands: Array<{ path: string; body: Record<string, unknown> }>
const api = createApi(async () => 'test')
const overviewQuote =
  'Fictional Agency invites FM-2026 for Integrated facilities maintenance. Three years with an optional two-year extension. North and South campuses. Store services: 60 months plus optional 36 months.'
function overviewSummary() {
  const fact = (value: string) => ({
    value,
    citations: [{ anchor_id: 'overview-paragraph-2', quote: overviewQuote }],
  })
  return {
    buyer: fact('Fictional Agency'),
    reference: fact('FM-2026'),
    scope: fact('Integrated facilities maintenance'),
    contract_period: fact('Three years with an optional two-year extension'),
    sites: fact('North and South campuses'),
  }
}
beforeEach(() => {
  document.documentElement.classList.add('dark')
  active = owner
  tender = boundedTender()
  review = reviewCase()
  commands = []
  feedback = []
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
        if (path.endsWith('/opportunity-feedback/feedback-1/answer'))
          feedback[0] = { ...feedback[0], answer: String(body.answer) }
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
              {
                anchor_id: 'overview-paragraph-2',
                paragraph: 2,
                text: overviewQuote,
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
      if (path.endsWith('/opportunity-feedback'))
        return Response.json({ items: feedback, next_cursor: null })
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
            {
              anchor_id: 'overview-paragraph-2',
              document_version_id: 'document-1',
              source_role: 'tender',
              text: overviewQuote,
              paragraph: 2,
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
  view: 'desk' | 'inbox' | 'reviews' | 'embedded' = 'desk'
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
          <Oversight actor={actor} api={api} />
        ) : (
          <ReviewDesk
            tenderId='tender-1'
            actor={actor}
            api={api}
            embedded={view === 'embedded'}
          />
        )}
      </div>
    </QueryClientProvider>
  )
}
it('shows only the review in the embedded preview', async () => {
  const screen = await mount(owner, 'embedded')
  await expect
    .element(
      screen.getByRole('heading', { name: 'Qualification brief', exact: true })
    )
    .toBeVisible()
  expect(
    screen.getByRole('tab', { name: 'Qualification', exact: true }).elements()
  ).toHaveLength(0)
  expect(
    screen.getByRole('tab', { name: 'Sources', exact: true }).elements()
  ).toHaveLength(0)
})
it('shows a cited qualification brief without automatically assigning questions or approving', async () => {
  const screen = await mount()
  for (const name of ['Preparation', 'Submission']) {
    await expect
      .element(screen.getByRole('tab', { name, exact: true }))
      .toBeVisible()
  }
  await expect
    .element(
      screen.getByRole('heading', { name: 'Qualification brief', exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByText('Critical condition unresolved', { exact: true }))
    .toBeVisible()
  await userEvent.click(
    screen.getByText('Source coverage and processing details', { exact: true })
  )
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
  const file = screen
    .getByRole('button', { name: 'instructions.docx', exact: true })
    .last()
  await userEvent.click(file)
  await expect.element(file).toHaveAttribute('aria-expanded', 'true')
  await userEvent.click(
    screen.getByRole('button', { name: 'Back to brief', exact: true })
  )
  await expect.element(file).toHaveFocus()
})

it.each(['light', 'dark'] as const)(
  'shows cited candidate overview extracts in the existing %s appearance',
  async (theme) => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    review.screening!.artifact.summary = overviewSummary()
    const screen = await mount()
    const overview = screen.getByRole('region', {
      name: 'Qualification overview',
    })
    for (const fact of Object.values(overviewSummary()))
      await expect
        .element(overview.getByText(fact.value, { exact: true }))
        .toBeVisible()
    await expect
      .element(
        overview.getByText('Extracted · verify against sources', {
          exact: true,
        })
      )
      .toBeVisible()
    for (const label of [
      'Buyer',
      'Reference',
      'Scope',
      'Contract period',
      'Sites',
    ])
      await expect
        .element(
          overview.getByRole('button', {
            name: label + ' source 1',
            exact: true,
          })
        )
        .toBeVisible()
    expect(commands).toHaveLength(0)
    await page.screenshot({
      path:
        '../../../../../output/implementation/tender-lifecycle-2026-11-03/overview-' +
        theme +
        '.png',
    })
  }
)
it.each(['missing', 'null', 'partial'] as const)(
  'shows unknown overview fields for a %s summary without notice or legacy fallbacks',
  async (state) => {
    if (state === 'null') review.screening!.artifact.summary = null
    if (state === 'partial')
      review.screening!.artifact.summary = {
        ...overviewSummary(),
        sites: { value: null, citations: [] },
      }
    review.screening!.artifact.facts.scope = {
      value: 'Old scope must not appear.',
    }
    const screen = await mount()
    const overview = screen.getByRole('region', {
      name: 'Qualification overview',
    })
    await expect
      .poll(
        () =>
          overview
            .getByText('Unknown in this brief.', { exact: true })
            .elements().length
      )
      .toBe(state === 'partial' ? 1 : 5)
    await expect
      .element(
        overview.getByRole('button', { name: 'Sites source 1', exact: true })
      )
      .not.toBeInTheDocument()
    await expect
      .element(overview.getByText('Old scope must not appear.'))
      .not.toBeInTheDocument()
    expect(commands).toHaveLength(0)
  }
)
it('replaces earlier extracts with unknowns when a newer brief has no summary', async () => {
  review.screening!.artifact.summary = overviewSummary()
  const screen = await mount()
  const overview = screen.getByRole('region', {
    name: 'Qualification overview',
  })
  await expect
    .element(overview.getByText('Fictional Agency', { exact: true }))
    .toBeVisible()
  review = structuredClone(review)
  review.screening_version_id = 'screen-2'
  review.screening!.id = 'screen-2'
  review.screening!.artifact.summary = null
  await cache.invalidateQueries({ queryKey: ['review-case'] })
  await expect
    .poll(
      () =>
        overview.getByText('Unknown in this brief.', { exact: true }).elements()
          .length
    )
    .toBe(5)
  await expect
    .element(overview.getByText('Fictional Agency', { exact: true }))
    .not.toBeInTheDocument()
  await expect
    .element(
      overview.getByRole('button', { name: 'Scope source 1', exact: true })
    )
    .not.toBeInTheDocument()
  expect(commands).toHaveLength(0)
})
it.each(['light', 'dark'] as const)(
  'puts the decision and responsible person before a partial pack inventory in %s appearance',
  async (theme) => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    review.closing_at = null
    review.next_actor_id = 'owner'
    const artifact = review.screening!.artifact
    artifact.approval_blockers = [
      'CRITICAL_COVERAGE_UNKNOWN',
      'CRITICAL_CONDITION_UNRESOLVED',
      'CLOSING_UNKNOWN',
    ]
    artifact.coverage = {
      complete: false,
      source_complete: false,
      requires_wider_review: true,
      deferred: ['maps.pdf'],
      gaps: Array.from({ length: 58 }, (_, index) => ({
        filename: 'maps.pdf',
        location_label: 'Page ' + (index + 1),
        materiality: 'unknown',
      })),
    }
    const screen = await mount()
    const overview = screen.getByRole('region', {
      name: 'Qualification overview',
    })
    await expect
      .element(
        overview.getByRole('heading', { name: 'Hold pending information' })
      )
      .toBeVisible()
    await expect
      .element(overview.getByText('Bid owner', { exact: true }))
      .toBeVisible()
    await expect
      .element(overview.getByText('Closing unknown', { exact: true }))
      .toBeVisible()
    await expect
      .element(overview.getByText('Critical coverage unknown', { exact: true }))
      .toBeVisible()
    await expect
      .element(
        screen.getByText('maps.pdf · Page 1 · Materiality unknown', {
          exact: true,
        })
      )
      .not.toBeVisible()
    await expect
      .element(overview.getByText('Unknown in this brief.').first())
      .toBeVisible()
    const nextAction = overview.getByRole('heading', { name: 'Next action' })
    const facts = overview.getByText('Closing deadline', {
      exact: true,
    })
    expect(
      nextAction.element().compareDocumentPosition(facts.element()) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
    expect(commands).toHaveLength(0)
    await page.screenshot({
      path:
        '../../../../../output/implementation/tender-lifecycle-2026-11-02/qualification-' +
        theme +
        '.png',
    })
    await userEvent.click(
      overview.getByRole('button', {
        name: 'View review requests',
        exact: true,
      })
    )
    await expect
      .element(screen.getByRole('region', { name: 'Review requests' }))
      .toHaveFocus()
    expect(commands).toHaveLength(0)
    await userEvent.click(
      screen.getByText('Source coverage and processing details', {
        exact: true,
      })
    )
    await expect
      .element(
        screen.getByText('maps.pdf · Page 58 · Materiality unknown', {
          exact: true,
        })
      )
      .toBeVisible()
    expect(commands).toHaveLength(0)
  }
)

it('keeps scoring, submission and future commitments separate and groups unassigned requests by function', async () => {
  const artifact = review.screening!.artifact
  artifact.findings.push(
    {
      ...artifact.findings[0],
      id: 'quality',
      statement: 'Quality exclusion threshold.',
      kind: 'scored_criterion',
    },
    {
      ...artifact.findings[0],
      id: 'forms',
      statement: 'Completed tender forms.',
      kind: 'bid_artifact',
    },
    {
      ...artifact.findings[0],
      id: 'staff',
      statement: 'Mobilisation staffing commitment.',
      kind: 'delivery_commitment',
      due_stage: 'mobilisation',
      critical: false,
      critical_basis: null,
      material_now: false,
    }
  )
  artifact.request_drafts.push({
    draft_ref: 'finding:staff',
    purpose: 'screening_input',
    finding_ids: ['staff'],
    question: 'Confirm the mobilisation approach.',
    owner_function: 'operations',
    suggested_role: 'service_reviewer',
  })
  const screen = await mount()
  for (const heading of [
    'Eligibility',
    'Submission requirements',
    'Scored criteria',
    'Award and delivery obligations',
  ]) {
    await expect
      .element(screen.getByRole('heading', { name: heading, exact: true }))
      .toBeVisible()
  }
  for (const statement of [
    'Quality exclusion threshold.',
    'Completed tender forms.',
    'Mobilisation staffing commitment.',
  ]) {
    await expect
      .element(screen.getByRole('heading', { name: statement, exact: true }))
      .toBeVisible()
  }
  const requests = screen.getByRole('region', { name: 'Review requests' })
  await expect
    .element(requests.getByRole('heading', { name: 'Compliance', exact: true }))
    .toBeVisible()
  await expect
    .element(requests.getByRole('heading', { name: 'Operations', exact: true }))
    .toBeVisible()
  expect(
    requests
      .getByRole('button', { name: 'Assign request', exact: true })
      .elements()
  ).toHaveLength(3)
  expect(commands).toHaveLength(0)
})

it.each([true, false])(
  'shows a recorded preparation decision with current=%s without granting new authority',
  async (current) => {
    review.preparation_decision = {
      id: 'decision-1',
      screening_version_id: 'screen-1',
      approval_task_id: 'approval-task',
      actor_id: 'approver',
      outcome: 'approve_preparation',
      reason: 'Prepare the permitted bid scope.',
      preparation_scope: 'Review the service delivery approach.',
      preparation_budget: { amount: '500', currency: 'SGD' },
      conditions: [],
      created_at: '2026-11-01T02:00:00Z',
      is_current: current,
      currency_reason: current
        ? null
        : 'INPUT_EVIDENCE_SCREENING_OR_TIME_CHANGED',
    }
    review.tender_stage = 'preparing_bid'
    if (current) {
      review.state = 'Completed'
      review.next_actor_id = null
    }
    const screen = await mount()
    const overview = screen.getByRole('region', {
      name: 'Qualification overview',
    })
    await expect
      .element(
        overview.getByText(
          current
            ? 'Preparation authorised'
            : 'Preparation decision needs reassessment',
          { exact: true }
        )
      )
      .toBeVisible()
    if (current) {
      await expect
        .element(
          overview.getByText('No outstanding qualification action.', {
            exact: true,
          })
        )
        .toBeVisible()
      await expect
        .element(overview.getByText('Bid owner', { exact: true }))
        .not.toBeInTheDocument()
    }
    expect(commands).toHaveLength(0)
  }
)

it('keeps qualification next steps complete after a current decline', async () => {
  review.state = 'Completed'
  review.tender_stage = 'closed'
  review.next_actor_id = null
  review.open_inputs = 0
  review.open_approvals = 0
  review.preparation_decision = {
    id: 'decline-1',
    screening_version_id: 'screen-1',
    approval_task_id: 'approval-task',
    actor_id: 'approver',
    outcome: 'decline',
    reason: 'Declined after review.',
    preparation_scope: null,
    preparation_budget: null,
    conditions: [],
    created_at: '2026-11-01T02:00:00Z',
    is_current: true,
    currency_reason: null,
  }
  const screen = await mount()
  const overview = screen.getByRole('region', {
    name: 'Qualification overview',
  })
  await expect
    .element(
      overview.getByText('No outstanding qualification action.', {
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(overview.getByText('Bid owner', { exact: true }))
    .not.toBeInTheDocument()
  expect(commands).toHaveLength(0)
})

it('keeps qualification next steps based on current server counts rather than stale requests', async () => {
  review.next_actor_id = 'reviewer'
  review.open_inputs = 1
  review.open_approvals = 0
  tender.review_tasks = [
    scopedTask(),
    {
      ...scopedTask(),
      id: 'stale-task',
      manifest: { ...scopedTask().manifest, source_signature: 'old-sources' },
    },
  ]
  const screen = await mount()
  const overview = screen.getByRole('region', {
    name: 'Qualification overview',
  })
  await expect
    .element(overview.getByText(/1 current review request/))
    .toBeVisible()
  await expect
    .element(overview.getByText('Operations lead', { exact: true }))
    .toBeVisible()
  expect(commands).toHaveLength(0)
})

it('keeps qualification next steps neutral when the assigned actor is absent from the directory', async () => {
  review.next_actor_id = 'unlisted-reviewer'
  const screen = await mount()
  const overview = screen.getByRole('region', {
    name: 'Qualification overview',
  })
  await expect
    .element(overview.getByText('Workspace member', { exact: true }))
    .toBeVisible()
  await expect
    .element(overview.getByText('Bid owner', { exact: true }))
    .not.toBeInTheDocument()
})

it('preserves the suggested team for a later-duty finding without creating a request', async () => {
  const artifact = review.screening!.artifact
  artifact.findings.push({
    ...artifact.findings[0],
    id: 'later-staffing',
    statement: 'Staffing is due at mobilisation.',
    kind: 'delivery_commitment',
    due_stage: 'mobilisation',
    critical: false,
    critical_basis: null,
    material_now: false,
    owner_function: 'operations',
  })
  artifact.work_packages.push({
    owner_function: 'operations',
    finding_ids: ['later-staffing'],
  })
  const screen = await mount()
  await expect
    .element(screen.getByText('Suggested team: Operations', { exact: true }))
    .toBeVisible()
  expect(
    screen
      .getByRole('region', { name: 'Review requests' })
      .getByRole('button', { name: 'Assign request', exact: true })
      .elements()
  ).toHaveLength(2)
  expect(commands).toHaveLength(0)
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
    screen.getByRole('tab', { name: 'Qualification', exact: true })
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
  screen = await mount({ ...owner, user_id: 'viewer', roles: ['viewer'] })
  await expect
    .element(screen.getByText('Completed', { exact: true }))
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
  await userEvent.click(
    screen.getByText('Source coverage and processing details', { exact: true })
  )
  await expect
    .element(screen.getByText(/annex.pdf.*Materiality unknown/))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Approve preparation', exact: true })
    )
    .not.toBeInTheDocument()
})

it('opens assigned work and feedback from the same Human Inbox list', async () => {
  tender.review_tasks = [scopedTask()]
  feedback = [
    {
      id: 'feedback-1',
      sender_id: owner.user_id,
      recipient_id: reviewer.user_id,
      question: 'Can we cover the weekend shifts?',
      notice: opportunity().notice,
      answer: null,
      answered_at: null,
      created_at: '2026-11-01T00:00:00Z',
    },
  ]
  const screen = await mount(reviewer, 'inbox')
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Confirm current FM registration.',
      })
    )
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Can we cover the weekend shifts?',
    })
  )
  await userEvent.fill(
    screen.getByLabelText('Your reply'),
    'Yes, with the on-call team.'
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send reply' }))
  await expect
    .poll(() => commands)
    .toContainEqual({
      path: '/api/v1/opportunity-feedback/feedback-1/answer',
      body: {
        answer: 'Yes, with the on-call team.',
        client_request_id: expect.any(String),
      },
    })
  await expect
    .element(screen.getByText('Reply: Yes, with the on-call team.'))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Confirm current FM registration.',
    })
  )
  await expect
    .element(screen.getByLabelText('Your answer', { exact: true }))
    .toBeVisible()
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

it.each(['Tender source 1', 'Scope source 1'])(
  'keeps preparation form values while inspecting %s evidence',
  async (source) => {
    review.screening!.artifact.summary = overviewSummary()
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
      screen.getByRole('button', { name: source, exact: true })
    )
    await expect
      .element(screen.getByRole('complementary', { name: 'Source documents' }))
      .toBeVisible()
    if (source === 'Scope source 1')
      await expect
        .element(screen.getByRole('blockquote'))
        .toHaveTextContent(overviewQuote)
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
  }
)

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

it.each([false, true])(
  'requires an explicit condition for material or conditional work (conditional=%s)',
  async (conditional) => {
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
      material_now: !conditional,
      critical: false,
      critical_basis: null,
      status: 'unconfirmed',
      ...(conditional
        ? {
            preparation_role: 'future_duty' as const,
            preparation_basis: 'Staffing is due during mobilisation.',
          }
        : {}),
    })
    if (conditional) artifact.preparation_condition_ids = ['staff']
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
  }
)

it.each(['light', 'dark'] as const)(
  'shows source-backed questions, confirmed ownership and secondary diagnostics in %s',
  async (theme) => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    const artifact = review.screening!.artifact
    artifact.summary = overviewSummary()
    artifact.summary.contract_period = { value: null, citations: [] }
    artifact.summary.sites = { value: null, citations: [] }
    artifact.overview_issues = [
      {
        field: 'contract_period',
        kind: 'conflicting',
        question: 'Confirm which period applies to store services.',
        citations: [
          {
            anchor_id: 'overview-paragraph-2',
            quote: 'Three years with an optional two-year extension.',
          },
          {
            anchor_id: 'overview-paragraph-2',
            quote: 'Store services: 60 months plus optional 36 months.',
          },
        ],
      },
      {
        field: 'sites',
        kind: 'not_established',
        question: 'Confirm the named sites and phased commencement.',
        citations: [],
      },
    ]
    artifact.request_drafts.push(
      ...artifact.overview_issues.map((issue) => ({
        draft_ref: 'overview:' + issue.field,
        purpose: 'screening_input',
        finding_ids: [],
        owner_function: issue.field === 'sites' ? 'operations' : 'bid_team',
        question: issue.question,
      }))
    )
    tender.review_tasks = [
      {
        ...scopedTask(),
        draft_ref: 'overview:contract_period',
        requirement_ids: [],
        question: artifact.overview_issues[0].question,
      },
    ]
    review.open_inputs = 1
    const screen = await mount()
    const questions = screen.getByRole('region', {
      name: 'Qualification questions',
    })
    await expect
      .element(
        questions.getByText('Confirm which period applies to store services.', {
          exact: true,
        })
      )
      .toBeVisible()
    await expect
      .element(questions.getByText(/Assigned to Operations lead · Due/))
      .toBeVisible()
    await expect
      .element(
        questions.getByText('Suggested team: Operations · Unassigned', {
          exact: true,
        })
      )
      .toBeVisible()
    await expect
      .element(screen.getByText(/Source extraction:/))
      .not.toBeVisible()
    await page.screenshot({
      path:
        '../../../../../output/implementation/qualification-decision-quality-2026-11-03/questions-' +
        theme +
        '.png',
    })
    expect(commands).toHaveLength(0)
    await userEvent.click(
      questions.getByRole('button', { name: 'Issue source 2', exact: true })
    )
    await expect
      .element(
        screen.getByRole('button', { name: 'Back to brief', exact: true })
      )
      .toBeVisible()
    await expect
      .element(screen.getByRole('blockquote'))
      .toHaveTextContent('Store services: 60 months plus optional 36 months.')
    await userEvent.click(
      screen.getByRole('button', { name: 'View extracted text', exact: true })
    )
    await expect
      .element(screen.getByText(overviewQuote, { exact: true }))
      .toBeVisible()
    expect(commands).toHaveLength(0)
  }
)

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
