/* eslint-disable @tanstack/query/exhaustive-deps -- Session changes clear the query cache. */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Pencil, Plus, X } from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Field, useAction, ActionError } from './actions'
import { type Actor, type Api, type Company, requestId, singapore } from './api'
import research from './company-research.json'

type Profile = NonNullable<NonNullable<Company['current']>['profile']>
const views = ['Overview', 'Track record', 'Sources', 'History']
const awardSource = research.profile.sources.find(
  (source) => source.publisher === 'Ministry of Finance'
)!
function profileFrom(company?: Company): Profile {
  if (company?.current?.profile) return company.current.profile
  if (company?.current)
    return { content: company.current.reference_text || '', sources: [] }
  return structuredClone(research.profile)
}

export function CompanyEvidence({ actor, api }: { actor: Actor; api: Api }) {
  const cache = useQueryClient()
  const query = useQuery({
    queryKey: ['company-evidence'],
    queryFn: () => api.get<Company>('/company-evidence'),
    refetchInterval: 5000,
  })
  const [tab, setTab] = useState('Overview')
  const [editor, setEditor] = useState<'document' | 'sources' | null>(null)
  const [uploading, setUploading] = useState(false)
  const [draft, setDraft] = useState<Profile>(research.profile)
  const [revision, setRevision] = useState(0)
  const [saved, setSaved] = useState(false)
  const [conflict, setConflict] = useState(false)
  const action = useAction(() => {
    setConflict(true)
    void query.refetch()
  })
  const profile = profileFrom(query.data)
  const current = query.data?.current
  const admin = actor.roles.includes('admin')
  const editingHere =
    editor === 'document'
      ? tab === 'Overview'
      : editor === 'sources' && tab === 'Sources'
  function beginEdit(mode: 'document' | 'sources') {
    setDraft(structuredClone(profile))
    setRevision(query.data!.evidence_revision)
    setSaved(false)
    setConflict(false)
    setEditor(mode)
    setTab(mode === 'document' ? 'Overview' : 'Sources')
  }
  function save(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = {
      expected_evidence_revision: revision,
      client_request_id: requestId(),
      accept: true,
      effective_on:
        current?.effective_on ||
        new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Singapore' }).format(
          new Date()
        ),
      expires_on: current?.expires_on || null,
      reason:
        editor === 'sources' ? 'Updated company sources' : 'Updated Company.md',
      profile: structuredClone(draft),
    }
    action.run(async () => {
      await api.send('/company-evidence/profile', body)
      setEditor(null)
      setSaved(true)
      await cache.invalidateQueries()
    })
  }
  return (
    <Tabs
      value={tab}
      onValueChange={setTab}
      className='flex h-full min-h-0 flex-col gap-0'
    >
      <header className='flex h-12 shrink-0 items-center justify-between gap-4 border-b px-6'>
        <h1 className='text-xl font-medium'>Company</h1>
        {admin && tab === 'Overview' && !editor && (
          <Button
            size='sm'
            variant='outline'
            onClick={() => beginEdit('document')}
            disabled={!query.data || query.isError}
          >
            <Pencil className='size-3.5' /> Edit company
          </Button>
        )}
        {admin && tab === 'Sources' && (
          <div className='flex items-center gap-2'>
            {!editor && (
              <Button
                size='sm'
                variant='outline'
                onClick={() => beginEdit('sources')}
                disabled={!query.data || query.isError}
              >
                <Pencil className='size-3.5' /> Edit sources
              </Button>
            )}
            <Button
              size='sm'
              onClick={() => {
                setSaved(false)
                setUploading(true)
              }}
              disabled={!query.data || query.isError || !!editor}
            >
              <Plus className='size-3.5' /> Upload source
            </Button>
          </div>
        )}
      </header>
      {admin && uploading && query.data && (
        <ReferenceUpload
          api={api}
          revision={query.data.evidence_revision}
          onClose={() => setUploading(false)}
          onRefresh={() => void query.refetch()}
          onSaved={() => {
            setUploading(false)
            setSaved(true)
            void cache.invalidateQueries()
          }}
        />
      )}
      <div className='overflow-x-auto border-b px-6 py-2.5'>
        <TabsList aria-label='Company views'>
          {views.map((value) => (
            <TabsTrigger
              key={value}
              value={value}
              id={'company-tab-' + value.replaceAll(' ', '-')}
              aria-controls='company-content'
            >
              {value}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
      {query.error && (
        <p role='alert' className='border-b px-6 py-4 text-sm text-destructive'>
          {query.error.message}
        </p>
      )}
      {saved && (
        <p role='status' className='border-b px-6 py-3 text-sm'>
          Company saved. Existing tender assessments need reassessment.
        </p>
      )}
      {query.isPending ? (
        <p className='px-6 py-6 text-sm text-muted-foreground'>
          Loading company…
        </p>
      ) : (
        query.data && (
          <div
            id='company-content'
            className='min-h-0 flex-1'
            role='tabpanel'
            aria-labelledby={'company-tab-' + tab.replaceAll(' ', '-')}
          >
            {editingHere ? (
              <form onSubmit={save}>
                <div className='border-b px-6 py-5'>
                  {editor === 'document' ? (
                    <Field label='Company.md'>
                      <Textarea
                        aria-label='Company document'
                        value={draft.content}
                        maxLength={80000}
                        required
                        rows={24}
                        disabled={action.busy || action.uncertain}
                        className='min-h-[60vh] font-mono text-[15px] leading-relaxed'
                        onChange={(event) =>
                          setDraft({ ...draft, content: event.target.value })
                        }
                      />
                    </Field>
                  ) : (
                    <SourceEditor
                      sources={draft.sources}
                      disabled={action.busy || action.uncertain}
                      onChange={(sources) => setDraft({ ...draft, sources })}
                    />
                  )}
                </div>
                <div className='space-y-3 border-b px-6 py-4'>
                  <p className='text-sm text-muted-foreground'>
                    Saving creates a version and marks existing tender
                    assessments for reassessment.
                  </p>
                  <ActionError action={action} />
                  {conflict && (
                    <Button
                      type='button'
                      size='sm'
                      variant='outline'
                      disabled={query.isFetching || query.isError}
                      onClick={() => {
                        setDraft(structuredClone(profileFrom(query.data)))
                        setRevision(query.data!.evidence_revision)
                        setConflict(false)
                      }}
                    >
                      Reload saved version
                    </Button>
                  )}
                  <div className='flex gap-2'>
                    <Button
                      size='sm'
                      disabled={
                        action.busy ||
                        action.uncertain ||
                        conflict ||
                        !draft.content.trim()
                      }
                    >
                      {action.busy
                        ? 'Saving…'
                        : editor === 'sources'
                          ? 'Save sources'
                          : 'Save company'}
                    </Button>
                    <Button
                      type='button'
                      size='sm'
                      variant='ghost'
                      disabled={action.busy || action.uncertain}
                      onClick={() => setEditor(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              </form>
            ) : tab === 'Overview' ? (
              <article className='border-b px-6 py-5'>
                <CompanyDocument content={profile.content} />
              </article>
            ) : tab === 'Track record' ? (
              <PublicAwards />
            ) : tab === 'Sources' ? (
              <>
                {profile.sources.map((source, index) => (
                  <div
                    key={source.url + index}
                    className='border-b px-6 py-4 hover:bg-accent/40'
                  >
                    <a
                      href={source.url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='inline-flex items-center gap-2 text-[15px] font-medium hover:underline'
                    >
                      {source.title}
                      <ArrowUpRight className='size-3.5 shrink-0 text-muted-foreground' />
                    </a>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      {source.publisher} · Checked {source.checked_on}
                    </p>
                    <p className='mt-1 truncate text-xs text-muted-foreground'>
                      {source.url}
                    </p>
                  </div>
                ))}
                {!profile.sources.length && (
                  <p className='border-b px-6 py-5 text-base text-muted-foreground'>
                    No external source links saved.
                  </p>
                )}
              </>
            ) : (
              <CompanyHistory
                api={api}
                actor={actor}
                history={query.data.history || []}
              />
            )}
          </div>
        )
      )}
    </Tabs>
  )
}

function CompanyDocument({ content }: { content: string }) {
  return (
    <div className='w-full space-y-4 text-base leading-relaxed'>
      {content.split(/\n\s*\n/).map((block, index) => {
        const heading = /^(#{1,3}) (.+)$/.exec(block)
        if (heading)
          return heading[1].length === 1 ? (
            <h2 key={index} className='text-2xl font-semibold tracking-tight'>
              {heading[2]}
            </h2>
          ) : (
            <h3 key={index} className='pt-2 text-base font-semibold'>
              {heading[2]}
            </h3>
          )
        return (
          <p key={index} className='break-words whitespace-normal'>
            {block}
          </p>
        )
      })}
    </div>
  )
}

function SourceEditor({
  sources,
  onChange,
  disabled,
}: {
  sources: Profile['sources']
  onChange: (sources: Profile['sources']) => void
  disabled: boolean
}) {
  return (
    <fieldset disabled={disabled} className='space-y-5'>
      <h2 className='text-lg font-medium'>Edit sources</h2>
      {sources.map((source, index) => (
        <div
          key={index}
          className='grid max-w-4xl gap-3 border-b pb-5 sm:grid-cols-2'
        >
          {(['title', 'url', 'publisher', 'checked_on'] as const).map((key) => (
            <Field
              key={key}
              label={
                {
                  title: 'Source title',
                  url: 'Source URL',
                  publisher: 'Publisher',
                  checked_on: 'Checked on',
                }[key] +
                ' ' +
                (index + 1)
              }
            >
              <Input
                value={source[key]}
                type={
                  key === 'url' ? 'url' : key === 'checked_on' ? 'date' : 'text'
                }
                required
                maxLength={
                  key === 'title' || key === 'publisher' ? 200 : undefined
                }
                onChange={(event) =>
                  onChange(
                    sources.map((item, i) =>
                      i === index
                        ? { ...item, [key]: event.target.value }
                        : item
                    )
                  )
                }
              />
            </Field>
          ))}
          <Button
            type='button'
            size='sm'
            variant='ghost'
            className='w-fit'
            onClick={() => onChange(sources.filter((_, i) => i !== index))}
          >
            <X className='size-3.5' /> Remove source {index + 1}
          </Button>
        </div>
      ))}
      <Button
        type='button'
        size='sm'
        variant='outline'
        disabled={sources.length >= 30}
        onClick={() =>
          onChange([
            ...sources,
            {
              title: '',
              url: '',
              publisher: '',
              checked_on: new Intl.DateTimeFormat('en-CA', {
                timeZone: 'Asia/Singapore',
              }).format(new Date()),
            },
          ])
        }
      >
        <Plus className='size-3.5' /> Add source
      </Button>
    </fieldset>
  )
}

function PublicAwards() {
  return (
    <>
      <div className='overflow-x-auto'>
        <table
          aria-label='Public contract awards'
          className='w-full text-left text-[15px]'
        >
          <thead className='border-b text-sm text-muted-foreground'>
            <tr>
              {[
                'Contract / buyer',
                'Award date',
                'Published amount · SGD',
                'Source',
              ].map((label) => (
                <th key={label} className='px-6 py-3 font-normal'>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...research.awards]
              .sort((a, b) => {
                const date = (value: string) =>
                  Date.parse(value.split('/').reverse().join('-'))
                return date(b.award_date) - date(a.award_date)
              })
              .map((award) => (
                <tr
                  key={award.tender_no}
                  className='border-b transition-colors hover:bg-accent/40'
                >
                  <td className='min-w-72 px-6 py-4'>
                    <span
                      className='font-medium'
                      title={award.tender_description}
                    >
                      {award.title}
                    </span>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      {award.agency}
                    </p>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      {award.tender_no} · {award.tender_detail_status}
                    </p>
                  </td>
                  <td className='px-6 py-4 text-sm whitespace-nowrap'>
                    {award.award_date}
                  </td>
                  <td className='px-6 py-4 whitespace-nowrap tabular-nums'>
                    {Number(award.awarded_amt).toLocaleString('en-SG', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className='px-6 py-4'>
                    <a
                      href={awardSource.url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='inline-flex items-center gap-1 text-sm underline underline-offset-4'
                      aria-label={'GeBIZ source for ' + award.tender_no}
                    >
                      GeBIZ <ArrowUpRight className='size-3.5' />
                    </a>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p className='border-b px-6 py-4 text-sm text-muted-foreground'>
        Amounts have differing pricing bases and are not company revenue or
        directly comparable rates.{' '}
        <a
          href='https://data.gov.sg/open-data-licence'
          target='_blank'
          rel='noopener noreferrer'
          className='underline underline-offset-4'
        >
          Singapore Open Data Licence
        </a>
      </p>
    </>
  )
}

type CompanyVersion = NonNullable<Company['current']>

function CompanyHistory({
  api,
  actor,
  history,
}: {
  api: Api
  actor: Actor
  history: CompanyVersion[]
}) {
  const [selected, setSelected] = useState<CompanyVersion | null>(null)
  const mobile = useIsMobile()
  const list = (
    <div>
      {history.length ? (
        history.map((version) => (
          <div
            key={version.id}
            className='flex flex-wrap items-start justify-between gap-3 border-b px-6 py-4 text-sm'
          >
            <div className='min-w-0 flex-1'>
              <p>
                Version {version.evidence_revision} · {version.reason}
              </p>
              <p
                className='mt-1 text-xs text-muted-foreground'
                title={version.created_by}
              >
                {singapore(version.created_at)} ·{' '}
                {version.created_by === actor.user_id ? 'You' : 'Admin'}
              </p>
            </div>
            <Button
              type='button'
              size='sm'
              variant='outline'
              aria-pressed={selected?.id === version.id}
              onClick={() => setSelected(version)}
            >
              See version
            </Button>
          </div>
        ))
      ) : (
        <p className='border-b px-6 py-5 text-base text-muted-foreground'>
          No saved versions yet.
        </p>
      )}
    </div>
  )
  const panel = selected && (
    <CompanyVersionPanel
      api={api}
      version={selected}
      onClose={() => setSelected(null)}
    />
  )
  if (mobile && selected) return <div className='h-full min-h-0'>{panel}</div>
  return (
    <ResizablePanelGroup direction='horizontal' className='h-full! min-h-0'>
      <ResizablePanel
        id='company-history'
        order={1}
        minSize={35}
        className='overflow-y-auto!'
      >
        {list}
      </ResizablePanel>
      {selected && (
        <>
          <ResizableHandle withHandle />
          <ResizablePanel
            id='company-version'
            order={2}
            defaultSize={40}
            minSize={28}
          >
            {panel}
          </ResizablePanel>
        </>
      )}
    </ResizablePanelGroup>
  )
}

function CompanyVersionPanel({
  api,
  version,
  onClose,
}: {
  api: Api
  version: CompanyVersion
  onClose: () => void
}) {
  const query = useQuery({
    queryKey: ['company-evidence-version', version.id],
    queryFn: () =>
      api.get<CompanyVersion>('/company-evidence/versions/' + version.id),
  })
  const content = query.data?.profile?.content ?? query.data?.reference_text
  return (
    <aside
      aria-label='Company version details'
      className='flex h-full min-w-0 flex-col'
    >
      <header className='flex h-12 shrink-0 items-center justify-between gap-3 border-b px-6'>
        <h2 className='text-base font-medium'>
          Version {version.evidence_revision}
        </h2>
        <Button
          type='button'
          size='icon'
          variant='ghost'
          aria-label='Close version'
          onClick={onClose}
        >
          <X className='size-4' />
        </Button>
      </header>
      <div className='border-b px-6 py-3 text-xs text-muted-foreground'>
        {singapore(version.created_at)} · Read-only
      </div>
      <div className='min-h-0 flex-1 overflow-y-auto px-6 py-5'>
        {query.isPending ? (
          <p className='text-sm text-muted-foreground'>Loading version…</p>
        ) : query.error ? (
          <p role='alert' className='text-sm text-destructive'>
            {query.error.message}
          </p>
        ) : (
          <CompanyDocument content={content || ''} />
        )}
      </div>
    </aside>
  )
}

function ReferenceUpload({
  api,
  revision,
  onSaved,
  onRefresh,
  onClose,
}: {
  api: Api
  revision: number
  onSaved: () => void
  onRefresh: () => void
  onClose: () => void
}) {
  const [expectedRevision, setExpectedRevision] = useState(revision)
  const [conflict, setConflict] = useState(false)
  const action = useAction(() => {
    setConflict(true)
    onRefresh()
  })
  function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const element = event.currentTarget
    const form = new FormData(element)
    const upload = new FormData()
    upload.append('file', form.get('file') as File)
    upload.append(
      'metadata',
      JSON.stringify({
        expected_evidence_revision: expectedRevision,
        client_request_id: requestId(),
        accept: true,
        effective_on: form.get('effective_on'),
        expires_on: form.get('expires_on') || null,
        reason: form.get('reason'),
      })
    )
    action.run(async () => {
      await api.upload('/company-evidence', upload)
      onSaved()
    })
  }
  const locked = action.busy || action.uncertain
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !locked) onClose()
      }}
    >
      <DialogContent
        className='max-h-[90dvh] overflow-y-auto sm:max-w-xl'
        showCloseButton={!locked}
      >
        <DialogHeader>
          <DialogTitle>Upload source</DialogTitle>
          <DialogDescription>
            Replaces the active company evidence; previous versions stay in
            history. Use a born-digital PDF or simple DOCX, up to 20 MiB.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className='space-y-4'>
          <fieldset disabled={locked} className='space-y-4'>
            <Field label='Company reference file'>
              <Input name='file' type='file' accept='.pdf,.docx' required />
            </Field>
            <div className='grid gap-4 sm:grid-cols-2'>
              <Field label='Effective on'>
                <Input name='effective_on' type='date' required />
              </Field>
              <Field label='Expires on (optional)'>
                <Input name='expires_on' type='date' />
              </Field>
            </div>
            <Field label='Acceptance reason'>
              <Textarea name='reason' required maxLength={2000} />
            </Field>
            <label className='flex items-start gap-2 text-sm'>
              <input type='checkbox' required className='mt-1' />I reviewed and
              accept this company reference.
            </label>
          </fieldset>
          <ActionError action={action} />
          {conflict && (
            <Button
              type='button'
              size='sm'
              variant='outline'
              disabled={revision === expectedRevision}
              onClick={() => {
                setExpectedRevision(revision)
                setConflict(false)
              }}
            >
              Use latest company version
            </Button>
          )}
          <div className='flex justify-end gap-2'>
            <Button
              type='button'
              size='sm'
              variant='ghost'
              disabled={locked}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button size='sm' disabled={locked || conflict}>
              {action.busy ? 'Accepting &' : 'Accept company evidence'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
