import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { type Api, type Tender } from './api'
import { SourceCoverage } from './source-coverage'
import { SourcePane } from './source-pane'
import { TenderIntake } from './tender-intake'

it('accepts a 64-file mixed tender pack without omitting files', async () => {
  const upload = vi.fn<
    (path: string, body: FormData) => Promise<{ input_revision: number }>
  >(async () => ({ input_revision: 2 }))
  const send = vi.fn(async (path: string) =>
    path === '/tenders' ? { id: 'pub-tender', input_revision: 1 } : {}
  )
  const complete = vi.fn()
  const screen = await render(
    <TenderIntake
      api={{ upload, send } as unknown as Api}
      onComplete={complete}
      onCancel={() => {}}
    />
  )
  const formats = ['pdf', 'docx', 'doc', 'xlsx', 'pptx']
  const files = Array.from(
    { length: 64 },
    (_, index) =>
      new File(
        ['original'],
        'Document ' + index + '.' + formats[index % formats.length]
      )
  )
  await userEvent.upload(screen.getByLabelText('Tender files'), files)
  await expect.element(screen.getByText('64 files ready')).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Analyse tender', exact: true })
  )
  await expect.poll(() => complete.mock.calls.length).toBe(1)
  const body = upload.mock.calls[0]?.[1] as FormData
  expect(body.getAll('files')).toHaveLength(64)
  expect(JSON.parse(String(body.get('metadata'))).files).toHaveLength(64)
})

it('rejects conflicting basenames before flattening a folder upload', async () => {
  const screen = await render(
    <TenderIntake api={{} as Api} onComplete={() => {}} onCancel={() => {}} />
  )
  await expect
    .element(
      screen.getByRole('button', { name: 'Choose a folder', exact: true })
    )
    .toBeVisible()
  await userEvent.upload(screen.getByLabelText('Tender files'), [
    new File(['one'], 'Schedule.xlsx'),
    new File(['two'], 'schedule.xlsx'),
  ])
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('share the name')
  await expect
    .element(
      screen.getByRole('button', { name: 'Analyse tender', exact: true })
    )
    .toBeDisabled()
})

it('shows every original file and its coverage gaps without claiming images were read', async () => {
  const documents = [
    { id: 'cover', filename: 'Cover.pdf', byte_size: 1 },
    { id: 'rates', filename: 'Rates.xlsx', byte_size: 1 },
    { id: 'maps', filename: 'Maps.pptx', byte_size: 1 },
  ] as Tender['documents']
  const open = vi.fn()
  const screen = await render(
    <SourceCoverage
      documents={documents}
      coverage={{
        complete: false,
        total_files: 3,
        parsed_files: 2,
        pending_files: 1,
        issues: 1,
        documents: [
          {
            document_version_id: 'cover',
            status: 'partial',
            error_code: 'SOURCE_INCOMPLETE',
            locations: [
              {
                page: 2,
                status: 'partial',
                error_code: 'IMAGE_REQUIRES_REVIEW',
              },
            ],
          },
          {
            document_version_id: 'rates',
            status: 'complete',
            error_code: null,
            locations: [],
          },
        ],
      }}
      onDocument={open}
    />
  )
  await userEvent.click(screen.getByText('Source coverage', { exact: true }))
  await expect
    .element(screen.getByRole('button', { name: 'Cover.pdf', exact: true }))
    .toBeVisible()
  await expect
    .element(screen.getByText('Page 2: image needs review'))
    .toBeVisible()
  await expect.element(screen.getByText('Waiting to be read')).toBeVisible()
  await expect
    .element(
      screen.getByText(
        'Some source content still needs review. A pursuit decision remains blocked.'
      )
    )
    .toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Rates.xlsx', exact: true })
  )
  expect(open).toHaveBeenCalledWith('rates')
})

it('shows spreadsheet cell provenance in the protected source reader', async () => {
  const api = {
    blob: async () =>
      new Blob(
        [
          JSON.stringify({
            status: 'partial',
            locations: [
              {
                paragraph: 2,
                location_label: 'Sheet Rates drawing 1',
                status: 'partial',
                error_code: 'IMAGE_REQUIRES_REVIEW',
              },
            ],
            anchors: [
              {
                anchor_id: 'rates-row-1',
                paragraph: 1,
                location_label: 'Sheet Rates, cells A1:D1',
                text: 'Air-conditioning maintenance | Monthly | 12',
              },
            ],
          }),
        ],
        { type: 'application/json' }
      ),
  } as unknown as Api
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const screen = await render(
    <QueryClientProvider client={cache}>
      <SourcePane
        api={api}
        documents={
          [{ id: 'rates', filename: 'Rates.xlsx' }] as Tender['documents']
        }
        anchor={undefined}
        quote={undefined}
      />
    </QueryClientProvider>
  )
  await userEvent.click(
    screen.getByRole('button', { name: 'View extracted text' })
  )
  await expect
    .element(screen.getByText('Sheet Rates, cells A1:D1', { exact: true }))
    .toBeVisible()
  await expect
    .element(
      screen.getByText('Air-conditioning maintenance | Monthly | 12', {
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByText('This file has content that still needs review.', {
        exact: true,
      })
    )
    .toBeVisible()
  await expect
    .element(
      screen.getByText('Sheet Rates drawing 1: image needs review', {
        exact: true,
      })
    )
    .toBeVisible()
})

it('reloads an Office source when parsing finishes after an initial source-not-parsed response', async () => {
  let calls = 0
  const api = {
    blob: async (path: string) => {
      if (path.endsWith('/original')) throw new Error('Original unavailable')
      calls++
      if (calls === 1) throw new Error('SOURCE_NOT_PARSED')
      return new Blob(
        [
          JSON.stringify({
            status: 'complete',
            anchors: [
              {
                anchor_id: 'ready-p1',
                paragraph: 1,
                text: 'Native text is now ready',
              },
            ],
          }),
        ],
        { type: 'application/json' }
      )
    },
  } as unknown as Api
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Reader() {
    const [ready, setReady] = useState(false)
    return (
      <QueryClientProvider client={client}>
        <button onClick={() => setReady(true)}>Finish parsing</button>
        <SourcePane
          api={api}
          documents={
            [{ id: 'ready', filename: 'Ready.docx' }] as Tender['documents']
          }
          anchor={undefined}
          quote={undefined}
          coverage={{
            complete: ready,
            total_files: 1,
            parsed_files: ready ? 1 : 0,
            pending_files: ready ? 0 : 1,
            issues: 0,
            documents: [
              {
                document_version_id: 'ready',
                status: ready ? 'complete' : 'pending',
                error_code: null,
                locations: [],
              },
            ],
          }}
        />
      </QueryClientProvider>
    )
  }
  const screen = await render(<Reader />)
  await userEvent.click(
    screen.getByRole('button', { name: 'View extracted text' })
  )
  await expect
    .element(screen.getByRole('alert'))
    .toHaveTextContent('SOURCE_NOT_PARSED')
  await userEvent.click(screen.getByRole('button', { name: 'Finish parsing' }))
  await expect
    .element(screen.getByText('Native text is now ready'))
    .toBeVisible()
  expect(calls).toBe(2)
})
