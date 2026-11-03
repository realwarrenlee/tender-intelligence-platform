/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronRight,
  FilePlus2,
  FileText,
  X,
} from 'lucide-react'
import Link from 'next/link'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ActionError, Field, selectStyle, useAction } from './actions'
import { AddDocuments } from './add-documents'
import {
  type Actor,
  type Api,
  type Anchor,
  type Citation,
  type Member,
  type ReviewCase,
  type Task,
  type Tender,
  requestId,
  singapore,
} from './api'
import { PreparationPanel } from './preparation-panel'
import {
  QualificationOverview,
  screeningAttention as attention,
} from './qualification-overview'
import { AnswerForm } from './questions'
import { type SourceCoverageData } from './source-coverage'
import { SourcePane } from './source-pane'
import { SubmissionPanel } from './submission-panel'
import { TaskDialog } from './task-dialog'

type RequestDraft = {
  draft_ref: string
  purpose: string
  question: string
  owner_function?: string
}
const words = (value: string) => value.replaceAll('_', ' ')
function RequestConfirmation({
  draft,
  review,
  api,
  members,
  disabled,
  onChange,
  onClose,
  onReturnFocus,
}: {
  draft: RequestDraft
  review: ReviewCase
  api: Api
  members: Member[]
  disabled: boolean
  onChange: () => void
  onClose: () => void
  onReturnFocus: () => void
}) {
  const action = useAction(onChange)
  const pending = disabled || action.busy || action.uncertain
  return (
    <TaskDialog
      title='Confirm human request'
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <form
        className='grid gap-4'
        onSubmit={(event) => {
          event.preventDefault()
          if (pending) return
          const form = new FormData(event.currentTarget)
          const due = String(form.get('due') || '')
          const command = {
            expected_assessment_version_id: review.screening_version_id,
            draft_ref: draft.draft_ref,
            assignee_id: String(form.get('assignee')),
            question: String(form.get('question')),
            ...(due
              ? { due_at: new Date(due + ':00+08:00').toISOString() }
              : {}),
            client_request_id: requestId(),
          }
          action.run(async () => {
            await api.send(
              '/tenders/' + review.tender_id + '/review-tasks',
              command
            )
            onChange()
            onClose()
          })
        }}
      >
        <p className='text-sm text-muted-foreground'>
          Choose the person responsible for this exact request.
        </p>
        {draft.draft_ref.startsWith('proposal:') && (
          <p className='text-sm text-muted-foreground'>
            An answer starts qualification reassessment. The bid owner will need
            to reconfirm the Technical response plan before drafting resumes.
          </p>
        )}
        <Field label='Question'>
          <Textarea
            name='question'
            defaultValue={draft.question}
            required
            maxLength={2000}
            disabled={pending}
          />
        </Field>
        <Field label='Assign to'>
          <select
            name='assignee'
            required
            defaultValue=''
            className={selectStyle}
            disabled={pending}
          >
            <option value='' disabled>
              Choose a member
            </option>
            {members
              .filter((member) =>
                member.roles.some((role) => ['member', 'admin'].includes(role))
              )
              .map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.display_name}
                </option>
              ))}
          </select>
        </Field>
        <Field label='Due · Singapore (optional)'>
          <Input name='due' type='datetime-local' disabled={pending} />
        </Field>
        <ActionError action={action} />
        <div className='flex justify-end gap-2'>
          <Button
            type='button'
            variant='ghost'
            disabled={action.busy || action.uncertain}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button disabled={pending}>Confirm request</Button>
        </div>
      </form>
    </TaskDialog>
  )
}

