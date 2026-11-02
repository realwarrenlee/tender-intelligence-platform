'use client'

import { useParams, useSearchParams } from 'next/navigation'
import { ReviewDesk } from '@/features/qualification/review-desk'
import { useSession } from '@/features/qualification/session'

export default function TenderPage() {
  const { tenderId } = useParams<{ tenderId: string }>()
  const { actor, api } = useSession()
  const initialTab =
    useSearchParams().get('section') === 'questions'
      ? 'Questions'
      : 'Assessment'
  return actor ? (
    <ReviewDesk
      key={tenderId + initialTab}
      tenderId={tenderId}
      actor={actor}
      api={api}
      initialTab={initialTab}
    />
  ) : null
}
