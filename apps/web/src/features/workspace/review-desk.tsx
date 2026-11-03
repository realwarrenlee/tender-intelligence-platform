/* eslint-disable @tanstack/query/exhaustive-deps -- The API client is stable for a session; identity changes clear QueryClient. Keep resource keys serializable. */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw,
  ArrowLeft,
  ArrowUpRight,
  File as FileIcon,
  Ellipsis,
  CircleAlert,
  CheckCircle2,
  LoaderCircle,
  Clock3,
  FilePlus2,
  Pencil,
  MessageSquare,
  History as HistoryIcon,
  X,
  UserRound,
  Building2,
  ChevronDown,
} from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { ActionError, useAction } from './actions'
import { AddDocuments } from './add-documents'
import {
  type Actor,
  type Api,
  type Tender,
  type Assessment,
  type Anchor,
  type Citation,
  type Member,
  type History,
  requestId,
  singapore,
} from './api'
import { AssistantPanel } from './assistant-panel'
import {
  FindingCorrection,
  FactCorrection,
  ReconcileChanges,
} from './corrections'
import { DecisionBadge } from './decision-badge'
import { DecisionHistory, VersionHistory } from './decision-history'
import { memberName } from './identity'
import { Questions } from './questions'
import { ScreeningBrief } from './screening-brief'
import { type SourceCoverageData } from './source-coverage'
import { SourcePane } from './source-pane'
import { TenderIntake } from './tender-intake'

type Props = {
  tenderId: string
  actor: Actor
  api: Api
  initialTab?: 'Assessment' | 'Questions' | 'Preparation' | 'Submission'
  embedded?: boolean
  focusTaskId?: string
  onBack?: () => void
}

const findingStatus = {
  met: {
    label: 'Supported',
    color: 'text-green-600 dark:text-green-400',
    icon: CheckCircle2,
  },
  unmet: {
    label: 'Not met',
    color: 'text-red-600 dark:text-red-400',
    icon: CircleAlert,
  },
  unconfirmed: {
    label: 'Needs confirmation',
    color: 'text-amber-700 dark:text-amber-400',
    icon: CircleAlert,
  },
  not_assessed: {
    label: 'Not assessed',
    color: 'text-muted-foreground',
    icon: CircleAlert,
  },
}

