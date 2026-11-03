'use client'
/* eslint-disable @tanstack/query/exhaustive-deps -- API identity is stable for a session; session changes clear the shared query cache. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Input } from '@/components/ui/input'
import { type Api, type Member } from './api'
import { memberName } from './identity'

export function Members({ api }: { api: Api }) {
  const [filter, setFilter] = useState('')
  const query = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const items = (query.data?.items || []).filter((m) =>
    (m.display_name + ' ' + m.roles.join(' '))
      .toLowerCase()
      .includes(filter.toLowerCase())
  )
  return (
    <div>
      <header className='flex h-12 items-center justify-between border-b px-6'>
        <h1 className='text-xl font-medium'>Members</h1>
        <Input
          aria-label='Find a member'
          placeholder='Find a member…'
          className='h-8 w-64 text-base'
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </header>
      {query.error && (
        <p role='alert' className='m-6 text-base text-destructive'>
          {query.error.message}
        </p>
      )}
      {query.isPending && (
        <p role='status' className='p-6 text-base text-muted-foreground'>
          Loading members…
        </p>
      )}
      <table className='w-full text-left text-[15px]'>
        <thead className='border-b text-sm text-muted-foreground'>
          <tr>
            <th className='px-6 py-2 font-normal'>Name</th>
            <th className='px-6 py-2 font-normal'>Workspace roles</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m) => (
            <tr key={m.user_id} className='border-b border-border/40'>
              <td className='px-6 py-3 font-medium'>
                {memberName(m.display_name)}
              </td>
              <td className='px-6 py-3 text-sm text-muted-foreground'>
                {m.roles.map((r) => r.replaceAll('_', ' ')).join(', ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!query.isPending && !query.error && !items.length && (
        <p className='p-6 text-base text-muted-foreground'>
          No matching members.
        </p>
      )}
    </div>
  )
}
