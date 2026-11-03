/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useState } from 'react'
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { ActionError, useAction } from './actions'
import {
  type Actor,
  type Api,
  type Opportunity,
  type OpportunityDiscovery,
  type Opportunities,
  requestId,
  singapore,
} from './api'
import { AskForFeedback } from './opportunity-feedback'
import { QueueLayout } from './queue-layout'

function DiscoverySchedule({ actor, api }: { actor: Actor; api: Api }) {
  const key = ['opportunity-discovery', actor.user_id]
  const cache = useQueryClient()
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.get<OpportunityDiscovery>('/opportunity-discovery'),
  })
  const action = useAction(
    () => void cache.invalidateQueries({ queryKey: key })
  )
  if (query.isError)
    return (
      <div className='border-b px-6 py-3 text-sm' role='alert'>
        Couldn’t load the GeBIZ scan schedule.{' '}
        <Button variant='link' size='sm' onClick={() => void query.refetch()}>
          Retry
        </Button>
      </div>
    )
  if (!query.data?.configured) return null
  const { enabled, can_edit } = query.data
  return (
    <div className='border-b px-6 py-3 text-sm'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div>
          <p className='font-medium'>Daily GeBIZ scan</p>
          <p className='text-muted-foreground'>
            8:00 a.m. Singapore time · {enabled ? 'On' : 'Off'}
          </p>
        </div>
        {can_edit && (
          <input
            type='checkbox'
            role='switch'
            aria-label='Daily GeBIZ scan'
            aria-checked={enabled}
            className='size-5 accent-primary'
            checked={enabled}
            disabled={action.busy || action.uncertain}
            onChange={(event) => {
              const checked = event.target.checked
              action.run(async () => {
                const saved = await api.send<OpportunityDiscovery>(
                  '/opportunity-discovery',
                  { enabled: checked },
                  'PUT'
                )
                cache.setQueryData(key, saved)
              })
            }}
          />
        )}
      </div>
      <ActionError action={action} />
    </div>
  )
}

function Suggestion({
  item,
  actor,
  api,
  refresh,
}: {
  item: Opportunity
  actor: Actor
  api: Api
  refresh: () => void
}) {
  const action = useAction(refresh)
  const router = useRouter()
  const [done, setDone] = useState(false)
  const canAct =
    actor.roles.some((role) => role === 'member' || role === 'admin') &&
    actor.user_id === item.intake_owner_user_id
  const disabled = !canAct || done || action.busy || action.uncertain
  function triage(choice: 'start_assessment' | 'dismiss') {
    const command = {
      expected_revision: item.revision,
      action: choice,
      client_request_id: requestId(),
    }
    action.run(async () => {
      const result = await api.send<Opportunity>(
        '/opportunity-suggestions/' + item.id + '/triage',
        command
      )
      setDone(true)
      refresh()
      if (result.tender_id)
        router.push('/tenders/' + encodeURIComponent(result.tender_id))
    })
  }
  const reasons = Array.isArray(item.match.reasons) ? item.match.reasons : []
  return (
    <article
      aria-label={item.notice.title}
      className='space-y-4 border-b px-6 py-5'
    >
      <div>
        <h2 className='text-lg font-medium'>{item.notice.title}</h2>
        <p className='mt-1 text-sm text-muted-foreground'>
          {item.notice.buyer || 'Buyer unknown'} · {item.notice.reference}
        </p>
        <p className='mt-1 text-sm text-muted-foreground'>
          Closes {singapore(item.notice.closing_at)}
        </p>
      </div>
      <div className='flex flex-wrap gap-3 text-sm'>
        <span>
          {item.notice.origin === 'controlled_import'
            ? 'Controlled import'
            : 'Public notice'}
        </span>
        <span>Notice only</span>
        {item.notice.access_gaps.includes('ATTACHMENTS_NOT_OBTAINED') && (
          <span>Attachments not obtained</span>
        )}
      </div>
      <p className='text-sm text-muted-foreground'>
        {reasons.length
          ? 'Source match: ' +
            reasons.map((reason) => String(reason.quote || '')).join('; ')
          : 'Potential Facilities Management opportunity.'}{' '}
        Relevance does not establish eligibility.
      </p>
      <details className='text-sm'>
        <summary className='cursor-pointer'>
          Source notice and access limits
        </summary>
        <p className='mt-3 break-words whitespace-pre-wrap'>
          {item.notice.evidence_text}
        </p>
        <p className='mt-3 text-muted-foreground'>
          Observed {singapore(item.notice.retrieved_at)}
        </p>
        {item.notice.origin === 'public_notice' &&
          item.notice.source_url?.startsWith('https://www.gebiz.gov.sg/') && (
            <a
              href={item.notice.source_url}
              target='_blank'
              rel='noreferrer'
              className='mt-3 inline-block underline'
            >
              Open source notice
            </a>
          )}
        {!!item.notice.access_gaps.length && (
          <p className='mt-3'>
            {item.notice.access_gaps
              .map((gap) => gap.replaceAll('_', ' ').toLowerCase())
              .join(' · ')}
          </p>
        )}
      </details>
      <ActionError action={action} />
      <div className='flex flex-wrap gap-2'>
        {item.tender_id ? (
          <Button asChild size='sm'>
            <Link href={'/tenders/' + encodeURIComponent(item.tender_id)}>
              Open tender
            </Link>
          </Button>
        ) : (
          <Button
            size='sm'
            disabled={disabled}
            onClick={() => triage('start_assessment')}
          >
            Start assessment
          </Button>
        )}
        {canAct && !item.tender_id && (
          <Button
            size='sm'
            variant='ghost'
            disabled={disabled || item.state === 'dismissed'}
            onClick={() => triage('dismiss')}
          >
            Dismiss
          </Button>
        )}
      </div>
      {canAct && !item.tender_id && (
        <AskForFeedback item={item} actor={actor} api={api} />
      )}
    </article>
  )
}

