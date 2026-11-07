'use client'
import { useSession } from '@/features/workspace/session'
import { Oversight } from '@/features/workspace/workspace-activity'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <Oversight actor={actor} api={api} /> : null
}
