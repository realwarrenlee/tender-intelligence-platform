import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { page, userEvent } from 'vitest/browser'
import type { Actor, Api } from './api'
import { PreparationPanel } from './preparation-panel'

it('links a requirement to approved wording and saves the draft against the displayed versions', async () => {
  const send = vi.fn().mockResolvedValue({ version: 2 })
  const requestEvidence = vi.fn()
  const source = vi.fn()
  const get = vi.fn(async (path: string) =>
    path.endsWith('/proposal')
      ? {
          entity: 'Fictional FM Pte Ltd',
          company_version_id: 'company-version',
          company_filename: 'approved-company.docx',
          wording: [
            {
              id: 'approved',
              text: 'Fictional FM Pte Ltd will roster qualified HVAC technicians before mobilisation.',
              location: 'Paragraph 2',
            },
          ],
          requirements: [
            {
              id: 'staff',
              statement: 'Minimum HVAC staffing',
              section: 'Delivery approach',
              citations: [
                {
                  anchor_id: 'staffing',
                  quote: 'Minimum staffing is due during mobilisation.',
                },
              ],
              request_ref: 'proposal:staff',
              question: 'Provide current staffing evidence.',
            },
          ],
          can_request_input: true,
        }
      : {
          approval_id: 'approval',
          can_create: false,
          items: [
            {
              id: 'technical',
              kind: 'technical_response',
              revision: 5,
              plan_revision: 2,
              screening_version_id: 'screening',
              owner_id: 'owner',
              reviewer_id: 'reviewer',
              status: 'draft',
              due_at: '2098-12-29T09:00:00+08:00',
              findings: [],
              files: [],
              reviews: [],
              previous_plans: [],
              permitted_actions: ['draft_proposal'],
            },
          ],
        }
  )
  const api = { send, get } as unknown as Api
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PreparationPanel
        api={api}
        actor={{ user_id: 'owner' } as Actor}
        tenderId='tender'
        members={[]}
        findings={[]}
        onOpen={source}
        onChange={vi.fn()}
        onRequestProposal={requestEvidence}
      />
    </QueryClientProvider>
  )
  expect(get).not.toHaveBeenCalledWith(expect.stringMatching(/\/proposal$/))
  await page.getByText('Proposal drafting', { exact: true }).click()
  await expect
    .element(page.getByText('Evidence needed for this response.'))
    .toBeVisible()
  await page.getByRole('button', { name: 'Request evidence' }).click()
  expect(requestEvidence).toHaveBeenCalledWith(
    expect.objectContaining({ request_ref: 'proposal:staff' }),
    expect.any(HTMLElement)
  )
  expect(send).not.toHaveBeenCalled()
  await page.getByRole('button', { name: 'Tender source 1' }).click()
  expect(source).toHaveBeenCalledWith(
    'screening',
    expect.objectContaining({ anchor_id: 'staffing' })
  )
  await userEvent.selectOptions(
    page.getByLabelText('Approved response wording'),
    'approved'
  )
  await expect
    .element(page.getByText('Company evidence · Paragraph 2'))
    .toBeVisible()
  await page
    .getByRole('button', { name: 'Generate and save proposal draft' })
    .click()
  await expect
    .element(page.getByText('Proposal draft saved as version 2.'))
    .toBeVisible()
  expect(send).toHaveBeenCalledWith(
    '/tenders/tender/preparation/technical/proposal',
    expect.objectContaining({
      action: 'draft_proposal',
      expected_revision: 5,
      approval_id: 'approval',
      company_version_id: 'company-version',
      selections: { staff: 'approved' },
    })
  )
})
