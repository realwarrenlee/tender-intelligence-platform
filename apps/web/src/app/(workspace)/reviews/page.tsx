'use client'
import { useSession } from '@/features/workspace/session'
import { ReviewWork } from '@/features/workspace/workspace-activity'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <ReviewWork actor={actor} api={api} /> : null
}
