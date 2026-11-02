import type { components } from './api.generated'

export type Actor = Omit<components['schemas']['ActorView'], 'schema_version'>
export type Tender = components['schemas']['TenderDetail']
export type Assessment = components['schemas']['AssessmentView']
export type Anchor = components['schemas']['SourceAnchor']
export type Member = components['schemas']['MemberView']
export type History = components['schemas']['HistoryView']
export type Task = components['schemas']['ReviewTaskView']
export type Citation = components['schemas']['Citation']
export type Draft = components['schemas']['ReviewDraft']
export type Company = components['schemas']['CompanyView']
export type AssistantAnswer = components['schemas']['AssistantView']
export type Inbox = components['schemas']['InboxView']

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryable = false
  ) {
    super(message)
  }
}
export function createApi(
  getToken: () => Promise<string | null>,
  onUnauthorized?: () => void
) {
  async function raw(path: string, init: RequestInit = {}) {
    const token = await getToken()
    if (!token)
      throw new ApiError(401, 'UNAUTHENTICATED', 'Sign in to continue.')
    const headers = new Headers(init.headers)
    headers.set('Authorization', 'Bearer ' + token)
    const response = await fetch('/api/v1' + path, { ...init, headers })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      if (response.status === 401) onUnauthorized?.()
      throw new ApiError(
        response.status,
        body.code || 'REQUEST_FAILED',
        body.message || 'The request failed. Refresh and try again.',
        body.retryable === true
      )
    }
    return response
  }
  return {
    get: async <T>(path: string) => (await raw(path)).json() as Promise<T>,
    send: async <T>(path: string, body: unknown, method = 'POST') =>
      (
        await raw(path, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
      ).json() as Promise<T>,
    upload: async <T>(path: string, body: FormData) =>
      (await raw(path, { method: 'POST', body })).json() as Promise<T>,
    blob: async (path: string) => (await raw(path)).blob(),
  }
}
export type Api = ReturnType<typeof createApi>
export const requestId = () => crypto.randomUUID()
export function singapore(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Unknown'
  return (
    new Intl.DateTimeFormat('en-SG', {
      timeZone: 'Asia/Singapore',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value)) + ' SGT'
  )
}

export type ReviewCase = components['schemas']['ReviewCaseView']
export type ReviewCases = components['schemas']['ReviewCasesView']
export type HumanActions = components['schemas']['InboxActionsView']
export type Opportunity = components['schemas']['OpportunityView']
export type Opportunities = components['schemas']['OpportunitiesView']
