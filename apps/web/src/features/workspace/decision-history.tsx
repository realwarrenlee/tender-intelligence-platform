import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Field, ActionError, useAction } from './actions'
import {
  type Api,
  type Actor,
  type Assessment,
  type Tender,
  type History,
  type Member,
  requestId,
  singapore,
} from './api'
import { DecisionBadge } from './decision-badge'

export function VersionHistory({
  history,
  members,
  onSelect,
}: {
  history: History | undefined
  members: Member[]
  onSelect: (id: string) => void
}) {
  const name = (id: string) =>
    members.find((member) => member.user_id === id)?.display_name || id
  return (
    <div className='space-y-7'>
      <section>
        <h3 className='mb-4 font-semibold'>Assessment history</h3>
        <ul className='divide-y'>
          {history?.assessments.map((item) => (
            <li key={item.id} className='space-y-2 py-3 first:pt-0'>
              <div className='flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm'>
                <Button
                  type='button'
                  variant='link'
                  className='h-auto p-0 text-sm'
                  aria-label={'View assessment revision ' + item.input_revision}
                  onClick={() => onSelect(item.id)}
                >
                  Revision {item.input_revision}
                </Button>
                <span className='text-xs text-muted-foreground'>
                  {item.is_current ? 'Current' : 'Historical'}
                </span>
              </div>
              <p className='text-xs break-words text-muted-foreground'>
                {name(item.created_by)} · {singapore(item.created_at)}
              </p>
            </li>
          ))}
        </ul>
        {history && !history.assessments.length && (
          <p className='text-base text-muted-foreground'>No assessments yet.</p>
        )}
      </section>
      <section className='border-t pt-6'>
        <h3 className='mb-4 font-semibold'>Decision history</h3>
        <ul className='divide-y'>
          {history?.decisions.map((decision) => (
            <li key={decision.id} className='space-y-2 py-3 first:pt-0'>
              <p className='text-sm font-medium capitalize'>
                {decision.decision} ·{' '}
                {decision.is_current ? 'Current' : 'Non-current'}
              </p>
              <p className='text-base break-words'>{decision.reason}</p>
              <p className='text-xs break-words text-muted-foreground'>
                {name(decision.actor_id)} · {singapore(decision.created_at)}
              </p>
            </li>
          ))}
        </ul>
        {history && !history.decisions.length && (
          <p className='text-base text-muted-foreground'>
            No decision recorded.
          </p>
        )}
      </section>
    </div>
  )
}

export function DecisionHistory({
  api,
  actor,
  tender,
  assessment,
  members,
  locked,
  onChange,
}: {
  api: Api
  actor: Actor
  tender: Tender
  assessment: Assessment
  members: Member[]
  locked: boolean
  onChange: () => void
}) {
  const action = useAction(onChange)
  const download = useAction()
  const name = (id: string) =>
    members.find((member) => member.user_id === id)?.display_name || id
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const submitter = (event.nativeEvent as SubmitEvent)
      .submitter as HTMLButtonElement | null
    const choice = submitter?.value || 'pursue'
    if (locked || (choice === 'pursue' && assessment.blockers.length)) return
    const form = new FormData(event.currentTarget)
    const body = {
      expected_input_revision: tender.input_revision,
      assessment_version_id: assessment.id,
      decision: choice,
      reason: String(form.get('reason')),
      review_complete: true,
      client_request_id: requestId(),
    }
    action.run(async () => {
      await api.send('/tenders/' + tender.id + '/decisions', body)
      onChange()
    })
  }
  function exportBrief() {
    download.run(async () => {
      const blob = await api.blob(
        '/tenders/' +
          tender.id +
          '/qualification-brief?assessment_version_id=' +
          assessment.id
      )
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = 'qualification-' + assessment.id + '.md'
      link.click()
      setTimeout(() => URL.revokeObjectURL(href), 1000)
    })
  }
  return (
    <section className='space-y-7'>
      <div className='space-y-4'>
        <h2 className='text-xl font-semibold tracking-tight'>Decision</h2>
        <DecisionBadge
          decision={assessment.candidate.recommendation.decision}
        />
      </div>
      {tender.decision && (
        <div role='status' className='space-y-2 border-y py-5 text-base'>
          <p className='font-medium capitalize'>
            {tender.decision.decision} ·{' '}
            {tender.decision.is_current
              ? 'Current human decision'
              : 'Non-current decision'}
          </p>
          <p>{tender.decision.reason}</p>
          <p className='text-muted-foreground'>
            {name(tender.decision.actor_id)} ·{' '}
            {singapore(tender.decision.created_at)}
          </p>
        </div>
      )}
      {actor.roles.some((role) => role === 'member' || role === 'admin') ? (
        <form className='space-y-5' onSubmit={submit}>
          <Field label='Decision reason'>
            <Textarea name='reason' required maxLength={2000} rows={3} />
          </Field>
          <ActionError action={action} />
          <div className='flex flex-wrap gap-3'>
            <Button
              type='submit'
              size='sm'
              value='pursue'
              disabled={
                locked ||
                assessment.blockers.length > 0 ||
                action.busy ||
                action.uncertain
              }
            >
              Record pursue decision
            </Button>
            <Button
              type='submit'
              size='sm'
              variant='outline'
              value='hold'
              disabled={locked || action.busy || action.uncertain}
            >
              Hold
            </Button>
            <Button
              type='submit'
              size='sm'
              variant='outline'
              value='decline'
              disabled={locked || action.busy || action.uncertain}
            >
              Decline
            </Button>
          </div>
        </form>
      ) : (
        <p className='text-base text-muted-foreground'>
          A Member or Admin records the human decision.
        </p>
      )}
      <Button
        type='button'
        variant='link'
        className='h-auto px-0'
        onClick={exportBrief}
        disabled={download.busy}
      >
        Preview qualification brief
      </Button>
      <ActionError action={download} />
    </section>
  )
}
