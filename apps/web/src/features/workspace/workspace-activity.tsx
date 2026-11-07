'use client'
/* eslint-disable @tanstack/query/exhaustive-deps -- API identity is stable for a session; session changes clear the shared query cache. */
import { useEffect, useState } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  type ReviewCases,
  type HumanActions,
  singapore,
  type Actor,
  type Api,
  type Member,
} from './api'
import {
  OpportunityFeedbackDetail,
  useOpportunityFeedback,
} from './opportunity-feedback'
import { OpportunitySuggestions } from './opportunity-suggestions'
import { QueueLayout } from './queue-layout'
import { ReviewDesk } from './review-desk'

const queueRow =
  'block w-full border-b px-6 py-4 text-left text-sm hover:bg-accent/40 '

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
  const feedbackQuery = useOpportunityFeedback({ actor, api })
  const rows = [
    ...(query.data?.pages.flatMap((page) => page.items) || []).map((item) => ({
      kind: 'work' as const,
      id: 'work:' + item.task_id,
      deadline: Date.parse(item.due_at),
      item,
    })),
    ...(feedbackQuery.data?.pages.flatMap((page) => page.items) || []).map(
      (item) => ({
        kind: 'feedback' as const,
        id: 'feedback:' + item.id,
        deadline:
          !item.answer &&
          item.recipient_id === actor.user_id &&
          item.notice.closing_at
            ? Date.parse(item.notice.closing_at)
            : Infinity,
        item,
      })
    ),
  ].sort((a, b) => a.deadline - b.deadline)
  const active =
    rows.find((row) => row.id === selected) || (mobile ? undefined : rows[0])
  const onBack = mobile ? () => setSelected(null) : undefined
  const list = (
    <section aria-label='Human actions' className='h-full overflow-y-auto'>
      {(query.isPending || feedbackQuery.isPending) && (
        <p role='status' className='p-6'>
          Loading Inbox…
        </p>
      )}
      {[
        { label: 'Assigned work', request: query },
        { label: 'Tender feedback', request: feedbackQuery },
      ].map(
        ({ label, request }) =>
          request.error && (
            <p key={label} role='alert' className='p-6'>
              {label}: {request.error.message}{' '}
              <Button variant='link' onClick={() => void request.refetch()}>
                Retry
              </Button>
            </p>
          )
      )}
      {rows.map((row) => (
        <button
          key={row.id}
          type='button'
          aria-label={row.item.question}
          aria-pressed={active?.id === row.id}
          className={queueRow + (active?.id === row.id ? 'bg-accent/60' : '')}
          onClick={() => setSelected(row.id)}
        >
          <span className='block font-medium'>{row.item.question}</span>
          {row.kind === 'feedback' ? (
            <span className='mt-2 block text-xs text-muted-foreground'>
              {row.item.notice.title} ·{' '}
              {row.item.answer
                ? 'Replied'
                : row.item.recipient_id === actor.user_id
                  ? 'Reply requested'
                  : 'Awaiting reply'}
            </span>
          ) : (
            <>
              <span className='mt-2 block text-xs text-muted-foreground'>
                {row.item.kind === 'preparation_approval'
                  ? 'Preparation decision'
                  : row.item.kind === 'preparation_review'
                    ? 'Working file review'
                    : row.item.kind === 'preparation_deliverable'
                      ? 'Bid deliverable'
                      : row.item.kind === 'preparation_reconfirm'
                        ? 'Deliverable reconfirmation'
                        : 'Input requested'}{' '}
                · Due {singapore(row.item.due_at)}
              </span>
              {!row.item.is_current && (
                <span className='mt-1 block text-xs text-amber-700 dark:text-amber-300'>
                  Sources changed · Review with bid owner
                </span>
              )}
            </>
          )}
        </button>
      ))}
      {query.isSuccess && feedbackQuery.isSuccess && !rows.length && (
        <p className='p-6 text-muted-foreground'>No actions assigned to you.</p>
      )}
      {(query.hasNextPage || feedbackQuery.hasNextPage) && (
        <Button
          variant='outline'
          className='m-4'
          disabled={
            query.isFetchingNextPage || feedbackQuery.isFetchingNextPage
          }
          onClick={() => {
            if (query.hasNextPage) void query.fetchNextPage()
            if (feedbackQuery.hasNextPage) void feedbackQuery.fetchNextPage()
          }}
        >
          Load more
        </Button>
      )}
    </section>
  )
  const detail = !active ? (
    <p className='p-8 text-muted-foreground'>Select an item to open it.</p>
  ) : active.kind === 'feedback' ? (
    <OpportunityFeedbackDetail
      key={active.id}
      item={active.item}
      actor={actor}
      api={api}
      onBack={onBack}
    />
  ) : (
    <ReviewDesk
      key={active.id}
      tenderId={active.item.tender_id}
      actor={actor}
      api={api}
      initialTab={
        active.item.kind === 'preparation_review' ||
        active.item.kind === 'preparation_deliverable' ||
        active.item.kind === 'preparation_reconfirm'
          ? 'Preparation'
          : 'Questions'
      }
      focusTaskId={active.item.task_id}
      embedded
      onBack={onBack}
    />
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

function QueueTabsHeader({
  title,
  tabs,
}: {
  title: string
  tabs: Record<string, string>
}) {
  return (
    <>
      <header className='flex h-12 shrink-0 items-center border-b px-6'>
        <h1 className='text-xl font-medium'>{title}</h1>
      </header>
      <div className='shrink-0 overflow-x-auto border-b px-6 py-2.5'>
        <TabsList aria-label={title + ' views'}>
          {Object.entries(tabs).map(([value, label]) => (
            <TabsTrigger key={value} value={value}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
    </>
  )
}

export function WorkspaceInbox({ actor, api }: { actor: Actor; api: Api }) {
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
      <QueueTabsHeader
        title='Inbox'
        tabs={{ human: 'Human', agent: 'Agent' }}
      />
      <TabsContent value='human' className='min-h-0'>
        <HumanQueue actor={actor} api={api} />
      </TabsContent>
      <TabsContent value='agent' className='min-h-0'>
        <OpportunitySuggestions actor={actor} api={api} />
      </TabsContent>
    </Tabs>
  )
}

const oversightTabs = { overdue: 'Overdue', upcoming: 'Upcoming' }

export function Oversight({ actor, api }: { actor: Actor; api: Api }) {
  const query = useQuery({
    queryKey: ['review-cases', actor.user_id, 'oversight'],
    queryFn: async ({ signal }) => {
      const items: ReviewCases['items'] = []
      let cursor: string | null = null
      do {
        const page: ReviewCases = await api.get(
          '/review-cases?limit=50' +
            (cursor ? '&after=' + encodeURIComponent(cursor) : ''),
          signal
        )
        items.push(...page.items)
        cursor = page.next_cursor
      } while (cursor)
      return items
    },
    refetchInterval: 15000,
  })
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const names = new Map(
    members.data?.items.map((member) => [member.user_id, member.display_name])
  )
  const now = query.dataUpdatedAt
  const rows = (query.data || [])
    .flatMap((item) => {
      const action = item.next_action
      if (!action || item.tender_stage === 'closed') return []
      const dates = [action.due_at, item.closing_at]
        .map((value) => Date.parse(value || ''))
        .filter(Number.isFinite)
      const deadline = Math.min(...dates)
      return [{ item, action, deadline }]
    })
    .sort((a, b) => a.deadline - b.deadline)
  return (
    <Tabs defaultValue='overdue' className='flex h-full min-h-0 flex-col gap-0'>
      <QueueTabsHeader title='Oversight' tabs={oversightTabs} />
      {Object.keys(oversightTabs).map((tab) => {
        const overdue = tab === 'overdue'
        const visible = rows.filter((row) =>
          overdue ? row.deadline < now : row.deadline >= now
        )
        return (
          <TabsContent
            key={tab}
            value={tab}
            className='min-h-0 overflow-y-auto'
          >
            {query.isPending && (
              <p role='status' className='p-6'>
                Loading oversight…
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
            {query.isSuccess && !visible.length && (
              <p className='p-6 text-muted-foreground'>
                {tab === 'overdue' ? 'No overdue work.' : 'No upcoming work.'}
              </p>
            )}
            {visible.map(({ item, action }) => {
              const params = new URLSearchParams({ section: action.section })
              if (action.task_id) params.set('task', action.task_id)
              const href =
                '/tenders/' + encodeURIComponent(item.tender_id) + '?' + params
              return (
                <Link key={item.tender_id} href={href} className={queueRow}>
                  <span className='flex items-center justify-between gap-4'>
                    <span className='min-w-0'>
                      <span className='block font-medium'>{item.title}</span>
                      <span className='mt-2 block text-xs text-muted-foreground'>
                        {action.label} ·{' '}
                        {names.get(action.assignee_id || '') ||
                          'Assignee unavailable'}{' '}
                        ·{' '}
                        {action.due_at
                          ? 'Due ' + singapore(action.due_at)
                          : 'No internal deadline'}{' '}
                        ·{' '}
                        {item.closing_at
                          ? 'Tender closes ' + singapore(item.closing_at)
                          : 'Closing date unavailable'}
                      </span>
                    </span>
                    <ChevronRight
                      className='size-4 shrink-0 text-muted-foreground'
                      aria-hidden='true'
                    />
                  </span>
                </Link>
              )
            })}
          </TabsContent>
        )
      })}
    </Tabs>
  )
}
