'use client'

/* eslint-disable @tanstack/query/exhaustive-deps -- The API client is stable for a session; identity changes clear QueryClient. Keep resource keys serializable. */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createClient, type Session } from '@supabase/supabase-js'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from './actions'
import { createApi, type Actor, type Api } from './api'
import { workspaceDestination } from './navigation'

const url = process.env.NEXT_PUBLIC_SUPABASE_URL
const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
const configured =
  typeof url === 'string' &&
  typeof key === 'string' &&
  key.startsWith('sb_publishable_')
const supabase = configured ? createClient(url, key) : null
type WorkspaceSession = {
  session: Session | null
  actor: Actor | undefined
  api: Api
  loading: boolean
  error: Error | null
  retry: () => void
  signOut: () => Promise<void>
}
const Context = createContext<WorkspaceSession | null>(null)
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(configured)
  const subject = useRef<string | null>(null)
  const cache = useQueryClient()
  useEffect(() => {
    if (!supabase) return
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, next) => {
      if (subject.current !== (next?.user.id || null)) {
        cache.clear()
        subject.current = next?.user.id || null
      }
      setSession(next)
      setLoading(false)
    })
    return () => subscription.unsubscribe()
  }, [cache])
  const api = useMemo(
    () =>
      createApi(
        async () => {
          if (!supabase) return null
          const { data } = await supabase.auth.getSession()
          return data.session?.access_token || null
        },
        () => {
          void supabase?.auth.signOut({ scope: 'local' })
        }
      ),
    []
  )
  const me = useQuery({
    queryKey: ['me', session?.user.id],
    enabled: !!session,
    queryFn: () => api.get<Actor>('/me'),
    retry: false,
    refetchInterval: 30000,
  })
  async function signOut() {
    if (!supabase) return
    const { error } = await supabase.auth.signOut({ scope: 'local' })
    if (error) throw new Error('Sign-out could not be confirmed. Try again.')
    cache.clear()
  }
  return (
    <Context.Provider
      value={{
        session,
        actor: me.data,
        api,
        loading: loading || (!!session && me.isPending),
        error: me.error,
        retry: () => {
          void me.refetch()
        },
        signOut,
      }}
    >
      {children}
    </Context.Provider>
  )
}
export function useSession() {
  const context = useContext(Context)
  if (!context) throw new Error('Workspace session is unavailable.')
  return context
}
function SignInRedirect() {
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const section = search.get('section')
  const tab = search.get('tab')
  const destination = workspaceDestination(
    pathname +
      (pathname.startsWith('/tenders/') && section === 'questions'
        ? '?section=questions'
        : pathname === '/inbox' && (tab === 'human' || tab === 'agent')
          ? '?tab=' + tab
          : '')
  )
  useEffect(() => {
    router.replace('/sign-in?redirect=' + encodeURIComponent(destination))
  }, [router, destination])
  return (
    <p role='status' className='m-8'>
      Opening sign-in…
    </p>
  )
}
export function SessionGate({ children }: { children: React.ReactNode }) {
  const auth = useSession()
  if (!configured)
    return (
      <div role='alert' className='m-8'>
        Configure the Supabase URL and publishable browser key locally.
      </div>
    )
  if (auth.loading)
    return (
      <p role='status' className='m-8'>
        Checking sign-in…
      </p>
    )
  if (!auth.session) return <SignInRedirect />
  if (auth.error)
    return (
      <div className='m-8 space-y-3'>
        <p role='alert'>{auth.error.message}</p>
        <Button onClick={auth.retry}>Retry access check</Button>
        <Button variant='outline' onClick={() => void auth.signOut()}>
          Sign out
        </Button>
      </div>
    )
  if (!auth.actor) return null
  return children
}
export function Login() {
  const router = useRouter()
  const search = useSearchParams()
  const auth = useSession()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const next = search.get('redirect') || '/tenders'
  const safe = workspaceDestination(next)
  useEffect(() => {
    if (auth.session && !auth.loading && !auth.error) router.replace(safe)
  }, [auth.session, auth.loading, auth.error, safe, router])
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabase) return
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    const { error } = await supabase.auth.signInWithPassword({
      email: String(form.get('email')).trim(),
      password: String(form.get('password')),
    })
    if (error)
      setError(
        error.status === 400
          ? 'Check your email and password.'
          : 'Sign-in is unavailable. Please try again.'
      )
    setBusy(false)
  }
  return (
    <main className='grid min-h-svh place-items-center bg-background p-6'>
      <section className='w-full max-w-sm'>
        <p className='mb-5 border-b pb-3 text-sm font-semibold tracking-tight'>
          CBM Tender
        </p>
        <h1 className='text-xl font-medium'>Sign in to your workspace</h1>
        <p className='mt-2 mb-6 text-sm text-muted-foreground'>
          Review evidence, resolve questions and record your decision.
        </p>
        {!configured ? (
          <p role='alert' className='text-sm text-destructive'>
            Sign-in is unavailable. Contact your workspace administrator.
          </p>
        ) : (
          <form onSubmit={submit} className='space-y-4'>
            <Field label='Email'>
              <Input
                name='email'
                type='email'
                autoComplete='username'
                required
              />
            </Field>
            <Field label='Password'>
              <Input
                name='password'
                type='password'
                autoComplete='current-password'
                required
              />
            </Field>
            {(error || auth.error) && (
              <p role='alert' className='text-sm text-destructive'>
                {error || auth.error?.message}
              </p>
            )}
            <Button className='w-full' disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        )}
        <p className='mt-6 text-xs text-muted-foreground'>
          Access is provisioned by your workspace administrator.
        </p>
      </section>
    </main>
  )
}
