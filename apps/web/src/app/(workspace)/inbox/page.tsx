'use client'
import { useSession } from '@/features/workspace/session'
import { WorkspaceInbox } from '@/features/workspace/workspace-activity'

export default function Page() {
  const { actor, api } = useSession()
  return actor ? <WorkspaceInbox actor={actor} api={api} /> : null
}
