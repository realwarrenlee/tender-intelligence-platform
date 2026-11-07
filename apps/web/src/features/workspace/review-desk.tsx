/* eslint-disable @tanstack/query/exhaustive-deps -- The API client is stable for a session; identity changes clear QueryClient. */
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Actor, Api, Tender } from './api'
import { ScreeningBrief } from './screening-brief'

export function ReviewDesk({
  tenderId,
  actor,
  api,
  initialTab,
  embedded,
  onBack,
  focusTaskId,
}: {
  tenderId: string
  actor: Actor
  api: Api
  initialTab?: 'Assessment' | 'Questions' | 'Preparation' | 'Submission'
  embedded?: boolean
  onBack?: () => void
  focusTaskId?: string
}) {
  const detail = useQuery({
    queryKey: ['tender', tenderId],
    queryFn: () => api.get<Tender>('/tenders/' + tenderId),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((job) =>
        ['queued', 'running'].includes(job.status)
      )
        ? 2000
        : 30000,
  })
  const tender = detail.data
  if (!tender)
    return (
      <div className='space-y-4 p-8'>
        {onBack && (
          <Button variant='ghost' onClick={onBack}>
            <ArrowLeft className='size-4' />
            Back to list
          </Button>
        )}
        {detail.error ? (
          <p role='alert'>{detail.error.message}</p>
        ) : (
          <p role='status'>Loading tender…</p>
        )}
        {detail.error && (
          <Button variant='outline' onClick={() => void detail.refetch()}>
            Retry
          </Button>
        )}
      </div>
    )
  return (
    <ScreeningBrief
      tender={tender}
      actor={actor}
      api={api}
      initialTab={initialTab}
      focusTaskId={focusTaskId}
      embedded={embedded}
      onBack={onBack}
    />
  )
}
