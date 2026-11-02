/* eslint-disable @tanstack/query/exhaustive-deps -- The API client is stable for a session; identity changes clear QueryClient. Keep resource keys serializable. */
import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  ArrowUpRight,
  RefreshCw,
  Search,
  Files,
  Trash2,
} from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  type Actor,
  type Api,
  type Inbox,
  type Member,
  type ReviewCase,
  singapore,
} from './api'
import { DecisionBadge } from './decision-badge'
import { DeleteTender } from './delete-tender'
import { TenderIntake } from './tender-intake'
import { useReviewCases } from './workspace-activity'

export function WorkInbox({ actor, api }: { actor: Actor; api: Api }) {
  return actor.qualification_workflow_enabled ? (
    <QualificationTenders actor={actor} api={api} />
  ) : (
    <LegacyWorkInbox actor={actor} api={api} />
  )
}
function LegacyWorkInbox({ actor, api }: { actor: Actor; api: Api }) {
  const [filter, setFilter] = useState('')
  const [view, setView] = useState('list')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState('closing')
  const [creating, setCreating] = useState(false)
  const router = useRouter()
  const cache = useQueryClient()
  const [deleting, setDeleting] = useState<Inbox['items'][number] | null>(null)
  const deleteTrigger = useRef<HTMLButtonElement | null>(null)
  const heading = useRef<HTMLHeadingElement | null>(null)
  const canDelete = actor.roles.includes('bid_owner')
  function deleteButton(tender: Inbox['items'][number]) {
    return canDelete ? (
      <Button
        size='icon'
        variant='ghost'
        aria-label={'Delete ' + tender.title}
        title='Delete tender'
        className='size-8 shrink-0 text-muted-foreground hover:text-destructive'
        onClick={(event) => {
          deleteTrigger.current = event.currentTarget
          setDeleting(tender)
        }}
      >
        <Trash2 className='size-3.5' />
      </Button>
    ) : null
  }
  const query = useQuery({
    queryKey: ['tenders'],
    queryFn: () => api.get<Inbox>('/tenders'),
    refetchInterval: 5000,
  })
  const items = (query.data?.items || [])
    .filter((t) => status === 'all' || t.assessment_status === status)
    .filter((t) =>
      (t.title + ' ' + t.source_label)
        .toLowerCase()
        .includes(filter.toLowerCase())
    )
    .sort(
      (a, b) =>
        Number(!!a.decision?.is_current && a.decision.decision === 'decline') -
          Number(
            !!b.decision?.is_current && b.decision.decision === 'decline'
          ) ||
        (sort === 'title'
          ? a.title.localeCompare(b.title)
          : sort === 'newest'
            ? Date.parse(b.created_at) - Date.parse(a.created_at)
            : (a.closing_at ? Date.parse(a.closing_at) : Infinity) -
              (b.closing_at ? Date.parse(b.closing_at) : Infinity))
    )
  if (creating)
    return (
      <div className='mx-auto w-full max-w-7xl space-y-24 p-6 md:p-10'>
        <p className='text-sm text-muted-foreground'>
          Tenders <span className='mx-3'>/</span>
          <span className='text-foreground'>New tender</span>
        </p>
        <TenderIntake
          api={api}
          onCancel={() => setCreating(false)}
          onChange={() => void query.refetch()}
          onComplete={(id) => router.push('/tenders/' + encodeURIComponent(id))}
        />
      </div>
    )
  return (
    <div className='flex min-h-full flex-col'>
      <header className='flex h-12 items-center justify-between gap-4 border-b px-6'>
        <div>
          <h1 ref={heading} tabIndex={-1} className='text-xl font-medium'>
            Tenders
          </h1>
        </div>
        {actor.roles.includes('bid_owner') && (
          <Button size='sm' onClick={() => setCreating(true)}>
            <Plus className='size-3.5' />
            Create tender
          </Button>
        )}
      </header>
      <div className='flex items-center gap-3 border-b px-6 py-2.5'>
        <div className='flex items-center gap-1' aria-label='Tender display'>
          {['list', 'board'].map((value) => (
            <Button
              key={value}
              variant='ghost'
              size='sm'
              aria-pressed={view === value}
              onClick={() => setView(value)}
              className={
                'h-7 rounded-full text-sm capitalize ' +
                (view === value ? 'bg-accent' : '')
              }
            >
              {value === 'list' ? 'List' : 'Board'}
            </Button>
          ))}
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger
            size='sm'
            aria-label='Assessment status'
            className='text-sm'
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>All assessments</SelectItem>
            <SelectItem value='not_ready'>Not ready</SelectItem>
            <SelectItem value='non_current'>Needs reassessment</SelectItem>
            <SelectItem value='current'>Current assessment</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger
            size='sm'
            aria-label='Sort tenders'
            className='text-sm'
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='closing'>Closing date</SelectItem>
            <SelectItem value='newest'>Newest first</SelectItem>
            <SelectItem value='title'>Name</SelectItem>
          </SelectContent>
        </Select>
        <div className='relative ml-auto w-72'>
          <Search className='pointer-events-none absolute top-2 left-2.5 size-3.5 text-muted-foreground' />
          <Input
            className='h-8 border-transparent bg-muted/40 pl-8 text-base shadow-none'
            aria-label='Filter tenders by name or reference'
            placeholder='Find a tender…'
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <Button
          size='sm'
          variant='ghost'
          onClick={() => void query.refetch()}
          aria-label='Refresh'
        >
          <RefreshCw className='size-3.5' />
        </Button>
      </div>
      {query.error && (
        <div
          role='alert'
          className='m-6 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive'
        >
          {query.error.message}
        </div>
      )}
      <div className='flex items-center gap-2 border-b bg-muted/20 px-6 py-2.5 text-xs text-muted-foreground'>
        <Files className='size-3.5' />
        <span>
          {query.isPending
            ? 'Loading tenders…'
            : query.isError
              ? 'Tenders unavailable'
              : items.length + ' tenders'}
        </span>
      </div>
      {!!items.length && view === 'list' && (
        <div className='overflow-x-auto'>
          <table className='w-full text-left text-[15px]'>
            <thead className='border-b text-sm text-muted-foreground'>
              <tr>
                {[
                  'Tender / buyer',
                  'Closing · Singapore',
                  'Assessment',
                  'Human decision',
                  'Next action',
                ].map((label) => (
                  <th key={label} className='px-6 py-3 font-normal'>
                    {label}
                  </th>
                ))}
                {canDelete && (
                  <th className='w-14'>
                    <span className='sr-only'>Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr
                  key={t.id}
                  className='border-b transition-colors hover:bg-accent/40'
                >
                  <td className='min-w-64 px-6 py-4'>
                    <Link
                      href={'/tenders/' + encodeURIComponent(t.id)}
                      className='group flex items-start gap-2 font-medium'
                    >
                      <span>{t.title}</span>
                      <ArrowUpRight className='mt-0.5 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100' />
                    </Link>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      {t.buyer ||
                        (t.source_label === 'manual_upload'
                          ? 'Uploaded tender'
                          : t.source_label)}
                    </p>
                  </td>
                  <td className='px-6 py-4 text-xs whitespace-nowrap text-muted-foreground'>
                    {singapore(t.closing_at)}
                  </td>
                  <td className='px-6 py-4'>
                    <DecisionBadge decision={t.recommendation} />
                    <p className='mt-1 text-xs text-muted-foreground'>
                      {t.assessment_status.replace(/_/g, ' ')}
                    </p>
                  </td>
                  <td className='px-6 py-4'>
                    {t.decision ? (
                      <>
                        <DecisionBadge decision={t.decision.decision} />
                        <p className='mt-1 text-xs text-muted-foreground'>
                          {t.decision.is_current ? 'Current' : 'Non-current'}
                        </p>
                      </>
                    ) : (
                      <span className='text-sm text-muted-foreground'>
                        Awaiting review
                      </span>
                    )}
                  </td>
                  <td className='min-w-44 px-6 py-4 text-[15px] text-muted-foreground'>
                    {t.next_action}
                  </td>
                  {canDelete && (
                    <td className='pr-4 text-right'>{deleteButton(t)}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!query.isPending && !query.error && view === 'board' && (
        <section
          aria-label='Tender board'
          className='min-h-0 flex-1 overflow-auto p-3'
        >
          <div className='grid min-w-[800px] grid-cols-3 gap-3'>
            {(
              [
                ['not_ready', 'Not ready'],
                ['non_current', 'Needs reassessment'],
                ['current', 'Current assessment'],
              ] as const
            ).map(([value, label]) => (
              <div key={value} className='rounded-md border bg-muted/10'>
                <h2 className='flex h-10 items-center justify-between border-b px-3 text-sm font-medium'>
                  {label}
                  <span className='text-muted-foreground'>
                    {items.filter((t) => t.assessment_status === value).length}
                  </span>
                </h2>
                <div className='space-y-3 p-3'>
                  {items
                    .filter((t) => t.assessment_status === value)
                    .map((t) => (
                      <article
                        key={t.id}
                        className='rounded-md border bg-container p-4'
                      >
                        <div className='flex items-start justify-between gap-2'>
                          <Link
                            href={'/tenders/' + encodeURIComponent(t.id)}
                            className='text-[15px] font-medium hover:underline'
                          >
                            {t.title}
                          </Link>
                          {deleteButton(t)}
                        </div>
                        <p className='mt-2 text-xs text-muted-foreground'>
                          {t.buyer || 'Buyer unknown'}
                        </p>
                        <div className='my-4 flex flex-wrap gap-4 text-sm'>
                          <div>
                            <p className='mb-2 text-muted-foreground'>
                              Assessment
                            </p>
                            <DecisionBadge decision={t.recommendation} />
                          </div>
                          <div>
                            <p className='mb-2 text-muted-foreground'>
                              Human decision
                            </p>
                            {t.decision ? (
                              <>
                                <DecisionBadge decision={t.decision.decision} />
                                <p className='mt-1 text-xs text-muted-foreground'>
                                  {t.decision.is_current
                                    ? 'Current'
                                    : 'Non-current'}
                                </p>
                              </>
                            ) : (
                              'Awaiting review'
                            )}
                          </div>
                        </div>
                        <p className='border-t pt-3 text-[15px] leading-6 text-muted-foreground'>
                          {t.next_action}
                        </p>
                        <p className='mt-3 text-xs text-muted-foreground'>
                          Closing {singapore(t.closing_at)}
                        </p>
                      </article>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {!items.length && !query.error && !query.isPending && view === 'list' && (
        <div className='flex flex-1 flex-col items-center justify-center gap-3 px-6 py-24 text-center'>
          <div className='mb-1 grid size-12 place-items-center rounded-xl border bg-muted/30'>
            <Files className='size-5 text-muted-foreground' />
          </div>
          <h2 className='text-lg font-medium'>
            {filter || status !== 'all'
              ? 'No matching tenders'
              : 'No tenders yet'}
          </h2>
          <p className='max-w-sm text-base leading-6 text-muted-foreground'>
            {filter || status !== 'all'
              ? 'Try another name, source reference or assessment filter.'
              : 'Your qualification work starts here. Create a tender and add the source documents to begin.'}
          </p>
        </div>
      )}
      {deleting && (
        <DeleteTender
          tender={deleting}
          api={api}
          onClose={() => setDeleting(null)}
          onRefresh={() => void query.refetch()}
          onReturnFocus={() => {
            if (deleteTrigger.current?.isConnected)
              deleteTrigger.current.focus()
            else heading.current?.focus()
          }}
          onDeleted={async () => {
            const id = deleting.id
            await cache.cancelQueries({ queryKey: ['tenders'] })
            cache.setQueryData<Inbox>(['tenders'], (inbox) =>
              inbox
                ? { ...inbox, items: inbox.items.filter((t) => t.id !== id) }
                : inbox
            )
            cache.removeQueries({ queryKey: ['tender', id] })
            cache.removeQueries({ queryKey: ['history', id] })
            setDeleting(null)
            void cache.invalidateQueries({ queryKey: ['tenders'] })
          }}
        />
      )}
    </div>
  )
}

function QualificationTenders({ actor, api }: { actor: Actor; api: Api }) {
  const query = useReviewCases(api, actor)
  const cache = useQueryClient()
  const router = useRouter()
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('')
  const [deleting, setDeleting] = useState<ReviewCase | null>(null)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const items = (query.data?.pages.flatMap((page) => page.items) || []).filter(
    (item) =>
      (item.title + ' ' + item.state)
        .toLowerCase()
        .includes(filter.toLowerCase())
  )
  if (creating)
    return (
      <div className='mx-auto w-full max-w-7xl space-y-8 p-6 md:p-10'>
        <h1 className='text-xl font-medium'>New tender</h1>
        <p className='text-sm text-muted-foreground'>
          Save the source files, then start a bounded screening from the shared
          review.
        </p>
        <TenderIntake
          api={api}
          saveOnly
          onCancel={() => setCreating(false)}
          onChange={() => {
            void cache.invalidateQueries({ queryKey: ['review-cases'] })
          }}
          onComplete={(id) => router.push('/tenders/' + encodeURIComponent(id))}
        />
      </div>
    )
  return (
    <div className='flex min-h-full min-w-0 flex-col'>
      <header className='flex h-12 items-center justify-between gap-4 border-b px-6'>
        <h1 ref={heading} tabIndex={-1} className='text-xl font-medium'>
          Tenders
        </h1>
        {actor.roles.includes('bid_owner') && (
          <Button size='sm' onClick={() => setCreating(true)}>
            <Plus className='size-3.5' />
            Create tender
          </Button>
        )}
      </header>
      <div className='border-b px-6 py-3'>
        <Input
          aria-label='Find loaded tenders'
          placeholder='Find a tender…'
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          className='max-w-sm'
        />
      </div>
      {query.error && (
        <p role='alert' className='p-6'>
          {query.error.message}{' '}
          <Button variant='link' onClick={() => void query.refetch()}>
            Retry
          </Button>
        </p>
      )}
      {query.isPending && (
        <p role='status' className='p-6'>
          Loading tenders…
        </p>
      )}
      <div className='overflow-x-auto'>
        <table
          aria-label='Tender cases'
          className='w-full border-collapse text-left text-sm'
        >
          <thead className='border-b bg-accent/20 text-muted-foreground'>
            <tr>
              {[
                'Tender',
                'Closing · Singapore',
                'Stage',
                'Review progress',
                'Next responsible person',
                'Actions',
              ].map((label) => (
                <th key={label} className='px-6 py-3 font-normal'>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.tender_id} className='border-b hover:bg-accent/40'>
                <td className='min-w-64 px-6 py-4'>
                  <Link
                    href={'/tenders/' + encodeURIComponent(item.tender_id)}
                    className='text-[15px] font-medium hover:underline'
                  >
                    {item.title}
                  </Link>
                </td>
                <td className='px-6 py-4 whitespace-nowrap text-muted-foreground'>
                  {singapore(item.closing_at)}
                </td>
                <td className='px-6 py-4'>
                  {item.tender_stage === 'preparing_bid'
                    ? 'Preparing bid'
                    : item.tender_stage === 'closed'
                      ? 'Closed'
                      : 'Assessing'}
                </td>
                <td className='px-6 py-4'>
                  {item.state}
                  {item.preparation_decision &&
                    !item.preparation_decision.is_current && (
                      <p className='mt-1 text-xs text-amber-700 dark:text-amber-300'>
                        Earlier preparation authority is non-current
                      </p>
                    )}
                </td>
                <td className='px-6 py-4'>
                  {item.next_actor_id
                    ? members.data?.items.find(
                        (member) => member.user_id === item.next_actor_id
                      )?.display_name || 'Assigned member'
                    : 'No pending action'}
                </td>
                <td className='px-6 py-4'>
                  {actor.roles.includes('bid_owner') && (
                    <Button
                      size='icon'
                      variant='ghost'
                      aria-label={'Delete ' + item.title}
                      onClick={(event) => {
                        trigger.current = event.currentTarget
                        setDeleting(item)
                      }}
                    >
                      <Trash2 className='size-4' />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!query.isPending && !query.isError && !items.length && (
        <p className='p-6 text-muted-foreground'>
          {filter
            ? 'No matching tenders in loaded results.'
            : 'No tenders yet. Start a suggestion from Agent Inbox or add your tender files.'}
        </p>
      )}
      {query.hasNextPage && (
        <Button
          className='m-4 self-start'
          variant='outline'
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          Load more tenders
        </Button>
      )}
      {deleting && (
        <DeleteTender
          tender={{
            id: deleting.tender_id,
            title: deleting.title,
            input_revision: deleting.input_revision,
          }}
          api={api}
          onClose={() => setDeleting(null)}
          onRefresh={() => void query.refetch()}
          onReturnFocus={() => {
            if (trigger.current?.isConnected) trigger.current.focus()
            else heading.current?.focus()
          }}
          onDeleted={async () => {
            await cache.cancelQueries({ queryKey: ['review-cases'] })
            setDeleting(null)
            await cache.invalidateQueries()
          }}
        />
      )}
    </div>
  )
}
