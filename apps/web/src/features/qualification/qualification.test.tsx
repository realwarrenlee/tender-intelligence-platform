import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { createApi } from './api'
import { ReviewDesk } from './review-desk'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const citation = {
  anchor_id: 'tender-page-1',
  quote: 'Provide two qualified technicians every Saturday.',
}
const fact = (value: string | null) => ({
  value,
  citations: value ? [citation] : [],
})
const requirement = {
  local_ref: 'R1',
  text: 'Provide two qualified technicians every Saturday.',
  kind: 'delivery',
  mandatory: true,
  tender_citations: [citation],
  status: 'unconfirmed',
  company_citations: [],
  explanation: 'The company profile does not confirm Saturday allocation.',
  missing_information: 'Confirm Saturday availability.',
}
const assessment = {
  id: 'assessment-1',
  input_revision: 2,
  created_by: 'owner',
  is_current: true,
  candidate: {
    summary: 'Saturday availability needs confirmation.',
    key_facts: {
      title: fact('Fictional campus maintenance'),
      buyer: fact('Fictional buyer'),
      closing_at: fact('2026-11-20T16:00:00+08:00'),
      service_start_on: fact(null),
      term_months: { value: 12, citations: [citation] },
    },
    requirements: [requirement],
    recommendation: {
      decision: 'hold',
      reasons: ['Staffing is unconfirmed.'],
      condition_refs: ['R1'],
    },
    review_requests: [
      {
        draft_ref: 'Q1',
        requirement_refs: ['R1'],
        suggested_role: 'engineering_lead',
        question: 'Can two qualified technicians attend every Saturday?',
        rationale: 'Availability is unconfirmed.',
      },
    ],
    warnings: [],
  },
  requirements: [{ id: 'a'.repeat(64), requirement, carried_forward: false }],
  blockers: [
    { code: 'QUALIFICATION_UNCONFIRMED', requirement_id: 'a'.repeat(64) },
  ],
  reconciliation: [],
  manual_corrections: [],
  run: null,
  human_reason: null,
}
const initial = {
  schema_version: 'm1.v1',
  id: 'tender-1',
  workspace_id: 'workspace',
  title: 'Fictional campus maintenance',
  source_label: 'manual_upload',
  owner_user_id: 'owner',
  input_revision: 2,
  created_at: '2026-10-24T01:00:00Z',
  source_set_version_id: 'source-set-1',
  documents: [
    {
      id: 'document-1',
      filename: 'tender.pdf',
      sha256: '1'.repeat(64),
      role: 'tender',
      content_type: 'application/pdf',
      byte_size: 100,
      page_count: 1,
      amends_version_id: null,
      created_at: '2026-10-24T01:00:00Z',
    },
  ],
  assessment,
  assessment_status: 'current',
  review_tasks: [],
  decision: null,
  jobs: [],
}
const task = {
  schema_version: 'm1.v1',
  id: 'task-1',
  tender_id: 'tender-1',
  assessment_version_id: 'assessment-1',
  assignee_id: 'reviewer',
  created_by: 'owner',
  draft_ref: 'Q1',
  requirement_ids: ['a'.repeat(64)],
  purpose: 'qualification_review',
  question: 'Can two qualified technicians attend every Saturday?',
  status: 'open',
  revision: 1,
  due_at: '2026-10-26T12:00:00Z',
  created_at: '2026-10-24T01:00:00Z',
  manifest: {},
  is_current: true,
  answer: null,
}
let view: typeof initial
let commands: Array<{ path: string; body: Record<string, unknown> }>
let failure: number | undefined
let networkFailures = 0
let reviewFailures = 0
let uploadFailures = 0
let queries: QueryClient
async function open(roles = ['bid_owner'], userId = 'owner', expand = true) {
  const api = createApi(async () => 'test-bearer')
  const screen = await render(
    <QueryClientProvider client={queries}>
      <ReviewDesk
        tenderId='tender-1'
        actor={{ user_id: userId, workspace_id: 'workspace', roles } as never}
        api={api}
      />
    </QueryClientProvider>
  )
  if (expand && view.assessment) {
    await expect
      .element(
        screen.getByRole('table', { name: 'Qualification checks', exact: true })
      )
      .toBeVisible()
    await userEvent.click(
      screen.getByText('Decision and history', { exact: true })
    )
    await userEvent.click(
      screen.getByText('All extracted requirements', { exact: true })
    )
    if (
      Array.from(document.querySelectorAll('button')).some(
        (button) => button.textContent?.trim() === 'Assign question'
      )
    )
      await userEvent.click(
        screen.getByRole('button', { name: 'Assign question', exact: true })
      )
  }
  return screen
}
beforeEach(() => {
  view = structuredClone(initial)
  commands = []
  failure = undefined
  networkFailures = 0
  reviewFailures = 0
  uploadFailures = 0
  queries = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (init?.method && init.method !== 'GET') {
        const body =
          init.body instanceof FormData
            ? {
                ...JSON.parse(String(init.body.get('metadata'))),
                filenames: init.body
                  .getAll('files')
                  .map((file) => (file as File).name),
              }
            : JSON.parse(String(init.body))
        commands.push({ path, body })
        if (path.endsWith('/documents')) {
          if (uploadFailures-- > 0)
            throw new TypeError('Interrupted upload response')
          view.input_revision++
          view.assessment.is_current = false
        }
        if (path.endsWith('/analyses') && networkFailures-- > 0)
          throw new TypeError('Simulated interrupted connection')
        if (path.endsWith('/review-tasks')) {
          if (body.draft_ref === 'Q2' && reviewFailures-- > 0)
            throw new TypeError('Interrupted review response')
          const saved = {
            ...structuredClone(task),
            id: 'task-' + body.draft_ref,
            draft_ref: body.draft_ref,
            question:
              body.question ||
              view.assessment.candidate.review_requests.find(
                (draft) => draft.draft_ref === body.draft_ref
              )?.question,
          }
          view.review_tasks = [
            ...view.review_tasks.filter(
              (previous: { id: string }) => previous.id !== saved.id
            ),
            saved,
          ] as never
        }
        if (path.endsWith('/assistant-messages'))
          return Response.json({
            answer: 'Saturday availability is unconfirmed.',
            citations: [citation],
            review_request_drafts: [],
            is_current: true,
          })
        return Response.json(
          path.endsWith('/review-tasks')
            ? task
            : { id: 'job-1', input_revision: 3 }
        )
      }
      if (failure && path.endsWith('/tenders/tender-1'))
        return Response.json(
          {
            code: 'AUTH_UNAVAILABLE',
            message: 'Sign-in service unavailable.',
            retryable: true,
          },
          { status: failure }
        )
      if (path.endsWith('/tenders/tender-1')) return Response.json(view)
      if (path.endsWith('/members'))
        return Response.json({
          schema_version: 'm1.v1',
          items: [
            {
              user_id: 'reviewer',
              display_name: 'Fictional engineering reviewer',
              roles: ['service_reviewer'],
            },
          ],
        })
      if (path.endsWith('/sources/document-1'))
        return new Response('%PDF-1.4', {
          headers: { 'Content-Type': 'application/pdf' },
        })
      if (path.endsWith('/sources'))
        return Response.json({
          schema_version: 'm1.v1',
          assessment_version_id: 'assessment-1',
          anchors: [
            {
              anchor_id: 'tender-page-1',
              document_version_id: 'document-1',
              source_role: 'tender',
              page: 1,
              paragraph: null,
              text: citation.quote,
            },
            {
              anchor_id: 'addendum-page-1',
              document_version_id: 'document-2',
              source_role: 'addendum',
              page: 1,
              text: 'Provide three qualified technicians.',
            },
          ],
        })
      if (path.endsWith('/history'))
        return Response.json({
          schema_version: 'm1.v1',
          assessments: [],
          decisions: [],
        })
      return Response.json({})
    })
  )
})
describe('qualification review desk', () => {
  it('shows the blocked assessment and opens a cited source location', async () => {
    const screen = await open()
    await expect
      .element(
        screen.getByRole('heading', { name: 'Fictional campus maintenance' })
      )
      .toBeVisible()
    await expect
      .element(
        screen
          .getByRole('table', { name: 'Qualification checks', exact: true })
          .getByText('Needs confirmation', { exact: true })
          .first()
      )
      .toBeVisible()
    await userEvent.click(
      screen.getByRole('button', { name: 'tender.pdf', exact: true }).first()
    )
    await expect
      .element(screen.getByText(citation.quote, { exact: true }).first())
      .toBeVisible()
    await expect
      .element(screen.getByRole('complementary', { name: 'Source documents' }))
      .toBeVisible()
  })
  it('requires owner confirmation with a named assignee before creating a task', async () => {
    const screen = await open()
    await expect
      .element(
        screen.getByRole('heading', { name: 'Review questions', exact: true })
      )
      .toBeVisible()
    await userEvent.selectOptions(screen.getByLabelText('Assign to'), [
      'reviewer',
    ])
    await userEvent.click(
      screen.getByRole('button', { name: 'Assign question', exact: true })
    )
    await vi.waitFor(() => expect(commands).toHaveLength(1))
    expect(commands[0].body).toMatchObject({
      expected_assessment_version_id: 'assessment-1',
      draft_ref: 'Q1',
      assignee_id: 'reviewer',
    })
  })
  it('lets the assignee record a typed answer and shows reassessment progress', async () => {
    view.review_tasks = [structuredClone(task)] as never
    const screen = await open(['service_reviewer'], 'reviewer')
    await expect
      .element(
        screen.getByRole('heading', { name: 'Review questions', exact: true })
      )
      .toBeVisible()
    await userEvent.selectOptions(screen.getByLabelText('Answer kind'), [
      'unable_to_confirm',
    ])
    await userEvent.fill(
      screen.getByLabelText('Your answer'),
      'The rota is not available yet.'
    )
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Save answer and reassess',
        exact: true,
      })
    )
    await vi.waitFor(() =>
      expect(commands[0]?.body).toMatchObject({
        response_kind: 'unable_to_confirm',
        text: 'The rota is not available yet.',
        expected_task_revision: 1,
      })
    )
  })
  it('exposes decision controls only to an approver', async () => {
    const screen = await open(['viewer'])
    await expect
      .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
      .toBeVisible()
    await expect
      .element(
        screen.getByRole('button', {
          name: 'Record pursue decision',
          exact: true,
        })
      )
      .not.toBeInTheDocument()
    await expect
      .element(screen.getByText('An approver records the human decision.'))
      .toBeVisible()
  })
  it('marks changes non-current and disables approval after refresh', async () => {
    const screen = await open(['approver'])
    await expect
      .element(
        screen.getByRole('heading', { name: 'Fictional campus maintenance' })
      )
      .toBeVisible()
    view.assessment.is_current = false
    view.assessment_status = 'non_current'
    await queries.invalidateQueries({ queryKey: ['tender', 'tender-1'] })
    await expect
      .element(screen.getByText(/Inputs have changed/), { timeout: 7000 })
      .toBeVisible()
    await expect
      .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
      .toBeVisible()
    await expect
      .element(
        screen.getByRole('button', {
          name: 'Record pursue decision',
          exact: true,
        })
      )
      .toBeDisabled()
  })
  it('shows an unreadable job without claiming the assessment is ready', async () => {
    view.assessment = null as never
    view.assessment_status = 'not_ready'
    view.jobs = [
      {
        id: 'job-1',
        status: 'needs_input',
        attempt: 1,
        input_revision: 2,
        completed_stages: ['parsing'],
        warnings: [{ code: 'SOURCE_INCOMPLETE' }],
        error_code: 'SOURCE_INCOMPLETE',
        output_version_id: null,
      },
    ] as never
    const screen = await open()
    await expect
      .element(screen.getByText(/SOURCE_INCOMPLETE/).first())
      .toBeVisible()
    await expect
      .element(screen.getByText('The assessment needs attention.'))
      .toBeVisible()
  })
  it('pauses mutations when refresh fails instead of presenting cached readiness', async () => {
    const screen = await open(['approver'])
    await expect
      .element(
        screen.getByRole('heading', { name: 'Fictional campus maintenance' })
      )
      .toBeVisible()
    failure = 503
    await queries.invalidateQueries({ queryKey: ['tender', 'tender-1'] })
    await expect
      .element(
        screen
          .getByRole('alert')
          .filter({ hasText: 'Sign-in service unavailable.' }),
        { timeout: 7000 }
      )
      .toBeVisible()
    await expect
      .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
      .toBeVisible()
    await expect
      .element(
        screen.getByRole('button', {
          name: 'Record pursue decision',
          exact: true,
        })
      )
      .toBeDisabled()
  })
})

