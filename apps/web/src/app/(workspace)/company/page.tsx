'use client'

import { CompanyEvidence } from '@/features/qualification/company-evidence'
import { useSession } from '@/features/qualification/session'

export default function EvidencePage() {
  const { actor, api } = useSession()
  return actor ? <CompanyEvidence actor={actor} api={api} /> : null
}
