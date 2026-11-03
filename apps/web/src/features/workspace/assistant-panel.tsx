import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Field, ActionError, useAction } from './actions'
import {
  type Api,
  type Actor,
  type Assessment,
  type Citation,
  type Member,
  type AssistantAnswer,
  requestId,
} from './api'
import { DraftConfirmation } from './questions'
import { Citations } from './source-pane'

export function AssistantPanel({
  api,
  actor,
  tenderId,
  assessment,
  members,
  locked,
  onChange,
  onOpen,
}: {
  api: Api
  actor: Actor
  tenderId: string
  assessment: Assessment
  members: Member[]
  locked: boolean
  onChange: () => void
  onOpen: (cite: Citation) => void
}) {
  const [answer, setAnswer] = useState<AssistantAnswer>()
  const action = useAction(onChange)
  function ask(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const body = {
      assessment_version_id: assessment.id,
      text: String(form.get('question')),
      client_request_id: requestId(),
    }
    action.run(async () => {
      setAnswer(
        await api.send<AssistantAnswer>(
          '/tenders/' + tenderId + '/assistant-messages',
          body
        )
      )
    })
  }
  return (
    <section className='space-y-4'>
      <h2 className='text-lg font-semibold'>Ask about assessment</h2>
      <p className='mt-2 text-xs text-muted-foreground'>
        The assistant explains evidence and prepares review drafts. Every new
        turn uses AI; business decisions remain human.
      </p>
      <form className='mt-4 grid gap-3' onSubmit={ask}>
        <Field label='Assessment question'>
          <Textarea name='question' required maxLength={4000} />
        </Field>
        <ActionError action={action} />
        <Button
          className='justify-self-start'
          disabled={action.busy || action.uncertain}
        >
          {action.busy ? 'Checking the evidence…' : 'Ask assistant'}
        </Button>
      </form>
      {answer && (
        <div className='mt-4 space-y-3'>
          <p className='text-base whitespace-pre-wrap'>{answer.answer}</p>
          <Citations
            items={answer.citations}
            label='Answer source'
            onOpen={onOpen}
          />
          {actor.roles.some((role) => role === 'member' || role === 'admin') &&
            answer.review_request_drafts.map((d) => (
              <DraftConfirmation
                key={d.draft_ref}
                api={api}
                tenderId={tenderId}
                assessment={assessment}
                draft={d}
                members={members}
                locked={locked || !answer.is_current}
                onChange={onChange}
              />
            ))}
        </div>
      )}
    </section>
  )
}