function PreparationDecision({
  review,
  task,
  api,
  members,
  disabled,
  onChange,
}: {
  review: ReviewCase
  task: Task
  api: Api
  members: Member[]
  disabled: boolean
  onChange: () => void
}) {
  const action = useAction(onChange)
  const [outcome, setOutcome] = useState('approve_preparation')
  const [reviewed, setReviewed] = useState(false)
  const screening = review.screening!.artifact
  const unresolved = screening.findings.filter((finding) =>
    screening.preparation_condition_ids
      ? screening.preparation_condition_ids.includes(finding.id)
      : finding.status === 'unconfirmed' && finding.material_now !== false
  )
  const blocked = !!screening.approval_blockers.length
  const approving = outcome === 'approve_preparation'
  const pending = disabled || action.busy || action.uncertain
  return (
    <form
      aria-label='Preparation decision'
      className='grid gap-4 border-t pt-5'
      onSubmit={(event) => {
        event.preventDefault()
        if (pending || (approving && (blocked || !reviewed))) return
        const form = new FormData(event.currentTarget)
        const command = {
          expected_input_revision: review.input_revision,
          expected_evidence_revision: review.evidence_revision,
          screening_version_id: review.screening_version_id,
          approval_task_id: task.id,
          outcome,
          reason: String(form.get('reason')),
          client_request_id: requestId(),
          ...(approving
            ? {
                preparation_scope: String(form.get('scope')),
                preparation_budget: {
                  amount: String(form.get('amount')),
                  currency: String(form.get('currency')),
                },
                conditions: unresolved.map((finding) => ({
                  finding_id: finding.id,
                  condition: String(form.get('condition:' + finding.id)),
                })),
              }
            : {}),
          ...(outcome === 'request_information'
            ? {
                next_assignee_id: String(form.get('next_assignee')),
                information_request: String(form.get('information')),
              }
            : {}),
        }
        action.run(async () => {
          await api.send(
            '/tenders/' + review.tender_id + '/preparation-decisions',
            command
          )
          onChange()
        })
      }}
    >
      <h3 className='font-medium'>Preparation decision</h3>
      <p className='text-sm text-muted-foreground'>
        Authorises bid preparation only. Final offer approval is a separate
        step.
      </p>
      <Field label='Outcome'>
        <select
          className={selectStyle}
          value={outcome}
          disabled={pending}
          onChange={(e) => setOutcome(e.target.value)}
        >
          <option value='approve_preparation'>Approve preparation</option>
          <option value='request_information'>Request information</option>
          <option value='decline'>Decline</option>
        </select>
      </Field>
      <Field label='Reason'>
        <Textarea name='reason' required maxLength={2000} disabled={pending} />
      </Field>
      {approving && (
        <>
          {blocked && (
            <p className='text-sm text-amber-700 dark:text-amber-300'>
              Resolve the brief's critical blockers before approving
              preparation.
            </p>
          )}
          <Field label='Preparation scope'>
            <Textarea
              name='scope'
              required
              maxLength={3000}
              disabled={pending}
            />
          </Field>
          <div className='grid gap-4 sm:grid-cols-2'>
            <Field label='Preparation budget'>
              <Input
                name='amount'
                type='number'
                min='0.01'
                step='0.01'
                required
                disabled={pending}
              />
            </Field>
            <Field label='Currency'>
              <select
                name='currency'
                className={selectStyle}
                defaultValue='SGD'
                disabled={pending}
              >
                <option value='SGD'>SGD</option>
                <option value='USD'>USD</option>
              </select>
            </Field>
          </div>
          {unresolved.map((finding) => (
            <Field key={finding.id} label={'Condition: ' + finding.statement}>
              <Textarea
                name={'condition:' + finding.id}
                required
                maxLength={1500}
                disabled={pending}
              />
            </Field>
          ))}
          <label className='flex items-start gap-3 text-sm'>
            <input
              type='checkbox'
              className='mt-1'
              checked={reviewed}
              disabled={pending}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I reviewed the preparation conditions
          </label>
        </>
      )}
      {outcome === 'request_information' && (
        <>
          <Field label='Next responsible person'>
            <select
              name='next_assignee'
              required
              className={selectStyle}
              disabled={pending}
              defaultValue=''
            >
              <option value='' disabled>
                Choose a member
              </option>
              {members
                .filter((member) =>
                  member.roles.some((role) =>
                    ['member', 'admin'].includes(role)
                  )
                )
                .map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {member.display_name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label='Information needed'>
            <Textarea
              name='information'
              required
              maxLength={2000}
              disabled={pending}
            />
          </Field>
        </>
      )}
      <ActionError action={action} />
      <Button
        className='justify-self-start'
        disabled={pending || (approving && (!reviewed || blocked))}
      >
        {approving
          ? 'Approve preparation'
          : outcome === 'decline'
            ? 'Decline'
            : 'Request information'}
      </Button>
    </form>
  )
}

export function ScreeningBrief({
  tender,
  actor,
  api,
  initialTab = 'Assessment',
  focusTaskId,
  embedded,
  onBack,
  onLegacy,
}: {
  tender: Tender
  actor: Actor
  api: Api
  initialTab?: 'Assessment' | 'Questions' | 'Preparation' | 'Submission'
  focusTaskId?: string
  embedded?: boolean
  onBack?: () => void
  onLegacy?: () => void
}) {
  const cache = useQueryClient()
  const sourceCoverage = tender.source_coverage as
    | SourceCoverageData
    | null
    | undefined
  const mobile = useIsMobile()
  const [tab, setTab] = useState(
    initialTab === 'Preparation' || initialTab === 'Submission'
      ? initialTab
      : 'Qualification'
  )
  const [selected, setSelected] = useState<Anchor>()
  const [quote, setQuote] = useState<string>()
  const [draft, setDraft] = useState<RequestDraft>()
  const [uploading, setUploading] = useState(false)
  const [sourceError, setSourceError] = useState('')
  const [focus, setFocus] = useState('')
  const trigger = useRef<HTMLButtonElement | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const questions = useRef<HTMLElement>(null)
  const reviewQuery = useQuery({
    queryKey: ['review-case', tender.id, actor.user_id],
    queryFn: () =>
      api.get<ReviewCase>('/review-cases/' + encodeURIComponent(tender.id)),
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.job_status || '')
        ? 2000
        : 15000,
  })
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const review = reviewQuery.data
  const screening = review?.screening?.artifact
  const sources = useQuery({
    queryKey: ['assessment-sources', review?.screening_version_id],
    staleTime: Infinity,
    enabled: !!review?.screening_version_id,
    queryFn: () =>
      api.get<{ anchors: Anchor[] }>(
        '/assessments/' + review!.screening_version_id + '/sources'
      ),
  })
  const anchors = sources.data?.anchors || []
  const refresh = () => {
    void cache.invalidateQueries({
      predicate: (query) => query.queryKey[0] !== 'source-file',
    })
  }
  const action = useAction(refresh)
  const processing = ['queued', 'running'].includes(review?.job_status || '')
  const errors = reviewQuery.error || sources.error || members.error
  const enabled = actor.qualification_workflow_enabled === true
  const paused = !enabled || !!errors || reviewQuery.isFetching || processing
  const current = review?.screening_is_current === true
  const owner = review?.permitted_actions.includes('start_screening') === true
  const locked = paused || !current
  const name = (id: string) =>
    members.data?.items.find((member) => member.user_id === id)?.display_name ||
    'Workspace member'
  const tasks = tender.review_tasks.filter(
    (task) => task.manifest.workflow === 'screening.v1'
  )
  const currentApproval = tasks
    .filter(
      (task) =>
        task.purpose === 'preparation_approval' &&
        task.status !== 'cancelled' &&
        task.assessment_version_id === review?.screening_version_id
    )
    .at(-1)
  const visibleTasks = focusTaskId
    ? tasks.filter((task) => task.id === focusTaskId)
    : tasks
  function taskCurrent(task: Task) {
    return (
      current &&
      task.manifest.source_signature === screening?.pins.source_signature &&
      task.manifest.evidence_revision === review?.evidence_revision &&
      (task.purpose !== 'preparation_approval' ||
        task.assessment_version_id === review?.screening_version_id)
    )
  }
  useEffect(() => {
    if (focusTaskId && initialTab !== 'Preparation')
      document.getElementById('screening-task-' + focusTaskId)?.focus()
    else if (initialTab === 'Questions')
      questions.current?.scrollIntoView({ block: 'start' })
  }, [
    focusTaskId,
    initialTab,
    tender.review_tasks,
    review?.screening_version_id,
  ])
  function start() {
    if (!review || paused || action.busy || action.uncertain) return
    const command = {
      expected_input_revision: tender.input_revision,
      ...(focus.trim() ? { investigation_queries: [focus.trim()] } : {}),
      client_request_id: requestId(),
    }
    action.run(async () => {
      await api.send('/tenders/' + tender.id + '/screenings', command)
      refresh()
    })
  }
  function returnFocus() {
    requestAnimationFrame(() => {
      if (trigger.current?.isConnected) trigger.current.focus()
      else heading.current?.focus()
    })
  }
  function open(citation: Citation) {
    if (document.activeElement instanceof HTMLButtonElement)
      trigger.current = document.activeElement
    const anchor = anchors.find((item) => item.anchor_id === citation.anchor_id)
    if (!anchor) {
      setSourceError(
        'Source reference is unavailable. Refresh this brief before relying on it.'
      )
      return
    }
    setSourceError('')
    setSelected(anchor)
    setQuote(citation.quote)
  }
  async function openPreparationSource(
    screeningId: string,
    citation: Citation
  ) {
    if (
      screeningId === review?.screening_version_id &&
      anchors.some((item) => item.anchor_id === citation.anchor_id)
    ) {
      open(citation)
      return
    }
    if (document.activeElement instanceof HTMLButtonElement)
      trigger.current = document.activeElement
    try {
      const pinned = await cache.fetchQuery({
        queryKey: ['assessment-sources', screeningId],
        queryFn: () =>
          api.get<{ anchors: Anchor[] }>(
            '/assessments/' + screeningId + '/sources'
          ),
        staleTime: Infinity,
      })
      const anchor = pinned.anchors.find(
        (item) => item.anchor_id === citation.anchor_id
      )
      if (!anchor) throw new Error('Missing pinned source')
      setSourceError('')
      setSelected(anchor)
      setQuote(citation.quote)
    } catch {
      setSourceError(
        'Source reference is unavailable. Refresh this brief before relying on it.'
      )
    }
  }
  function chooseDocument(id: string) {
    const document = tender.documents.find((item) => item.id === id)
    setSelected({
      anchor_id: '',
      document_version_id: id,
      source_role: document?.role || 'company_evidence',
      text: '',
      page: document?.content_type === 'application/pdf' ? 1 : null,
      paragraph: null,
    })
    setQuote(undefined)
  }
  const drafts = (screening?.request_drafts || []) as RequestDraft[]
  const pendingDrafts = (focusTaskId ? [] : drafts).filter(
    (item) =>
      !tasks.some(
        (task) =>
          task.status !== 'cancelled' &&
          task.assessment_version_id === review?.screening_version_id &&
          task.draft_ref === item.draft_ref
      )
  )
  const decision = review?.preparation_decision
  const showPreparation =
    initialTab === 'Preparation' ||
    actor.preparation_tracking_enabled ||
    !!review?.preparation
  const showSubmission =
    initialTab === 'Submission' ||
    actor.submission_control_enabled ||
    !!review?.submission_history
  const tenderTabs = [
    'Qualification',
    ...(showPreparation ? ['Preparation'] : []),
    ...(showSubmission ? ['Submission'] : []),
    ...(embedded ? [] : ['Sources']),
  ]
  const body = (
    <div className='flex h-full min-h-0 min-w-0 flex-col'>
      <header className='flex h-12 shrink-0 items-center justify-between gap-2 border-b px-4 sm:px-6'>
        <div className='flex min-w-0 items-center gap-2'>
          {onBack && (
            <Button
              size='icon'
              variant='ghost'
              aria-label='Back to list'
              onClick={onBack}
            >
              <ArrowLeft className='size-4' />
            </Button>
          )}
          <h1
            ref={heading}
            tabIndex={-1}
            className='truncate text-xl font-medium'
          >
            {tender.title}
          </h1>
        </div>
        {embedded && (
          <Button asChild size='sm' variant='ghost'>
            <Link
              href={
                '/tenders/' +
                encodeURIComponent(tender.id) +
                (tab === 'Preparation' || tab === 'Submission'
                  ? '?section=' + tab.toLowerCase()
                  : '')
              }
            >
              <ArrowUpRight className='size-4' />
              Open review
            </Link>
          </Button>
        )}
      </header>
      <Tabs value={tab} onValueChange={setTab} className='min-h-0 flex-1 gap-0'>
        {tenderTabs.length > 1 && (
          <div className='shrink-0 overflow-x-auto border-b px-6 py-2.5'>
            <TabsList aria-label='Tender views'>
              {tenderTabs.map((item) => (
                <TabsTrigger key={item} value={item}>
                  {item}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
        )}
        <TabsContent value='Sources' className='min-h-0 overflow-y-auto'>
          <div className='flex flex-wrap items-center justify-between gap-3 border-b px-6 py-3'>
            <h2 className='font-medium'>Tender sources</h2>
            {owner && (
              <Button
                size='sm'
                variant='outline'
                disabled={paused}
                onClick={(event) => {
                  trigger.current = event.currentTarget
                  setUploading(true)
                }}
              >
                <FilePlus2 className='size-4' />
                Add documents
              </Button>
            )}
          </div>
          {tender.opportunity && (
            <details className='border-b px-6 py-4 text-sm'>
              <summary className='cursor-pointer font-medium'>
                Current notice · Version {tender.opportunity.notice_version}
              </summary>
              <p className='mt-3'>
                {tender.opportunity.notice.origin === 'controlled_import'
                  ? 'Controlled import'
                  : 'Public notice'}{' '}
                · Notice only
              </p>
              <p className='mt-3 break-words whitespace-pre-wrap'>
                {String(tender.opportunity.notice.evidence_text || '')}
              </p>
              <p className='mt-3 text-muted-foreground'>
                Observed{' '}
                {singapore(
                  typeof tender.opportunity.notice.retrieved_at === 'string'
                    ? tender.opportunity.notice.retrieved_at
                    : null
                )}
              </p>
              {Array.isArray(tender.opportunity.notice.access_gaps) && (
                <p className='mt-3'>
                  {tender.opportunity.notice.access_gaps
                    .map((gap) => words(String(gap)).toLowerCase())
                    .join(' · ')}
                </p>
              )}
              {typeof tender.opportunity.notice.source_url === 'string' &&
                tender.opportunity.notice.source_url.startsWith(
                  'https://www.gebiz.gov.sg/'
                ) && (
                  <a
                    href={tender.opportunity.notice.source_url}
                    target='_blank'
                    rel='noreferrer'
                    className='mt-3 inline-block underline'
                  >
                    Open source notice
                  </a>
                )}
              {!!screening?.pins.notice_version_id &&
                screening!.pins.notice_version_id !==
                  tender.opportunity.notice_version_id && (
                  <p className='mt-3 text-amber-700 dark:text-amber-300'>
                    This brief uses an earlier notice. Review the amendment
                    before deciding.
                  </p>
                )}
            </details>
          )}
          {tender.opportunity && !tender.documents.length && (
            <div className='border-b px-6 py-4 text-sm'>
              <p>Notice only · Attachments not obtained</p>
              <p className='mt-2'>
                Add the tender documents before relying on a full qualification
                review.
              </p>
            </div>
          )}
          {tender.documents.map((document) => (
            <button
              key={document.id}
              type='button'
              aria-expanded={selected?.document_version_id === document.id}
              onClick={(event) => {
                trigger.current = event.currentTarget
                chooseDocument(document.id)
              }}
              className='flex w-full items-center gap-3 border-b px-6 py-3 text-left text-sm transition-colors hover:bg-accent/40 aria-expanded:bg-accent/40'
            >
              <FileText
                aria-hidden='true'
                className='size-4 shrink-0 text-muted-foreground'
              />
              <span className='min-w-0 flex-1 break-words'>
                {document.filename}
              </span>
              <ChevronRight
                aria-hidden='true'
                className='size-4 shrink-0 text-muted-foreground'
              />
            </button>
          ))}
          {!tender.documents.length && (
            <p className='px-6 py-4 text-muted-foreground'>
              No tender files have been added.
            </p>
          )}
        </TabsContent>
        <TabsContent value='Preparation' className='min-h-0 overflow-y-auto'>
          {showPreparation && (
            <PreparationPanel
              api={api}
              actor={actor}
              tenderId={tender.id}
              focusItemId={
                initialTab === 'Preparation' ? focusTaskId : undefined
              }
              members={members.data?.items || []}
              findings={screening?.findings || []}
              onOpen={(screeningId, citation) =>
                void openPreparationSource(screeningId, citation)
              }
              onChange={refresh}
              requestedProposalRefs={tasks
                .filter((task) => task.status === 'open' && taskCurrent(task))
                .map((task) => task.draft_ref)}
              onRequestProposal={
                owner && !locked
                  ? (requirement, button) => {
                      trigger.current = button
                      setDraft({
                        draft_ref: requirement.request_ref,
                        purpose: 'screening_input',
                        question: requirement.question,
                      })
                    }
                  : undefined
              }
            />
          )}
        </TabsContent>
        <TabsContent value='Submission' className='min-h-0 overflow-y-auto'>
          {showSubmission && (
            <SubmissionPanel
              api={api}
              actor={actor}
              tenderId={tender.id}
              members={members.data?.items || []}
              onChange={refresh}
            />
          )}
        </TabsContent>
        <TabsContent
          value='Qualification'
          forceMount
          className='min-h-0 overflow-y-auto data-[state=inactive]:hidden'
        >
          <div className='space-y-2 border-b px-6 py-4'>
            <div className='flex flex-wrap items-center justify-between gap-x-4 gap-y-2'>
              <h2 className='text-lg font-medium'>Qualification brief</h2>
              {onLegacy && (
                <Button
                  variant='link'
                  className='h-auto p-0'
                  onClick={onLegacy}
                >
                  View earlier assessment and history
                </Button>
              )}
            </div>
            {!enabled && (
              <p
                role='status'
                className='text-sm text-amber-700 dark:text-amber-300'
              >
                Screening is disabled. This saved brief is read-only.
              </p>
            )}
            {reviewQuery.isPending && (
              <p role='status'>Loading qualification brief…</p>
            )}
            {errors && (
              <p role='alert'>
                {errors.message} Actions requiring current evidence are paused.{' '}
                <Button variant='link' onClick={refresh}>
                  Retry
                </Button>
              </p>
            )}
            {review && (
              <>
                <p className='text-sm text-muted-foreground'>
                  <span className='font-medium text-foreground'>
                    {review.state}
                  </span>
                  {' · Closes '}
                  {singapore(review.closing_at)}
                </p>
                {screening && !current && (
                  <p
                    role='status'
                    className='text-sm text-amber-700 dark:text-amber-300'
                  >
                    Reassessment needed. This brief and earlier preparation
                    authority are non-current.
                  </p>
                )}
                {processing && (
                  <p role='status'>
                    {review.job_status === 'queued'
                      ? 'Screening queued'
                      : 'Bounded screening in progress'}{' '}
                    · Actions will update when a result is published.
                  </p>
                )}
                {!!review.attention && (
                  <p
                    role='status'
                    className='text-sm text-amber-700 dark:text-amber-300'
                  >
                    {attention(review.attention)}
                  </p>
                )}
                {review.job_status === 'failed' && (
                  <p role='alert'>
                    Screening did not complete. The bid owner can inspect the
                    sources and request another bounded run.
                  </p>
                )}
                {processing &&
                  owner &&
                  tender.jobs.find((job) =>
                    ['queued', 'running'].includes(job.status)
                  ) && (
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={action.busy || action.uncertain}
                      onClick={() => {
                        const job = tender.jobs.find((item) =>
                          ['queued', 'running'].includes(item.status)
                        )!
                        const command = {
                          expected_input_revision: tender.input_revision,
                          client_request_id: requestId(),
                        }
                        action.run(async () => {
                          await api.send('/jobs/' + job.id + '/cancel', command)
                          refresh()
                        })
                      }}
                    >
                      Cancel screening
                    </Button>
                  )}
              </>
            )}
            <ActionError action={action} />
          </div>
          {screening && (
            <>
              <QualificationOverview
                review={review!}
                members={members.data?.items || []}
                tasks={tasks.filter(
                  (task) => task.status === 'open' && taskCurrent(task)
                )}
                onOpen={open}
                onRequests={() => {
                  questions.current?.focus()
                  questions.current?.scrollIntoView({ block: 'start' })
                }}
              />
              <section
                ref={questions}
                aria-label='Review requests'
                tabIndex={-1}
                className='divide-y border-b'
              >
                <h2 className='px-6 py-4 text-lg font-medium'>
                  Review requests
                </h2>
                {visibleTasks.map((task) => (
                  <article
                    id={'screening-task-' + task.id}
                    tabIndex={-1}
                    key={task.id}
                    aria-label={task.question}
                    className='space-y-3 px-6 py-4 outline-none'
                  >
                    <h3 className='font-medium'>{task.question}</h3>
                    <p className='text-sm text-muted-foreground'>
                      {name(task.assignee_id)} · Due {singapore(task.due_at)} ·{' '}
                      {task.status}
                    </p>
                    {!taskCurrent(task) && task.status === 'open' && (
                      <p className='text-sm text-amber-700 dark:text-amber-300'>
                        Request is non-current. The bid owner must review its
                        source scope.
                      </p>
                    )}
                    {task.id === currentApproval?.id &&
                      review!.permitted_actions.includes('confirm_requests') &&
                      drafts.some(
                        (item) => item.draft_ref === 'preparation'
                      ) && (
                        <Button
                          size='sm'
                          variant='outline'
                          disabled={locked}
                          onClick={(event) => {
                            trigger.current = event.currentTarget
                            setDraft(
                              drafts.find(
                                (item) => item.draft_ref === 'preparation'
                              )
                            )
                          }}
                        >
                          Change approver
                        </Button>
                      )}
                    {task.answer && (
                      <div className='space-y-2 text-sm'>
                        <p>{task.answer.text}</p>
                        <p>
                          Answered by {name(task.answer.actor_id)} ·{' '}
                          {words(task.answer.response_kind || '')}
                        </p>
                        <p>Basis: {task.answer.basis || 'Not provided'}</p>
                      </div>
                    )}
                    {task.status === 'open' &&
                      taskCurrent(task) &&
                      task.assignee_id === actor.user_id &&
                      task.purpose !== 'preparation_approval' &&
                      actor.roles.some((role) =>
                        ['member', 'admin'].includes(role)
                      ) && (
                        <AnswerForm
                          api={api}
                          actor={actor}
                          task={task}
                          locked={locked}
                          onChange={refresh}
                        />
                      )}
                    {task.status === 'open' &&
                      taskCurrent(task) &&
                      task.assignee_id === actor.user_id &&
                      task.purpose === 'preparation_approval' &&
                      actor.roles.some(
                        (role) => role === 'member' || role === 'admin'
                      ) &&
                      review!.permitted_actions.includes(
                        'record_preparation_decision'
                      ) && (
                        <PreparationDecision
                          key={review!.screening_version_id}
                          review={review!}
                          task={task}
                          api={api}
                          members={members.data?.items || []}
                          disabled={locked}
                          onChange={refresh}
                        />
                      )}
                  </article>
                ))}
                {Array.from(
                  new Set(
                    pendingDrafts.map(
                      (item) => item.owner_function || 'bid_team'
                    )
                  )
                ).map((ownerFunction) => (
                  <div key={ownerFunction} className='divide-y'>
                    <h3 className='bg-muted/20 px-6 py-3 text-sm font-medium'>
                      {words(ownerFunction).replace(/^./, (letter) =>
                        letter.toUpperCase()
                      )}
                    </h3>
                    {pendingDrafts
                      .filter(
                        (item) =>
                          (item.owner_function || 'bid_team') === ownerFunction
                      )
                      .map((item) => (
                        <article
                          key={item.draft_ref}
                          className='space-y-3 px-6 py-4'
                        >
                          <p className='font-medium'>{item.question}</p>
                          <p className='text-sm text-muted-foreground'>
                            Draft · Unassigned
                          </p>
                          {review!.permitted_actions.includes(
                            'confirm_requests'
                          ) && (
                            <Button
                              size='sm'
                              variant='outline'
                              disabled={locked}
                              onClick={(event) => {
                                trigger.current = event.currentTarget
                                setDraft(item)
                              }}
                            >
                              Assign request
                            </Button>
                          )}
                        </article>
                      ))}
                  </div>
                ))}
              </section>
            </>
          )}
          {decision && (
            <section
              aria-label='Recorded preparation decision'
              className='space-y-3 border-b px-6 py-5'
            >
              <h2 className='text-lg font-medium'>
                {words(decision.outcome)} ·{' '}
                {decision.is_current ? 'Current' : 'Non-current'}
              </h2>
              {!screening && <p>{decision.reason}</p>}
              <p>{decision.preparation_scope}</p>
              {decision.preparation_budget && (
                <p>
                  {decision.preparation_budget.currency}{' '}
                  {String(decision.preparation_budget.amount)}
                </p>
              )}
              <p className='text-sm text-muted-foreground'>
                {name(decision.actor_id)} · {singapore(decision.created_at)}
              </p>
              {decision.conditions.map((condition, index) => (
                <p key={index} className='text-sm'>
                  {condition.condition}
                </p>
              ))}
            </section>
          )}
          {owner && (
            <section
              aria-label='Source investigation'
              className='space-y-4 border-b px-6 py-5'
            >
              <h2 className='text-lg font-medium'>Source investigation</h2>
              {owner && (
                <div className='max-w-lg'>
                  <Field label='Investigation focus (optional)'>
                    <Input
                      value={focus}
                      maxLength={200}
                      placeholder='A specific question to check'
                      disabled={paused || action.busy || action.uncertain}
                      onChange={(event) => setFocus(event.target.value)}
                    />
                  </Field>
                </div>
              )}
              {owner && (
                <Button
                  size='sm'
                  disabled={paused || action.busy || action.uncertain}
                  onClick={start}
                >
                  {screening
                    ? 'Investigate current sources'
                    : 'Start screening'}
                </Button>
              )}
            </section>
          )}
        </TabsContent>
      </Tabs>
      {sourceError && (
        <p role='alert' className='border-t p-4 text-sm'>
          {sourceError}
        </p>
      )}
    </div>
  )
  const viewer = (
    <div className='flex h-full min-h-0 flex-col border-l'>
      <div className='flex h-12 shrink-0 items-center justify-between border-b px-4'>
        <span className='text-sm font-medium'>Source evidence</span>
        <Button
          size='icon'
          variant='ghost'
          aria-label='Back to brief'
          onClick={() => {
            setSelected(undefined)
            returnFocus()
          }}
        >
          <X className='size-4' />
        </Button>
      </div>
      <div className='min-h-0 flex-1'>
        <SourcePane
          api={api}
          documents={tender.documents}
          anchor={selected}
          quote={quote}
          coverage={sourceCoverage}
        />
      </div>
    </div>
  )
  return (
    <div className='h-full min-h-0 min-w-0'>
      {mobile ? (
        <>
          <div className={selected ? 'hidden' : 'h-full'}>{body}</div>
          {selected && viewer}
        </>
      ) : (
        <ResizablePanelGroup direction='horizontal' className='h-full min-w-0'>
          <ResizablePanel id='brief' defaultSize={100} minSize={40}>
            {body}
          </ResizablePanel>
          {selected && <ResizableHandle withHandle />}
          {selected && (
            <ResizablePanel id='evidence' minSize={30}>
              {viewer}
            </ResizablePanel>
          )}
        </ResizablePanelGroup>
      )}
      {draft && review && (
        <RequestConfirmation
          draft={draft}
          review={review}
          api={api}
          members={members.data?.items || []}
          disabled={locked}
          onChange={refresh}
          onClose={() => setDraft(undefined)}
          onReturnFocus={returnFocus}
        />
      )}
      {uploading && (
        <AddDocuments
          api={api}
          tender={tender}
          locked={paused}
          onChange={refresh}
          onClose={() => setUploading(false)}
          onReturnFocus={returnFocus}
        />
      )}
    </div>
  )
}
