'use client'
import { useSession } from '@/features/qualification/session'
import { ReviewWork } from '@/features/qualification/workspace-activity'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <ReviewWork actor={actor} api={api} /> : null
}
