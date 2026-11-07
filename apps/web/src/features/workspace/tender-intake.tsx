import { useRef, useState } from 'react'
import { File as FileIcon, LoaderCircle, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ActionError, useAction } from './actions'
import { type Api, requestId } from './api'
import { tenderFileError, tenderFileTypes } from './tender-files'

export function TenderIntake({
  api,
  onComplete,
  onCancel,
  onChange,
}: {
  api: Api
  onComplete: (id: string) => void
  onCancel: () => void
  onChange?: () => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [complete, setComplete] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const saved = useRef<{
    id: string
    input_revision: number
    uploaded: boolean
  } | null>(null)
  const action = useAction(onChange)
  const disabled = action.busy || action.uncertain || complete

  function add(incoming: File[]) {
    if (disabled || !incoming.length) return
    const next = [...files, ...incoming]
    const message = tenderFileError(next, [])
    if (message) {
      setError(message)
      return
    }
    setError('')
    setFiles(next)
  }

  function save(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (complete || !files.length) return
    const createId = requestId()
    const uploadId = requestId()
    let uploadBody: FormData | undefined
    action.run(async () => {
      if (!saved.current) {
        saved.current = {
          ...(await api.send<{ id: string; input_revision: number }>(
            '/tenders',
            {
              title:
                files[0].name.replace(/\.[^.]+$/, '').slice(0, 300) ||
                'New tender',
              source_label: 'manual_upload',
              client_request_id: createId,
            }
          )),
          uploaded: false,
        }
      }
      const record = saved.current
      if (!record.uploaded) {
        if (!uploadBody) {
          uploadBody = new FormData()
          files.forEach((file) => uploadBody!.append('files', file))
          uploadBody.append(
            'metadata',
            JSON.stringify({
              expected_input_revision: record.input_revision,
              client_request_id: uploadId,
              files: files.map(() => ({ role: 'tender' })),
            })
          )
        }
        await api.upload('/tenders/' + record.id + '/documents', uploadBody)
        record.uploaded = true
      }
      setComplete(true)
      onChange?.()
      onComplete(record.id)
    })
  }

  return (
    <form onSubmit={save} className='space-y-7'>
      <div
        className={
          'flex min-h-64 flex-col items-center justify-center gap-4 rounded-md border border-dashed px-6 py-10 transition-colors ' +
          (dragging
            ? 'border-foreground bg-accent'
            : 'border-muted-foreground/50 bg-muted/10')
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
          className='mb-1 size-12 text-muted-foreground'
          strokeWidth={1.5}
        />
        <div className='space-y-2 text-center'>
          <p className='text-lg font-medium'>Drag files here to add them</p>
          <Button
            type='button'
            variant='link'
            className='h-auto p-0 text-base text-muted-foreground underline underline-offset-4'
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
      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}
      {!!files.length && (
        <section
          aria-label='Selected files'
          className='overflow-hidden border-y'
        >
          <h2 className='border-b py-3 text-base font-medium'>
            {files.length} {files.length === 1 ? 'file' : 'files'} ready
          </h2>
          <ul className='max-h-80 divide-y overflow-y-auto'>
            {files.map((file, index) => (
              <li key={index} className='flex items-center gap-3 py-3 text-sm'>
                <FileIcon
                  aria-hidden='true'
                  className='size-5 shrink-0 text-muted-foreground'
                />
                <span className='min-w-0 break-words'>
                  {file.webkitRelativePath || file.name}
                </span>
                <Button
                  type='button'
                  size='icon'
                  variant='ghost'
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
        </section>
      )}
      <ActionError action={action} />
      <div className='flex gap-4'>
        <Button size='sm' disabled={disabled || !files.length}>
          {action.busy && <LoaderCircle className='size-4 animate-spin' />}
          {action.busy ? 'Saving sources…' : 'Save sources'}
        </Button>
        <Button
          type='button'
          size='sm'
          variant='ghost'
          disabled={action.busy || action.uncertain}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </form>
  )
}