it('hides answer controls when an assigned member no longer has an answering role', async () => {
  view.review_tasks = [structuredClone(task)] as never
  const screen = await open(['viewer'], 'reviewer')
  await expect
    .element(
      screen.getByRole('heading', { name: 'Review questions', exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Save answer and reassess',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
})
it('retries an unknown mutation outcome with the same request identity', async () => {
  networkFailures = 1
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Reassess', exact: true })
  )
  await expect
    .element(screen.getByRole('button', { name: 'Retry same request' }))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await expect
    .element(screen.getByRole('menuitem', { name: 'Reassess', exact: true }))
    .toHaveAttribute('aria-disabled', 'true')
  await userEvent.keyboard('{Escape}')
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same request' })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(2))
  expect(commands[0].body.client_request_id).toBe(
    commands[1].body.client_request_id
  )
})
it('preserves the Singapore calendar date when correcting an early closing time', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Edit tender details', exact: true })
  )
  const panel = screen.getByRole('dialog', { name: 'Edit tender details' })
  await userEvent.fill(
    panel.getByLabelText(
      'Reviewed value (Singapore time; blank means unknown)'
    ),
    '2026-11-20T06:00'
  )
  await userEvent.selectOptions(
    panel.getByLabelText('Supporting source').first(),
    ['tender-page-1']
  )
  await userEvent.fill(
    panel.getByLabelText('Reason for correction').first(),
    'Reviewed the source deadline.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Save fact correction' })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(1))
  expect(commands[0].body).toMatchObject({
    edits: {
      key_facts: { closing_at: { value: '2026-11-20T06:00:00+08:00' } },
    },
  })
})

