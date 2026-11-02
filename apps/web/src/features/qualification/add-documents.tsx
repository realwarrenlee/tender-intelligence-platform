import { useRef, useState } from 'react'
import { File as FileIcon, LoaderCircle, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ActionError, Field, selectStyle, useAction } from './actions'
import { type Api, type Tender, requestId } from './api'
import { TaskDialog } from './task-dialog'
import { tenderFileError, tenderFileTypes } from './tender-files'

export function AddDocuments({
  api,
  tender,
  locked,
  onChange,
  onClose,
  onReturnFocus,
}: {
  api: Api
  tender: Tender
  locked: boolean
  onChange: () => void
  onClose: () => void
  onReturnFocus: () => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [role, setRole] = useState('tender')
  const [amends, setAmends] = useState('')
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const action = useAction(onChange)
  const pending = action.busy || action.uncertain
  const disabled = locked || pending

  function add(incoming: File[]) {
    if (disabled || !incoming.length) return
    const next = [...files, ...incoming]
    const message = tenderFileError(next, tender.documents)
    if (message) {
      setError(message)
      return
    }
    setFiles(next)
    setError('')
  }

  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (disabled || !files.length || (role === 'addendum' && !amends)) return
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    body.append(
      'metadata',
      JSON.stringify({
        expected_input_revision: tender.input_revision,
        client_request_id: requestId(),
        files: files.map(() => ({
          role,
          ...(role === 'addendum' ? { amends_version_id: amends } : {}),
        })),
      })
    )
    action.run(async () => {
      await api.upload('/tenders/' + tender.id + '/documents', body)
      onChange()
      onClose()
    })
  }

  return (
    <TaskDialog
      title='Add documents'
      action={action}
      onClose={onClose}
      onReturnFocus={onReturnFocus}
    >
      <form onSubmit={submit} className='min-w-0 space-y-4'>
        <div
          className={
            'flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed px-5 py-6 ' +
            (dragging
              ? 'border-foreground bg-accent'
              : 'border-muted-foreground/50')
          }
          onDragOver={(event) => {
            event.preventDefault()
            if (!disabled) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            add(Array.from(event.dataTransfer.files))
          }}
        >
          <FileIcon
            aria-hidden='true'
            className='size-9 text-muted-foreground'
            strokeWidth={1.5}
          />
          <div className='space-y-2 text-center text-base'>
            <p>Drag files here to add them</p>
            <Button
              type='button'
              variant='link'
              className='h-auto p-0 text-muted-foreground underline underline-offset-4'
              disabled={disabled}
              onClick={() => input.current?.click()}
            >
              Or choose your files
            </Button>
            <Button
              type='button'
              variant='link'
              className='ml-3 h-auto p-0 text-muted-foreground underline underline-offset-4'
              disabled={disabled}
              onClick={() => folderInput.current?.click()}
            >
              Choose a folder
            </Button>
          </div>
          <Input
            ref={input}
            aria-label='Tender files'
            type='file'
            multiple
            accept={tenderFileTypes}
            className='sr-only h-px w-px'
            tabIndex={-1}
            disabled={disabled}
            onChange={(event) => {
              add(Array.from(event.currentTarget.files || []))
              event.currentTarget.value = ''
            }}
          />
          <Input
            ref={folderInput}
            aria-label='Tender folder'
            type='file'
            multiple
            {...{ webkitdirectory: '' }}
            className='sr-only h-px w-px'
            tabIndex={-1}
            disabled={disabled}
            onChange={(event) => {
              add(Array.from(event.currentTarget.files || []))
              event.currentTarget.value = ''
            }}
          />
        </div>
        {!!files.length && (
          <ul
            aria-label='Selected files'
            className='max-h-80 divide-y overflow-y-auto rounded-md border'
          >
            {files.map((file, index) => (
              <li
                key={index}
                className='flex items-center gap-3 px-4 py-2 text-base'
              >
                <FileIcon
                  aria-hidden='true'
                  className='size-4 shrink-0 text-muted-foreground'
                />
                <span className='min-w-0 break-words'>
                  {file.webkitRelativePath || file.name}
                </span>
                <Button
                  type='button'
                  variant='ghost'
                  size='icon'
                  className='ml-auto size-8'
                  aria-label={'Remove ' + file.name}
                  disabled={disabled}
                  onClick={() => setFiles(files.filter((_, i) => i !== index))}
                >
                  <X className='size-4' />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <details className='text-base'>
          <summary className='w-fit cursor-pointer text-sm text-muted-foreground'>
            Document options
          </summary>
          <div className='mt-3 grid min-w-0 gap-3'>
            <Field label='Document type'>
              <select
                className={selectStyle}
                value={role}
                disabled={disabled}
                onChange={(event) => setRole(event.target.value)}
              >
                <option value='tender'>Tender documents</option>
                <option value='addendum'>Addendum</option>
                <option value='reference_note'>Reference note</option>
              </select>
            </Field>
            {role === 'addendum' && (
              <Field label='Updates document'>
                <select
                  className={selectStyle}
                  value={amends}
                  disabled={disabled}
                  onChange={(event) => setAmends(event.target.value)}
                  required
                >
                  <option value=''>Choose the original document</option>
                  {tender.documents
                    .filter((document) =>
                      ['tender', 'addendum'].includes(document.role)
                    )
                    .map((document) => (
                      <option key={document.id} value={document.id}>
                        {document.filename}
                      </option>
                    ))}
                </select>
              </Field>
            )}
          </div>
        </details>
        {error && (
          <p role='alert' className='text-base text-red-500'>
            {error}
          </p>
        )}
        <ActionError action={action} />
        <div className='flex justify-end gap-3'>
          <Button
            type='button'
            variant='ghost'
            disabled={pending}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            disabled={
              disabled || !files.length || (role === 'addendum' && !amends)
            }
          >
            {action.busy && <LoaderCircle className='size-4 animate-spin' />}
            Add documents
          </Button>
        </div>
      </form>
    </TaskDialog>
  )
}
