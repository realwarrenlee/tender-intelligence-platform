/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ActionError, Field, selectStyle, useAction } from './actions'
import {
  type Actor,
  type Api,
  type Citation,
  type Member,
  requestId,
  singapore,
} from './api'
import type { components } from './api.generated'
import { CommercialCostingPanel } from './commercial-costing-panel'
import { ProposalPanel } from './proposal-panel'
import { Citations } from './source-pane'
import { TaskDialog } from './task-dialog'

type Deliverable = components['schemas']['Deliverable']
type Preparation = components['schemas']['PreparationView']
type WorkAction = Exclude<
  Deliverable['permitted_actions'][number],
  'draft_proposal'
>
type DialogState = { approvalId: string } & (
  | { action: 'create' }
  | { action: WorkAction; item: Deliverable }
)

const labels = {
  technical_response: 'Technical response',
  pricing_workbook: 'Pricing workbook',
}
const statuses = {
  draft: 'In preparation',
  in_review: 'Awaiting review',
  changes_requested: 'Changes requested',
  accepted: 'Accepted for preparation',
  non_current: 'Needs reconfirmation',
}
const actions = {
  create: 'Add deliverable',
  upload: 'Upload version',
  request_review: 'Request review',
  accept: 'Accept version',
  request_changes: 'Request changes',
  reconfirm: 'Reconfirm deliverable',
  update_plan: 'Edit deliverable plan',
}