it('submits both reviewed source clauses when reconciling an amendment', async () => {
  const older = structuredClone(requirement)
  view.assessment.reconciliation = [
    {
      kind: 'missing_or_changed',
      requirement_id: 'old-id',
      resolved: false,
      previous_requirement: older,
    },
  ] as never
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', {
      name: 'Review changed obligations',
      exact: true,
    })
  )
  await userEvent.selectOptions(screen.getByLabelText('Affected obligation'), [
    'old-id',
  ])
  await userEvent.click(
    screen.getByLabelText(requirement.text, { exact: true })
  )
  await userEvent.selectOptions(
    screen
      .getByRole('group', { name: 'Supporting citation 1', exact: true })
      .getByLabelText('Supporting source'),
    ['tender-page-1']
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Add supporting citation', exact: true })
  )
  await userEvent.selectOptions(
    screen
      .getByRole('group', { name: 'Supporting citation 2', exact: true })
      .getByLabelText('Supporting source'),
    ['addendum-page-1']
  )
  await userEvent.fill(
    screen.getByLabelText('Reason for reconciliation'),
    'Reviewed the original and replacement clauses.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Save reviewed mapping', exact: true })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(1))
  expect(commands[0].body).toMatchObject({
    edits: {
      reconciliations: [
        {
          citations: [
            citation,
            {
              anchor_id: 'addendum-page-1',
              quote: 'Provide three qualified technicians.',
            },
          ],
        },
      ],
    },
  })
})

