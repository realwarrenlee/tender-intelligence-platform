'use client'

import { CompanyEvidence } from '@/features/workspace/company-evidence'
import { useSession } from '@/features/workspace/session'

export default function EvidencePage() {
  const { actor, api } = useSession()
  return actor ? <CompanyEvidence actor={actor} api={api} /> : null
}
