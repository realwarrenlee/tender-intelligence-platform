'use client'
/* eslint-disable @tanstack/query/exhaustive-deps -- API identity is stable for a session; session changes clear the shared query cache. */
import { useEffect, useState } from 'react'
import {
  useQueries,
  useQuery,
  useQueryClient,
  useInfiniteQuery,
} from '@tanstack/react-query'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/circle/components/ui/resizable'
import { useIsMobile } from '@/circle/hooks/use-mobile'
import {
  CheckCircle2,
  ChevronDown,
  Circle,
  Inbox as InboxIcon,
  XCircle,
} from 'lucide-react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  type ReviewCases,
  type HumanActions,
  singapore,
  type Actor,
  type Api,
  type Inbox,
  type Tender,
  type History,
  type Member,
} from './api'
import { inboxUpdates, InboxPreview, type InboxUpdate } from './inbox-updates'
import { OpportunitySuggestions } from './opportunity-suggestions'
import { ReviewDesk } from './review-desk'
import { reviewGroup, type ReviewGroup } from './review-status'

const groups: ReviewGroup[] = ['Open', 'Completed', 'Closed']
const icons = { Open: Circle, Completed: CheckCircle2, Closed: XCircle }

function StatusGroup({
  label,
  count,
  children,
}: {
  label: ReviewGroup
  count: number
  children: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(label === 'Open')
  return (
    <div>
      <button
        type='button'
        aria-label={label + ' reviews (' + count + ')'}
        aria-expanded={expanded}
        aria-controls={'review-group-' + label}
        onClick={() => setExpanded(!expanded)}
        className='flex h-8 w-full cursor-pointer items-center gap-1.5 border-b border-border/40 bg-accent/30 px-4 text-left text-sm font-medium select-none'
      >
        {label}
        <ChevronDown
          aria-hidden='true'
          className={
            'size-3 text-muted-foreground transition-transform ' +
            (expanded ? '' : '-rotate-90')
          }
        />
        <span className='ml-auto font-normal text-muted-foreground'>
          {count}
        </span>
      </button>
      <div id={'review-group-' + label} hidden={!expanded}>
        {children}
      </div>
    </div>
  )
}

function TenderQueue({
  actor,
  api,
  mode,
}: {
  actor: Actor
  api: Api
  mode: 'inbox' | 'reviews'
}) {
  const mobile = useIsMobile()
  const [selected, setSelected] = useState<string | null>(null)
  const cache = useQueryClient()
  const [filter, setFilter] = useState('')
  const list = useQuery({
    queryKey: ['tenders'],
    queryFn: () => api.get<Inbox>('/tenders'),
    refetchInterval: 15000,
  })
  // shortcut: Uses the API's latest 100 authorized tenders; add pagination when workspace volume warrants it.
  const details = useQueries({
    queries: (list.data?.items || []).map((tender) => ({
      queryKey: ['tender', tender.id],
      queryFn: () =>
        api.get<Tender>('/tenders/' + encodeURIComponent(tender.id)),
      refetchInterval: 15000,
    })),
  })
  const tenders = details.flatMap((query) => (query.data ? [query.data] : []))
  const histories = useQueries({
    queries:
      mode === 'inbox'
        ? tenders
            .filter(
              (tender) =>
                tender.assessment &&
                (tender.owner_user_id === actor.user_id ||
                  actor.roles.includes('approver'))
            )
            .map((tender) => ({
              queryKey: ['history', tender.id],
              queryFn: () =>
                api.get<History>(
                  '/tenders/' + encodeURIComponent(tender.id) + '/history'
                ),
              refetchInterval: 15000,
            }))
        : [],
  })
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
    enabled: mode === 'inbox',
  })
  const reviews = tenders
    .filter((tender) => tender.assessment || tender.review_tasks.length)
    .filter(
      (tender) =>
        tender.owner_user_id === actor.user_id ||
        (actor.roles.includes('approver') && !!tender.assessment) ||
        tender.review_tasks.some(
          (task) =>
            task.assignee_id === actor.user_id ||
            task.created_by === actor.user_id
        )
    )
    .sort(
      (a, b) => groups.indexOf(reviewGroup(a)) - groups.indexOf(reviewGroup(b))
    )
  const updates =
    mode === 'inbox'
      ? tenders
          .flatMap((tender) =>
            inboxUpdates(
              tender,
              actor,
              histories
                .flatMap((query) => (query.data ? [query.data] : []))
                .find((history) =>
                  history.assessments.some(
                    (item) => item.id === tender.assessment?.id
                  )
                )
            )
          )
          .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
      : []
  type QueueRow = {
    id: string
    tender: Tender
    update?: InboxUpdate
    label: string
    description: string
    created_at: string
  }
  const eligible: QueueRow[] =
    mode === 'reviews'
      ? reviews.map((tender) => ({
          id: tender.id,
          tender,
          label: tender.title,
          description: '',
          created_at: tender.created_at,
        }))
      : updates.map((update) => ({
          id: update.id,
          tender: update.tender,
          update,
          label:
            update.label +
            ' · ' +
            update.tender.title +
            (update.task ? ' · ' + update.task.question : ''),
          description:
            update.task?.question ||
            update.tender.assessment?.candidate.summary ||
            '',
          created_at: update.created_at,
        }))
  const rows = eligible.filter((row) =>
    (
      row.label +
      ' ' +
      row.description +
      ' ' +
      row.tender.review_tasks.map((task) => task.question).join(' ')
    )
      .toLowerCase()
      .includes(filter.toLowerCase())
  )
  const active =
    eligible.find((row) => row.id === selected) ||
    (mobile ? undefined : rows[0])
  const error =
    list.error ||
    details.find((query) => query.error)?.error ||
    histories.find((query) => query.error)?.error ||
    (mode === 'inbox' && members.error)
  const loading =
    list.isPending ||
    details.some((query) => query.isPending) ||
    histories.some((query) => query.isPending)
  const refresh = () => {
    void cache.invalidateQueries({
      predicate: (query) => query.queryKey[0] !== 'source-file',
    })
  }
  const title = mode === 'reviews' ? 'Reviews' : 'Inbox'
  function row(item: QueueRow) {
    const tender = item.tender
    const group = mode === 'reviews' ? reviewGroup(tender) : 'Open'
    const Icon = icons[group]
    return (
      <button
        key={item.id}
        type='button'
        aria-label={item.label}
        aria-pressed={active?.id === item.id}
        onClick={() => setSelected(item.id)}
        className={
          'flex w-full items-center gap-2 border-b border-border/40 px-4 py-3 text-left text-sm transition-colors ' +
          (active?.id === item.id ? 'bg-accent/60' : 'hover:bg-sidebar/50')
        }
      >
        <Icon
          aria-hidden='true'
          className={
            'size-4 shrink-0 ' +
            (group === 'Completed'
              ? 'text-indigo-400'
              : 'text-muted-foreground')
          }
        />
        <span className='min-w-0 flex-1'>
          <span className='block truncate text-[15px] font-medium'>
            {tender.title}
          </span>
          {item.update && (
            <>
              <span className='mt-1 block text-xs text-muted-foreground'>
                {item.update.label}
              </span>
              <span className='mt-1 block truncate text-xs text-muted-foreground'>
                {item.description}
              </span>
            </>
          )}
        </span>
        <span className='shrink-0 text-xs text-muted-foreground'>
          {new Intl.DateTimeFormat('en-SG', {
            month: 'short',
            day: 'numeric',
            timeZone: 'Asia/Singapore',
          }).format(new Date(item.created_at))}
        </span>
      </button>
    )
  }
  const listPane = (
    <section
      aria-label={title + ' list'}
      className='flex h-full min-w-0 flex-col bg-container'
    >
      <header className='flex h-12 shrink-0 items-center border-b px-4'>
        <h1 className='text-xl font-medium'>{title}</h1>
      </header>
      <div className='shrink-0 border-b p-3'>
        <Input
          aria-label={
            mode === 'reviews' ? 'Find review work' : 'Find an inbox action'
          }
          placeholder={
            mode === 'reviews' ? 'Find a review…' : 'Find an action…'
          }
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          className='h-8 text-base'
        />
      </div>
      {error && (
        <p role='alert' className='p-4 text-base text-destructive'>
          {error.message}
        </p>
      )}
      {loading && (
        <p role='status' className='p-4 text-base text-muted-foreground'>
          Loading {mode === 'reviews' ? 'reviews' : 'actions'}…
        </p>
      )}
      <div className='min-h-0 flex-1 overflow-y-auto'>
        {mode === 'reviews'
          ? groups.map((group) => {
              const items = rows.filter(
                (item) => reviewGroup(item.tender) === group
              )
              return (
                <StatusGroup key={group} label={group} count={items.length}>
                  {items.map(row)}
                </StatusGroup>
              )
            })
          : rows.map(row)}
        {!loading && !error && !rows.length && (
          <p className='p-6 text-base text-muted-foreground'>
            {filter
              ? 'No matching work.'
              : mode === 'inbox'
                ? 'No updates need attention.'
                : 'No reviews for you.'}
          </p>
        )}
      </div>
      {(list.data?.items.length || 0) >= 100 && (
        <p className='border-t px-4 py-2 text-xs text-muted-foreground'>
          Showing the 100 most recent tenders.
        </p>
      )}
    </section>
  )
  const content = active ? (
    <section aria-label='Tender preview' className='h-full min-h-0 min-w-0'>
      {active.update ? (
        <InboxPreview
          key={active.id}
          update={active.update}
          actor={actor}
          api={api}
          members={members.data?.items || []}
          paused={!!error}
          onChange={refresh}
          onBack={mobile ? () => setSelected(null) : undefined}
        />
      ) : (
        <ReviewDesk
          key={active.id}
          tenderId={active.tender.id}
          actor={actor}
          api={api}
          embedded
          onBack={mobile ? () => setSelected(null) : undefined}
        />
      )}
    </section>
  ) : (
    <div className='flex h-full flex-col items-center justify-center gap-4 p-8 text-center text-muted-foreground'>
      <InboxIcon aria-hidden='true' className='size-10 stroke-1' />
      <p className='text-base'>
        Select a {mode === 'reviews' ? 'tender review' : 'update'} to view its
        content and take action.
      </p>
    </div>
  )
  return mobile ? (
    <div className='h-full min-w-0'>{active ? content : listPane}</div>
  ) : (
    <ResizablePanelGroup direction='horizontal' className='h-full min-w-0'>
      <ResizablePanel defaultSize={32} minSize={24} maxSize={45}>
        {listPane}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel minSize={45}>{content}</ResizablePanel>
    </ResizablePanelGroup>
  )
}

