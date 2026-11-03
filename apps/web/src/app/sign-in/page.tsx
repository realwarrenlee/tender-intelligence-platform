import { Suspense } from 'react'
import { Login } from '@/features/workspace/session'
import { Providers } from '../providers'

export default function SignInPage() {
  return (
    <Providers>
      <Suspense fallback={<p role='status'>Opening sign-in…</p>}>
        <Login />
      </Suspense>
    </Providers>
  )
}
