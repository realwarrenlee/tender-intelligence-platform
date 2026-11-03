'use client'
import { Members } from '@/features/workspace/members'
import { useSession } from '@/features/workspace/session'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <Members api={api} /> : null
}
