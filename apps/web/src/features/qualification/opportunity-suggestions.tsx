/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useState } from 'react'
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Field, selectStyle, ActionError, useAction } from './actions'
import {
  type Actor,
  type Api,
  type Opportunity,
  type Opportunities,
  requestId,
  singapore,
} from './api'

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
    actor.roles.includes('bid_owner') &&
    actor.user_id === item.intake_owner_user_id
  const disabled = !canAct || done || action.busy || action.uncertain
  function triage(choice: 'start_assessment' | 'defer' | 'dismiss') {
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
      {item.budget_status !== 'available' && !item.tender_id && (
        <p className='text-sm text-amber-700 dark:text-amber-300'>
          {item.budget_status === 'blocked'
            ? 'Screening budget is blocked.'
            : 'An approved screening budget is needed before starting assessment.'}
        </p>
      )}
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
            disabled={disabled || item.budget_status !== 'available'}
            onClick={() => triage('start_assessment')}
          >
            Start assessment
          </Button>
        )}
        {canAct && !item.tender_id && (
          <>
            <Button
              size='sm'
              variant='outline'
              disabled={disabled || item.state === 'deferred'}
              onClick={() => triage('defer')}
            >
              Defer
            </Button>
            <Button
              size='sm'
              variant='ghost'
              disabled={disabled || item.state === 'dismissed'}
              onClick={() => triage('dismiss')}
            >
              Dismiss
            </Button>
          </>
        )}
      </div>
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
  const [state, setState] = useState('suggested')
  const cache = useQueryClient()
  const query = useInfiniteQuery({
    queryKey: ['opportunity-suggestions', actor.user_id, state],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<Opportunities>(
        '/opportunity-suggestions?state=' +
          state +
          '&limit=50' +
          (pageParam ? '&after=' + encodeURIComponent(pageParam) : '')
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    refetchInterval: 15000,
  })
  const items = query.data?.pages.flatMap((page) => page.items) || []
  const refresh = () => {
    void cache.invalidateQueries({
      predicate: (q) =>
        ['opportunity-suggestions', 'tenders', 'review-cases'].includes(
          String(q.queryKey[0])
        ),
    })
  }
  return (
    <section
      aria-label='Opportunity suggestions'
      className='h-full overflow-y-auto'
    >
      <div className='border-b px-6 py-3'>
        <Field label='Suggestion status'>
          <select
            className={selectStyle + ' max-w-56'}
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option value='suggested'>Suggested</option>
            <option value='deferred'>Deferred</option>
            <option value='dismissed'>Dismissed</option>
            <option value='activated'>Started</option>
          </select>
        </Field>
      </div>
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
          No {state === 'activated' ? 'started' : state} opportunities assigned
          to you.
        </p>
      )}
      {items.map((item) => (
        <Suggestion
          key={item.id + ':' + item.revision}
          item={item}
          actor={actor}
          api={api}
          refresh={refresh}
        />
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
}
