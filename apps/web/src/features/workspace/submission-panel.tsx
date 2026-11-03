/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ActionError, Field, selectStyle, useAction } from './actions'
import { requestId, singapore, type Actor, type Api, type Member } from './api'
import type { components } from './api.generated'
import { TaskDialog } from './task-dialog'

type View = components['schemas']['SubmissionView']
type Package = components['schemas']['SubmissionPackage']
type ReleaseFile = components['schemas']['ReleaseFile']
type Dialog =
  | { kind: 'seal'; snapshot: string; previous: Package | undefined }
  | { kind: 'approve' | 'reject' | 'receipt'; package: Package }

const states = {
  awaiting_release: 'Awaiting release decision',
  approved: 'Approved for release · awaiting portal receipt',
  rejected: 'Release declined',
  submitted: 'Submitted',
  closed: 'Tender closed',
  non_current: 'Non-current package',
}
const labels = {
  seal: 'Seal package and assign approver',
  approve: 'Approve release',
  reject: 'Decline release',
  receipt: 'Record portal submission',
}

export function SubmissionPanel({
  api,
  actor,
  tenderId,
  members,
  onChange,
}: {
  api: Api
  actor: Actor
  tenderId: string
  members: Member[]
  onChange: () => void
}) {
  const tenderPath = '/tenders/' + encodeURIComponent(tenderId)
  const path = tenderPath + '/submission'
  const query = useQuery({
    queryKey: ['submission', tenderId, actor.user_id],
    queryFn: () => api.get<View>(path),
    refetchInterval: 15000,
  })
  const [dialog, setDialog] = useState<Dialog>()
  const [downloadError, setDownloadError] = useState('')
  const trigger = useRef<HTMLButtonElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const action = useAction(() => void query.refetch())
  const data = query.data
  const current = data?.packages[0]
  const memberName = (id: string) =>
    members.find((member) => member.user_id === id)?.display_name ||
    'Workspace member'
  const eligibleApprovers = members.filter(
    (member) =>
      member.user_id !== actor.user_id &&
      member.roles.some((role) => role === 'member' || role === 'admin') &&
      !(
        current &&
        (current.state === 'awaiting_release' ||
          current.state === 'approved') &&
        member.user_id === current.approver_id
      )
  )

  function open(next: Dialog, button: HTMLButtonElement) {
    trigger.current = button
    setDialog(next)
  }

  function restoreFocus() {
    requestAnimationFrame(() => {
      if (trigger.current?.isConnected) trigger.current.focus()
      else heading.current?.focus()
    })
  }

  async function download(url: string, filename: string) {
    setDownloadError('')
    try {
      const href = URL.createObjectURL(await api.blob(url))
      const link = document.createElement('a')
      link.href = href
      link.download = filename
      link.click()
      setTimeout(() => URL.revokeObjectURL(href), 1000)
    } catch (error) {
      setDownloadError(
        error instanceof Error
          ? error.message
          : 'The file could not be downloaded.'
      )
    }
  }

  function fileList(files: ReleaseFile[]) {
    return (
      <ul className='space-y-2'>
        {files.map((file) => (
          <li key={file.file_id} className='text-sm'>
            <Button
              variant='link'
              size='sm'
              className='h-auto px-0 text-left whitespace-normal'
              onClick={() =>
                void download(
                  tenderPath +
                    '/preparation/' +
                    file.item_id +
                    '/files/' +
                    file.file_id,
                  file.filename
                )
              }
            >
              v{file.version} · {file.filename}
            </Button>
            <p className='text-muted-foreground'>
              Accepted by {memberName(file.reviewer_id)} · Plan revision{' '}
              {file.plan_revision}
              {file.requirements_checked && ' · Linked requirements checked'}
            </p>
            <p className='font-mono text-xs break-all text-muted-foreground'>
              SHA-256 {file.sha256}
            </p>
          </li>
        ))}
      </ul>
    )
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!dialog) return
    const form = new FormData(event.currentTarget)
    const request = { client_request_id: requestId() }
    action.run(async () => {
      if (dialog.kind === 'seal') {
        await api.send(path + '/packages', {
          ...request,
          expected_snapshot: dialog.snapshot,
          previous_package_id: dialog.previous?.id ?? null,
          approver_id: form.get('approver'),
        })
      } else if (dialog.kind === 'receipt') {
        const submitted = String(form.get('submitted'))
        const upload = new FormData()
        upload.set('file', form.get('file')!)
        upload.set(
          'metadata',
          JSON.stringify({
            ...request,
            portal_reference: form.get('reference'),
            submitted_at:
              submitted + (submitted.length === 16 ? ':00' : '') + '+08:00',
          })
        )
        await api.upload(
          path + '/packages/' + dialog.package.id + '/receipt',
          upload
        )
      } else {
        await api.send(path + '/packages/' + dialog.package.id + '/decision', {
          ...request,
          outcome: dialog.kind === 'approve' ? 'approved' : 'rejected',
          note: form.get('note'),
          checks_confirmed: form.has('confirmed'),
        })
      }
      setDialog(undefined)
      void query.refetch()
      onChange()
    })
  }

  return (
    <>
      <section
        className='space-y-3 border-b px-6 py-5'
        aria-label='Release checks'
      >
        <h2 ref={heading} tabIndex={-1} className='text-lg font-medium'>
          Release checks
        </h2>
        {query.isPending && <p role='status'>Loading submission packages…</p>}
        {query.error && (
          <p role='alert'>
            {query.error.message}{' '}
            <Button variant='link' onClick={() => void query.refetch()}>
              Retry
            </Button>
          </p>
        )}
        {downloadError && <p role='alert'>{downloadError}</p>}
        {data && (
          <>
            <ul className='divide-y border-y text-sm'>
              {data.checks.map((check, index) => (
                <li
                  key={index}
                  className='flex items-baseline justify-between gap-3 py-2'
                >
                  <span>{check.label}</span>
                  <span
                    className={
                      check.passed
                        ? 'text-muted-foreground'
                        : 'text-amber-700 dark:text-amber-300'
                    }
                  >
                    {check.passed ? 'Passed' : 'Blocked'}
                  </span>
                </li>
              ))}
            </ul>
            {data.can_seal &&
              data.snapshot &&
              !query.isError &&
              eligibleApprovers.length > 0 && (
                <>
                  <h3 className='text-sm font-medium'>Files ready to seal</h3>
                  {fileList(data.candidate_files)}
                  <Button
                    size='sm'
                    onClick={(event) =>
                      open(
                        {
                          kind: 'seal',
                          snapshot: data.snapshot!,
                          previous: current,
                        },
                        event.currentTarget
                      )
                    }
                  >
                    {labels.seal}
                  </Button>
                </>
              )}
          </>
        )}
      </section>
      {data?.packages.length === 0 && (
        <p className='px-6 py-5 text-sm text-muted-foreground'>
          No submission package sealed.
        </p>
      )}
      {data?.packages.map((item) => (
        <section
          key={item.id}
          aria-label={'Package ' + item.version}
          className='space-y-3 border-b px-6 py-5'
        >
          <div className='flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1'>
            <h3 className='font-medium'>Package {item.version}</h3>
            <p className='text-sm font-medium'>{states[item.state]}</p>
          </div>
          <p className='text-sm text-muted-foreground'>
            Release approver: {memberName(item.approver_id)} · Sealed{' '}
            {singapore(item.sealed_at)}
          </p>
          {fileList(item.files)}
          {item.decision && (
            <div className='space-y-1 text-sm'>
              <p className='font-medium'>
                {item.decision.outcome === 'approved'
                  ? 'Release approved'
                  : 'Release declined'}
              </p>
              <p>
                {memberName(item.decision.actor_id)} ·{' '}
                {singapore(item.decision.decided_at)}
              </p>
              <p>{item.decision.note}</p>
            </div>
          )}
          {item.receipt && (
            <div className='space-y-1 text-sm'>
              <p className='font-medium'>Portal submission recorded</p>
              <p>
                {item.receipt.portal_reference} ·{' '}
                {singapore(item.receipt.submitted_at)}
              </p>
              <Button
                variant='link'
                size='sm'
                className='h-auto px-0'
                onClick={() =>
                  void download(
                    path + '/packages/' + item.id + '/receipt',
                    item.receipt!.filename
                  )
                }
              >
                Download portal receipt
              </Button>
            </div>
          )}
          {!query.isError && (item.can_decide || item.can_record_receipt) && (
            <div className='flex flex-wrap gap-2'>
              {(item.can_decide
                ? (['approve', 'reject'] as const)
                : (['receipt'] as const)
              ).map((kind) => (
                <Button
                  key={kind}
                  size='sm'
                  variant={kind === 'reject' ? 'outline' : 'default'}
                  onClick={(event) =>
                    open({ kind, package: item }, event.currentTarget)
                  }
                >
                  {labels[kind]}
                </Button>
              ))}
            </div>
          )}
        </section>
      ))}
      {dialog && (
        <TaskDialog
          title={labels[dialog.kind]}
          action={action}
          description={
            dialog.kind === 'seal'
              ? 'Sealing fixes the file versions and names the release approver.'
              : 'Package ' + dialog.package.version
          }
          onClose={() => setDialog(undefined)}
          onReturnFocus={restoreFocus}
        >
          <form onSubmit={submit} className='space-y-4'>
            <fieldset
              disabled={action.busy || action.uncertain}
              className='space-y-3'
            >
              {dialog.kind === 'seal' ? (
                <Field label='Release approver'>
                  <select
                    name='approver'
                    className={selectStyle}
                    required
                    defaultValue=''
                  >
                    <option value=''>Select member</option>
                    {eligibleApprovers.map((member) => (
                      <option key={member.user_id} value={member.user_id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </Field>
              ) : dialog.kind === 'receipt' ? (
                <>
                  <Field label='Portal reference'>
                    <Input name='reference' required maxLength={200} />
                  </Field>
                  <Field label='Portal submission time (SGT)'>
                    <Input
                      name='submitted'
                      type='datetime-local'
                      step={1}
                      required
                    />
                  </Field>
                  <Field label='Portal receipt PDF'>
                    <Input
                      name='file'
                      type='file'
                      accept='.pdf,application/pdf'
                      required
                    />
                  </Field>
                </>
              ) : (
                <>
                  <Field label='Decision reason'>
                    <Textarea name='note' required maxLength={2000} />
                  </Field>
                  {dialog.kind === 'approve' && (
                    <label className='flex items-start gap-2 text-sm'>
                      <input name='confirmed' type='checkbox' required />I
                      checked the technical and commercial offer and submission
                      requirements for this package.
                    </label>
                  )}
                </>
              )}
            </fieldset>
            <ActionError action={action} />
            <Button type='submit' disabled={action.busy || action.uncertain}>
              {labels[dialog.kind]}
            </Button>
          </form>
        </TaskDialog>
      )}
    </>
  )
}
