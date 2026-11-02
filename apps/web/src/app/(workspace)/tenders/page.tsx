'use client'

import { useSession } from '@/features/qualification/session'
import { WorkInbox } from '@/features/qualification/work-inbox'

export default function TendersPage() {
  const { actor, api } = useSession()
  return actor ? <WorkInbox actor={actor} api={api} /> : null
}
