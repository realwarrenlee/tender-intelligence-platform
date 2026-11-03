'use client'

import { useSession } from '@/features/workspace/session'
import { WorkInbox } from '@/features/workspace/work-inbox'

export default function TendersPage() {
  const { actor, api } = useSession()
  return actor ? <WorkInbox actor={actor} api={api} /> : null
}