export function PreparationPanel({
  api,
  actor,
  tenderId,
  focusItemId,
  members,
  findings,
  onOpen,
  onChange,
  onRequestProposal,
  requestedProposalRefs = [],
}: {
  api: Api
  actor: Actor
  tenderId: string
  focusItemId?: string
  members: Member[]
  findings: { id: string; statement: string }[]
  onOpen: (screeningId: string, citation: Citation) => void
  onChange: () => void
  onRequestProposal?: (
    requirement: components['schemas']['ProposalRequirement'],
    trigger: HTMLButtonElement
  ) => void
  requestedProposalRefs?: string[]
}) {
  const url = '/tenders/' + encodeURIComponent(tenderId) + '/preparation'
  const query = useQuery({
    queryKey: ['preparation', tenderId, actor.user_id],
    queryFn: () => api.get<Preparation>(url),
    refetchInterval: 15000,
  })
  const [dialog, setDialog] = useState<DialogState>()
  const [downloadError, setDownloadError] = useState('')
  const trigger = useRef<HTMLButtonElement | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const data = query.data
  const focusedItem = useRef<HTMLElement>(null)
  const hasFocusedItem =
    !!focusItemId && !!data?.items.some((item) => item.id === focusItemId)
  useEffect(() => {
    if (hasFocusedItem) focusedItem.current?.focus()
  }, [hasFocusedItem, focusItemId])
  function open(next: DialogState, button: HTMLButtonElement) {
    trigger.current = button
    setDialog(next)
  }
  function restoreFocus() {
    requestAnimationFrame(() => {
      if (trigger.current?.isConnected) trigger.current.focus()
      else heading.current?.focus()
    })
  }
  const name = (id: string) =>
    members.find((member) => member.user_id === id)?.display_name ||
    'Assigned member'
  async function download(
    item: Deliverable,
    file: Deliverable['files'][number]
  ) {
    setDownloadError('')
    try {
      const blob = await api.blob(url + '/' + item.id + '/files/' + file.id)
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = file.filename
      link.click()
      setTimeout(() => URL.revokeObjectURL(href), 1000)
    } catch (error) {
      setDownloadError(
        error instanceof Error
          ? error.message
          : 'The working file could not be downloaded.'
      )
    }
  }
  const kinds = (Object.keys(labels) as Deliverable['kind'][]).filter(
    (kind) => !data?.items.some((item) => item.kind === kind)
  )
  return (
    <>
      <section className='space-y-2 border-b px-6 py-5'>
        <div className='flex flex-wrap items-center justify-between gap-3'>
          <h2 ref={heading} tabIndex={-1} className='text-lg font-medium'>
            Bid deliverables
          </h2>
          {data?.approval_id &&
            data.can_create &&
            kinds.length > 0 &&
            !query.isError && (
              <Button
                size='sm'
                onClick={(e) =>
                  open(
                    { action: 'create', approvalId: data.approval_id! },
                    e.currentTarget
                  )
                }
              >
                Add deliverable
              </Button>
            )}
        </div>
        {data && (
          <p className='text-sm text-muted-foreground'>
            {data.approval_id
              ? data.scope
              : 'A current preparation approval is required before work can start or resume.'}
          </p>
        )}
      </section>
      {query.isPending && (
        <p role='status' className='px-6 py-5'>
          Loading deliverables…
        </p>
      )}
      {query.error && (
        <p role='alert' className='px-6 py-5'>
          {query.error.message}{' '}
          <Button variant='link' onClick={() => void query.refetch()}>
            Retry
          </Button>
        </p>
      )}
      {downloadError && (
        <p role='alert' className='px-6 py-3'>
          {downloadError}
        </p>
      )}
      {data?.items.length === 0 && (
        <p className='px-6 py-5 text-sm text-muted-foreground'>
          No deliverables tracked yet.
        </p>
      )}
      {data?.items.map((item) => (
        <section
          key={item.id}
          ref={focusItemId === item.id ? focusedItem : undefined}
          tabIndex={-1}
          aria-label={labels[item.kind]}
          className='space-y-4 border-b px-6 py-5'
        >
          <div className='space-y-2'>
            <div className='flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1'>
              <h3 className='font-medium'>{labels[item.kind]}</h3>
              <p className='text-sm font-medium'>{statuses[item.status]}</p>
            </div>
            <p className='flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground'>
              <span>Owner: {name(item.owner_id)}</span>
              <span>Reviewer: {name(item.reviewer_id)}</span>
              <span>Internal due: {singapore(item.due_at)}</span>
            </p>
            {item.proposal_entity && (
              <p className='text-sm text-muted-foreground'>
                Bidding entity · {item.proposal_entity}
              </p>
            )}
          </div>
          {item.proposal_issue && (
            <p className='text-sm'>{item.proposal_issue}</p>
          )}
          {item.kind === 'technical_response' &&
            data.approval_id &&
            item.status !== 'non_current' &&
            !query.isError && (
              <ProposalPanel
                api={api}
                path={url + '/' + item.id + '/proposal'}
                approvalId={data.approval_id}
                revision={item.revision}
                planRevision={item.plan_revision}
                canDraft={item.permitted_actions.includes('draft_proposal')}
                onRequest={onRequestProposal}
                requestedRefs={requestedProposalRefs}
                onOpen={(citation) =>
                  onOpen(item.screening_version_id, citation)
                }
                onChange={() => {
                  void query.refetch()
                  onChange()
                }}
              />
            )}
          {item.kind === 'pricing_workbook' &&
            data.approval_id &&
            item.permitted_actions.includes('upload') &&
            !query.isError && (
              <CommercialCostingPanel
                api={api}
                tenderId={tenderId}
                uploadUrl={url + '/' + item.id + '/files'}
                approvalId={data.approval_id}
                revision={item.revision}
                onSaved={() => {
                  void query.refetch()
                  onChange()
                }}
              />
            )}
          {!!item.findings.length && (
            <details className='text-sm'>
              <summary className='cursor-pointer'>
                Linked requirements ({item.findings.length})
              </summary>
              <ul className='mt-2 space-y-2'>
                {item.findings.map((finding) => (
                  <li key={finding.id}>
                    {finding.statement}
                    <Citations
                      items={finding.citations}
                      label='Source'
                      onOpen={(citation) =>
                        onOpen(item.screening_version_id, citation)
                      }
                    />
                  </li>
                ))}
              </ul>
            </details>
          )}
          {!!item.previous_plans.length && (
            <details className='space-y-2 text-sm'>
              <summary className='cursor-pointer'>
                Previous plans ({item.previous_plans.length})
              </summary>
              {item.previous_plans.map((plan) => (
                <div key={plan.revision} className='space-y-1 border-l pl-3'>
                  <p>
                    Plan revision {plan.revision} · {singapore(plan.created_at)}
                  </p>
                  <p>
                    Owner: {name(plan.owner_id)} · Reviewer:{' '}
                    {name(plan.reviewer_id)}
                  </p>
                  <p>Internal due: {singapore(plan.due_at)}</p>
                  {plan.findings.map((finding) => (
                    <div key={finding.id}>
                      <p>{finding.statement}</p>
                      <Citations
                        items={finding.citations}
                        label='Source'
                        onOpen={(citation) =>
                          onOpen(plan.screening_version_id, citation)
                        }
                      />
                    </div>
                  ))}
                </div>
              ))}
            </details>
          )}
          <div className='space-y-2 text-sm'>
            {item.files[0] ? (
              <Button
                type='button'
                variant='outline'
                size='sm'
                onClick={() => void download(item, item.files[0])}
              >
                v{item.files[0].version} · {item.files[0].filename}
              </Button>
            ) : (
              <p className='text-muted-foreground'>No working file uploaded.</p>
            )}
            {item.reviews
              .filter((review) => review.is_current)
              .map((review) => (
                <div key={review.id} className='space-y-1'>
                  <p className='font-medium'>Review scope</p>
                  <p>{review.scope}</p>
                  {review.reason && (
                    <p className='text-muted-foreground'>{review.reason}</p>
                  )}
                </div>
              ))}
            {(item.files.length > 1 || item.reviews.length > 0) && (
              <details className='space-y-2'>
                <summary className='cursor-pointer'>
                  File and review history
                </summary>
                <ul className='divide-y'>
                  {item.files.map((file) => (
                    <li key={file.id} className='space-y-1 py-2'>
                      <Button
                        variant='link'
                        size='sm'
                        className='h-auto px-0'
                        onClick={() => void download(item, file)}
                      >
                        Download v{file.version} · {file.filename}
                      </Button>
                      <p className='text-muted-foreground'>
                        {name(file.actor_id)} · {singapore(file.created_at)}
                      </p>
                      {item.reviews
                        .filter((review) => review.file_id === file.id)
                        .map((review) => (
                          <div
                            key={review.id}
                            className='space-y-1 border-l pl-3'
                          >
                            <p>
                              {review.outcome
                                ? statuses[review.outcome]
                                : 'Review requested'}
                              {!review.is_current && ' · Non-current'}
                              {' · Plan revision ' + review.plan_revision}
                            </p>
                            <p>
                              {name(review.reviewer_id)} ·{' '}
                              {singapore(
                                review.reviewed_at || review.created_at
                              )}
                            </p>
                            <p>{review.scope}</p>
                            {review.reason && <p>{review.reason}</p>}
                          </div>
                        ))}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
          {data.approval_id &&
            !query.isError &&
            item.permitted_actions.length > 0 && (
              <div className='flex flex-wrap gap-2'>
                {item.permitted_actions
                  .filter((action) => action !== 'draft_proposal')
                  .map((action) => (
                    <Button
                      key={action}
                      size='sm'
                      variant={
                        action === 'request_changes' || action === 'update_plan'
                          ? 'outline'
                          : 'default'
                      }
                      onClick={(e) =>
                        open(
                          { action, approvalId: data.approval_id!, item },
                          e.currentTarget
                        )
                      }
                    >
                      {actions[action]}
                    </Button>
                  ))}
              </div>
            )}
        </section>
      ))}
      {dialog && (
        <PreparationDialog
          api={api}
          url={url}
          dialog={dialog}
          kinds={kinds}
          members={members}
          findings={findings}
          onChange={() => {
            void query.refetch()
            onChange()
          }}
          onClose={() => setDialog(undefined)}
          onReturnFocus={restoreFocus}
        />
      )}
    </>
  )
}

function PreparationDialog({
  api,
  url,
  dialog,
  kinds,
  members,
  findings,
  onChange,
  onClose,
  onReturnFocus,
}: {
  api: Api
  url: string
  dialog: DialogState
  kinds: Deliverable['kind'][]
  members: Member[]
  findings: { id: string; statement: string }[]
  onChange: () => void
  onClose: () => void
  onReturnFocus: () => void
}) {
  const action = useAction(onChange)
  const item = 'item' in dialog ? dialog.item : undefined
  const [kind, setKind] = useState(item?.kind || kinds[0])
  const formAction = dialog.action
  const planning =
    formAction === 'create' ||
    formAction === 'reconfirm' ||
    formAction === 'update_plan'
  const assignees = members.filter((member) =>
    member.roles.some((role) => role === 'member' || role === 'admin')
  )
  const latest = item?.files[0]
  return (
    <TaskDialog
      title={actions[formAction]}
      description={
        planning && item
          ? 'Changing the plan requires a fresh review of the working file.'
          : latest && formAction !== 'upload'
            ? 'v' + latest.version + ' · ' + latest.filename
            : undefined
      }
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <form
        className='space-y-4'
        onSubmit={(event) => {
          event.preventDefault()
          const form = new FormData(event.currentTarget)
          const command = {
            approval_id: dialog.approvalId,
            client_request_id: requestId(),
            expected_revision: item?.revision,
          }
          const plan = {
            due_at: form.get('due') + ':00+08:00',
            finding_ids: form.getAll('findings'),
            owner_id: form.get('owner'),
            reviewer_id: form.get('reviewer'),
            ...(kind === 'technical_response' && form.has('proposal-entity')
              ? { proposal_entity: String(form.get('proposal-entity')) }
              : {}),
          }
          action.run(async () => {
            const path = item ? url + '/' + item.id : url
            if (formAction === 'create') {
              await api.send(path, {
                ...command,
                ...plan,
                kind: form.get('kind'),
              })
            } else if (formAction === 'upload') {
              form.set('metadata', JSON.stringify(command))
              await api.upload(path + '/files', form)
            } else {
              await api.send(path + '/actions', {
                ...command,
                action: formAction,
                ...(planning ? plan : { note: form.get('note') }),
                ...(form.has('requirements-checked')
                  ? { requirements_checked: true }
                  : {}),
              })
            }
            onChange()
            onClose()
            onReturnFocus()
          })
        }}
      >
        <fieldset
          className='space-y-4'
          disabled={action.busy || action.uncertain}
        >
          {formAction === 'create' && (
            <Field label='Deliverable'>
              <select
                className={selectStyle}
                name='kind'
                required
                value={kind}
                onChange={(event) =>
                  setKind(event.target.value as Deliverable['kind'])
                }
              >
                {kinds.map((kind) => (
                  <option key={kind} value={kind}>
                    {labels[kind]}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {formAction === 'accept' && !!item?.findings.length && (
            <div className='space-y-2 text-sm'>
              <ul className='list-disc space-y-1 pl-5'>
                {item.findings.map((finding) => (
                  <li key={finding.id}>
                    {finding.statement}
                    {finding.condition && (
                      <p className='text-muted-foreground'>
                        Approval condition: {finding.condition}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
              <label className='flex items-start gap-2'>
                <input
                  type='checkbox'
                  name='requirements-checked'
                  required={!!item.proposal_requires_confirmation}
                />
                I checked that this version satisfies the linked requirements
                and their approval conditions.
              </label>
            </div>
          )}
          {planning ? (
            <>
              {kind === 'technical_response' && (
                <Field label='Bidding legal entity for proposal drafting'>
                  <Input
                    name='proposal-entity'
                    maxLength={200}
                    defaultValue={item?.proposal_entity || ''}
                  />
                </Field>
              )}
              {(['owner', 'reviewer'] as const).map((role) => {
                const prior =
                  role === 'owner' ? item?.owner_id : item?.reviewer_id
                return (
                  <Field
                    key={role}
                    label={role === 'owner' ? 'Deliverable owner' : 'Reviewer'}
                  >
                    <select
                      className={selectStyle}
                      name={role}
                      required
                      defaultValue={
                        assignees.some((member) => member.user_id === prior)
                          ? prior
                          : ''
                      }
                    >
                      <option value=''>Select member</option>
                      {assignees.map((member) => (
                        <option key={member.user_id} value={member.user_id}>
                          {member.display_name}
                        </option>
                      ))}
                    </select>
                  </Field>
                )
              })}
              <Field label='Internal due time (SGT)'>
                <Input
                  name='due'
                  type='datetime-local'
                  required
                  defaultValue={
                    item
                      ? new Date(Date.parse(item.due_at) + 8 * 3600000)
                          .toISOString()
                          .slice(0, 16)
                      : undefined
                  }
                />
              </Field>
              {!!findings.length && (
                <fieldset className='max-h-40 space-y-2 overflow-y-auto border-y py-3'>
                  <legend className='px-1 text-sm'>
                    Linked requirements (optional)
                  </legend>
                  {findings.map((finding) => (
                    <label
                      key={finding.id}
                      className='flex items-start gap-2 text-sm'
                    >
                      <input
                        type='checkbox'
                        className='mt-1'
                        name='findings'
                        value={finding.id}
                        defaultChecked={item?.findings.some(
                          (linked) =>
                            linked.id === finding.id &&
                            linked.statement === finding.statement
                        )}
                      />
                      {finding.statement}
                    </label>
                  ))}
                </fieldset>
              )}
            </>
          ) : formAction === 'upload' ? (
            <Field label='Working file (up to 20 MiB)'>
              <Input
                type='file'
                name='file'
                required
                accept={
                  item?.kind === 'pricing_workbook' ? '.xlsx' : '.pdf,.docx'
                }
              />
            </Field>
          ) : (
            <Field
              label={
                formAction === 'request_review'
                  ? 'Review scope'
                  : 'Review reason'
              }
            >
              <Textarea name='note' required maxLength={2000} />
            </Field>
          )}
        </fieldset>
        <ActionError action={action} />
        <div className='flex justify-end gap-2'>
          <Button
            type='button'
            variant='outline'
            onClick={onClose}
            disabled={action.busy || action.uncertain}
          >
            Cancel
          </Button>
          <Button type='submit' disabled={action.busy || action.uncertain}>
            Confirm {actions[formAction].toLowerCase()}
          </Button>
        </div>
      </form>
    </TaskDialog>
  )
}