it('refreshes historical decision currency after an external input change without manual refresh', async () => {
  const decision = {
    id: 'decision-1',
    decision: 'hold',
    reason: 'Waiting for staffing.',
    actor_id: 'owner',
    created_at: '2026-10-24T01:00:00Z',
    is_current: true,
  }
  const original = globalThis.fetch
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/history'))
        return Response.json({
          assessments: [],
          decisions: [{ ...decision, is_current: view.assessment.is_current }],
        })
      return original(input, init)
    })
  )
  const screen = await open(['approver'])
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'View history', exact: true })
  )
  await expect
    .element(screen.getByText('hold · Current', { exact: true }))
    .toBeVisible()
  view.assessment.is_current = false
  view.input_revision++
  await expect
    .element(screen.getByText('hold · Non-current', { exact: true }), {
      timeout: 35000,
    })
    .toBeVisible()
}, 40000)

it('gives the explicit decision controls clear accessible names', async () => {
  const screen = await open(['approver'])
  await expect
    .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Record pursue decision',
        exact: true,
      })
    )
    .toBeVisible()
})

it('reads parsed DOCX content without a download action', async () => {
  view.documents[0].filename = 'tender.docx'
  view.documents[0].content_type =
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  const original = globalThis.fetch
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/sources/document-1'))
        return Response.json({
          anchors: [
            {
              anchor_id: 'p1',
              paragraph: 1,
              text: 'Fictional DOCX source paragraph.',
            },
          ],
        })
      return original(input, init)
    })
  )
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'Review source documents' })
  )
  await expect
    .element(
      screen.getByText('Fictional DOCX source paragraph.', { exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('link', {
        name: 'Download extracted source text',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
})

it('keeps sources optional and exposes every finding without stage tabs or demo badges', async () => {
  const extra = {
    ...structuredClone(requirement),
    local_ref: 'R2',
    text: 'Provide monthly reporting.',
    status: 'met',
  }
  view.assessment.requirements.push({
    id: 'b'.repeat(64),
    requirement: extra,
    carried_forward: false,
  })
  const screen = await open()
  await expect
    .element(
      screen.getByRole('heading', { name: 'Fictional campus maintenance' })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('cell', { name: /^Provide monthly reporting/ }))
    .toBeVisible()
  await expect.element(screen.getByRole('tab')).not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('complementary', { name: 'Source documents' }))
    .not.toBeInTheDocument()
  await expect.element(screen.getByText(/Demo tender/)).not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Review source documents', exact: true })
  )
  await expect
    .element(screen.getByRole('complementary', { name: 'Source documents' }))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Close source documents', exact: true })
  )
  await expect
    .element(screen.getByRole('complementary', { name: 'Source documents' }))
    .not.toBeInTheDocument()
})

it('distinguishes a queued job from active work and returns to the assessment after completion', async () => {
  view.assessment = null as never
  view.assessment_status = 'not_ready'
  const job = {
    id: 'job-1',
    status: 'queued',
    attempt: 0,
    input_revision: 2,
    completed_stages: [] as string[],
    warnings: [],
    error_code: null,
    output_version_id: null,
  }
  view.jobs = [job] as never
  const screen = await open()
  await expect
    .element(
      screen.getByRole('heading', {
        name: 'Waiting for processing',
        exact: true,
      })
    )
    .toBeVisible()
  await expect.element(screen.getByRole('progressbar')).not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', { name: 'Review questions', exact: true })
    )
    .not.toBeInTheDocument()

  job.status = 'running'
  job.attempt = 1
  await expect
    .element(
      screen.getByRole('heading', {
        name: 'Reading your documents',
        exact: true,
      }),
      { timeout: 7000 }
    )
    .toBeVisible()
  await expect.element(screen.getByRole('progressbar')).toBeInTheDocument()

  job.status = 'completed'
  job.completed_stages = [
    'source_manifest',
    'parsing',
    'analysis',
    'validation',
  ]
  view.assessment = structuredClone(assessment)
  view.assessment_status = 'current'
  await expect
    .element(
      screen.getByRole('heading', { name: 'Review questions', exact: true }),
      { timeout: 7000 }
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('region', { name: 'Tender processing' }))
    .not.toBeInTheDocument()
})

it('shows honest processing without cancellation or a ready assessment', async () => {
  view.assessment = null as never
  view.jobs = [
    {
      id: 'job-1',
      status: 'running',
      input_revision: 2,
      completed_stages: ['parsing'],
      warnings: [],
      error_code: null,
    },
  ] as never
  const screen = await open()
  await expect
    .element(
      screen.getByRole('heading', {
        name: 'Preparing your assessment',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'Cancel processing' }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: 'Continue to decision' }))
    .not.toBeInTheDocument()
  await userEvent.click(screen.getByText('Source coverage', { exact: true }))
  await expect
    .element(
      screen.getByRole('button', { name: 'tender.pdf', exact: true }).first()
    )
    .toBeVisible()
})

