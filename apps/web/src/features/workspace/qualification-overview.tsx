import { ArrowDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  type Citation,
  type Member,
  type ReviewCase,
  type Task,
  singapore,
} from './api'
import { Citations } from './source-pane'

export function screeningAttention(value: string) {
  if (value.includes('BUDGET_EXHAUSTED')) return 'Budget exhausted'
  if (value.includes('LIMIT')) return 'Screening limit reached'
  if (value === 'SCREENING_DEPENDENCY_WIDER_REQUIRED')
    return 'A wider review is needed'
  if (value === 'SCREENING_INVALID')
    return 'The generated brief could not be verified. Earlier validated findings are retained.'
  if (/PROVIDER|PRICING|CONFIGURED/.test(value))
    return 'Screening is unavailable. The bid owner needs to check service configuration.'
  return value
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase())
}

const requirementGroups = [
  ['eligibility', 'Eligibility'],
  ['bid_artifact', 'Submission requirements'],
  ['scored_criterion', 'Scored criteria'],
  ['delivery_commitment', 'Award and delivery obligations'],
  ['informational', 'Other information'],
] as const

export function QualificationOverview({
  review,
  members,
  tasks,
  onOpen,
  onRequests,
}: {
  review: ReviewCase
  members: Member[]
  tasks: Task[]
  onOpen: (citation: Citation) => void
  onRequests: () => void
}) {
  const screening = review.screening?.artifact
  if (!screening) return null
  const gaps = Array.isArray(screening.coverage.gaps)
    ? (screening.coverage.gaps as Record<string, unknown>[])
    : []
  const deferred = Array.isArray(screening.coverage.deferred)
    ? (screening.coverage.deferred as string[])
    : []
  const completed = review.state === 'Completed'
  const needsReassessment =
    review.state === 'Needs reassessment' || !review.screening_is_current
  const nextActor = review.next_actor_id
    ? members.find((member) => member.user_id === review.next_actor_id)
        ?.display_name || 'Workspace member'
    : null
  const openRequests = review.open_inputs + review.open_approvals
  const recommendations = {
    needs_information: 'Hold pending information',
    promising: 'Consider bid preparation',
    outside_policy: 'Evidenced entry condition failure',
  }
  const decision = review.preparation_decision
  const assignment = (ref: string) =>
    tasks.find((task) => task.draft_ref === ref)
  const assignmentLabel = (task: Task) =>
    'Assigned to ' +
    (members.find((member) => member.user_id === task.assignee_id)
      ?.display_name || 'Workspace member') +
    ' · Due ' +
    singapore(task.due_at)
  const decisionLabels = {
    approve_preparation: 'Preparation authorised',
    request_information: 'Further information requested',
    decline: 'Opportunity declined',
  }
  return (
    <>
      <section
        aria-label='Qualification overview'
        className='divide-y border-b'
      >
        <div className='grid gap-x-10 gap-y-5 px-6 py-5 lg:grid-cols-2'>
          <div className='space-y-4'>
            {decision && (
              <div className='space-y-1'>
                <p className='text-sm text-muted-foreground'>
                  Recorded preparation decision
                </p>
                <p className='font-medium'>
                  {decision.is_current
                    ? decisionLabels[decision.outcome]
                    : 'Preparation decision needs reassessment'}
                </p>
                <p className='text-sm'>{decision.reason}</p>
              </div>
            )}
            <div className='space-y-2'>
              <p className='text-sm text-muted-foreground'>
                Screening recommendation
              </p>
              <h3 className='text-lg font-medium'>
                {recommendations[screening.recommendation]}
              </h3>
              <p className='text-sm text-muted-foreground'>
                {decision
                  ? 'Preparation authority is limited to the recorded decision and scope.'
                  : 'A human decision is required to authorise bid preparation.'}
              </p>
              {screening.approval_blockers.map((blocker) => (
                <p
                  key={blocker}
                  className='text-sm text-amber-700 dark:text-amber-300'
                >
                  {screeningAttention(blocker)}
                </p>
              ))}
              {screening.wider_review_reason && (
                <p className='text-sm'>{screening.wider_review_reason}</p>
              )}
            </div>
          </div>
          <div className='space-y-2'>
            <h3 className='font-medium'>Next action</h3>
            {!completed && nextActor && (
              <p className='text-sm font-medium'>{nextActor}</p>
            )}
            <p className='max-w-prose text-sm text-muted-foreground'>
              {completed
                ? 'No outstanding qualification action.'
                : needsReassessment
                  ? 'Review the changed evidence before confirming further requests.'
                  : openRequests
                    ? `${openRequests} current review request${openRequests === 1 ? '' : 's'}. Review the named assignments and evidence below.`
                    : 'Review the outstanding requirements and confirm who should provide each input.'}
            </p>
            {!completed && (
              <Button size='sm' variant='outline' onClick={onRequests}>
                View review requests
                <ArrowDown aria-hidden='true' className='size-4' />
              </Button>
            )}
          </div>
        </div>
        <div className='px-6 py-4'>
          <h3 className='mb-3 font-medium'>Tender facts</h3>
          <dl className='divide-y text-sm'>
            <div className='grid gap-1 py-2 sm:grid-cols-[10rem_minmax(0,1fr)]'>
              <dt className='text-muted-foreground'>Closing deadline</dt>
              <dd>{singapore(review.closing_at)}</dd>
              <dd className='sm:col-start-2'>
                <Citations
                  items={
                    (
                      screening.facts.closing_at as
                        | { citations?: Citation[] }
                        | undefined
                    )?.citations || []
                  }
                  label='Closing source'
                  onOpen={onOpen}
                />
              </dd>
            </div>
            <div className='grid gap-1 py-2 sm:grid-cols-[10rem_minmax(0,1fr)]'>
              <dt className='text-muted-foreground'>Company evidence</dt>
              <dd>
                {screening.company_evidence.accepted_version_id
                  ? 'Accepted version used'
                  : 'No accepted version'}
              </dd>
              {Array.isArray(screening.company_evidence.gaps) &&
                screening.company_evidence.gaps.map((gap) => (
                  <dd
                    key={String(gap)}
                    className='text-amber-700 sm:col-start-2 dark:text-amber-300'
                  >
                    {screeningAttention(String(gap))}
                  </dd>
                ))}
            </div>
            {(
              [
                ['buyer', 'Buyer'],
                ['reference', 'Reference'],
                ['scope', 'Scope'],
                ['contract_period', 'Contract period'],
                ['sites', 'Sites'],
              ] as const
            ).map(([key, label]) => {
              const fact = screening.summary?.[key]
              return (
                <div
                  key={key}
                  className='grid gap-1 py-2 sm:grid-cols-[10rem_minmax(0,1fr)]'
                >
                  <dt className='text-muted-foreground'>{label}</dt>
                  <dd>{fact?.value ?? 'Unknown in this brief.'}</dd>
                  {!!fact?.citations.length && (
                    <dd className='sm:col-start-2'>
                      <Citations
                        items={fact.citations}
                        label={label + ' source'}
                        onOpen={onOpen}
                      />
                    </dd>
                  )}
                </div>
              )
            })}
          </dl>
          <p className='pt-2 text-xs text-muted-foreground'>
            Extracted · verify against sources
          </p>
        </div>
        {!!screening.overview_issues?.length && (
          <section aria-label='Qualification questions' className='divide-y'>
            <h3 className='px-6 py-4 font-medium'>Questions to resolve</h3>
            {screening.overview_issues.map((issue) => {
              const task = assignment('overview:' + issue.field)
              const team =
                issue.field === 'sites' || issue.field === 'scope'
                  ? 'Operations'
                  : 'Bid team'
              return (
                <article
                  key={issue.field}
                  className='space-y-1 px-6 py-3 text-sm'
                >
                  <p className='text-muted-foreground'>
                    {issue.field
                      .replaceAll('_', ' ')
                      .replace(/^./, (letter) => letter.toUpperCase())}{' '}
                    ·{' '}
                    {issue.kind === 'conflicting'
                      ? 'Conflicting source terms'
                      : 'Not established'}
                  </p>
                  <p>{issue.question}</p>
                  <p className='text-muted-foreground'>
                    {task
                      ? assignmentLabel(task)
                      : 'Suggested team: ' + team + ' · Unassigned'}
                  </p>
                  <Citations
                    items={issue.citations}
                    label='Issue source'
                    onOpen={onOpen}
                  />
                </article>
              )
            })}
          </section>
        )}
      </section>
      <section aria-label='Screening findings' className='divide-y border-b'>
        {requirementGroups.map(([kind, label]) => {
          const findings = screening.findings.filter(
            (finding) => finding.kind === kind
          )
          if (!findings.length) return null
          return (
            <section key={kind} aria-label={label}>
              <div className='flex items-center justify-between gap-3 border-b bg-muted/20 px-6 py-3'>
                <h2 className='font-medium'>{label}</h2>
                <span className='text-sm text-muted-foreground'>
                  {findings.length} requirement
                  {findings.length === 1 ? '' : 's'}
                </span>
              </div>
              <div className='divide-y'>
                {findings.map((finding) => {
                  const conditional =
                    finding.status === 'unconfirmed' &&
                    finding.material_now === false &&
                    screening.preparation_condition_ids?.includes(finding.id) &&
                    (finding.preparation_role === 'preparation_work' ||
                      finding.preparation_role === 'future_duty')
                  const task = assignment('finding:' + finding.id)
                  return (
                    <article key={finding.id} className='space-y-2 px-6 py-4'>
                      <h3 className='font-medium'>{finding.statement}</h3>
                      <p className='text-sm text-muted-foreground'>
                        Due {finding.due_stage} ·{' '}
                        {conditional
                          ? finding.preparation_role === 'preparation_work'
                            ? 'Preparation work'
                            : 'Future duty'
                          : finding.critical
                            ? 'Critical'
                            : finding.material_now === true
                              ? 'Material now'
                              : finding.material_now === false
                                ? 'Later consideration'
                                : 'Present impact needs review'}
                      </p>
                      <p className='text-sm'>
                        {conditional
                          ? 'Unconfirmed · Condition required before preparation approval.'
                          : finding.status === 'unconfirmed'
                            ? 'Needs confirmation'
                            : finding.status === 'supported'
                              ? 'Supported'
                              : 'Evidenced failure'}
                      </p>
                      {task && (
                        <p className='text-sm'>{assignmentLabel(task)}</p>
                      )}
                      <p className='text-sm text-muted-foreground'>
                        Suggested team:{' '}
                        {finding.owner_function
                          .replaceAll('_', ' ')
                          .replace(/^./, (letter) => letter.toUpperCase())}
                      </p>
                      <Citations
                        items={finding.tender_citations}
                        label='Tender source'
                        onOpen={onOpen}
                      />
                      <Citations
                        items={finding.company_citations}
                        label='Company source'
                        onOpen={onOpen}
                      />
                      {finding.answer_ids.map((id) => (
                        <Button
                          key={id}
                          variant='link'
                          size='sm'
                          className='h-auto px-0'
                          onClick={() =>
                            onOpen({ anchor_id: id + '-answer', quote: '' })
                          }
                        >
                          Reviewer answer
                        </Button>
                      ))}
                    </article>
                  )
                })}
              </div>
            </section>
          )
        })}
      </section>
      <details className='border-b px-6 py-5 text-sm'>
        <summary className='cursor-pointer font-medium'>
          Source coverage and processing details
        </summary>
        <div className='mt-4 space-y-3'>
          <p className='text-muted-foreground'>
            Source extraction:{' '}
            {screening.coverage.source_complete ? 'Complete' : 'Incomplete'} ·
            Investigation:{' '}
            {screening.coverage.complete
              ? 'Complete for this scope'
              : 'Needs review'}
          </p>
          {gaps.map((gap, index) => (
            <p key={index}>
              {String(gap.filename || 'Source region')}
              {gap.location_label
                ? ' · ' + String(gap.location_label)
                : ''} ·{' '}
              {gap.materiality === 'reviewed_nonmaterial'
                ? 'Reviewed as nonmaterial; source remains partial'
                : 'Materiality unknown'}
            </p>
          ))}
          {!!deferred.length && (
            <p>Pending investigation: {deferred.join(', ')}</p>
          )}
          <p>
            Screening spend{' '}
            <span>
              USD {String(screening.usage.actual_cost_usd ?? 'unknown')}
            </span>{' '}
            · Reserved USD {String(screening.usage.reserved_usd ?? 'unknown')} ·
            Allowance USD {String(screening.usage.limit_usd ?? 'unknown')}{' '}
            across runs
          </p>
        </div>
      </details>
    </>
  )
}
