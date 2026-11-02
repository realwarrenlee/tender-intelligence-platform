/* eslint-disable @tanstack/query/exhaustive-deps -- The API client is stable for a session; identity changes clear QueryClient. Keep resource keys serializable. */
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { File as FileIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { type Anchor, type Api, type Citation, type Tender } from './api'
import { PdfPreview } from './pdf-preview'
import { coverageIssue, type SourceCoverageData } from './source-coverage'

export function Citations({
  items,
  label,
  onOpen,
}: {
  items: Citation[]
  label: string
  onOpen: (cite: Citation) => void
}) {
  return (
    <span className='flex flex-wrap gap-1'>
      {items.map((cite, index) => (
        <Button
          type='button'
          key={cite.anchor_id + index}
          variant='link'
          size='sm'
          className='h-auto px-0 text-sm'
          onClick={() => onOpen(cite)}
        >
          {label + ' ' + (index + 1)}
        </Button>
      ))}
    </span>
  )
}
export function SourcePane({
  api,
  documents,
  anchor,
  quote,
  onDocument,
  coverage,
}: {
  api: Api
  documents: Tender['documents']
  anchor: Anchor | undefined
  quote: string | undefined
  onDocument: (id: string) => void
  coverage?: SourceCoverageData | null
}) {
  const selectedParagraph = useRef<HTMLDivElement>(null)
  const id = anchor?.document_version_id || documents[0]?.id
  const answer = anchor?.source_role === 'review_answer'
  const selectedFile = documents.find((document) => document.id === id)
  const readiness =
    selectedFile?.content_type === 'application/pdf' ||
    selectedFile?.filename.endsWith('.pdf')
      ? 'pdf'
      : coverage?.documents.find(
          (document) => document.document_version_id === id
        )?.status || 'pending'
  const query = useQuery({
    queryKey: ['source-file', id, readiness],
    staleTime: readiness === 'pdf' ? Infinity : 0,
    enabled: !!id && !answer,
    queryFn: () => api.blob('/sources/' + encodeURIComponent(id!)),
  })
  const [parsed, setParsed] = useState<{
    anchors: Array<{
      anchor_id: string
      paragraph?: number
      page?: number
      location_label?: string | null
      text: string
    }>
    status?: 'complete' | 'partial' | 'failed'
    locations?: SourceCoverageData['documents'][number]['locations']
  }>({ anchors: [] })
  const paragraphs = parsed.anchors
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset extracted paragraphs when the protected source changes.
    setParsed({ anchors: [] })
    if (!query.data?.type.includes('json')) return
    let active = true
    void query.data
      .text()
      .then((text) => {
        const value = JSON.parse(text)
        if (active) setParsed({ ...value, anchors: value.anchors || [] })
      })
      .catch(() => {
        if (active) setParsed({ anchors: [] })
      })
    return () => {
      active = false
    }
  }, [query.data])
  useEffect(() => {
    selectedParagraph.current?.scrollIntoView({ block: 'nearest' })
  }, [anchor?.anchor_id, paragraphs])
  const pdf = query.data?.type.includes('pdf')
  const sourceCoverage =
    coverage?.documents.find((item) => item.document_version_id === id) ||
    (parsed.status
      ? { status: parsed.status, locations: parsed.locations || [] }
      : undefined)
  const filename =
    documents.find((d) => d.id === id)?.filename ||
    (answer ? 'Reviewer evidence' : 'Company evidence')
  return (
    <aside
      aria-label='Source documents'
      className='flex h-full min-h-0 flex-col bg-container'
    >
      <Tabs
        value={id || ''}
        onValueChange={onDocument}
        className='min-h-0 flex-1 gap-0'
      >
        <TabsList
          aria-label='Source files'
          className='h-10 w-full shrink-0 justify-start gap-0 overflow-x-auto rounded-none border-b bg-transparent p-0'
        >
          {documents.map((document) => (
            <TabsTrigger
              key={document.id}
              value={document.id}
              className='h-full max-w-64 flex-none rounded-none border-0 border-r px-4 text-sm data-[state=active]:bg-muted data-[state=active]:shadow-none'
            >
              <FileIcon aria-hidden='true' className='size-3.5' />
              <span className='truncate'>{document.filename}</span>
            </TabsTrigger>
          ))}
          {!!id && !documents.some((document) => document.id === id) && (
            <TabsTrigger
              value={id}
              className='h-full max-w-64 flex-none rounded-none border-0 border-r px-4 text-sm'
            >
              <FileIcon aria-hidden='true' className='size-3.5' />
              <span className='truncate'>{filename}</span>
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent
          key={id}
          value={id || ''}
          data-source-scroll
          className='min-h-0 flex-1 overflow-auto [scrollbar-gutter:stable]'
        >
          {sourceCoverage &&
            sourceCoverage.status !== 'complete' &&
            sourceCoverage.status !== 'pending' && (
              <div
                role='status'
                className='border-b px-4 py-3 text-sm text-amber-700 dark:text-amber-300'
              >
                <p>This file has content that still needs review.</p>
                {sourceCoverage.locations
                  .filter((location) => location.status !== 'complete')
                  .map((location, index) => (
                    <p key={index} className='mt-1 text-xs'>
                      {location.location_label ||
                        (location.page
                          ? 'Page ' + location.page
                          : location.paragraph
                            ? 'Paragraph ' + location.paragraph
                            : 'Content')}
                      {': ' + coverageIssue(location.error_code)}
                    </p>
                  ))}
              </div>
            )}
          {quote && (
            <blockquote className='m-4 border-l-2 border-amber-400 bg-amber-400/5 p-3 text-base whitespace-pre-wrap'>
              {quote}
            </blockquote>
          )}
          {answer && (
            <div className='space-y-2 p-4 text-base'>
              <p>{anchor.question}</p>
              <p className='whitespace-pre-wrap'>{anchor.text}</p>
              {anchor.basis && <p>Basis: {anchor.basis}</p>}
            </div>
          )}
          {query.error && (
            <p role='alert' className='p-4 text-base text-red-500'>
              {query.error.message}
            </p>
          )}
          {!id && (
            <p className='py-16 text-center text-base text-muted-foreground'>
              No source documents yet.
            </p>
          )}
          {!!id && !answer && query.isPending && (
            <p role='status' className='p-4 text-base text-muted-foreground'>
              Loading source…
            </p>
          )}
          {!!paragraphs.length && (
            <div className='space-y-4 p-4'>
              {paragraphs.map((paragraph) => (
                <div
                  ref={
                    paragraph.anchor_id === anchor?.anchor_id
                      ? selectedParagraph
                      : undefined
                  }
                  key={paragraph.anchor_id}
                  className={
                    paragraph.anchor_id === anchor?.anchor_id
                      ? 'rounded bg-amber-400/10 p-3'
                      : 'p-3'
                  }
                >
                  <p className='mb-1 text-xs text-muted-foreground'>
                    {paragraph.location_label ||
                      (paragraph.page
                        ? 'Page ' + paragraph.page
                        : 'Paragraph ' + paragraph.paragraph)}
                  </p>
                  <p className='text-base whitespace-pre-wrap'>
                    {paragraph.text}
                  </p>
                </div>
              ))}
            </div>
          )}
          {pdf && query.data && (
            <PdfPreview
              key={id}
              file={query.data}
              initialPage={anchor?.page || 1}
            />
          )}
        </TabsContent>
      </Tabs>
    </aside>
  )
}
