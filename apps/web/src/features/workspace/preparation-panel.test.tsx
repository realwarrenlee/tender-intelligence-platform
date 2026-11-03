import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { page } from 'vitest/browser'
import type { Actor, Api } from './api'
import { PreparationPanel } from './preparation-panel'

it('opens assigned review work without mutating it and sends the displayed revision on explicit acceptance', async () => {
  const send = vi.fn().mockResolvedValue({})
  const get = vi.fn().mockResolvedValue({
    approval_id: 'approval',
    can_create: false,
    items: [
      {
        id: 'deliverable',
        kind: 'technical_response',
        revision: 3,
        owner_id: 'owner',
        reviewer_id: 'reviewer',
        status: 'in_review',
        proposal_requires_confirmation: true,
        due_at: '2098-12-29T09:00:00+08:00',
        findings: [
          { id: 'staffing', statement: 'Minimum staffing', citations: [] },
        ],
        previous_plans: [],
        files: [{ id: 'file', filename: 'response.pdf', version: 2 }],
        reviews: [
          {
            id: 'review',
            file_id: 'file',
            scope: 'Check technical coverage',
            is_current: true,
          },
        ],
        permitted_actions: ['accept', 'request_changes'],
      },
    ],
  })
  const api = { get, send } as unknown as Api
  const actor = { user_id: 'reviewer', workspace_id: 'workspace' } as Actor
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PreparationPanel
        api={api}
        actor={actor}
        tenderId='tender'
        focusItemId='deliverable'
        members={[]}
        findings={[]}
        onOpen={vi.fn()}
        onChange={vi.fn()}
      />
    </QueryClientProvider>
  )
  await expect
    .element(page.getByText('Check technical coverage').first())
    .toBeVisible()
  await expect
    .element(
      page.getByRole('button', { name: 'v2 · response.pdf', exact: true })
    )
    .toBeVisible()
  expect(send).not.toHaveBeenCalled()
  await expect
    .element(page.getByRole('button', { name: 'Upload version' }))
    .not.toBeInTheDocument()
  await page
    .getByRole('button', { name: 'Accept version', exact: true })
    .click()
  await expect
    .element(page.getByRole('dialog'))
    .toHaveTextContent('v2 · response.pdf')
  await page
    .getByLabelText('Review reason')
    .fill('Checked each technical requirement.')
  await page.getByRole('button', { name: 'Confirm accept version' }).click()
  expect(send).not.toHaveBeenCalled()
  await page.getByRole('checkbox', { name: /I checked/ }).click()
  await page.getByRole('button', { name: 'Confirm accept version' }).click()
  await expect
    .poll(() => send.mock.calls[0])
    .toEqual([
      '/tenders/tender/preparation/deliverable/actions',
      expect.objectContaining({
        approval_id: 'approval',
        expected_revision: 3,
        action: 'accept',
        note: 'Checked each technical requirement.',
        requirements_checked: true,
        client_request_id: expect.any(String),
      }),
    ])
})