it('records an explicit pursue decision without a second review checkbox', async () => {
  view.assessment.blockers = []
  view.assessment.requirements[0].requirement.status = 'met'
  view.assessment.candidate.review_requests = []
  view.assessment.candidate.recommendation.decision = 'pursue'
  const screen = await open(['approver'])
  await expect
    .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
    .toBeVisible()
  await expect.element(screen.getByRole('checkbox')).not.toBeInTheDocument()
  await userEvent.fill(
    screen.getByLabelText('Decision reason'),
    'Reviewed the current assessment.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Record pursue decision', exact: true })
  )
  await vi.waitFor(() =>
    expect(commands[0]?.body).toMatchObject({
      expected_input_revision: 2,
      assessment_version_id: 'assessment-1',
      decision: 'pursue',
      review_complete: true,
      reason: 'Reviewed the current assessment.',
    })
  )
})

it('persists an edited question with its selected assignee and due date', async () => {
  const screen = await open()
  await expect
    .element(
      screen.getByRole('heading', { name: 'Review questions', exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'Review source documents' }))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Edit', exact: true })
  )
  await userEvent.fill(
    screen.getByLabelText('Question', { exact: true }),
    'Can we confirm the Saturday rota?'
  )
  await userEvent.selectOptions(
    screen.getByLabelText('Assign to', { exact: true }),
    ['reviewer']
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Assign question', exact: true })
  )
  await vi.waitFor(() =>
    expect(commands[0]?.body).toMatchObject({
      expected_assessment_version_id: 'assessment-1',
      draft_ref: 'Q1',
      assignee_id: 'reviewer',
      question: 'Can we confirm the Saturday rota?',
      due_at: expect.any(String),
    })
  )
})

it('retries the interrupted check assignment without resending its completed predecessor', async () => {
  view.assessment.requirements.push({
    id: 'b'.repeat(64),
    carried_forward: false,
    requirement: {
      ...structuredClone(requirement),
      local_ref: 'R2',
      text: 'Confirm mobilisation readiness.',
    },
  })
  view.assessment.candidate.review_requests.push({
    ...structuredClone(view.assessment.candidate.review_requests[0]),
    draft_ref: 'Q2',
    requirement_refs: ['R2'],
    question: 'Can we confirm mobilisation?',
  })
  reviewFailures = 1
  const screen = await open()
  await userEvent.selectOptions(
    screen.getByLabelText('Assign to', { exact: true }),
    ['reviewer']
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Assign question', exact: true })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(1))
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Review check: Confirm mobilisation readiness.',
      exact: true,
    })
  )
  if (!screen.getByLabelText('Assign to', { exact: true }).elements().length)
    await userEvent.click(
      screen.getByRole('button', { name: 'Assign question', exact: true })
    )
  await userEvent.selectOptions(
    screen.getByLabelText('Assign to', { exact: true }),
    ['reviewer']
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Assign question', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same request' })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(3))
  expect(commands.map((command) => command.body.draft_ref)).toEqual([
    'Q1',
    'Q2',
    'Q2',
  ])
  expect(commands[1].body.client_request_id).toBe(
    commands[2].body.client_request_id
  )
})

it('opens compact actions and a focused upload task without the general popup', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await expect.element(screen.getByRole('menu')).toBeVisible()
  await expect
    .element(screen.getByRole('dialog', { name: 'Tender actions' }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('menuitem', { name: 'Refresh', exact: true }))
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Add documents', exact: true })
  )
  await expect
    .element(screen.getByRole('dialog', { name: 'Add documents', exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByText('Drag files here to add them'))
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Requirement to correct'))
    .not.toBeInTheDocument()
  expect(commands).toHaveLength(0)
})

it('opens row correction with that requirement already selected', async () => {
  view.assessment.requirements.push({
    id: 'b'.repeat(64),
    requirement: {
      ...structuredClone(requirement),
      local_ref: 'R2',
      text: 'Monthly reporting needs confirmation.',
    },
    carried_forward: false,
  })
  const screen = await open()
  const row = screen
    .getByRole('row')
    .filter({ hasText: 'Monthly reporting needs confirmation.' })
  await userEvent.click(row.getByRole('button', { name: /Finding actions/ }))
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Correct finding', exact: true })
  )
  const dialog = screen.getByRole('dialog', {
    name: 'Correct finding',
    exact: true,
  })
  await expect
    .element(
      dialog.getByText('Monthly reporting needs confirmation.', { exact: true })
    )
    .toBeVisible()
  await expect
    .element(dialog.getByLabelText('Requirement to correct'))
    .not.toBeInTheDocument()
  await userEvent.fill(
    dialog.getByLabelText('Reason for correction'),
    'Reviewed the reporting requirement.'
  )
  await userEvent.click(
    dialog.getByRole('button', { name: 'Save finding correction' })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(1))
  expect(commands[0].body).toMatchObject({
    expected_assessment_version_id: 'assessment-1',
    edits: {
      requirements: [{ requirement_id: 'b'.repeat(64), status: 'unconfirmed' }],
    },
  })
  await expect.element(dialog).not.toBeInTheDocument()
})