export function WorkspaceInbox({ actor, api }: { actor: Actor; api: Api }) {
  return actor.qualification_workflow_enabled ? (
    <QualificationInbox actor={actor} api={api} />
  ) : (
    <TenderQueue actor={actor} api={api} mode='inbox' />
  )
}
export function ReviewWork({ actor, api }: { actor: Actor; api: Api }) {
  return actor.qualification_workflow_enabled ? (
    <TeamReviews actor={actor} api={api} />
  ) : (
    <TenderQueue actor={actor} api={api} mode='reviews' />
  )
}

export function useReviewCases(api: Api, actor: Actor) {
  return useInfiniteQuery({
    queryKey: ['review-cases', actor.user_id],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<ReviewCases>(
        '/review-cases?limit=50' +
          (pageParam ? '&after=' + encodeURIComponent(pageParam) : '')
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    refetchInterval: 15000,
  })
}

function QueueLayout({
  list,
  detail,
}: {
  list: React.ReactNode
  detail: React.ReactNode
}) {
  return (
    <ResizablePanelGroup direction='horizontal' className='h-full min-w-0'>
      <ResizablePanel defaultSize={32} minSize={24} maxSize={45}>
        {list}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel minSize={45}>{detail}</ResizablePanel>
    </ResizablePanelGroup>
  )
}

function HumanQueue({ actor, api }: { actor: Actor; api: Api }) {
  const mobile = useIsMobile()
  const [selected, setSelected] = useState<string | null>(null)
  const query = useInfiniteQuery({
    queryKey: ['inbox-actions', actor.user_id],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<HumanActions>(
        '/inbox-actions?limit=50' +
          (pageParam ? '&after=' + encodeURIComponent(pageParam) : '')
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    refetchInterval: 15000,
  })
  const rows = query.data?.pages.flatMap((page) => page.items) || []
  const active =
    rows.find((item) => item.task_id === selected) ||
    (mobile ? undefined : rows[0])
  const list = (
    <section aria-label='Human actions' className='h-full overflow-y-auto'>
      {query.isPending && (
        <p role='status' className='p-6'>
          Loading assigned actions…
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
      {rows.map((item) => (
        <button
          key={item.task_id}
          type='button'
          aria-label={item.question}
          aria-pressed={active?.task_id === item.task_id}
          className={
            'block w-full border-b px-6 py-4 text-left text-sm hover:bg-accent/40 ' +
            (active?.task_id === item.task_id ? 'bg-accent/60' : '')
          }
          onClick={() => setSelected(item.task_id)}
        >
          <span className='block font-medium'>{item.question}</span>
          <span className='mt-2 block text-xs text-muted-foreground'>
            {item.kind === 'preparation_approval'
              ? 'Preparation decision'
              : 'Input requested'}{' '}
            · Due {singapore(item.due_at)}
          </span>
          {!item.is_current && (
            <span className='mt-1 block text-xs text-amber-700 dark:text-amber-300'>
              Sources changed · Review with bid owner
            </span>
          )}
        </button>
      ))}
      {!query.isPending && !query.isError && !rows.length && (
        <p className='p-6 text-muted-foreground'>No actions assigned to you.</p>
      )}
      {query.hasNextPage && (
        <Button
          variant='outline'
          className='m-4'
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          Load more actions
        </Button>
      )}
    </section>
  )
  const detail = active ? (
    <ReviewDesk
      key={active.task_id}
      tenderId={active.tender_id}
      actor={actor}
      api={api}
      initialTab='Questions'
      focusTaskId={active.task_id}
      embedded
      onBack={mobile ? () => setSelected(null) : undefined}
    />
  ) : (
    <p className='p-8 text-muted-foreground'>
      Select an assigned action to open its review.
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

function QualificationInbox({ actor, api }: { actor: Actor; api: Api }) {
  const router = useRouter()
  const search = useSearchParams()
  const value = search.get('tab') === 'agent' ? 'agent' : 'human'
  const [tab, setTab] = useState(value)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Follow browser back/forward and shared Inbox URLs.
    setTab(value)
  }, [value])
  return (
    <Tabs
      value={tab}
      onValueChange={(next) => {
        setTab(next)
        router.replace('/inbox?tab=' + next, { scroll: false })
      }}
      className='flex h-full min-h-0 flex-col gap-0'
    >
      <header className='flex h-12 shrink-0 items-center border-b px-6'>
        <h1 className='text-xl font-medium'>Inbox</h1>
      </header>
      <div className='border-b px-6 py-2.5'>
        <TabsList
          aria-label='Inbox views'
          className='h-auto gap-1 bg-transparent p-0'
        >
          {['human', 'agent'].map((item) => (
            <TabsTrigger
              key={item}
              value={item}
              className='h-7 flex-none rounded-full border-0 px-3 text-sm shadow-none data-[state=active]:bg-accent data-[state=active]:shadow-none'
            >
              {item === 'human' ? 'Human' : 'Agent'}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
      <TabsContent value='human' className='min-h-0'>
        <HumanQueue actor={actor} api={api} />
      </TabsContent>
      <TabsContent value='agent' className='min-h-0'>
        <OpportunitySuggestions actor={actor} api={api} />
      </TabsContent>
    </Tabs>
  )
}

function TeamReviews({ actor, api }: { actor: Actor; api: Api }) {
  const query = useReviewCases(api, actor)
  const mobile = useIsMobile()
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const items = query.data?.pages.flatMap((page) => page.items) || []
  const visible = items.filter((item) =>
    (item.title + ' ' + item.state).toLowerCase().includes(filter.toLowerCase())
  )
  const active =
    visible.find((item) => item.tender_id === selected) ||
    (mobile ? undefined : visible[0])
  const list = (
    <section aria-label='Reviews list' className='flex h-full min-h-0 flex-col'>
      <header className='flex h-12 shrink-0 items-center border-b px-6'>
        <h1 className='text-xl font-medium'>Reviews</h1>
      </header>
      <div className='border-b p-3'>
        <Input
          aria-label='Find loaded reviews'
          placeholder='Find a review…'
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className='min-h-0 flex-1 overflow-y-auto'>
        {query.isPending && (
          <p role='status' className='p-6'>
            Loading team reviews…
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
        {visible.map((item) => (
          <button
            key={item.tender_id}
            type='button'
            aria-pressed={active?.tender_id === item.tender_id}
            className={
              'block w-full border-b px-6 py-4 text-left hover:bg-accent/40 ' +
              (active?.tender_id === item.tender_id ? 'bg-accent/60' : '')
            }
            onClick={() => setSelected(item.tender_id)}
          >
            <span className='block text-[15px] font-medium'>{item.title}</span>
            <span className='mt-2 block text-sm'>{item.state}</span>
            <span className='mt-1 block text-xs text-muted-foreground'>
              {item.next_actor_id
                ? 'Next: ' +
                  (members.data?.items.find(
                    (m) => m.user_id === item.next_actor_id
                  )?.display_name || 'Assigned member')
                : item.tender_stage === 'closed'
                  ? 'Declined'
                  : 'Preparation decision recorded'}
            </span>
          </button>
        ))}
        {!query.isPending && !query.isError && !visible.length && (
          <p className='p-6 text-muted-foreground'>
            {filter
              ? 'No matching reviews in loaded results.'
              : 'No team reviews yet.'}
          </p>
        )}
        {query.hasNextPage && (
          <Button
            variant='outline'
            className='m-4'
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            Load more reviews
          </Button>
        )}
      </div>
    </section>
  )
  const detail = active ? (
    <ReviewDesk
      key={active.tender_id}
      tenderId={active.tender_id}
      actor={actor}
      api={api}
      embedded
      onBack={mobile ? () => setSelected(null) : undefined}
    />
  ) : (
    <p className='p-8 text-muted-foreground'>Select a team review.</p>
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
