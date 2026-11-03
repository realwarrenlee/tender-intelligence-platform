import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { page, userEvent } from 'vitest/browser'
import { read, utils, write } from 'xlsx'
import type { Actor, Api } from './api'
import { PreparationPanel } from './preparation-panel'

it('compares the example locally and saves only a complete working scenario for this tender', async () => {
  const tenderId = '10000000-0000-4000-8000-000000000001'
  const upload = vi.fn(async (_url: string, _form: FormData) => ({}))
  const get = vi.fn().mockResolvedValue({
    approval_id: 'approval',
    can_create: false,
    items: [
      {
        id: 'pricing',
        kind: 'pricing_workbook',
        revision: 7,
        owner_id: 'owner',
        reviewer_id: 'reviewer',
        status: 'draft',
        due_at: '2098-12-29T09:00:00+08:00',
        findings: [],
        files: [],
        reviews: [],
        previous_plans: [],
        permitted_actions: ['upload'],
      },
    ],
  })
  const api = { upload, get } as unknown as Api
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PreparationPanel
        api={api}
        actor={{ user_id: 'owner' } as Actor}
        tenderId={tenderId}
        members={[]}
        findings={[]}
        onOpen={vi.fn()}
        onChange={vi.fn()}
      />
    </QueryClientProvider>
  )
  await page.getByText('Compare supplier quotes and calculate cost').click()
  await page.getByRole('button', { name: 'Load fictional example' }).click()
  await expect.element(page.getByText(/SGD\s*4,966\.50/)).toBeVisible()
  await expect
    .element(
      page.getByRole('button', { name: 'Save as pricing workbook version' })
    )
    .not.toBeInTheDocument()
  expect(upload).not.toHaveBeenCalled()

  const example = read(
    await (await fetch('/examples/hvac-costing-example.xlsx')).arrayBuffer()
  )
  example.Sheets.Assumptions.B2 = { t: 's', v: 'working' }
  async function loadWorking(id: string) {
    example.Sheets.Assumptions.C2 = { t: 's', v: id }
    await userEvent.upload(page.getByLabelText('Costing input workbook'), [
      new File(
        [write(example, { type: 'array', bookType: 'xlsx' })],
        'working.xlsx'
      ),
    ])
  }
  await loadWorking('10000000-0000-4000-8000-000000000002')
  await expect
    .element(page.getByText('This workbook belongs to a different tender.'))
    .toBeVisible()
  await expect
    .element(
      page.getByRole('button', { name: 'Save as pricing workbook version' })
    )
    .not.toBeInTheDocument()
  await loadWorking(tenderId)
  const save = page.getByRole('button', {
    name: 'Save as pricing workbook version',
  })
  await expect.element(save).toBeEnabled()
  await userEvent.selectOptions(
    page.getByLabelText('Supplier scenario'),
    'BETA'
  )
  await expect.element(save).toBeDisabled()
  await page
    .getByRole('checkbox', {
      name: 'Use documented estimates where the quote has a gap',
    })
    .click()
  await expect.element(page.getByText(/SGD\s*5,012\.70/)).toBeVisible()
  await save.click()
  await expect
    .element(
      page.getByText(
        'Pricing workbook version saved. Request review when ready.'
      )
    )
    .toBeVisible()
  expect(upload).toHaveBeenCalledTimes(1)
  const [url, form] = upload.mock.calls[0]
  expect(url).toBe('/tenders/' + tenderId + '/preparation/pricing/files')
  expect(JSON.parse(String(form.get('metadata')))).toMatchObject({
    approval_id: 'approval',
    expected_revision: 7,
    client_request_id: expect.any(String),
  })
  const book = read(await (form.get('file') as File).arrayBuffer())
  expect(
    utils.sheet_to_json(book.Sheets.Estimate, { header: 1 })
  ).toContainEqual(['Total before tax (SGD)', 5012.7])
})
