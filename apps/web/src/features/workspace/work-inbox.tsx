/* eslint-disable @tanstack/query/exhaustive-deps -- The API client is stable for a session; identity changes clear QueryClient. Keep resource keys serializable. */
import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  type Actor,
  type Api,
  type Member,
  type ReviewCase,
  singapore,
} from './api'
import { DeleteTender } from './delete-tender'
import { TenderIntake } from './tender-intake'
import { useReviewCases } from './workspace-activity'

export function WorkInbox({ actor, api }: { actor: Actor; api: Api }) {
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
      <div>
        <header className='flex h-12 items-center border-b px-6'>
          <h1 className='text-xl font-medium'>New tender</h1>
        </header>
        <div className='space-y-4 px-6 py-5'>
          <p className='text-sm text-muted-foreground'>
            Save the source files, then start screening from the tender review.
          </p>
          <TenderIntake
            api={api}
            onCancel={() => setCreating(false)}
            onChange={() => {
              void cache.invalidateQueries({ queryKey: ['review-cases'] })
            }}
            onComplete={(id) =>
              router.push('/tenders/' + encodeURIComponent(id))
            }
          />
        </div>
      </div>
    )
  return (
    <div className='flex min-h-full min-w-0 flex-col'>
      <header className='flex h-12 items-center justify-between gap-4 border-b px-6'>
        <h1 ref={heading} tabIndex={-1} className='text-xl font-medium'>
          Tenders
        </h1>
        {actor.roles.some((role) => role === 'member' || role === 'admin') && (
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
        <p role='alert' className='border-b px-6 py-3 text-sm text-destructive'>
          {query.error.message}{' '}
          <Button variant='link' onClick={() => void query.refetch()}>
            Retry
          </Button>
        </p>
      )}
      {query.isPending && (
        <p role='status' className='px-6 py-3 text-sm text-muted-foreground'>
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
                  {actor.roles.some(
                    (role) => role === 'member' || role === 'admin'
                  ) && (
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
            : 'No tenders yet.'}
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
