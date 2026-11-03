import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { createApi } from './api'
import { CompanyEvidence } from './company-evidence'
import research from './company-research.json'

let company: Record<string, unknown>
let commands: { path: string; body: Record<string, unknown> }[]
let conflict: boolean
beforeEach(() => {
  company = {
    schema_version: 'm1.v1',
    evidence_revision: 0,
    current: null,
    history: [],
  }
  commands = []
  conflict = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input, init) => {
      if (init?.method === 'POST') {
        const body =
          init.body instanceof FormData
            ? JSON.parse(String(init.body.get('metadata')))
            : JSON.parse(String(init.body))
        commands.push({ path: String(input), body })
        if (conflict) {
          company.evidence_revision = 1
          return new Response(
            JSON.stringify({
              code: 'STALE_EVIDENCE',
              message: 'Company changed; refresh before saving.',
            }),
            { status: 409 }
          )
        }
        company = {
          ...company,
          evidence_revision: 1,
          current: {
            id: 'profile-1',
            evidence_revision: 1,
            created_by: 'admin',
            created_at: '2026-10-28T02:00:00Z',
            effective_on: '2026-10-28',
            expires_on: null,
            filename: 'Company.docx',
            reason: body.reason,
            profile: body.profile,
            reference_text: null,
          },
        }
        return Response.json({ id: 'profile-1', evidence_revision: 1 })
      }
      if (String(input).includes('/company-evidence/versions/'))
        return Response.json({
          id: 'old-version',
          evidence_revision: 1,
          created_by: 'admin',
          created_at: '2026-10-28T02:00:00Z',
          effective_on: '2026-10-28',
          expires_on: null,
          filename: 'Company.docx',
          reason: 'Earlier company knowledge',
          profile: {
            content: '# Earlier company\n\nEarlier company knowledge.',
            sources: [],
          },
          reference_text: null,
        })
      return Response.json(company)
    })
  )
})
function setup(roles: string[]) {
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={cache}>
      <CompanyEvidence
        actor={{ user_id: 'admin', workspace_id: 'workspace', roles } as never}
        api={createApi(async () => 'token')}
      />
    </QueryClientProvider>
  )
}
it('shows sourced Company knowledge and public awards to members without editing controls', async () => {
  const screen = await setup(['viewer'])
  await expect
    .element(screen.getByRole('heading', { name: 'Company', exact: true }))
    .toBeVisible()
  await expect.element(screen.getByText(/UEN 197100922N/).first()).toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'Edit company' }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: 'Upload source' }))
    .not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('tab', { name: 'Track record' }))
  await expect
    .element(screen.getByRole('table', { name: 'Public contract awards' }))
    .toBeVisible()
  expect(
    screen.getByRole('table').query()!.querySelectorAll('tbody tr')
  ).toHaveLength(16)
  await userEvent.click(screen.getByRole('tab', { name: 'Sources' }))
  await expect
    .element(
      screen.getByRole('link', { name: 'S01 · BCA company registrations' })
    )
    .toHaveAttribute('href', research.profile.sources[0].url)
  await expect
    .element(screen.getByRole('button', { name: 'Save company' }))
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('tab', { name: 'History', exact: true })
  )
  await expect.element(screen.getByText('No saved versions yet.')).toBeVisible()
})
it('lets an admin save the editable profile and its original source links', async () => {
  const screen = await setup(['admin'])
  await expect
    .element(screen.getByRole('button', { name: 'Upload source', exact: true }))
    .not.toBeInTheDocument()
  for (const name of ['Track record', 'History']) {
    await userEvent.click(screen.getByRole('tab', { name, exact: true }))
    await expect
      .element(
        screen.getByRole('button', { name: 'Edit company', exact: true })
      )
      .not.toBeInTheDocument()
    await expect
      .element(
        screen.getByRole('button', { name: 'Upload source', exact: true })
      )
      .not.toBeInTheDocument()
  }
  await userEvent.click(
    screen.getByRole('tab', { name: 'Overview', exact: true })
  )
  await userEvent.click(screen.getByRole('button', { name: 'Edit company' }))
  await userEvent.fill(
    screen.getByRole('textbox', { name: 'Company document' }),
    'Confirm the mobilisation team before bidding.'
  )

  await userEvent.click(
    screen.getByRole('button', { name: 'Save company', exact: true })
  )
  await expect
    .element(
      screen.getByText(
        'Company saved. Existing tender assessments need reassessment.'
      )
    )
    .toBeVisible()
  expect(commands[0].path).toBe('/api/v1/company-evidence/profile')
  expect(commands[0].body.expected_evidence_revision).toBe(0)
  expect((commands[0].body.profile as typeof research.profile).sources).toEqual(
    research.profile.sources
  )
  await expect
    .element(screen.getByText('Confirm the mobilisation team before bidding.'))
    .toBeVisible()
  expect((commands[0].body.profile as typeof research.profile).content).toBe(
    'Confirm the mobilisation team before bidding.'
  )
  await userEvent.click(
    screen.getByRole('tab', { name: 'Sources', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Edit sources', exact: true })
  )
  await expect
    .element(screen.getByRole('textbox', { name: 'Company document' }))
    .not.toBeInTheDocument()
  await userEvent.fill(
    screen.getByRole('textbox', { name: 'Source title 1', exact: true }),
    'Company website'
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Save sources', exact: true })
  )
  await expect
    .element(screen.getByRole('link', { name: 'Company website', exact: true }))
    .toBeVisible()
  expect((commands[1].body.profile as typeof research.profile).content).toBe(
    'Confirm the mobilisation team before bidding.'
  )
})
it('retains an admin draft and its original revision when another admin saves first', async () => {
  const screen = await setup(['admin'])
  await userEvent.click(screen.getByRole('button', { name: 'Edit company' }))
  await userEvent.fill(
    screen.getByRole('textbox', { name: 'Company document' }),
    'Keep this unfinished draft.'
  )

  conflict = true
  await userEvent.click(
    screen.getByRole('button', { name: 'Save company', exact: true })
  )
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('Company changed; refresh before saving.')
  await expect
    .element(screen.getByRole('textbox', { name: 'Company document' }))
    .toHaveValue('Keep this unfinished draft.')
  expect(commands[0].body.expected_evidence_revision).toBe(0)
  await expect
    .element(screen.getByRole('button', { name: 'Reload saved version' }))
    .toBeVisible()
})

it('opens source upload from the primary header action and closes without changing content', async () => {
  const screen = await setup(['admin'])
  await userEvent.click(
    screen.getByRole('tab', { name: 'Sources', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload source', exact: true })
  )
  await expect
    .element(screen.getByRole('dialog', { name: 'Upload source' }))
    .toBeVisible()
  await expect
    .element(screen.getByLabelText('Company reference file'))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Cancel', exact: true })
  )
  await expect.element(screen.getByRole('dialog')).not.toBeInTheDocument()
  expect(commands).toHaveLength(0)
})

it('recovers a stale source upload without losing the file or entered metadata', async () => {
  const screen = await setup(['admin'])
  await userEvent.click(
    screen.getByRole('tab', { name: 'Sources', exact: true })
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload source', exact: true })
  )
  await userEvent.upload(screen.getByLabelText('Company reference file'), [
    new File(['reference'], 'CBM-reference.pdf', { type: 'application/pdf' }),
  ])
  await userEvent.fill(
    screen.getByLabelText('Effective on', { exact: true }),
    '2026-10-28'
  )
  await userEvent.fill(
    screen.getByRole('textbox', { name: 'Acceptance reason' }),
    'New public reference'
  )
  await userEvent.click(screen.getByRole('checkbox'))
  conflict = true
  await userEvent.click(
    screen.getByRole('button', { name: 'Accept company evidence', exact: true })
  )
  await expect
    .element(screen.getByRole('button', { name: 'Use latest company version' }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('textbox', { name: 'Acceptance reason' }))
    .toHaveValue('New public reference')
  expect(
    (
      screen
        .getByLabelText('Company reference file')
        .query() as HTMLInputElement
    ).files?.[0].name
  ).toBe('CBM-reference.pdf')
  await userEvent.click(
    screen.getByRole('button', { name: 'Use latest company version' })
  )
  conflict = false
  await userEvent.click(
    screen.getByRole('button', { name: 'Accept company evidence', exact: true })
  )
  await expect.element(screen.getByRole('dialog')).not.toBeInTheDocument()
  expect(
    commands.map((command) => command.body.expected_evidence_revision)
  ).toEqual([0, 1])
})

it('shows the chosen historical document in a read-only right panel', async () => {
  company.history = [
    {
      id: 'old-version',
      evidence_revision: 1,
      created_by: 'admin',
      created_at: '2026-10-28T02:00:00Z',
      effective_on: '2026-10-28',
      expires_on: null,
      filename: 'Company.docx',
      reason: 'Earlier company knowledge',
      profile: null,
      reference_text: null,
    },
  ]
  const screen = await setup(['viewer'])
  await userEvent.click(
    screen.getByRole('tab', { name: 'History', exact: true })
  )
  await expect
    .element(screen.getByRole('button', { name: 'Download version' }))
    .not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'See version', exact: true })
  )
  await expect
    .element(
      screen.getByRole('complementary', { name: 'Company version details' })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByRole('heading', { name: 'Earlier company', exact: true })
    )
    .toBeVisible()
  expect(document.querySelectorAll('textarea')).toHaveLength(0)
  expect(commands).toHaveLength(0)
  await userEvent.click(
    screen.getByRole('button', { name: 'Close version', exact: true })
  )
  await expect
    .element(
      screen.getByRole('complementary', { name: 'Company version details' })
    )
    .not.toBeInTheDocument()
})
