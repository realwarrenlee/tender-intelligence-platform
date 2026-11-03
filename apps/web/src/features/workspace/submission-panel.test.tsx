import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { page } from 'vitest/browser'
import type { Actor, Api } from './api'
import { SubmissionPanel } from './submission-panel'

it('requires explicit approval of the displayed package and keeps portal submission separate', async () => {
  const item = {
    id: 'package-one',
    version: 1,
    approver_id: 'approver',
    state: 'awaiting_release',
    files: [
      {
        item_id: 'technical',
        file_id: 'technical-v2',
        filename: 'technical.pdf',
        sha256: 'a'.repeat(64),
        version: 2,
        reviewer_id: 'reviewer',
        plan_revision: 1,
      },
    ],
    can_decide: true,
    can_record_receipt: false,
    decision: null as null | {
      outcome: string
      note: string
      actor_id: string
    },
    receipt: null,
  }
  const send = vi.fn(async () => {
    item.state = 'approved'
    item.can_decide = false
    item.decision = {
      outcome: 'approved',
      note: 'Reviewed the final offer.',
      actor_id: 'approver',
    }
  })
  const upload = vi.fn()
  const api = {
    get: async () => ({ checks: [], packages: [{ ...item }], can_seal: false }),
    send,
    upload,
  } as unknown as Api
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SubmissionPanel
        api={api}
        actor={{ user_id: 'approver' } as Actor}
        tenderId='tender'
        members={[]}
        onChange={vi.fn()}
      />
    </QueryClientProvider>
  )
  await expect
    .element(page.getByText('Awaiting release decision'))
    .toBeVisible()
  await expect
    .element(page.getByRole('button', { name: 'v2 · technical.pdf' }))
    .toBeVisible()
  expect(send).not.toHaveBeenCalled()
  await page.getByRole('button', { name: 'Approve release' }).click()
  const dialog = page.getByRole('dialog')
  await dialog
    .getByLabelText('Decision reason')
    .fill('Reviewed the final offer.')
  await dialog.getByRole('button', { name: 'Approve release' }).click()
  expect(send).not.toHaveBeenCalled()
  await dialog.getByRole('checkbox').click()
  await dialog.getByRole('button', { name: 'Approve release' }).click()
  await expect
    .element(page.getByText('Approved for release · awaiting portal receipt'))
    .toBeVisible()
  expect(send).toHaveBeenCalledWith(
    '/tenders/tender/submission/packages/package-one/decision',
    expect.objectContaining({ outcome: 'approved', checks_confirmed: true })
  )
  expect(upload).not.toHaveBeenCalled()
  await expect
    .element(page.getByText('Portal submission recorded'))
    .not.toBeInTheDocument()
})
