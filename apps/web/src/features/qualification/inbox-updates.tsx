import { ArrowLeft, ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import {
  type Actor,
  type Api,
  type History,
  type Member,
  type Task,
  type Tender,
  singapore,
} from './api'
import { DecisionBadge } from './decision-badge'
import { AnswerForm } from './questions'

export type InboxUpdate = {
  id: string
  label: 'Question assigned' | 'Answer received' | 'Assessment ready'
  created_at: string
  tender: Tender
  task?: Task
}

export function inboxUpdates(
  tender: Tender,
  actor: Actor,
  history?: History
): InboxUpdate[] {
  const open = tender.review_tasks.some((task) => task.status === 'open')
  if (
    tender.decision?.is_current &&
    (tender.decision.decision !== 'hold' || !open)
  )
    return []
  const updates: InboxUpdate[] = []
  for (const task of tender.review_tasks) {
    if (task.status === 'open' && task.assignee_id === actor.user_id) {
      updates.push({
        id: 'assigned:' + task.id,
        label: 'Question assigned',
        created_at: task.created_at,
        tender,
        task,
      })
    }
    if (
      task.status === 'answered' &&
      task.answer &&
      task.answer.actor_id !== actor.user_id &&
      (tender.owner_user_id === actor.user_id ||
        task.created_by === actor.user_id) &&
      !(
        tender.decision?.is_current &&
        Date.parse(tender.decision.created_at) >=
          Date.parse(task.answer.created_at)
      )
    ) {
      updates.push({
        id: 'answer:' + task.answer.id,
        label: 'Answer received',
        created_at: task.answer.created_at,
        tender,
        task,
      })
    }
  }
  const assessment = tender.assessment
  const version = history?.assessments.find(
    (item) => item.id === assessment?.id && item.is_current
  )
  if (
    assessment?.is_current &&
    version &&
    !tender.decision?.is_current &&
    (tender.owner_user_id === actor.user_id || actor.roles.includes('approver'))
  ) {
    updates.push({
      id: 'assessment:' + assessment.id,
      label: 'Assessment ready',
      created_at: version.created_at,
      tender,
    })
  }
  return updates
}

export function InboxPreview({
  update,
  actor,
  api,
  members,
  paused,
  onChange,
  onBack,
}: {
  update: InboxUpdate
  actor: Actor
  api: Api
  members: Member[]
  paused: boolean
  onChange: () => void
  onBack?: () => void
}) {
  const { tender, task } = update
  const name = (id: string) =>
    members.find((member) => member.user_id === id)?.display_name || id
  const canAnswer =
    task?.status === 'open' &&
    task.assignee_id === actor.user_id &&
    actor.roles.some(
      (role) => role === 'bid_owner' || role === 'service_reviewer'
    )
  return (
    <section
      aria-label='Inbox update'
      className='flex h-full min-h-0 min-w-0 flex-col'
    >
      <header className='flex h-12 shrink-0 items-center justify-between gap-3 border-b px-6'>
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
          <span className='truncate text-sm font-medium'>{update.label}</span>
        </div>
        <Button asChild>
          <Link href={'/tenders/' + encodeURIComponent(tender.id)}>
            Open review
            <ArrowUpRight className='size-4' />
          </Link>
        </Button>
      </header>
      <div className='min-h-0 flex-1 overflow-y-auto p-8'>
        <div className='mx-auto max-w-3xl space-y-7'>
          <div className='space-y-2'>
            <h1 className='text-xl font-semibold tracking-tight'>
              {tender.title}
            </h1>
            <p className='text-xs text-muted-foreground'>
              {singapore(update.created_at)}
            </p>
          </div>
          {task ? (
            <article
              aria-label={task.question}
              className='space-y-4 border-t pt-6'
            >
              <h2 className='text-lg font-medium'>{task.question}</h2>
              <p className='text-base text-muted-foreground'>
                {name(task.assignee_id)} · Due {singapore(task.due_at)}
              </p>
              {!task.is_current && (
                <p className='text-xs text-amber-700 dark:text-amber-300'>
                  Original source snapshot
                </p>
              )}
              {task.answer ? (
                <div className='space-y-3 text-base'>
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
                canAnswer && (
                  <AnswerForm
                    api={api}
                    actor={actor}
                    task={task}
                    locked={paused}
                    onChange={onChange}
                  />
                )
              )}
            </article>
          ) : (
            tender.assessment && (
              <div className='space-y-5 border-t pt-6'>
                <DecisionBadge
                  decision={tender.assessment.candidate.recommendation.decision}
                />
                <p className='text-base leading-relaxed'>
                  {tender.assessment.candidate.summary}
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </section>
  )
}
