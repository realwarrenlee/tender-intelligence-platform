import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field, ActionError, useAction, selectStyle } from './actions'
import { type Api, type Anchor, type Assessment, requestId } from './api'
import { TaskDialog } from './task-dialog'

type Record = Assessment['requirements'][number]
function CitationFields({
  anchors,
  initial,
  required = false,
}: {
  anchors: Anchor[]
  initial?: { anchor_id: string; quote: string }
  required?: boolean
}) {
  const [anchor, setAnchor] = useState(initial?.anchor_id || '')
  const [quote, setQuote] = useState(initial?.quote || '')
  return (
    <div className='space-y-3'>
      <Field label='Supporting source'>
        <select
          name='anchor_id'
          className={selectStyle}
          required={required}
          value={anchor}
          onChange={(e) => {
            setAnchor(e.target.value)
            setQuote(
              anchors
                .find((a) => a.anchor_id === e.target.value)
                ?.text.slice(0, 600) || ''
            )
          }}
        >
          <option value=''>No source selected</option>
          {anchors.map((a) => (
            <option key={a.anchor_id} value={a.anchor_id}>
              {a.source_role.replace('_', ' ') +
                ' · ' +
                (a.page
                  ? 'page ' + a.page
                  : a.paragraph
                    ? 'paragraph ' + a.paragraph
                    : a.question || 'reviewer answer')}
            </option>
          ))}
        </select>
      </Field>
      <Field label='Exact supporting quote'>
        <Textarea
          name='quote'
          maxLength={1000}
          required={required}
          value={quote}
          onChange={(e) => setQuote(e.target.value)}
        />
      </Field>
    </div>
  )
}
export function FindingCorrection({
  api,
  tenderId,
  assessment,
  record,
  anchors,
  onChange,
  onClose,
  onReturnFocus,
  locked,
}: {
  api: Api
  tenderId: string
  assessment: Assessment
  record: Record
  anchors: Anchor[]
  onChange: () => void
  onClose: () => void
  onReturnFocus: () => void
  locked: boolean
}) {
  const req = record.requirement
  const [status, setStatus] = useState(req.status)
  const action = useAction(onChange)
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const quote = String(form.get('quote') || '').trim(),
      anchor = String(form.get('anchor_id') || '')
    const body = {
      expected_assessment_version_id: assessment.id,
      client_request_id: requestId(),
      reason: String(form.get('reason')),
      edits: {
        requirements: [
          {
            requirement_id: record.id,
            status,
            company_citations:
              quote && anchor ? [{ anchor_id: anchor, quote }] : [],
            explanation: String(form.get('explanation')),
            missing_information:
              status === 'unconfirmed' ? String(form.get('missing')) : null,
          },
        ],
      },
    }
    action.run(async () => {
      await api.send('/tenders/' + tenderId + '/assessment', body, 'PATCH')
      onChange()
      onClose()
    })
  }
  return (
    <TaskDialog
      title='Correct finding'
      description={req.text}
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <form onSubmit={submit} className='grid min-w-0 gap-4'>
        <Field label='Reviewed finding'>
          <select
            className={selectStyle}
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
          >
            <option value='met'>Met</option>
            <option value='unmet'>Unmet</option>
            <option value='unconfirmed'>Unconfirmed</option>
            <option
              value='not_assessed'
              disabled={
                req.mandatory && ['eligibility', 'delivery'].includes(req.kind)
              }
            >
              Not assessed
            </option>
          </select>
        </Field>
        <Field label='Finding explanation'>
          <Textarea
            name='explanation'
            defaultValue={req.explanation}
            required
            maxLength={2000}
          />
        </Field>
        {status === 'unconfirmed' && (
          <Field label='Missing information'>
            <Textarea
              name='missing'
              defaultValue={req.missing_information || ''}
              required
              maxLength={2000}
            />
          </Field>
        )}
        <CitationFields
          anchors={anchors.filter(
            (a) =>
              a.source_role === 'company_evidence' ||
              (a.source_role === 'review_answer' &&
                a.requirement_ids?.includes(record.id))
          )}
          initial={req.company_citations[0]}
          required={status === 'met' || status === 'unmet'}
        />
        <Field label='Reason for correction'>
          <Textarea name='reason' required maxLength={2000} />
        </Field>
        <ActionError action={action} />
        <div className='flex flex-wrap justify-end gap-3'>
          <Button
            type='button'
            variant='ghost'
            disabled={action.busy || action.uncertain}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button disabled={locked || action.busy || action.uncertain}>
            Save finding correction
          </Button>
        </div>
      </form>
    </TaskDialog>
  )
}
export function FactCorrection({
  api,
  tenderId,
  assessment,
  anchors,
  locked,
  onChange,
  onClose,
  onReturnFocus,
}: {
  api: Api
  tenderId: string
  assessment: Assessment
  anchors: Anchor[]
  locked: boolean
  onChange: () => void
  onClose: () => void
  onReturnFocus: () => void
}) {
  const [field, setField] = useState('closing_at')
  const action = useAction(onChange)
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const raw = String(form.get('value') || '').trim(),
      anchor = String(form.get('anchor_id') || ''),
      quote = String(form.get('quote') || '').trim()
    const value = raw
      ? field === 'term_months'
        ? Number(raw)
        : field === 'closing_at'
          ? raw + ':00+08:00'
          : raw
      : null
    const body = {
      expected_assessment_version_id: assessment.id,
      client_request_id: requestId(),
      reason: String(form.get('reason')),
      edits: {
        key_facts: {
          [field]: {
            value,
            citations:
              raw && anchor && quote ? [{ anchor_id: anchor, quote }] : [],
          },
        },
      },
    }
    action.run(async () => {
      await api.send('/tenders/' + tenderId + '/assessment', body, 'PATCH')
      onChange()
      onClose()
    })
  }
  return (
    <TaskDialog
      title='Edit tender details'
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <form className='grid min-w-0 gap-4' onSubmit={submit}>
        <Field label='Fact to correct'>
          <select
            className={selectStyle}
            value={field}
            onChange={(e) => setField(e.target.value)}
          >
            <option value='closing_at'>Closing date and time</option>
            <option value='title'>Tender title</option>
            <option value='buyer'>Buyer</option>
            <option value='service_start_on'>Service start date</option>
            <option value='term_months'>Contract months</option>
          </select>
        </Field>
        <Field
          label={
            field === 'closing_at'
              ? 'Reviewed value (Singapore time; blank means unknown)'
              : 'Reviewed value (blank means unknown)'
          }
        >
          <Input
            name='value'
            key={field}
            type={
              field === 'closing_at'
                ? 'datetime-local'
                : field === 'service_start_on'
                  ? 'date'
                  : field === 'term_months'
                    ? 'number'
                    : 'text'
            }
            min={field === 'term_months' ? 1 : undefined}
            max={field === 'term_months' ? 1200 : undefined}
          />
        </Field>
        <CitationFields
          anchors={anchors.filter((a) =>
            ['tender', 'addendum'].includes(a.source_role)
          )}
        />
        <p className='text-xs text-muted-foreground'>
          A known value needs its supporting source and exact quote. Clearing a
          value records it as unknown.
        </p>
        <Field label='Reason for correction'>
          <Textarea name='reason' required maxLength={2000} />
        </Field>
        <ActionError action={action} />
        <div className='flex flex-wrap justify-end gap-3'>
          <Button
            type='button'
            variant='ghost'
            disabled={action.busy || action.uncertain}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button disabled={locked || action.busy || action.uncertain}>
            Save fact correction
          </Button>
        </div>
      </form>
    </TaskDialog>
  )
}
export function ReconcileChanges({
  api,
  tenderId,
  assessment,
  anchors,
  locked,
  onChange,
  onClose,
  onReturnFocus,
}: {
  api: Api
  tenderId: string
  assessment: Assessment
  anchors: Anchor[]
  locked: boolean
  onChange: () => void
  onClose: () => void
  onReturnFocus: () => void
}) {
  const pending = assessment.reconciliation.filter(
    (c) => !c.resolved && c.requirement_id
  )
  const action = useAction(onChange)
  const [targets, setTargets] = useState<string[]>([])
  const [citationCount, setCitationCount] = useState(1)
  const candidates = assessment.requirements.filter((r) => !r.carried_forward)
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const citations = form.getAll('anchor_id').map((id, i) => ({
      anchor_id: String(id),
      quote: String(form.getAll('quote')[i]),
    }))
    const reviewed = form.get('reviewed') === 'on'
    const body = {
      expected_assessment_version_id: assessment.id,
      client_request_id: requestId(),
      reason: String(form.get('reason')),
      edits: {
        reconciliations: [
          {
            previous_requirement_id: String(form.get('previous')),
            replacement_requirement_ids: targets,
            citations,
          },
        ],
        requirements: reviewed
          ? candidates
              .filter((r) => targets.includes(r.id))
              .map((r) => ({
                requirement_id: r.id,
                status: r.requirement.status,
                company_citations: r.requirement.company_citations,
                explanation: r.requirement.explanation,
                missing_information: r.requirement.missing_information,
              }))
          : [],
      },
    }
    action.run(async () => {
      await api.send('/tenders/' + tenderId + '/assessment', body, 'PATCH')
      setTargets([])
      onChange()
      onClose()
    })
  }
  if (!pending.length) return null
  return (
    <TaskDialog
      title='Review changed obligations'
      description='Map an older obligation to its supported current replacement. Unanswered obligations stay visible.'
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <form className='min-w-0 space-y-4' onSubmit={submit}>
        <Field label='Affected obligation'>
          <select name='previous' className={selectStyle} required>
            <option value=''>Choose the obligation to reconcile</option>
            {pending.map((c, i) => (
              <option key={i} value={c.requirement_id!}>
                {c.kind +
                  ' · ' +
                  (assessment.requirements.find(
                    (r) => r.id === c.requirement_id
                  )?.requirement.text ||
                    c.previous_requirement?.text ||
                    c.requirement_id)}
              </option>
            ))}
          </select>
        </Field>
        <fieldset className='space-y-2'>
          <legend className='mb-2 text-sm font-medium'>
            Current replacements
          </legend>
          {candidates.map((r) => (
            <label className='flex items-start gap-2 text-sm' key={r.id}>
              <input
                className='mt-1'
                type='checkbox'
                checked={targets.includes(r.id)}
                onChange={(e) =>
                  setTargets(
                    e.target.checked
                      ? [...targets, r.id]
                      : targets.filter((x) => x !== r.id)
                  )
                }
              />
              {r.requirement.text}
            </label>
          ))}
        </fieldset>
        {Array.from({ length: citationCount }, (_, i) => (
          <fieldset key={i} className='space-y-2 border-t pt-3'>
            <legend className='text-sm'>Supporting citation {i + 1}</legend>
            <CitationFields
              anchors={anchors.filter((a) =>
                ['tender', 'addendum'].includes(a.source_role)
              )}
              required
            />
          </fieldset>
        ))}
        <Button
          type='button'
          variant='outline'
          onClick={() => setCitationCount((n) => n + 1)}
        >
          Add supporting citation
        </Button>
        <label className='flex items-start gap-2 text-sm'>
          <input type='checkbox' name='reviewed' className='mt-1' />I reviewed
          the selected replacement findings against their supporting evidence.
        </label>
        <Field label='Reason for reconciliation'>
          <Textarea name='reason' required maxLength={2000} />
        </Field>
        <ActionError action={action} />
        <div className='flex flex-wrap justify-end gap-3'>
          <Button
            type='button'
            variant='ghost'
            disabled={action.busy || action.uncertain}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            disabled={
              locked || action.busy || action.uncertain || !targets.length
            }
          >
            Save reviewed mapping
          </Button>
        </div>
      </form>
    </TaskDialog>
  )
}
