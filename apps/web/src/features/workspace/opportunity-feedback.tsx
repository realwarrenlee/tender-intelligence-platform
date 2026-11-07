/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useState } from 'react'
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ActionError, Field, selectStyle, useAction } from './actions'
import {
  type Actor,
  type Api,
  type Member,
  type Opportunity,
  type OpportunityFeedback,
  type OpportunityFeedbackList,
  requestId,
  singapore,
} from './api'

type InboxProps = { actor: Actor; api: Api }
const feedbackKey = 'opportunity-feedback'

function useMembers(api: Api) {
  return useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
  })
}

export function AskForFeedback({
  actor,
  api,
  item,
}: InboxProps & { item: Opportunity }) {
  const [open, setOpen] = useState(false)
  const [sent, setSent] = useState(false)
  const [recipient, setRecipient] = useState('')
  const [question, setQuestion] = useState('')
  const cache = useQueryClient()
  const action = useAction(
    () =>
      void cache.invalidateQueries({ queryKey: ['opportunity-suggestions'] })
  )
  const members = useMembers(api)
  return (
    <div className='mt-4'>
      <Button
        size='sm'
        variant='outline'
        onClick={() => setOpen(!open)}
        disabled={action.busy || action.uncertain}
      >
        {open ? 'Cancel request' : 'Ask for input'}
      </Button>
      {sent && (
        <p role='status' className='mt-2 text-sm'>
          Request sent to your teammate’s Human Inbox.
        </p>
      )}
      {open && (
        <form
          className='mt-3 grid max-w-lg gap-3'
          onSubmit={(event) => {
            event.preventDefault()
            const body = {
              recipient_id: recipient,
              question: question.trim(),
              expected_revision: item.revision,
              client_request_id: requestId(),
            }
            action.run(async () => {
              await api.send(
                '/opportunity-suggestions/' + item.id + '/feedback',
                body
              )
              setOpen(false)
              setSent(true)
              setRecipient('')
              setQuestion('')
              void cache.invalidateQueries({ queryKey: [feedbackKey] })
            })
          }}
        >
          <Field label='Teammate'>
            <select
              className={selectStyle}
              value={recipient}
              onChange={(event) => setRecipient(event.target.value)}
              required
            >
              <option value=''>Choose a teammate</option>
              {members.data?.items
                .filter((member) => member.user_id !== actor.user_id)
                .map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {member.display_name}
                  </option>
                ))}
            </select>
          </Field>
          {members.isError && (
            <p role='alert' className='text-sm'>
              {members.error.message}
            </p>
          )}
          <Field label='Question'>
            <Textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              required
              maxLength={1000}
            />
          </Field>
          <ActionError action={action} />
          <Button
            type='submit'
            size='sm'
            className='justify-self-start'
            disabled={
              !recipient || !question.trim() || action.busy || action.uncertain
            }
          >
            Send request
          </Button>
        </form>
      )}
    </div>
  )
}

function FeedbackReply({ item, api }: { item: OpportunityFeedback; api: Api }) {
  const [answer, setAnswer] = useState('')
  const cache = useQueryClient()
  const refresh = () =>
    void cache.invalidateQueries({ queryKey: [feedbackKey] })
  const action = useAction(refresh)
  return (
    <form
      className='mt-3 grid max-w-lg gap-3'
      onSubmit={(event) => {
        event.preventDefault()
        const body = { answer: answer.trim(), client_request_id: requestId() }
        action.run(async () => {
          await api.send('/opportunity-feedback/' + item.id + '/answer', body)
          setAnswer('')
          refresh()
        })
      }}
    >
      <Field label='Your reply'>
        <Textarea
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          required
          maxLength={2000}
        />
      </Field>
      <ActionError action={action} />
      <Button
        size='sm'
        type='submit'
        className='justify-self-start'
        disabled={!answer.trim() || action.busy || action.uncertain}
      >
        Send reply
      </Button>
    </form>
  )
}

export function useOpportunityFeedback({ actor, api }: InboxProps) {
  return useInfiniteQuery({
    queryKey: [feedbackKey, actor.user_id],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<OpportunityFeedbackList>(
        '/opportunity-feedback' +
          (pageParam ? '?after=' + encodeURIComponent(pageParam) : '')
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    refetchInterval: 15000,
  })
}

export function OpportunityFeedbackDetail({
  actor,
  api,
  item,
  onBack,
}: InboxProps & { item: OpportunityFeedback; onBack?: () => void }) {
  const members = useMembers(api)
  const name = (id: string) =>
    members.data?.items.find((member) => member.user_id === id)?.display_name ||
    'Workspace member'
  return (
    <article className='h-full space-y-3 overflow-y-auto px-6 py-5 text-sm'>
      {onBack && (
        <Button variant='ghost' onClick={onBack}>
          <ArrowLeft className='size-4' />
          Back to list
        </Button>
      )}
      <h2 className='text-lg font-semibold'>{item.notice.title}</h2>
      <p className='text-muted-foreground'>
        {item.notice.reference} · Closes {singapore(item.notice.closing_at)}
      </p>
      <p>
        {item.sender_id === actor.user_id
          ? 'To ' + name(item.recipient_id)
          : 'From ' + name(item.sender_id)}
      </p>
      <p className='whitespace-pre-wrap'>{item.question}</p>
      <details>
        <summary className='cursor-pointer'>Source notice</summary>
        <p className='mt-2 whitespace-pre-wrap'>{item.notice.evidence_text}</p>
      </details>
      {item.answer ? (
        <p className='whitespace-pre-wrap'>Reply: {item.answer}</p>
      ) : item.recipient_id === actor.user_id ? (
        <FeedbackReply api={api} item={item} />
      ) : (
        <p className='text-muted-foreground'>Awaiting reply</p>
      )}
    </article>
  )
}