export function OpportunitySuggestions({
  actor,
  api,
}: {
  actor: Actor
  api: Api
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const mobile = useIsMobile()
  const cache = useQueryClient()
  const query = useInfiniteQuery({
    queryKey: ['opportunity-suggestions', actor.user_id, 'suggested'],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<Opportunities>(
        '/opportunity-suggestions?state=suggested&limit=50' +
          (pageParam ? '&after=' + encodeURIComponent(pageParam) : '')
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    refetchInterval: 15000,
  })
  const items = query.data?.pages.flatMap((page) => page.items) || []
  const active =
    items.find((item) => item.id === selected) ||
    (mobile ? undefined : items[0])
  const refresh = () => {
    void cache.invalidateQueries({
      predicate: (q) =>
        ['opportunity-suggestions', 'tenders', 'review-cases'].includes(
          String(q.queryKey[0])
        ),
    })
  }
  const list = (
    <section
      aria-label='Opportunity suggestions'
      className='h-full overflow-y-auto'
    >
      <DiscoverySchedule actor={actor} api={api} />
      {query.isPending && (
        <p role='status' className='p-6'>
          Loading suggestions…
        </p>
      )}
      {query.error && (
        <p role='alert' className='p-6'>
          {query.error.message}{' '}
          <Button variant='link' onClick={() => void query.refetch()}>
            Retry
          </Button>
        </p>
      )}
      {!query.isPending && !query.isError && !items.length && (
        <p className='p-6 text-muted-foreground'>
          No suggested opportunities assigned to you.
        </p>
      )}
      {items.map((item) => (
        <button
          key={item.id}
          type='button'
          aria-label={item.notice.title}
          aria-pressed={active?.id === item.id}
          className={
            'block w-full border-b px-6 py-4 text-left text-sm hover:bg-accent/40 ' +
            (active?.id === item.id ? 'bg-accent/60' : '')
          }
          onClick={() => setSelected(item.id)}
        >
          <span className='block font-medium'>{item.notice.title}</span>
          <span className='mt-2 block text-xs text-muted-foreground'>
            {item.notice.buyer || 'Buyer unknown'} · Closes{' '}
            {singapore(item.notice.closing_at)}
          </span>
        </button>
      ))}
      {query.hasNextPage && (
        <Button
          className='m-4'
          variant='outline'
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          Load more suggestions
        </Button>
      )}
    </section>
  )
  const detail = active ? (
    <div className='h-full overflow-y-auto'>
      {mobile && (
        <Button variant='ghost' onClick={() => setSelected(null)}>
          <ArrowLeft className='size-4' />
          Back to list
        </Button>
      )}
      <Suggestion
        key={active.id + ':' + active.revision}
        item={active}
        actor={actor}
        api={api}
        refresh={refresh}
      />
    </div>
  ) : (
    <p className='p-8 text-muted-foreground'>
      Select a suggestion to view its details.
    </p>
  )
  return mobile ? (
    active ? (
      detail
    ) : (
      list
    )
  ) : (
    <QueueLayout list={list} detail={detail} />
  )
}
