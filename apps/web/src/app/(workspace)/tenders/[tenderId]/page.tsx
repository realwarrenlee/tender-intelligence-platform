'use client'

import { useParams, useSearchParams } from 'next/navigation'
import { ReviewDesk } from '@/features/workspace/review-desk'
import { useSession } from '@/features/workspace/session'

export default function TenderPage() {
  const { tenderId } = useParams<{ tenderId: string }>()
  const { actor, api } = useSession()
  const search = useSearchParams()
  const section = search.get('section')
  const taskId =
    section === 'questions' || section === 'preparation'
      ? search.get('task') || undefined
      : undefined
  const initialTab =
    section === 'submission'
      ? 'Submission'
      : section === 'preparation'
        ? 'Preparation'
        : section === 'questions'
          ? 'Questions'
          : 'Assessment'
  return actor ? (
    <ReviewDesk
      key={tenderId + ':' + initialTab + ':' + (taskId || '')}
      tenderId={tenderId}
      actor={actor}
      api={api}
      initialTab={initialTab}
      focusTaskId={taskId}
    />
  ) : null
}
