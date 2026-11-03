import { ChevronDown } from 'lucide-react'
import { type Tender } from './api'

export type SourceCoverageData = {
  complete: boolean
  total_files: number
  parsed_files: number
  pending_files: number
  issues: number
  documents: Array<{
    document_version_id: string
    filename?: string | null
    status: 'complete' | 'partial' | 'failed' | 'pending'
    error_code: string | null
    locations: Array<{
      page?: number | null
      paragraph?: number | null
      status: string
      error_code?: string | null
      location_label?: string | null
    }>
  }>
}

export function coverageIssue(code?: string | null) {
  if (code === 'IMAGE_REQUIRES_REVIEW') return 'image needs review'
  if (code === 'SOURCE_INCOMPLETE') return 'some content needs review'
  return code?.replace(/_/g, ' ').toLowerCase() || 'content needs review'
}

export function SourceCoverage({
  documents,
  coverage,
  onDocument,
}: {
  documents: Tender['documents']
  coverage?: SourceCoverageData | null
  onDocument: (id: string) => void
}) {
  if (!documents.length && !coverage?.total_files) return null
  const results = new Map(
    coverage?.documents.map((item) => [item.document_version_id, item])
  )
  const files = [
    ...documents.map((document) => ({
      id: document.id,
      filename: document.filename,
    })),
    ...(coverage?.documents
      .filter(
        (item) =>
          !documents.some(
            (document) => document.id === item.document_version_id
          )
      )
      .map((item) => ({
        id: item.document_version_id,
        filename: item.filename || 'Company evidence',
      })) || []),
  ]
  return (
    <details className='border-b'>
      <summary className='flex cursor-pointer list-none flex-wrap items-center gap-x-4 gap-y-1 px-6 py-4 text-sm'>
        <span className='font-medium'>Source coverage</span>
        <span className='text-muted-foreground'>
          {coverage?.parsed_files || 0} of{' '}
          {coverage?.total_files || files.length} files processed
          {!!coverage?.issues && ' · ' + coverage.issues + ' need review'}
        </span>
        <ChevronDown aria-hidden='true' className='ml-auto size-4 shrink-0' />
      </summary>
      {coverage &&
        !coverage.complete &&
        (coverage.issues > 0 || !coverage.pending_files) && (
          <p
            role='status'
            className='border-t px-6 py-3 text-sm text-amber-700 dark:text-amber-300'
          >
            Some source content still needs review. A pursuit decision remains
            blocked.
          </p>
        )}
      <ul className='max-h-96 divide-y overflow-y-auto border-t'>
        {files.map((file) => {
          const result = results.get(file.id)
          const issues =
            result?.locations.filter(
              (location) => location.status !== 'complete'
            ) || []
          return (
            <li key={file.id} className='px-6 py-3 text-sm'>
              <div className='flex items-start justify-between gap-4'>
                <button
                  type='button'
                  className='min-w-0 text-left break-words underline-offset-4 hover:underline'
                  onClick={() => onDocument(file.id)}
                >
                  {file.filename}
                </button>
                <span
                  className={
                    'shrink-0 ' +
                    (result?.status === 'complete'
                      ? 'text-muted-foreground'
                      : 'text-amber-700 dark:text-amber-300')
                  }
                >
                  {result?.status === 'complete'
                    ? 'Read'
                    : result?.status === 'partial'
                      ? 'Needs review'
                      : result?.status === 'failed'
                        ? 'Could not read'
                        : 'Waiting to be read'}
                </span>
              </div>
              {!!issues.length && (
                <p className='mt-1 text-xs text-muted-foreground'>
                  {issues
                    .slice(0, 3)
                    .map(
                      (location) =>
                        (location.location_label ||
                          (location.page
                            ? 'Page ' + location.page
                            : location.paragraph
                              ? 'Paragraph ' + location.paragraph
                              : 'Content')) +
                        ': ' +
                        coverageIssue(location.error_code)
                    )
                    .join('; ')}
                  {issues.length > 3 &&
                    '; ' +
                      (issues.length - 3) +
                      ' more locations. Open the source for details.'}
                </p>
              )}
              {result &&
                result.status !== 'complete' &&
                result.status !== 'pending' &&
                !issues.length && (
                  <p className='mt-1 text-xs text-muted-foreground'>
                    {coverageIssue(result.error_code)}
                  </p>
                )}
            </li>
          )
        })}
      </ul>
    </details>
  )
}