it('shows history in the optional dock and restores the source action on close', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'View history', exact: true })
  )
  await expect
    .element(
      screen.getByRole('complementary', { name: 'History', exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByText('No decision recorded.', { exact: true }))
    .toBeVisible()
  await expect.element(screen.getByRole('dialog')).not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Close history', exact: true })
  )
  await expect
    .element(
      screen.getByRole('complementary', { name: 'History', exact: true })
    )
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', {
        name: 'Review source documents',
        exact: true,
      })
    )
    .toBeVisible()
})

it('preserves addendum metadata and the request identity across an interrupted upload', async () => {
  uploadFailures = 1
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Add documents', exact: true })
  )
  const dialog = screen.getByRole('dialog', {
    name: 'Add documents',
    exact: true,
  })
  await userEvent.upload(dialog.getByLabelText('Tender files'), [
    new File(['pack'], 'Addendum.pdf', { type: 'application/pdf' }),
  ])
  await userEvent.click(dialog.getByText('Document options', { exact: true }))
  await userEvent.selectOptions(dialog.getByLabelText('Document type'), [
    'addendum',
  ])
  await userEvent.selectOptions(dialog.getByLabelText('Updates document'), [
    'document-1',
  ])
  await userEvent.click(
    dialog.getByRole('button', { name: 'Add documents', exact: true })
  )
  await expect
    .element(dialog.getByRole('button', { name: 'Retry same request' }))
    .toBeVisible()
  await expect
    .element(dialog.getByRole('button', { name: 'Cancel', exact: true }))
    .toBeDisabled()
  await userEvent.click(
    dialog.getByRole('button', { name: 'Close', exact: true })
  )
  await expect.element(dialog).toBeVisible()
  await userEvent.click(
    dialog.getByRole('button', { name: 'Retry same request' })
  )
  await vi.waitFor(() => expect(commands).toHaveLength(2))
  expect(commands[0].body).toMatchObject({
    expected_input_revision: 2,
    filenames: ['Addendum.pdf'],
    files: [{ role: 'addendum', amends_version_id: 'document-1' }],
  })
  expect(commands[0].body.client_request_id).toBe(
    commands[1].body.client_request_id
  )
  expect(commands.map((command) => command.path)).toEqual([
    '/api/v1/tenders/tender-1/documents',
    '/api/v1/tenders/tender-1/documents',
  ])
  await expect.element(dialog).not.toBeInTheDocument()
})

it('keeps owner-only edits out of the viewer menu', async () => {
  const screen = await open(['viewer'])
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await expect
    .element(
      screen.getByRole('menuitem', { name: 'View history', exact: true })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('menuitem', { name: 'Add documents', exact: true })
    )
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('menuitem', { name: 'Edit tender details', exact: true })
    )
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: /Finding actions:/ }))
    .not.toBeInTheDocument()
})

it('keeps the decision draft when the history dock opens and closes', async () => {
  const screen = await open(['approver'])
  await expect
    .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
    .toBeVisible()
  await userEvent.fill(
    screen.getByLabelText('Decision reason'),
    'Waiting for the operational review.'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'View history', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Close history', exact: true })
  )
  await expect
    .element(screen.getByLabelText('Decision reason'))
    .toHaveValue('Waiting for the operational review.')
  expect(commands).toHaveLength(0)
})

