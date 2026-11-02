'use client'
/* eslint-disable @tanstack/query/exhaustive-deps -- API identity is stable for a session; session changes clear the shared query cache. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sun, Moon } from 'lucide-react'
import { useTheme } from 'next-themes'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { type Member } from './api'
import { memberName } from './identity'
import { useSession } from './session'

function Appearance() {
  const { resolvedTheme, setTheme } = useTheme()
  return (
    <section aria-labelledby='appearance-heading'>
      <h2 id='appearance-heading' className='text-xl font-medium'>
        Appearance
      </h2>
      <div className='mt-8 flex items-center justify-between gap-6 rounded-lg border p-5'>
        <p id='appearance-theme' className='text-sm'>
          Theme
        </p>
        <Tabs
          value={resolvedTheme === 'light' ? 'light' : 'dark'}
          onValueChange={setTheme}
        >
          <TabsList aria-labelledby='appearance-theme' className='h-8'>
            <TabsTrigger value='light' className='px-3 text-sm'>
              <Sun className='size-3.5' />
              Light
            </TabsTrigger>
            <TabsTrigger value='dark' className='px-3 text-sm'>
              <Moon className='size-3.5' />
              Dark
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
    </section>
  )
}
function Profile() {
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null)
  const { actor, session, api } = useSession()
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const name = memberName(
    members.data?.items.find((m) => m.user_id === actor?.user_id)
      ?.display_name ||
      session?.user.user_metadata.full_name ||
      session?.user.user_metadata.name ||
      session?.user.email ||
      'Workspace member'
  )
  const photo =
    session?.user.user_metadata.avatar_url ||
    session?.user.user_metadata.picture
  return (
    <section aria-labelledby='profile-heading'>
      <h2 id='profile-heading' className='text-xl font-medium'>
        Profile
      </h2>
      <dl className='mt-8 divide-y rounded-lg border text-base'>
        <div className='flex min-h-14 items-center justify-between gap-6 px-4 py-3'>
          <dt className='text-sm'>Profile picture</dt>
          <dd>
            <div className='grid size-9 place-items-center overflow-hidden rounded-full bg-accent'>
              {typeof photo === 'string' && photo && photo !== failedPhoto ? (
                <img
                  src={photo}
                  alt={name + "'s profile picture"}
                  className='size-full object-cover'
                  onError={() => setFailedPhoto(photo)}
                />
              ) : (
                <span className='text-xs'>{name.charAt(0).toUpperCase()}</span>
              )}
            </div>
          </dd>
        </div>
        {[
          ['Email', session?.user.email || 'Unavailable'],
          ['Name', name],
          [
            'Role',
            actor?.roles.map((r) => r.replaceAll('_', ' ')).join(', ') ||
              'Unavailable',
          ],
        ].map(([label, value]) => (
          <div
            key={label}
            className='flex min-h-14 items-center justify-between gap-6 px-4 py-3'
          >
            <dt className='shrink-0 text-sm'>{label}</dt>
            <dd className='max-w-sm min-w-0 text-right break-words'>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

export function WorkspaceSettings() {
  return (
    <div className='mx-auto max-w-2xl space-y-10 px-6 py-10'>
      <h1 className='sr-only'>Settings</h1>
      <Appearance />
      <Profile />
    </div>
  )
}
