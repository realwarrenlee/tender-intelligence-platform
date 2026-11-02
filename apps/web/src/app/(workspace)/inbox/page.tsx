'use client'
import { useSession } from '@/features/qualification/session'
import { WorkspaceInbox } from '@/features/qualification/workspace-activity'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <WorkspaceInbox actor={actor} api={api} /> : null
}