it('opens the grounded assistant in the dock and follows its source citation', async () => {
  const screen = await open()
  await userEvent.click(
    screen.getByRole('button', { name: 'More tender actions' })
  )
  await userEvent.click(
    screen.getByRole('menuitem', { name: 'Ask about assessment', exact: true })
  )
  const assistant = screen.getByRole('complementary', {
    name: 'Assistant',
    exact: true,
  })
  await userEvent.fill(
    assistant.getByLabelText('Assessment question'),
    'Why is Saturday staffing unconfirmed?'
  )
  await userEvent.click(
    assistant.getByRole('button', { name: 'Ask assistant', exact: true })
  )
  await expect
    .element(
      assistant.getByText('Saturday availability is unconfirmed.', {
        exact: true,
      })
    )
    .toBeVisible()
  expect(commands[0].body).toMatchObject({
    assessment_version_id: 'assessment-1',
    text: 'Why is Saturday staffing unconfirmed?',
  })
  await userEvent.click(
    assistant.getByRole('button', { name: 'Answer source 1', exact: true })
  )
  await expect
    .element(
      screen.getByRole('complementary', {
        name: 'Source documents',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(screen.getByText(citation.quote, { exact: true }).first())
    .toBeVisible()
})

it('opens a focused task by keyboard and restores focus after Escape', async () => {
  const screen = await open()
  const trigger = screen.getByRole('button', { name: 'More tender actions' })
  await expect.element(trigger).toBeVisible()
  trigger.element().focus()
  await userEvent.keyboard('{ArrowDown}')
  await expect
    .element(
      screen.getByRole('menuitem', { name: 'Add documents', exact: true })
    )
    .toHaveFocus()
  await userEvent.keyboard('{Enter}')
  await expect
    .element(screen.getByRole('dialog', { name: 'Add documents', exact: true }))
    .toBeVisible()
  await userEvent.keyboard('{Escape}')
  await expect
    .element(screen.getByRole('dialog', { name: 'Add documents', exact: true }))
    .not.toBeInTheDocument()
  await expect.element(trigger).toHaveFocus()
  expect(commands).toHaveLength(0)
})

it('keeps assessment, questions and decision in the same tender review', async () => {
  const screen = await open(['bid_owner', 'approver'])
  await expect
    .element(
      screen.getByRole('heading', { name: 'Review questions', exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('table', { name: 'Requirements and findings' }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('button', { name: 'Review questions', exact: true })
    )
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', { name: 'Record a decision', exact: true })
    )
    .not.toBeInTheDocument()
  await expect
    .element(
      screen.getByRole('button', { name: 'Continue to decision', exact: true })
    )
    .not.toBeInTheDocument()
})

it('keeps an unsaved decision mounted while an existing assessment is reassessed', async () => {
  const screen = await open(['bid_owner', 'approver'])
  await expect
    .element(screen.getByRole('heading', { name: 'Decision', exact: true }))
    .toBeVisible()
  await userEvent.fill(
    screen.getByLabelText('Decision reason'),
    'Keep this review draft.'
  )
  view.jobs = [
    {
      id: 'new-job',
      status: 'queued',
      attempt: 0,
      input_revision: 2,
      completed_stages: [],
      warnings: [],
      error_code: null,
      output_version_id: null,
    },
  ] as never
  await queries.invalidateQueries({ queryKey: ['tender', 'tender-1'] })
  await expect
    .element(screen.getByText('Preparing a new assessment…', { exact: true }), {
      timeout: 35000,
    })
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Decision reason'))
    .toHaveValue('Keep this review draft.')
  await expect
    .element(screen.getByRole('table', { name: 'Requirements and findings' }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'Hold', exact: true }))
    .toBeDisabled()
})

it('retains answer and decision drafts after a reassessment publishes a new version', async () => {
  view.review_tasks = [structuredClone(task)] as never
  const screen = await open(['service_reviewer', 'approver'], 'reviewer')
  await userEvent.fill(
    screen.getByLabelText('Your answer'),
    'Keep this answer draft.'
  )
  await userEvent.fill(
    screen.getByLabelText('Decision reason'),
    'Keep this decision draft.'
  )
  view.assessment = { ...structuredClone(assessment), id: 'assessment-next' }
  view.assessment.candidate.key_facts.title.value = 'Updated campus assessment'
  await queries.invalidateQueries({ queryKey: ['tender', 'tender-1'] })
  await expect
    .element(
      screen.getByRole('heading', {
        name: 'Updated campus assessment',
        exact: true,
      }),
      { timeout: 7000 }
    )
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Your answer'))
    .toHaveValue('Keep this answer draft.')
  await expect
    .element(screen.getByLabelText('Decision reason'))
    .toHaveValue('Keep this decision draft.')
})

it('uses the newly published assessment for new question assignments', async () => {
  const screen = await open()
  await expect
    .element(
      screen.getByRole('heading', { name: 'Review questions', exact: true })
    )
    .toBeVisible()
  view.assessment = { ...structuredClone(assessment), id: 'assessment-next' }
  view.assessment.candidate.key_facts.title.value = 'Updated campus assessment'
  view.assessment.candidate.review_requests[0].question =
    'Confirm the revised staffing requirement.'
  await queries.invalidateQueries({ queryKey: ['tender', 'tender-1'] })
  await expect
    .element(
      screen.getByText('Confirm the revised staffing requirement.', {
        exact: true,
      }),
      { timeout: 7000 }
    )
    .toBeVisible()
  await userEvent.selectOptions(
    screen.getByLabelText('Assign to', { exact: true }),
    ['reviewer']
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Assign question', exact: true })
  )
  await vi.waitFor(() =>
    expect(commands[0]?.body).toMatchObject({
      expected_assessment_version_id: 'assessment-next',
      draft_ref: 'Q1',
      assignee_id: 'reviewer',
    })
  )
})

describe('qualification check panel', () => {
  it('keeps qualification work separate and reuses the existing assigned question', async () => {
    view.review_tasks = [
      { ...structuredClone(task), draft_ref: 'manual-question' },
    ] as never
    view.assessment.requirements.push({
      id: 'c'.repeat(64),
      requirement: {
        ...structuredClone(requirement),
        local_ref: 'R3',
        kind: 'submission',
        text: 'Submit the customer price schedule.',
        status: 'not_assessed',
      },
      carried_forward: false,
    })
    const screen = await open(['bid_owner'], 'owner', false)
    const panel = screen.getByRole('complementary', {
      name: 'Check details',
      exact: true,
    })
    await expect.element(panel).toBeVisible()
    await expect
      .element(
        screen.getByRole('table', { name: 'Qualification checks', exact: true })
      )
      .toBeVisible()
    await expect
      .element(
        screen.getByText('1 qualification check needs confirmation.', {
          exact: true,
        })
      )
      .toBeVisible()
    await expect
      .element(
        screen
          .getByRole('table', { name: 'Qualification checks', exact: true })
          .getByText('Submit the customer price schedule.', { exact: true })
      )
      .not.toBeInTheDocument()
    await expect
      .element(screen.getByRole('complementary', { name: 'Tender properties' }))
      .not.toBeInTheDocument()
    await expect
      .element(panel.getByText(task.question, { exact: true }))
      .toBeVisible()
    await expect
      .element(panel.getByLabelText('Assign to'))
      .not.toBeInTheDocument()
    expect(commands).toHaveLength(0)
  })

  it('updates the contextual evidence when another check is selected and can close the panel', async () => {
    view.review_tasks = [
      { ...structuredClone(task), assignee_id: 'owner' },
    ] as never
    const extra = {
      ...structuredClone(requirement),
      local_ref: 'R2',
      text: 'Provide monthly reporting.',
      tender_citations: [
        { anchor_id: 'tender-page-1', quote: 'Monthly reporting is required.' },
      ],
    }
    view.assessment.requirements.push({
      id: 'b'.repeat(64),
      requirement: extra,
      carried_forward: false,
    })
    const screen = await open(['bid_owner'], 'owner', false)
    await expect
      .element(screen.getByRole('complementary', { name: 'Check details' }))
      .toBeVisible()
    await userEvent.fill(
      screen.getByLabelText('Your answer', { exact: true }),
      'Unfinished staffing response.'
    )
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Review check: Provide monthly reporting.',
        exact: true,
      })
    )
    const panel = screen.getByRole('complementary', { name: 'Check details' })
    await expect
      .element(
        panel.getByText('Monthly reporting is required.', { exact: true })
      )
      .toBeVisible()
    await userEvent.click(
      panel.getByRole('button', { name: 'Close check details', exact: true })
    )
    await vi.waitFor(() =>
      expect(
        document
          .querySelector('aside[aria-label="Check details"]')
          ?.hasAttribute('hidden')
      ).toBe(true)
    )
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Review check: Provide monthly reporting.',
        exact: true,
      })
    )
    await expect
      .element(screen.getByRole('complementary', { name: 'Check details' }))
      .toBeVisible()
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Review check: ' + requirement.text,
        exact: true,
      })
    )
    await expect
      .element(screen.getByLabelText('Your answer', { exact: true }))
      .toHaveValue('Unfinished staffing response.')
    expect(commands).toHaveLength(0)
  })
})

