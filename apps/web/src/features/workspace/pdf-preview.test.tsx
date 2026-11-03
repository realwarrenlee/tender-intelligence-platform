import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/app/globals.css'
import { expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { type Anchor, type Api, type Tender } from './api'
import { SourcePane } from './source-pane'

async function openSource(filename = 'Tender.pdf') {
  const bytes = await (
    await fetch(new URL('./test-fixtures/source.pdf', import.meta.url))
  ).arrayBuffer()
  const api = {
    blob: async (path: string) =>
      path.endsWith('/notes')
        ? new Blob(
            [
              JSON.stringify({
                anchors: [
                  {
                    anchor_id: 'note-1',
                    paragraph: 1,
                    text: 'Second source document content.',
                  },
                ],
              }),
            ],
            { type: 'application/json' }
          )
        : new Blob([bytes], { type: 'application/pdf' }),
  } as unknown as Api
  const document = {
    id: 'source',
    filename,
    role: 'tender',
    content_type: 'application/pdf',
    sha256: 'a'.repeat(64),
    byte_size: bytes.byteLength,
    page_count: 2,
    amends_version_id: null,
    created_at: '2026-10-25T00:00:00Z',
  } as Tender['documents'][number]
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Reader() {
    const [anchor, setAnchor] = useState<Anchor>()
    return (
      <>
        <button
          type='button'
          onClick={() =>
            setAnchor({
              anchor_id: '',
              document_version_id: 'notes',
              source_role: 'tender',
              text: '',
              page: null,
              paragraph: null,
            })
          }
        >
          Open Notes
        </button>
        <SourcePane
          api={api}
          documents={[
            document,
            {
              ...document,
              id: 'notes',
              filename: 'Notes.docx',
              content_type:
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            },
          ]}
          anchor={anchor}
          quote={undefined}
        />
      </>
    )
  }
  return render(
    <QueryClientProvider client={cache}>
      <div style={{ width: 640, height: 650 }}>
        <Reader />
      </div>
    </QueryClientProvider>
  )
}

it('keeps a long source title on one truncated line', async () => {
  const filename = 'A very long tender document filename '.repeat(8) + '.pdf'
  const screen = await openSource(filename)
  const title = screen.getByText(filename, { exact: true }).element()
  const style = getComputedStyle(title)
  expect(style.whiteSpace).toBe('nowrap')
  expect(style.textOverflow).toBe('ellipsis')
  expect(title.scrollWidth).toBeGreaterThan(title.clientWidth)
  expect(title.parentElement!.getBoundingClientRect().height).toBe(48)
})

it('reads every PDF page by scrolling at the full panel width', async () => {
  const screen = await openSource()
  await expect
    .element(
      screen.getByRole('img', { name: 'Tender document page 1', exact: true }),
      { timeout: 30000 }
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('button', { name: 'Next page' }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('button', { name: 'Zoom in' }))
    .not.toBeInTheDocument()
  await expect
    .element(screen.getByRole('link', { name: 'Download this source' }))
    .not.toBeInTheDocument()
  const canvas = screen
    .getByRole('img', { name: 'Tender document page 1', exact: true })
    .element()
  expect(
    Math.abs(
      canvas.getBoundingClientRect().width -
        canvas.parentElement!.getBoundingClientRect().width
    )
  ).toBeLessThanOrEqual(1)
  screen
    .getByRole('group', { name: 'PDF page 2', exact: true })
    .element()
    .scrollIntoView({ block: 'start' })
  await expect
    .element(
      screen.getByRole('img', { name: 'Tender document page 2', exact: true }),
      { timeout: 30000 }
    )
    .toBeVisible()
  expect(
    document.querySelector('[data-source-scroll]')!.scrollTop
  ).toBeGreaterThan(0)
})

it('shows the selected source title without a document selector', async () => {
  const screen = await openSource()
  await expect
    .element(screen.getByText('Tender.pdf', { exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByRole('combobox', { name: 'Source file' }))
    .not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Open Notes' }))
  await expect
    .element(screen.getByText('Notes.docx', { exact: true }))
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'View extracted text' })
  )
  await expect
    .element(
      screen.getByText('Second source document content.', { exact: true })
    )
    .toBeVisible()
  await expect
    .element(screen.getByRole('heading', { name: 'Source documents' }))
    .not.toBeInTheDocument()
})
