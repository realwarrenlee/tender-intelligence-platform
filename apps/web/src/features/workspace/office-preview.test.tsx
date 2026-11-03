import { expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import * as XLSX from 'xlsx'
import { DocxPreview, SpreadsheetPreview } from './office-preview'

it('renders the original Word document', async () => {
  const file = await (
    await fetch(new URL('./test-fixtures/source.docx', import.meta.url))
  ).blob()
  const screen = await render(<DocxPreview file={file} />)
  const frame = screen
    .getByTitle('Word document preview')
    .element() as HTMLIFrameElement
  await expect
    .poll(() => frame.contentDocument?.body.textContent, { timeout: 30000 })
    .toContain('Example tender condition')
})

it('switches worksheets and pages through rows', async () => {
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(
    book,
    XLSX.utils.aoa_to_sheet([
      ['First sheet'],
      ...Array.from({ length: 100 }, () => ['']),
      ['Later row'],
    ]),
    'First'
  )
  XLSX.utils.book_append_sheet(
    book,
    XLSX.utils.aoa_to_sheet([['Second sheet']]),
    'Second'
  )
  const file = new Blob([XLSX.write(book, { bookType: 'xlsx', type: 'array' })])
  const screen = await render(<SpreadsheetPreview file={file} />)
  await expect.element(screen.getByText('First sheet')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Next rows' }))
  await expect.element(screen.getByText('Later row')).toBeVisible()
  expect(
    screen.getByRole('combobox', { name: 'Sheet' }).element().tagName
  ).toBe('BUTTON')
  await userEvent.click(screen.getByRole('combobox', { name: 'Sheet' }))
  await userEvent.click(screen.getByRole('option', { name: 'Second' }))
  await expect.element(screen.getByText('Second sheet')).toBeVisible()
})