export function ReviewDesk({
  tenderId,
  actor,
  api,
  initialTab = 'Assessment',
  embedded = false,
  onBack,
  focusTaskId,
}: Props) {
  const router = useRouter()
  const cache = useQueryClient()
  const mobile = useIsMobile()
  const [legacyView, setLegacyView] = useState(false)
  const questionsSection = useRef<HTMLElement>(null)
  const [historicalId, setHistoricalId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Anchor>()
  const [quote, setQuote] = useState<string>()
  const [panel, setPanel] = useState<
    'source' | 'history' | 'assistant' | 'check' | null
  >(initialTab === 'Questions' || embedded ? 'check' : null)
  const [checkId, setCheckId] = useState<string | null>(null)
  const [checkKind, setCheckKind] = useState<'eligibility' | 'delivery' | null>(
    null
  )
  const [uploading, setUploading] = useState(false)
  const [editing, setEditing] = useState<
    'facts' | 'finding' | 'reconciliation' | null
  >(null)
  const actionsTrigger = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef<HTMLButtonElement | null>(null)
  const [correctionId, setCorrectionId] = useState('')
  const detail = useQuery({
    queryKey: ['tender', tenderId],
    queryFn: () => api.get<Tender>('/tenders/' + tenderId),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((job) =>
        ['queued', 'running'].includes(job.status)
      )
        ? 2000
        : 30000,
  })
  const old = useQuery({
    queryKey: ['assessment', historicalId],
    enabled: !!historicalId,
    queryFn: () => api.get<Assessment>('/assessments/' + historicalId),
  })
  const tender = detail.data
  const bounded =
    actor.qualification_workflow_enabled === true ||
    tender?.workflow === 'screening'
  const sourceCoverage = historicalId
    ? undefined
    : (
        tender as
          | (Tender & { source_coverage?: SourceCoverageData | null })
          | undefined
      )?.source_coverage
  const assessment = historicalId ? old.data : tender?.assessment
  const sources = useQuery({
    queryKey: ['assessment-sources', assessment?.id],
    staleTime: Infinity,
    enabled: !!assessment && (!bounded || legacyView),
    queryFn: () =>
      api.get<{ anchors: Anchor[] }>(
        '/assessments/' + assessment!.id + '/sources'
      ),
  })
  const members = useQuery({
    queryKey: ['members'],
    enabled: !bounded || legacyView,
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
  const history = useQuery({
    queryKey: ['history', tenderId],
    queryFn: () => api.get<History>('/tenders/' + tenderId + '/history'),
    enabled: !!tender && (!bounded || legacyView),
    refetchInterval: 30000,
  })
  const refresh = () => {
    void cache.invalidateQueries({
      predicate: (query) => query.queryKey[0] !== 'source-file',
    })
  }
  const action = useAction(refresh)
  const paused =
    detail.isError || sources.isError || old.isError || (bounded && legacyView)
  const owner =
    actor.roles.some((role) => role === 'member' || role === 'admin') &&
    !(bounded && legacyView)
  const job = tender?.jobs.find(
    (item) => item.input_revision === tender.input_revision
  )
  const analysisParts = job?.completed_stages
    .join(' ')
    .match(/analysis_parts:(\d+)\/(\d+)/)
  const analysisProgress = analysisParts
    ? 'Analysed ' + analysisParts[1] + ' of ' + analysisParts[2] + ' sections'
    : undefined
  const processing =
    !!job && ['queued', 'running'].includes(job.status) && !historicalId
  const locked =
    paused || processing || !!historicalId || !assessment?.is_current
  const assessmentId = assessment?.id
  useEffect(() => {
    if (initialTab === 'Questions' && assessmentId && !processing)
      questionsSection.current?.scrollIntoView({ block: 'start' })
  }, [initialTab, assessmentId, processing])
  function analyse() {
    const body = {
      expected_input_revision: tender!.input_revision,
      client_request_id: requestId(),
    }
    action.run(async () => {
      await api.send('/tenders/' + tenderId + '/analyses', body)
      setEditing(null)
      setPanel(null)
      refresh()
    })
  }
  function cancelAnalysis() {
    if (!job || !tender) return
    const body = {
      expected_input_revision: tender.input_revision,
      client_request_id: requestId(),
    }
    action.run(async () => {
      await api.send('/jobs/' + job.id + '/cancel', body)
      refresh()
    })
  }
  function open(citation: Citation) {
    if (embedded) {
      router.push('/tenders/' + encodeURIComponent(tenderId))
      return
    }
    const anchor = sources.data?.anchors.find(
      (item) => item.anchor_id === citation.anchor_id
    )
    if (anchor) {
      setSelected(anchor)
      setQuote(citation.quote)
      setPanel('source')
    }
  }
  function selectHistory(id: string) {
    setHistoricalId(id === tender?.assessment?.id ? null : id)
    setSelected(undefined)
    setQuote(undefined)
    setPanel(null)
    setEditing(null)
  }
  if (!tender)
    return (
      <div className='space-y-4 p-8'>
        {onBack && (
          <Button variant='ghost' onClick={onBack}>
            <ArrowLeft className='size-4' />
            Back to list
          </Button>
        )}
        {detail.error ? (
          <p role='alert'>{detail.error.message}</p>
        ) : (
          <p role='status'>Loading tender…</p>
        )}
        {detail.error && (
          <Button variant='outline' onClick={() => void detail.refetch()}>
            Retry
          </Button>
        )}
      </div>
    )
  if (bounded && !legacyView)
    return (
      <ScreeningBrief
        tender={tender}
        actor={actor}
        api={api}
        initialTab={initialTab}
        focusTaskId={focusTaskId}
        embedded={embedded}
        onBack={onBack}
        onLegacy={tender.assessment ? () => setLegacyView(true) : undefined}
      />
    )
  const title = assessment?.candidate.key_facts.title.value || tender.title
  const currentAnchor =
    selected &&
    (!selected.anchor_id ||
      sources.data?.anchors.some(
        (anchor) => anchor.anchor_id === selected.anchor_id
      ))
      ? selected
      : undefined
  const dockOpen =
    !!panel &&
    (panel !== 'check' ||
      (!!assessment?.requirements.length &&
        (!mobile || !!checkId || initialTab === 'Questions'))) &&
    (!processing || !!assessment || panel === 'source')
  const showSourceButton = dockOpen || !!assessment || !!tender.documents.length
  const pendingChanges =
    assessment?.reconciliation.filter(
      (change) => !change.resolved && change.requirement_id
    ) || []
  function restoreFocus() {
    const target = returnFocus.current?.isConnected
      ? returnFocus.current
      : actionsTrigger.current
    target?.focus()
  }
  function edit(task: typeof editing) {
    setPanel(null)
    setEditing(task)
  }
  const checks = (
    assessment?.requirements.filter(
      (item) =>
        item.requirement.mandatory &&
        ['eligibility', 'delivery'].includes(item.requirement.kind)
    ) || []
  ).sort(
    (a, b) =>
      Number(a.requirement.kind === 'delivery') -
      Number(b.requirement.kind === 'delivery')
  )
  const unresolved = checks.filter((item) => item.requirement.status !== 'met')
  const selectedCheck =
    assessment?.requirements.find((item) => item.id === checkId) ||
    (initialTab === 'Questions'
      ? checks.find((item) =>
          tender.review_tasks.some(
            (task) =>
              task.assignee_id === actor.user_id &&
              task.status === 'open' &&
              task.requirement_ids.includes(item.id)
          )
        )
      : undefined) ||
    unresolved[0] ||
    checks[0] ||
    assessment?.requirements[0]
  const eligibilityChecks = checks.filter(
    (record) => record.requirement.kind === 'eligibility'
  )
  const deliveryChecks = checks.filter(
    (record) => record.requirement.kind === 'delivery'
  )
  const splitChecks = !!eligibilityChecks.length && !!deliveryChecks.length
  const selectedKind =
    checkKind ||
    (selectedCheck?.requirement.kind === 'delivery'
      ? 'delivery'
      : 'eligibility')
  const shownChecks = splitChecks
    ? checks.filter((record) => record.requirement.kind === selectedKind)
    : checks
  const globalBlockerLabels = [
    ...new Set(
      (assessment?.blockers || [])
        .filter((blocker) => !blocker.requirement_id)
        .map((blocker) =>
          blocker.code === 'CLOSING_UNKNOWN'
            ? 'Closing date needs confirmation'
            : [
                  'SOURCE_INCOMPLETE',
                  'INCOMPLETE_SOURCE',
                  'UNSUPPORTED_INPUT',
                ].includes(blocker.code)
              ? 'Some source content needs review'
              : blocker.code === 'CONFLICTING_DATES'
                ? 'Conflicting source facts need review'
                : blocker.code.replace(/_/g, ' ').toLowerCase()
        )
    ),
  ]
  function workFor(record: Assessment['requirements'][number]) {
    return {
      tasks: tender!.review_tasks.filter(
        (task) =>
          task.status !== 'cancelled' &&
          task.requirement_ids.includes(record.id)
      ),
      drafts: assessment!.candidate.review_requests.filter((draft) =>
        draft.requirement_refs.includes(record.requirement.local_ref)
      ),
    }
  }
  const assignedTasks = tender.review_tasks.filter(
    (task) =>
      task.is_current &&
      task.status === 'open' &&
      checks.some((record) => task.requirement_ids.includes(record.id))
  )
  const unassignedChecks = unresolved.filter(
    (record) => !workFor(record).tasks.some((task) => task.is_current)
  )
  const correction =
    assessment?.requirements.find((item) => item.id === correctionId) ||
    assessment?.requirements[0]
  function sourceLinks(citations: Citation[]) {
    const seen = new Set<string>()
    return citations.flatMap((citation) => {
      const anchor = sources.data?.anchors.find(
        (item) => item.anchor_id === citation.anchor_id
      )
      if (!anchor || seen.has(anchor.document_version_id)) return []
      seen.add(anchor.document_version_id)
      const filename =
        tender!.documents.find(
          (document) => document.id === anchor.document_version_id
        )?.filename ||
        (anchor.source_role === 'review_answer' ? 'Reviewer answer' : 'Company')
      return [
        <button
          type='button'
          key={anchor.document_version_id}
          onClick={() => open(citation)}
          className='inline-flex max-w-full items-center gap-2 text-left text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline'
        >
          <FileIcon aria-hidden='true' className='size-4 shrink-0' />
          <span className='break-all'>{filename}</span>
        </button>,
      ]
    })
  }
  const viewer = (
    <SourcePane
      api={api}
      documents={tender.documents}
      anchor={currentAnchor}
      quote={currentAnchor ? quote : undefined}
      coverage={sourceCoverage}
    />
  )
  const auxiliaryDock =
    panel === 'source' ? (
      viewer
    ) : panel === 'history' ? (
      <aside
        aria-label='History'
        className='h-full min-h-0 overflow-y-auto p-6'
      >
        {history.isPending && (
          <p role='status' className='text-base text-muted-foreground'>
            Loading history…
          </p>
        )}
        {history.data && (
          <VersionHistory
            history={history.data}
            members={members.data?.items || []}
            onSelect={selectHistory}
          />
        )}
        {history.error && (
          <p role='alert' className='text-sm text-destructive'>
            {history.error.message}
            <Button variant='link' onClick={() => void history.refetch()}>
              Retry
            </Button>
          </p>
        )}
      </aside>
    ) : panel === 'assistant' && assessment ? (
      <aside
        aria-label='Assistant'
        className='h-full min-h-0 overflow-y-auto p-6'
      >
        <AssistantPanel
          key={assessment.id + '-assistant'}
          api={api}
          actor={actor}
          tenderId={tenderId}
          assessment={assessment}
          members={members.data?.items || []}
          locked={locked || members.isError}
          onChange={refresh}
          onOpen={open}
        />
      </aside>
    ) : null
  const dock = (
    <div className='h-full min-h-0'>
      <aside
        aria-label='Check details'
        hidden={panel !== 'check' || !dockOpen}
        className='h-full min-h-0 overflow-y-auto bg-container'
      >
        <header className='flex items-center justify-between gap-4 border-b px-6 py-5'>
          <h2 className='text-lg font-semibold'>Check details</h2>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            aria-label='Close check details'
            onClick={() => {
              setPanel(null)
              requestAnimationFrame(restoreFocus)
            }}
          >
            <X className='size-4' />
          </Button>
        </header>
        {selectedCheck && assessment && (
          <>
            <section className='space-y-3 border-b px-6 py-5'>
              <p
                className={
                  'flex items-center gap-2 text-sm ' +
                  findingStatus[selectedCheck.requirement.status].color
                }
              >
                {selectedCheck.requirement.status === 'met' ? (
                  <CheckCircle2 className='size-4' />
                ) : (
                  <CircleAlert className='size-4' />
                )}
                {findingStatus[selectedCheck.requirement.status].label}
              </p>
              <p className='text-[15px] leading-6'>
                {selectedCheck.requirement.missing_information ||
                  selectedCheck.requirement.text}
              </p>
            </section>
            <section className='space-y-4 border-b px-6 py-5'>
              <h3 className='text-sm font-medium'>
                Source · tender requirement
              </h3>
              {selectedCheck.requirement.tender_citations.map(
                (citation, index) => (
                  <div key={citation.anchor_id + index} className='space-y-3'>
                    <blockquote className='border-l-2 border-muted-foreground/40 pl-4 text-[15px] leading-6'>
                      {citation.quote}
                    </blockquote>
                    {sourceLinks([citation])}
                  </div>
                )
              )}
            </section>
            <section className='space-y-3 border-b px-6 py-5'>
              <h3 className='text-sm font-medium'>Supporting evidence</h3>
              {selectedCheck.requirement.company_citations.length ? (
                selectedCheck.requirement.company_citations.map(
                  (citation, index) => (
                    <div key={citation.anchor_id + index} className='space-y-2'>
                      <p className='text-[15px] leading-6'>{citation.quote}</p>
                      {sourceLinks([citation])}
                    </div>
                  )
                )
              ) : (
                <p className='text-sm leading-6 text-muted-foreground'>
                  No company evidence is cited for this check.
                </p>
              )}
              <Link
                href='/company'
                className='inline-flex items-center gap-2 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline'
              >
                <Building2 className='size-4' />
                Open company
              </Link>
            </section>
            <section ref={questionsSection} className='border-b px-6 py-5'>
              {checks.map((record) => {
                const work = workFor(record)
                const scopedAssessment = {
                  ...assessment,
                  candidate: {
                    ...assessment.candidate,
                    review_requests: work.drafts,
                  },
                }
                return (
                  <div key={record.id} hidden={selectedCheck.id !== record.id}>
                    <Questions
                      compact
                      api={api}
                      tenderId={tenderId}
                      actor={actor}
                      assessment={scopedAssessment}
                      tasks={work.tasks}
                      members={members.data?.items || []}
                      locked={locked || members.isError}
                      answerPaused={paused || !!historicalId}
                      onInspect={selectHistory}
                      onChange={refresh}
                    />
                  </div>
                )
              })}
              {members.error && (
                <p role='alert' className='mt-3 text-sm text-destructive'>
                  {members.error.message}
                </p>
              )}
            </section>
          </>
        )}
      </aside>

      <div hidden={panel === 'check'} className='h-full min-h-0'>
        {auxiliaryDock}
      </div>
    </div>
  )
  const content = (
    <div
      className={'w-full px-6 py-6 ' + (assessment ? 'space-y-3' : 'space-y-6')}
    >
      {onBack && (
        <h2 className='min-w-0 text-xl font-semibold tracking-tight break-words'>
          {title}
        </h2>
      )}
      {(detail.error || sources.error || old.error) && (
        <p
          role='alert'
          className='-mx-6 border-b px-6 pb-4 text-sm text-destructive'
        >
          {(detail.error || sources.error || old.error)?.message} Actions
          requiring current evidence are paused.
          <Button variant='link' className='ml-2 h-auto p-0' onClick={refresh}>
            Retry
          </Button>
        </p>
      )}
      {!!assessment && !assessment.is_current && !processing && (
        <p
          role='status'
          className='-mx-6 flex flex-wrap items-center gap-3 border-b px-6 pb-4 text-sm text-amber-700 dark:text-amber-300'
        >
          Inputs have changed. Reassess the current documents before deciding.
          {owner && !historicalId && (
            <Button
              size='sm'
              variant='outline'
              disabled={paused || action.busy || action.uncertain}
              onClick={analyse}
            >
              Reassess
            </Button>
          )}
        </p>
      )}
      {historicalId && (
        <p className='text-base text-amber-700 dark:text-amber-300'>
          Viewing a historical assessment.{' '}
          <Button
            variant='link'
            className='h-auto p-0'
            onClick={() => selectHistory(tender.assessment!.id)}
          >
            Return to current assessment
          </Button>
        </p>
      )}
      {processing && assessment && (
        <p role='status' className='text-base text-muted-foreground'>
          {analysisProgress || 'Preparing a new assessment…'}
        </p>
      )}
      <ActionError action={action} />
      {historicalId && old.isPending ? (
        <p role='status' className='text-base text-muted-foreground'>
          Loading assessment…
        </p>
      ) : processing && !assessment ? (
        <section aria-label='Tender processing' className='space-y-8 pt-6'>
          <div className='flex items-center gap-5'>
            {job!.status === 'queued' ? (
              <Clock3
                aria-hidden='true'
                className='size-10 text-muted-foreground'
              />
            ) : (
              <LoaderCircle
                aria-hidden='true'
                className='size-10 animate-spin text-amber-400'
              />
            )}
            <h2 className='text-xl font-semibold tracking-tight'>
              {job!.status === 'queued'
                ? 'Waiting for processing'
                : job!.completed_stages.includes('parsing')
                  ? 'Preparing your assessment'
                  : 'Reading your documents'}
            </h2>
          </div>
          {job!.status === 'running' && (
            <div
              role='progressbar'
              aria-label='Tender analysis progress'
              className='h-2 overflow-hidden rounded-full bg-muted'
            >
              <div className='h-full w-1/3 animate-pulse rounded-full bg-amber-400' />
            </div>
          )}
          <p role='status' className='text-base text-muted-foreground'>
            {job!.status === 'queued'
              ? 'Waiting to start'
              : analysisProgress ||
                (job!.completed_stages.includes('parsing')
                  ? 'Preparing the assessment'
                  : 'Reading the tender pack')}
          </p>
          {owner && (
            <Button
              variant='outline'
              size='sm'
              disabled={action.busy || action.uncertain}
              onClick={cancelAnalysis}
            >
              Cancel analysis
            </Button>
          )}
        </section>
      ) : !assessment ? (
        <div className='space-y-6'>
          {job &&
            ['needs_input', 'failed', 'cancelled', 'non_current'].includes(
              job.status
            ) && (
              <div
                role='alert'
                className='-mx-6 space-y-2 border-b px-6 pb-4 text-sm'
              >
                <p className='font-medium text-amber-700 dark:text-amber-300'>
                  The assessment needs attention.
                </p>
                <p>
                  {job.error_code === 'RECONCILIATION_REQUIRED'
                    ? 'Review the amended requirements before recording a decision.'
                    : job.error_code === 'SOURCE_INCOMPLETE'
                      ? 'Some documents could not be fully read. Review the sources before reassessing.'
                      : 'Review the documents before trying the analysis again.'}
                </p>
                {job.warnings
                  .filter((warning) => warning.message)
                  .map((warning, index) => (
                    <p key={index}>{String(warning.message)}</p>
                  ))}
              </div>
            )}
          {owner && !historicalId ? (
            <TenderIntake
              key={tender.id}
              api={api}
              tender={tender}
              onCancel={() => router.push('/tenders')}
              onChange={refresh}
              onComplete={refresh}
            />
          ) : (
            <p className='text-base text-muted-foreground'>
              No validated assessment yet. A bid owner can add documents and
              analyse this tender.
            </p>
          )}
        </div>
      ) : (
        <section className='-mx-6 -mb-6'>
          <div className='border-b px-6 pb-4'>
            <p className='text-sm text-muted-foreground'>
              {assessment.candidate.key_facts.buyer.value ||
                'Buyer needs confirmation'}
              {' · Closes '}
              {singapore(assessment.candidate.key_facts.closing_at.value)}
            </p>
            <div className='mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm'>
              <div className='flex items-center gap-3'>
                <span>AI recommendation</span>
                <DecisionBadge
                  decision={assessment.candidate.recommendation.decision}
                />
              </div>
              <div className='flex items-center gap-3'>
                <span className='text-muted-foreground'>Human decision</span>
                <span className='font-medium'>
                  {tender.decision
                    ? tender.decision.decision +
                      (tender.decision.is_current
                        ? ' · Current'
                        : ' · Non-current')
                    : 'Not recorded'}
                </span>
              </div>
            </div>
            <p className='mt-3 text-[15px] text-muted-foreground'>
              {splitChecks
                ? eligibilityChecks.length +
                  ' eligibility checks and ' +
                  deliveryChecks.length +
                  ' delivery checks'
                : unresolved.length
                  ? unresolved.length +
                    (unresolved.length === 1
                      ? ' qualification check needs confirmation.'
                      : ' qualification checks need confirmation.')
                  : 'All qualification checks are supported.'}
            </p>
          </div>
          {!!pendingChanges.length && (
            <div
              role='status'
              className='flex flex-wrap items-center gap-3 border-b px-6 py-4 text-sm text-amber-700 dark:text-amber-300'
            >
              <CircleAlert aria-hidden='true' className='size-4 shrink-0' />
              <span>
                Changed requirements need review before a pursuit decision.
              </span>
              {owner && (
                <Button
                  size='sm'
                  variant='outline'
                  disabled={locked}
                  onClick={() => edit('reconciliation')}
                >
                  Review changes
                </Button>
              )}
            </div>
          )}
          {!!globalBlockerLabels.length && (
            <p
              role='status'
              className='border-b px-6 py-3 text-sm text-amber-700 dark:text-amber-300'
            >
              {globalBlockerLabels.join('; ')}
            </p>
          )}
          <div className='border-b px-6 py-4'>
            <h2 className='text-lg font-semibold'>Qualification checks</h2>
          </div>
          {splitChecks && (
            <div
              role='group'
              aria-label='Check type'
              className='flex gap-1 border-b px-6 py-2'
            >
              {(['eligibility', 'delivery'] as const).map((kind) => (
                <button
                  key={kind}
                  type='button'
                  aria-pressed={selectedKind === kind}
                  className={
                    'rounded-md px-3 py-1.5 text-sm font-medium hover:bg-accent/60 ' +
                    (selectedKind === kind
                      ? 'bg-accent text-foreground'
                      : 'text-muted-foreground')
                  }
                  onClick={() => {
                    setCheckKind(kind)
                    setPanel(null)
                  }}
                >
                  {kind === 'eligibility' ? 'Eligibility' : 'Delivery'} (
                  {kind === 'eligibility'
                    ? eligibilityChecks.length
                    : deliveryChecks.length}
                  )
                </button>
              ))}
            </div>
          )}
          <table
            aria-label='Qualification checks'
            className='w-full table-fixed text-left text-[15px]'
          >
            <colgroup>
              <col className='w-[49%]' />
              <col className='w-[27%]' />
              <col />
              {owner && <col className='w-10' />}
            </colgroup>
            <thead className='border-b text-sm text-muted-foreground'>
              <tr>
                <th className='px-6 py-3 font-normal'>Check</th>
                <th className='py-3 pr-3 font-normal'>Progress</th>
                <th className='py-3 pr-4 font-normal'>Owner</th>
                {owner && (
                  <th>
                    <span className='sr-only'>Finding actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className='divide-y border-b'>
              {shownChecks.map((record) => {
                const work = workFor(record)
                const currentTasks = work.tasks.filter(
                  (task) => task.is_current
                )
                const currentTask =
                  currentTasks.find((task) => task.status === 'open') ||
                  currentTasks[0]
                const status = findingStatus[record.requirement.status]
                const Icon =
                  record.requirement.status === 'met'
                    ? CheckCircle2
                    : currentTask
                      ? UserRound
                      : status.icon
                const progress =
                  record.requirement.status === 'met'
                    ? status.label
                    : currentTask?.status === 'open'
                      ? 'Question assigned'
                      : currentTask?.answer
                        ? 'Answer received'
                        : status.label
                return (
                  <tr
                    key={record.id}
                    className={
                      'align-top transition-colors hover:bg-accent/40 ' +
                      (selectedCheck?.id === record.id && panel === 'check'
                        ? 'bg-accent/50'
                        : '')
                    }
                  >
                    <td className='p-0'>
                      <button
                        type='button'
                        aria-label={'Review check: ' + record.requirement.text}
                        aria-pressed={
                          selectedCheck?.id === record.id && panel === 'check'
                        }
                        onClick={(event) => {
                          returnFocus.current = event.currentTarget
                          setCheckId(record.id)
                          setPanel('check')
                        }}
                        className={
                          'w-full border-l-2 px-6 py-3 text-left font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring ' +
                          (selectedCheck?.id === record.id && panel === 'check'
                            ? 'border-l-amber-400'
                            : 'border-l-transparent')
                        }
                      >
                        <span className='line-clamp-2 leading-6'>
                          {record.requirement.text}
                        </span>
                        {record.carried_forward && (
                          <span className='mt-1 block text-xs text-amber-500'>
                            Needs reconciliation
                          </span>
                        )}
                      </button>
                    </td>
                    <td
                      className={
                        'py-3 pr-3 ' +
                        (currentTask && record.requirement.status !== 'met'
                          ? 'text-muted-foreground'
                          : status.color)
                      }
                    >
                      <span className='flex items-start gap-2 leading-6'>
                        <Icon
                          aria-hidden='true'
                          className='mt-1 size-4 shrink-0'
                        />
                        {progress}
                      </span>
                    </td>
                    <td className='py-3 pr-4 text-sm text-muted-foreground'>
                      {currentTask
                        ? memberName(
                            members.data?.items.find(
                              (member) =>
                                member.user_id === currentTask.assignee_id
                            )?.display_name || 'Assigned reviewer'
                          )
                        : record.requirement.status === 'met'
                          ? '—'
                          : 'Unassigned'}
                    </td>
                    {owner && (
                      <td className='py-3 pr-2'>
                        <DropdownMenu modal={false}>
                          <DropdownMenuTrigger asChild>
                            <Button
                              size='icon'
                              variant='ghost'
                              className='size-7'
                              aria-label={
                                'Finding actions: ' + record.requirement.text
                              }
                              onFocus={(event) => {
                                returnFocus.current = event.currentTarget
                              }}
                            >
                              <Ellipsis className='size-4' />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align='end'
                            onCloseAutoFocus={(event) => {
                              if (editing) event.preventDefault()
                            }}
                          >
                            <DropdownMenuItem
                              disabled={
                                locked || action.busy || action.uncertain
                              }
                              onSelect={() => {
                                setCorrectionId(record.id)
                                edit('finding')
                              }}
                            >
                              <Pencil />
                              Correct finding
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!checks.length && (
            <p className='border-b px-6 py-5 text-[15px] text-muted-foreground'>
              No mandatory eligibility or delivery checks were identified.
              Review the source coverage before deciding.
            </p>
          )}
          <p className='border-b px-6 py-2.5 text-xs text-muted-foreground'>
            {assignedTasks.length} assigned{' '}
            {assignedTasks.length === 1 ? 'question' : 'questions'} ·{' '}
            {unassignedChecks.length}{' '}
            {unassignedChecks.length === 1 ? 'check' : 'checks'} not assigned
          </p>
          <details className='group border-b'>
            <summary className='flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-sm font-medium'>
              Tender facts and submission requirements
              <ChevronDown aria-hidden='true' className='size-4 shrink-0' />
            </summary>
            <dl className='grid gap-5 px-6 pb-6 text-[15px] sm:grid-cols-2'>
              {Object.entries(assessment.candidate.key_facts)
                .filter(([key]) => key !== 'title')
                .map(([key, fact]) => (
                  <div key={key}>
                    <dt className='mb-1 text-xs text-muted-foreground'>
                      {key.replace(/_/g, ' ')}
                    </dt>
                    <dd>
                      {key === 'closing_at'
                        ? singapore(String(fact.value || ''))
                        : String(fact.value ?? 'Not supplied')}
                    </dd>
                  </div>
                ))}
            </dl>
            <ul className='divide-y border-t'>
              {assessment.requirements
                .filter((record) =>
                  ['submission', 'evaluation'].includes(record.requirement.kind)
                )
                .map((record) => (
                  <li key={record.id} className='px-6 py-4 text-[15px]'>
                    {record.requirement.text}
                  </li>
                ))}
            </ul>
          </details>
          <details className='border-b'>
            <summary className='flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-sm font-medium'>
              All extracted requirements
              <ChevronDown aria-hidden='true' className='size-4 shrink-0' />
            </summary>
            <table
              aria-label='Requirements and findings'
              className='w-full text-left text-[15px]'
            >
              <tbody className='divide-y border-t'>
                {assessment.requirements.map((record) => (
                  <tr key={record.id} className='align-top'>
                    <td className='px-6 py-4'>
                      <button
                        type='button'
                        className='text-left underline-offset-4 hover:underline'
                        onClick={(event) => {
                          returnFocus.current = event.currentTarget
                          setCheckId(record.id)
                          setPanel('check')
                        }}
                      >
                        {record.requirement.text}
                      </button>
                    </td>
                    <td
                      className={
                        'py-4 pr-6 text-sm ' +
                        findingStatus[record.requirement.status].color
                      }
                    >
                      {findingStatus[record.requirement.status].label}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className='space-y-3 border-t px-6 py-5 text-sm text-muted-foreground'>
              <h3 className='font-medium'>Assessment notes</h3>
              <p>{assessment.candidate.summary}</p>
              {assessment.candidate.warnings.map((warning, index) => (
                <p key={index} className='text-amber-700 dark:text-amber-300'>
                  {warning.message}
                </p>
              ))}
            </div>
          </details>
          <details className='border-b'>
            <summary className='flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 text-sm font-medium'>
              Decision and history
              <ChevronDown aria-hidden='true' className='size-4 shrink-0' />
            </summary>
            <div className='px-6 pb-6'>
              <DecisionHistory
                key={tenderId}
                api={api}
                actor={actor}
                tender={tender}
                assessment={assessment}
                members={members.data?.items || []}
                locked={locked}
                onChange={refresh}
              />
              <Button
                variant='link'
                className='mt-4 h-auto p-0'
                onClick={() => setPanel('history')}
              >
                View assessment and decision history
              </Button>
            </div>
          </details>
        </section>
      )}
    </div>
  )
  return (
    <div className='@container/review flex h-full min-h-0 min-w-0 flex-col'>
      <header className='flex h-12 shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-6'>
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
          <h1 className={onBack ? 'sr-only' : 'truncate text-xl font-medium'}>
            {title}
          </h1>
        </div>
        <div className='flex shrink-0 items-center gap-2'>
          {bounded && legacyView && (
            <Button
              size='sm'
              variant='ghost'
              onClick={() => setLegacyView(false)}
            >
              <ArrowLeft aria-hidden='true' className='size-4' />
              Back to qualification brief
            </Button>
          )}
          {(!processing || assessment) && (
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button
                  ref={actionsTrigger}
                  size='icon'
                  variant='ghost'
                  aria-label='More tender actions'
                  onFocus={(event) => {
                    returnFocus.current = event.currentTarget
                  }}
                >
                  <Ellipsis className='size-5' />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align='end'
                className='w-60'
                onCloseAutoFocus={(event) => {
                  if (uploading || editing) event.preventDefault()
                }}
              >
                {owner && (
                  <>
                    <DropdownMenuItem
                      disabled={
                        paused ||
                        processing ||
                        !!historicalId ||
                        action.busy ||
                        action.uncertain
                      }
                      onSelect={() => {
                        setPanel(null)
                        setUploading(true)
                      }}
                    >
                      <FilePlus2 />
                      Add documents
                    </DropdownMenuItem>
                    {assessment && (
                      <DropdownMenuItem
                        disabled={locked || action.busy || action.uncertain}
                        onSelect={() => edit('facts')}
                      >
                        <Pencil />
                        Edit tender details
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      disabled={
                        paused ||
                        processing ||
                        !!historicalId ||
                        action.busy ||
                        action.uncertain ||
                        !tender.documents.length
                      }
                      onSelect={analyse}
                    >
                      <RefreshCw />
                      {assessment ? 'Reassess' : 'Analyse tender'}
                    </DropdownMenuItem>
                    {!!pendingChanges.length && (
                      <DropdownMenuItem
                        disabled={locked || action.busy || action.uncertain}
                        onSelect={() => edit('reconciliation')}
                      >
                        <CircleAlert />
                        Review changed obligations
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                  </>
                )}
                {assessment && (
                  <DropdownMenuItem
                    onSelect={() => {
                      setPanel('assistant')
                    }}
                  >
                    <MessageSquare />
                    Ask about assessment
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem
                  onSelect={() => {
                    setPanel('history')
                  }}
                >
                  <HistoryIcon />
                  View history
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {showSourceButton && (!embedded || dockOpen) && (
            <Button
              size='sm'
              variant={embedded ? 'ghost' : 'default'}
              aria-label={
                panel === 'source' ||
                panel === 'history' ||
                panel === 'assistant'
                  ? panel === 'history'
                    ? 'Close history'
                    : panel === 'assistant'
                      ? 'Close assistant'
                      : 'Close source documents'
                  : 'Review source documents'
              }
              onClick={() =>
                setPanel(
                  panel === 'source' ||
                    panel === 'history' ||
                    panel === 'assistant'
                    ? 'check'
                    : 'source'
                )
              }
            >
              {panel === 'history' ? (
                <HistoryIcon className='size-4' />
              ) : panel === 'assistant' ? (
                <MessageSquare className='size-4' />
              ) : (
                <FileIcon className='size-4' />
              )}
              {panel === 'source' ||
              panel === 'history' ||
              panel === 'assistant'
                ? panel === 'history'
                  ? 'Close history'
                  : panel === 'assistant'
                    ? 'Close assistant'
                    : 'Close source'
                : 'Review source'}
            </Button>
          )}
          {embedded && (
            <Button asChild>
              <Link href={'/tenders/' + encodeURIComponent(tenderId)}>
                Open review
                <ArrowUpRight className='size-4' />
              </Link>
            </Button>
          )}
        </div>
      </header>
      <div
        className={
          mobile && dockOpen ? 'hidden' : 'flex min-h-0 min-w-0 flex-1'
        }
      >
        <ResizablePanelGroup
          direction='horizontal'
          className='min-h-0 min-w-0 flex-1'
        >
          <ResizablePanel
            id='assessment'
            order={1}
            minSize={35}
            className='overflow-y-auto!'
          >
            {content}
          </ResizablePanel>
          {!mobile && (
            <>
              <ResizableHandle
                withHandle
                className={dockOpen ? '' : 'hidden'}
              />
              <ResizablePanel
                id='review-detail'
                order={2}
                defaultSize={36}
                minSize={28}
                className={dockOpen ? 'min-w-0' : 'hidden!'}
              >
                {dock}
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>
      {mobile && (
        <div className={dockOpen ? 'min-h-0 flex-1' : 'hidden'}>{dock}</div>
      )}
      {uploading && owner && (
        <AddDocuments
          api={api}
          tender={tender}
          locked={paused || !!historicalId || action.busy || action.uncertain}
          onChange={refresh}
          onClose={() => setUploading(false)}
          onReturnFocus={restoreFocus}
        />
      )}
      {editing === 'facts' && assessment && owner && (
        <FactCorrection
          key={assessment.id}
          api={api}
          tenderId={tenderId}
          assessment={assessment}
          anchors={sources.data?.anchors || []}
          locked={locked}
          onChange={refresh}
          onClose={() => setEditing(null)}
          onReturnFocus={restoreFocus}
        />
      )}
      {editing === 'finding' && assessment && correction && owner && (
        <FindingCorrection
          key={assessment.id + correction.id}
          api={api}
          tenderId={tenderId}
          assessment={assessment}
          record={correction}
          anchors={sources.data?.anchors || []}
          locked={locked}
          onChange={refresh}
          onClose={() => setEditing(null)}
          onReturnFocus={restoreFocus}
        />
      )}
      {editing === 'reconciliation' && assessment && owner && (
        <ReconcileChanges
          key={assessment.id + '-reconcile'}
          api={api}
          tenderId={tenderId}
          assessment={assessment}
          anchors={sources.data?.anchors || []}
          locked={locked}
          onChange={refresh}
          onClose={() => setEditing(null)}
          onReturnFocus={restoreFocus}
        />
      )}
    </div>
  )
}
