import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Field, ActionError, selectStyle, useAction } from './actions'
import { type Api, type Task, requestId } from './api'

export function AnswerForm({
  api,
  task,
  locked,
  onChange,
}: {
  api: Api
  task: Task
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
      <Field label='Basis for your answer'>
        <Textarea
          name='basis'
          required={kind !== 'unable_to_confirm'}
          maxLength={2000}
        />
      </Field>
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
