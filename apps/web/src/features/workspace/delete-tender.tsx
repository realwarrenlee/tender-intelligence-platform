import { Button } from '@/components/ui/button'
import { ActionError, useAction } from './actions'
import { type Api, type Inbox, requestId } from './api'
import { TaskDialog } from './task-dialog'

export function DeleteTender({
  tender,
  api,
  onClose,
  onDeleted,
  onRefresh,
  onReturnFocus,
}: {
  tender: Pick<Inbox['items'][number], 'id' | 'title' | 'input_revision'>
  api: Api
  onClose: () => void
  onDeleted: () => Promise<void>
  onRefresh: () => void
  onReturnFocus: () => void
}) {
  const action = useAction(onRefresh)
  return (
    <TaskDialog
      title='Delete tender?'
      description='This removes the tender from Tenders, Inbox and Oversight and cancels pending screening. Documents and history are retained for recovery.'
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <p className='font-medium break-words'>{tender.title}</p>
      <ActionError action={action} />
      <div className='flex justify-end gap-2'>
        <Button
          variant='outline'
          disabled={action.busy || action.uncertain}
          onClick={onClose}
          autoFocus
        >
          Cancel
        </Button>
        <Button
          variant='destructive'
          disabled={action.busy || action.uncertain}
          onClick={() => {
            const command = {
              expected_input_revision: tender.input_revision,
              client_request_id: requestId(),
            }
            action.run(async () => {
              await api.send(
                '/tenders/' + encodeURIComponent(tender.id),
                command,
                'DELETE'
              )
              await onDeleted()
            })
          }}
        >
          {action.busy ? 'Deleting…' : 'Delete tender'}
        </Button>
      </div>
    </TaskDialog>
  )
}