it('separates eligibility from a large delivery checklist without dropping findings', async () => {
  view.assessment.requirements = [
    ...Array.from({ length: 2 }, (_, i) => ({
      id: 'eligibility-' + i,
      requirement: {
        ...structuredClone(requirement),
        local_ref: 'E' + i,
        kind: 'eligibility',
        text: 'Eligibility gate ' + i,
      },
      carried_forward: false,
    })),
    ...Array.from({ length: 40 }, (_, i) => ({
      id: 'delivery-' + i,
      requirement: {
        ...structuredClone(requirement),
        local_ref: 'D' + i,
        text: 'Delivery capability ' + i,
      },
      carried_forward: false,
    })),
  ]
  const screen = await open(['bid_owner'], 'owner', false)
  const table = screen.getByRole('table', {
    name: 'Qualification checks',
    exact: true,
  })
  await expect
    .element(
      table.getByRole('button', {
        name: 'Review check: Eligibility gate 0',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(
      table.getByRole('button', {
        name: 'Review check: Delivery capability 0',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Delivery (40)', exact: true })
  )
  await expect
    .element(
      table.getByRole('button', {
        name: 'Review check: Delivery capability 39',
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(
      table.getByRole('button', {
        name: 'Review check: Eligibility gate 0',
        exact: true,
      })
    )
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Eligibility (2)', exact: true })
  )
  await expect
    .element(
      table.getByRole('button', {
        name: 'Review check: Eligibility gate 1',
        exact: true,
      })
    )
    .toBeVisible()
  expect(commands).toHaveLength(0)
})

it('does not repeatedly fetch an idle tender or its history every two seconds', async () => {
  await open(['viewer'], 'viewer', false)
  await vi.waitFor(() =>
    expect(queries.getQueryData(['history', 'tender-1'])).toBeDefined()
  )
  const calls = () =>
    vi
      .mocked(fetch)
      .mock.calls.filter(([path]) =>
        [
          '/api/v1/tenders/tender-1',
          '/api/v1/tenders/tender-1/history',
        ].includes(String(path))
      ).length
  const initialCalls = calls()
  await new Promise((resolve) => setTimeout(resolve, 2300))
  expect(calls()).toBe(initialCalls)
})

it('continues refreshing a running analysis promptly', async () => {
  view.jobs = [{ id: 'job-1', status: 'running' }] as never
  await open(['viewer'], 'viewer', false)
  await vi.waitFor(
    () =>
      expect(
        vi
          .mocked(fetch)
          .mock.calls.filter(
            ([path]) => String(path) === '/api/v1/tenders/tender-1'
          ).length
      ).toBeGreaterThan(1),
    { timeout: 3500 }
  )
})
