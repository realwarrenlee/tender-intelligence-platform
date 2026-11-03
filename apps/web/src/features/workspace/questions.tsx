import { useMemo, useState } from 'react'
import { CircleAlert, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field, ActionError, selectStyle, useAction } from './actions'
import {
  type Actor,
  type Api,
  type Assessment,
  type Draft,
  type Member,
  type Task,
  requestId,
  singapore,
} from './api'
import { memberName } from './identity'

function reviewDue(closing: string | null) {
  const now = Date.now()
  const deadline = closing ? Date.parse(closing) : NaN
  const due =
    Number.isFinite(deadline) && deadline > now
      ? Math.max(
          now + 60_000,
          Math.min(now + 48 * 3600_000, deadline - 24 * 3600_000)
        )
      : now + 48 * 3600_000
  return new Date(due + 8 * 3600_000).toISOString().slice(0, 16)
}

function QuestionAssignments({
  api,
  tenderId,
  assessment,
  drafts,
  members,
  locked,
  onChange,
  compact = false,
}: {
  api: Api
  tenderId: string
  assessment: Assessment
  drafts: Draft[]
  compact?: boolean
  members: Member[]
  locked: boolean
  onChange: () => void
}) {
  const action = useAction(onChange)
  const key = (ref: string) => assessment.id + ':' + ref
  const closing = assessment.candidate.key_facts.closing_at.value
  const defaults = useMemo(
    () =>
      Object.fromEntries(
        drafts.map((draft) => [
          assessment.id + ':' + draft.draft_ref,
          { question: draft.question, assignee: '', due: reviewDue(closing) },
        ])
      ),
    [assessment.id, closing, drafts]
  )
  const [editing, setEditing] = useState<string | null>(null)
  const [assigning, setAssigning] = useState(!compact)
  const [sent, setSent] = useState<string[]>([])
  const [values, setValues] = useState(defaults)
  const pending = drafts.filter((draft) => !sent.includes(key(draft.draft_ref)))
  const disabled = locked || action.busy || action.uncertain
  function assignment(draft: Draft) {
    return values[key(draft.draft_ref)] || defaults[key(draft.draft_ref)]
  }
  function update(
    ref: string,
    field: 'question' | 'assignee' | 'due',
    value: string
  ) {
    setValues((previous) => ({
      ...previous,
      [key(ref)]: {
        ...(previous[key(ref)] ||
          assignment(drafts.find((draft) => draft.draft_ref === ref)!)),
        [field]: value,
      },
    }))
  }
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const commands = pending.map((draft) => ({
      expected_assessment_version_id: assessment.id,
      draft_ref: draft.draft_ref,
      assignee_id: assignment(draft).assignee,
      due_at: new Date(assignment(draft).due + ':00+08:00').toISOString(),
      ...(assignment(draft).question.trim() !== draft.question
        ? { question: assignment(draft).question.trim() }
        : {}),
      client_request_id: requestId(),
    }))
    const completed = new Set<string>()
    action.run(async () => {
      for (const command of commands) {
        if (completed.has(command.draft_ref)) continue
        await api.send('/tenders/' + tenderId + '/review-tasks', command)
        completed.add(command.draft_ref)
        setSent((previous) => [...previous, key(command.draft_ref)])
        onChange()
      }
    })
  }
  if (!drafts.length) return null
  if (!assigning)
    return (
      <Button
        className='w-full'
        disabled={disabled}
        onClick={() => setAssigning(true)}
      >
        Assign question
      </Button>
    )
  return (
    <form onSubmit={submit}>
      <div className={compact ? 'space-y-4' : 'divide-y border-y'}>
        {pending.map((draft) => {
          const value = assignment(draft)
          return (
            <div
              key={draft.draft_ref}
              className={
                compact
                  ? 'grid gap-4'
                  : 'grid items-start gap-6 py-7 lg:grid-cols-[minmax(0,1fr)_auto]'
              }
            >
              <div className='flex gap-4'>
                <CircleAlert
                  aria-hidden='true'
                  className={
                    compact ? 'hidden' : 'mt-0.5 size-5 shrink-0 text-amber-400'
                  }
                />
                {editing === key(draft.draft_ref) ? (
                  <div className='w-full'>
                    <Field label='Question'>
                      <Textarea
                        required
                        maxLength={2000}
                        value={value.question}
                        disabled={disabled}
                        onChange={(event) =>
                          update(
                            draft.draft_ref,
                            'question',
                            event.target.value
                          )
                        }
                      />
                    </Field>
                  </div>
                ) : (
                  <p className='pt-0.5 font-medium'>{value.question}</p>
                )}
              </div>
              <div
                className={
                  compact
                    ? 'grid gap-4'
                    : 'flex flex-wrap items-end gap-4 pl-9 lg:pl-0'
                }
              >
                <Field label='Assign to'>
                  <select
                    required
                    className={selectStyle + (compact ? '' : ' w-48')}
                    value={value.assignee}
                    disabled={disabled}
                    onChange={(event) =>
                      update(draft.draft_ref, 'assignee', event.target.value)
                    }
                  >
                    <option value='' disabled>
                      Choose a member
                    </option>
                    {members
                      .filter((member) =>
                        member.roles.some(
                          (role) => role === 'member' || role === 'admin'
                        )
                      )
                      .map((member) => (
                        <option key={member.user_id} value={member.user_id}>
                          {member.display_name}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label='Due'>
                  <Input
                    type='datetime-local'
                    required
                    className={compact ? 'w-full' : 'w-48'}
                    value={value.due}
                    disabled={disabled}
                    onChange={(event) =>
                      update(draft.draft_ref, 'due', event.target.value)
                    }
                  />
                </Field>
                <Button
                  type='button'
                  variant='ghost'
                  disabled={disabled}
                  onClick={() =>
                    setEditing(
                      editing === key(draft.draft_ref)
                        ? null
                        : key(draft.draft_ref)
                    )
                  }
                >
                  {editing === key(draft.draft_ref) ? 'Done' : 'Edit'}
                </Button>
              </div>
            </div>
          )
        })}
      </div>
      <ActionError action={action} />
      {!!pending.length && (
        <Button
          className={compact ? 'mt-5 w-full' : 'mt-7'}
          size='sm'
          disabled={disabled}
        >
          {compact && pending.length === 1 ? (
            'Assign question'
          ) : (
            <>
              Assign {pending.length}{' '}
              {pending.length === 1 ? 'question' : 'questions'}
            </>
          )}
          <ArrowRight className='size-4' />
        </Button>
      )}
    </form>
  )
}

export function DraftConfirmation({
  api,
  tenderId,
  assessment,
  draft,
  members,
  locked,
  onChange,
}: {
  api: Api
  tenderId: string
  assessment: Assessment
  draft: Draft
  members: Member[]
  locked: boolean
  onChange: () => void
}) {
  return (
    <QuestionAssignments
      api={api}
      tenderId={tenderId}
      assessment={assessment}
      drafts={[draft]}
      members={members}
      locked={locked}
      onChange={onChange}
    />
  )
}

export function AnswerForm({
  api,
  task,
  actor,
  locked,
  onChange,
}: {
  api: Api
  task: Task
  actor: Actor
  locked: boolean
  onChange: () => void
}) {
  const action = useAction(onChange)
  const [kind, setKind] = useState('confirmed')
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const body = {
      expected_task_revision: task.revision,
      response_kind: kind,
      text: String(form.get('text')),
      ...(String(form.get('basis') || '').trim()
        ? { basis: String(form.get('basis')) }
        : {}),
      client_request_id: requestId(),
    }
    action.run(async () => {
      await api.send('/review-tasks/' + task.id + '/answers', body)
      onChange()
    })
  }
  return (
    <form onSubmit={submit} className='mt-4 grid gap-3'>
      <Field label='Answer kind'>
        <select
          className={selectStyle}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value='confirmed'>Confirmed</option>
          <option value='denied'>Denied</option>
          <option value='unable_to_confirm'>Unable to confirm</option>
        </select>
      </Field>
      <Field label='Your answer'>
        <Textarea name='text' required maxLength={10000} />
      </Field>
      {(actor.roles.some((role) => role === 'member' || role === 'admin') ||
        task.manifest.workflow === 'screening.v1') && (
        <Field label='Basis for your answer'>
          <Textarea
            name='basis'
            required={
              task.manifest.workflow === 'screening.v1'
                ? kind !== 'unable_to_confirm'
                : false
            }
            maxLength={2000}
          />
        </Field>
      )}
      <ActionError action={action} />
      <Button
        className='justify-self-start'
        disabled={locked || action.busy || action.uncertain}
      >
        Save answer and reassess
      </Button>
    </form>
  )
}
export function Questions({
  api,
  tenderId,
  actor,
  assessment,
  tasks,
  members,
  locked,
  answerPaused,
  onInspect,
  onChange,
  compact = false,
}: {
  api: Api
  tenderId: string
  actor: Actor
  assessment: Assessment
  tasks: Task[]
  members: Member[]
  locked: boolean
  compact?: boolean
  answerPaused: boolean
  onInspect: (id: string) => void
  onChange: () => void
}) {
  const name = (id: string) =>
    memberName(
      members.find((member) => member.user_id === id)?.display_name || id
    )
  const drafts = assessment.candidate.review_requests.filter(
    (draft) =>
      !tasks.some(
        (task) =>
          task.status !== 'cancelled' &&
          ((task.assessment_version_id === assessment.id &&
            task.draft_ref === draft.draft_ref) ||
            (task.is_current &&
              task.status === 'open' &&
              draft.requirement_refs.every((ref) => {
                const record = assessment.requirements.find(
                  (item) => item.requirement.local_ref === ref
                )
                return !!record && task.requirement_ids.includes(record.id)
              })))
      )
  )
  return (
    <section className={compact ? 'space-y-4' : 'space-y-7'}>
      <h2
        className={
          compact
            ? 'text-sm font-medium'
            : 'text-xl font-semibold tracking-tight'
        }
      >
        Review questions
      </h2>
      {!!tasks.length && (
        <div className={compact ? 'space-y-6' : 'divide-y border-y'}>
          {tasks.map((task) => (
            <article
              key={task.id}
              aria-label={task.question}
              className={compact ? 'space-y-3' : 'py-6'}
            >
              <div className='flex flex-wrap items-start justify-between gap-4'>
                <p className='max-w-xl font-medium'>{task.question}</p>
                <p
                  className={
                    compact
                      ? 'text-xs text-muted-foreground'
                      : 'text-base text-muted-foreground'
                  }
                >
                  {name(task.assignee_id)} · Due {singapore(task.due_at)} ·{' '}
                  {task.status}
                </p>
              </div>
              {!task.is_current && (
                <div className='mt-2 text-xs text-amber-700 dark:text-amber-300'>
                  <p>Original source snapshot</p>
                  <Button
                    variant='link'
                    className='h-auto px-0'
                    onClick={() => onInspect(task.assessment_version_id)}
                  >
                    View original assessment
                  </Button>
                </div>
              )}
              {task.answer ? (
                <div className='mt-4 space-y-2 text-base'>
                  <p className='whitespace-pre-wrap'>{task.answer.text}</p>
                  <p className='text-muted-foreground'>
                    {name(task.answer.actor_id)} ·{' '}
                    {task.answer.response_kind.replace(/_/g, ' ')}
                  </p>
                  {task.answer.basis && <p>Basis: {task.answer.basis}</p>}
                  <p role='status'>
                    Reassessment:{' '}
                    {task.answer.reassessment_status.replace(/_/g, ' ')}
                  </p>
                </div>
              ) : (
                task.status === 'open' &&
                task.assignee_id === actor.user_id &&
                actor.roles.some(
                  (role) => role === 'member' || role === 'admin'
                ) && (
                  <AnswerForm
                    api={api}
                    task={task}
                    actor={actor}
                    locked={answerPaused}
                    onChange={onChange}
                  />
                )
              )}
            </article>
          ))}
        </div>
      )}
      {actor.roles.some((role) => role === 'member' || role === 'admin') && (
        <QuestionAssignments
          api={api}
          tenderId={tenderId}
          assessment={assessment}
          drafts={drafts}
          compact={compact}
          members={members}
          locked={locked}
          onChange={onChange}
        />
      )}
      {!tasks.length && !drafts.length && (
        <p className='text-base text-muted-foreground'>
          No open qualification questions.
        </p>
      )}
    </section>
  )
}
