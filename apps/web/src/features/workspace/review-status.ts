import { type Tender } from './api'

export type ReviewGroup = 'Open' | 'Completed' | 'Closed'

export function reviewGroup(tender: Tender): ReviewGroup {
  if (tender.decision?.is_current && tender.decision.decision === 'decline')
    return 'Closed'
  if (tender.review_tasks.some((task) => task.status === 'open')) return 'Open'
  if (tender.decision?.is_current) return 'Completed'
  if (
    !tender.assessment &&
    tender.review_tasks.length > 0 &&
    tender.review_tasks.every((task) => task.status === 'cancelled')
  )
    return 'Closed'
  return 'Open'
}
