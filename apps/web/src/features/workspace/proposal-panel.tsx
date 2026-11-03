/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the shared query cache. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { ActionError, Field, selectStyle, useAction } from './actions'
import { requestId, type Api, type Citation } from './api'
import type { components } from './api.generated'
import { Citations } from './source-pane'

type Proposal = components['schemas']['ProposalView']
type Requirement = components['schemas']['ProposalRequirement']
type Props = {
  api: Api
  path: string
  approvalId: string
  revision: number
  planRevision: number
  canDraft: boolean
  requestedRefs: string[]
  onRequest?: (requirement: Requirement, trigger: HTMLButtonElement) => void
  onOpen: (citation: Citation) => void
  onChange: () => void
}

export function ProposalPanel(props: Props) {
  const [open, setOpen] = useState(false)
  return (
    <details
      className='space-y-3 border-t pt-3'
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className='cursor-pointer text-sm font-medium'>
        Proposal drafting
      </summary>
      {open && <ProposalMatrix {...props} />}
    </details>
  )
}

function ProposalMatrix(props: Props) {
  const { api, path, planRevision } = props
  const query = useQuery({
    queryKey: ['proposal', path, planRevision],
    queryFn: () => api.get<Proposal>(path),
  })
  if (query.isPending)
    return (
      <p role='status' className='text-sm'>
        Loading proposal requirements…
      </p>
    )
  if (query.error)
    return (
      <p role='alert' className='text-sm'>
        {query.error.message}{' '}
        <Button variant='link' onClick={() => void query.refetch()}>
          Retry
        </Button>
      </p>
    )
  return (
    <ProposalEditor
      key={planRevision + ':' + query.data.company_version_id}
      {...props}
      view={query.data}
      refresh={() => void query.refetch()}
    />
  )
}

function ProposalEditor({
  api,
  path,
  approvalId,
  revision,
  canDraft,
  requestedRefs,
  onRequest,
  onOpen,
  onChange,
  view,
  refresh,
}: Props & { view: Proposal; refresh: () => void }) {
  const [selections, setSelections] = useState(view.saved_selections || {})
  const [saved, setSaved] = useState<number>()
  const action = useAction(() => {
    refresh()
    onChange()
  })
  const selected = Object.fromEntries(
    view.requirements.flatMap((row) => {
      const wording = view.wording.find(
        (entry) => entry.id === selections[row.id]
      )
      return wording && !row.evidenced_failure ? [[row.id, wording]] : []
    })
  )
  const gapCount = view.requirements.length - Object.keys(selected).length
  const disabled = action.busy || action.uncertain

  function generate() {
    const body = {
      action: 'draft_proposal',
      approval_id: approvalId,
      expected_revision: revision,
      client_request_id: requestId(),
      company_version_id: view.company_version_id,
      selections: Object.fromEntries(
        Object.entries(selected).map(([id, wording]) => [id, wording.id])
      ),
    }
    action.run(async () => {
      const file = await api.send<components['schemas']['PreparationFile']>(
        path,
        body
      )
      setSaved(file.version)
      refresh()
      onChange()
    })
  }

  return (
    <div className='space-y-3'>
      <p className='text-sm text-muted-foreground'>
        {view.entity
          ? 'Bidding legal entity · ' + view.entity
          : 'Ask the bid owner to confirm the bidding legal entity in the Technical response plan.'}
      </p>
      {view.company_filename && (
        <p className='text-sm text-muted-foreground'>
          Approved wording source · {view.company_filename}
        </p>
      )}
      {!view.requirements.length && (
        <p className='text-sm text-muted-foreground'>
          Link tender requirements in the Technical response plan to start the
          matrix.
        </p>
      )}
      {view.requirements.map((row) => {
        const wording = selected[row.id]
        return (
          <section key={row.id} className='space-y-2 border-t py-3 text-sm'>
            <p className='text-muted-foreground'>{row.section}</p>
            <h4 className='font-medium'>{row.statement}</h4>
            <Citations
              items={row.citations}
              label='Tender source'
              onOpen={onOpen}
            />
            {canDraft && !!view.wording.length && !row.evidenced_failure && (
              <Field label='Approved response wording'>
                <select
                  className={selectStyle}
                  disabled={disabled}
                  value={wording?.id || ''}
                  onChange={(event) => {
                    const id = event.target.value
                    setSelections((previous) => ({ ...previous, [row.id]: id }))
                    setSaved(undefined)
                  }}
                >
                  <option value=''>Evidence needed</option>
                  {view.wording.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.text}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {wording ? (
              <>
                <p className='whitespace-pre-wrap'>{wording.text}</p>
                <p className='text-muted-foreground'>
                  Company evidence · {wording.location}
                </p>
              </>
            ) : (
              <>
                <p className='text-muted-foreground'>
                  {row.evidenced_failure
                    ? 'Qualification found evidence of a gap. Resolve it before drafting.'
                    : 'Evidence needed for this response.'}
                </p>
                {requestedRefs.includes(row.request_ref) ? (
                  <p>Input request open</p>
                ) : (
                  view.can_request_input &&
                  onRequest && (
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={disabled}
                      onClick={(event) => onRequest(row, event.currentTarget)}
                    >
                      Request evidence
                    </Button>
                  )
                )}
              </>
            )}
          </section>
        )
      })}
      {canDraft && view.entity && !!view.requirements.length && (
        <>
          <p className='text-sm text-muted-foreground'>
            {gapCount
              ? gapCount +
                ' requirements need evidence. The draft will show these gaps.'
              : 'The reviewer will check how the selected wording addresses each requirement.'}
          </p>
          <Button size='sm' disabled={disabled} onClick={generate}>
            Generate and save proposal draft
          </Button>
          <ActionError action={action} />
          {saved !== undefined && (
            <p role='status' className='text-sm'>
              Proposal draft saved as version {saved}.
            </p>
          )}
        </>
      )}
    </div>
  )
}
