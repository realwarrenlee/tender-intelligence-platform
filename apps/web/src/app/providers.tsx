'use client'

import { useState, useSyncExternalStore } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DirectionProvider } from '@/context/direction-provider'
import { SessionProvider } from '@/features/workspace/session'

const subscribe = () => () => {}
export function Providers({ children }: { children: React.ReactNode }) {
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false
  )
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, refetchOnWindowFocus: true, staleTime: 0 },
          mutations: { retry: false },
        },
      })
  )
  // Existing session, theme and document-viewer components use browser APIs.
  if (!mounted)
    return (
      <p role='status' className='p-8'>
        Opening workspace…
      </p>
    )
  return (
    <QueryClientProvider client={client}>
      <DirectionProvider>
        <SessionProvider>{children}</SessionProvider>
      </DirectionProvider>
    </QueryClientProvider>
  )
}
