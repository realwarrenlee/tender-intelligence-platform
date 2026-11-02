'use client'
import { Members } from '@/features/qualification/members'
import { useSession } from '@/features/qualification/session'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <Members api={api} /> : null
}
