import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ActionError, Field, selectStyle, useAction } from './actions'
import { requestId, type Api } from './api'
import type { Costing } from './commercial-costing'

const exampleUrl = '/examples/hvac-costing-example.xlsx'
const costingMime =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const sgd = new Intl.NumberFormat('en-SG', {
  style: 'currency',
  currency: 'SGD',
  currencyDisplay: 'code',
})
const money = (value: bigint | null | undefined) =>
  value == null ? '—' : sgd.format(Number(value) / 100)

export function CommercialCostingPanel({
  api,
  tenderId,
  uploadUrl,
  approvalId,
  revision,
  onSaved,
}: {
  api: Api
  tenderId: string
  uploadUrl: string
  approvalId: string
  revision: number
  onSaved: () => void
}) {
  const [data, setData] = useState<{
    model: Costing
    engine: typeof import('./commercial-costing')
  }>()
  const [supplier, setSupplier] = useState('')
  const [estimates, setEstimates] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const action = useAction(onSaved)
  const blocked = loading || action.busy || action.uncertain
  const scenario = data?.engine.costScenario(data.model, supplier, estimates)
  const matching =
    data?.model.mode === 'working' &&
    String(data.model.tenderId).toLowerCase() === tenderId.toLowerCase()

  async function load(file?: File) {
    setLoading(true)
    setError('')
    setData(undefined)
    setSaved(false)
    try {
      const engine = await import('./commercial-costing')
      if (
        file &&
        (!/\.xlsx$/i.test(file.name) || file.size > engine.maxCostingBytes)
      )
        throw new Error('Choose an XLSX workbook up to 2 MiB.')
      const input = file || (await fetch(exampleUrl))
      if (input instanceof Response && !input.ok)
        throw new Error('The example workbook could not be loaded.')
      const model = engine.readCosting(await input.arrayBuffer())
      setSupplier(model.suppliers[0].id)
      setEstimates(false)
      setData({ model, engine })
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'The costing workbook could not be read.'
      )
    } finally {
      setLoading(false)
    }
  }

  function workbookFile() {
    if (!data) throw new Error('Load a workbook first.')
    return new File(
      [data.engine.exportCosting(data.model, supplier, estimates)],
      data.model.mode === 'example'
        ? 'example-costing-snapshot.xlsx'
        : 'supplier-costing-snapshot.xlsx',
      { type: costingMime }
    )
  }

  function download() {
    setError('')
    try {
      const file = workbookFile()
      const href = URL.createObjectURL(file)
      const link = document.createElement('a')
      link.href = href
      link.download = file.name
      link.click()
      setTimeout(() => URL.revokeObjectURL(href), 1000)
    } catch {
      setError('The costing workbook could not be exported.')
    }
  }

  function save() {
    if (!matching || !scenario || scenario.total === null || blocked) return
    setError('')
    setSaved(false)
    const form = new FormData()
    try {
      form.set('file', workbookFile())
    } catch {
      setError('The costing workbook could not be exported.')
      return
    }
    form.set(
      'metadata',
      JSON.stringify({
        approval_id: approvalId,
        expected_revision: revision,
        client_request_id: requestId(),
      })
    )
    action.run(async () => {
      await api.upload(uploadUrl, form)
      setSaved(true)
      onSaved()
    })
  }

  return (
    <details className='space-y-4 border-t pt-3'>
      <summary className='cursor-pointer text-sm font-medium'>
        Compare supplier quotes and calculate cost
      </summary>
      <p className='text-sm text-muted-foreground'>
        Use the example layout for one service package in SGD before tax. Enter
        comparable rates for the requested scope and period. Enter 5 for 5% risk
        or markup. For a working workbook, set Mode to working and use tender ID{' '}
        <code className='break-all'>{tenderId}</code>.
      </p>
      <div className='flex flex-wrap items-end gap-3'>
        <div className='max-w-full sm:max-w-xs'>
          <Field label='Costing input workbook'>
            <Input
              type='file'
              accept='.xlsx'
              disabled={blocked}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0]
                event.currentTarget.value = ''
                if (file) void load(file)
              }}
            />
          </Field>
        </div>
        <Button
          size='sm'
          variant='outline'
          disabled={blocked}
          onClick={() => void load()}
        >
          Load fictional example
        </Button>
        <Button size='sm' variant='link' asChild>
          <a href={exampleUrl} download>
            Download example workbook
          </a>
        </Button>
      </div>
      {loading && (
        <p role='status' className='text-sm'>
          Reading workbook…
        </p>
      )}
      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}
      {data && scenario && (
        <>
          <div className='space-y-2'>
            <h4 className='font-medium'>{data.model.title}</h4>
            {data.model.mode === 'example' && (
              <p className='text-sm text-muted-foreground'>
                Fictional example for comparison and practice.
              </p>
            )}
            <h5 className='text-sm font-medium'>Quote coverage</h5>
            {data.engine
              .compareQuotes(data.model)
              .map(({ supplier: source, lines, subtotal, total }) => (
                <details key={source.id} className='border-b py-2 text-sm'>
                  <summary className='cursor-pointer font-medium'>
                    {source.name} ·{' '}
                    {lines.filter((line) => line.amount !== null).length}/
                    {lines.length} comparable
                    {total !== null
                      ? ' · ' + money(total)
                      : subtotal !== null
                        ? ' · Partial subtotal ' + money(subtotal)
                        : ''}
                  </summary>
                  <p className='my-2 text-muted-foreground'>
                    {source.reference
                      ? `${source.reference} · ${source.date}`
                      : 'No quote received'}
                  </p>
                  <div className='overflow-x-auto'>
                    <table className='w-full text-left'>
                      <thead>
                        <tr className='border-b'>
                          <th scope='col' className='py-1 pr-3'>
                            Scope
                          </th>
                          <th scope='col' className='py-1 pr-3'>
                            Coverage
                          </th>
                          <th scope='col' className='py-1 pr-3'>
                            Quoted rate
                          </th>
                          <th scope='col' className='py-1 pr-3'>
                            Comparable cost
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {lines.map(({ item, quote, status, amount }) => (
                          <tr
                            key={item.id}
                            className='border-b align-top last:border-0'
                          >
                            <th scope='row' className='py-2 pr-3 font-medium'>
                              {item.name}
                              <span className='block font-normal text-muted-foreground'>
                                {Number(item.quantity) / 1000} {item.unit} ·{' '}
                                {item.reference}
                              </span>
                            </th>
                            <td className='py-2 pr-3'>
                              {status}
                              {quote?.notes && (
                                <p className='text-muted-foreground'>
                                  {quote.notes}
                                </p>
                              )}
                            </td>
                            <td className='py-2 pr-3'>
                              {money(quote?.rate)}
                              {quote?.unit && ' / ' + quote.unit}
                              {quote?.quantity != null && (
                                <p className='text-muted-foreground'>
                                  Qty {Number(quote.quantity) / 1000}
                                </p>
                              )}
                            </td>
                            <td className='py-2 pr-3'>{money(amount)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
          </div>
          <div className='space-y-3'>
            <h5 className='font-medium'>Costing scenario</h5>
            <Field label='Supplier scenario'>
              <select
                className={selectStyle}
                disabled={blocked}
                value={supplier}
                onChange={(event) => {
                  setSupplier(event.target.value)
                  setSaved(false)
                }}
              >
                {data.model.suppliers.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.name}
                  </option>
                ))}
              </select>
            </Field>
            <label className='flex items-start gap-2 text-sm'>
              <input
                type='checkbox'
                checked={estimates}
                disabled={blocked}
                onChange={(event) => {
                  setEstimates(event.target.checked)
                  setSaved(false)
                }}
              />
              Use documented estimates where the quote has a gap
            </label>
            <ul className='divide-y text-sm'>
              {scenario.lines.map(({ item, basis, amount }) => (
                <li key={item.id} className='py-2'>
                  {item.name} · {basis} · {money(amount)}
                  {basis === 'Estimate' && (
                    <p className='text-muted-foreground'>
                      {item.estimate!.basis} · Approval{' '}
                      {item.estimate!.approval}
                    </p>
                  )}
                </li>
              ))}
            </ul>
            <dl className='grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm'>
              <dt>Base cost</dt>
              <dd>{money(scenario.base)}</dd>
              <dt>Risk allowance ({Number(data.model.riskRate) / 100}%)</dt>
              <dd>{money(scenario.risk)}</dd>
              <dt>
                Markup on base plus risk ({Number(data.model.markupRate) / 100}
                %)
              </dt>
              <dd>{money(scenario.markup)}</dd>
              <dt className='font-medium'>Total before tax</dt>
              <dd className='font-medium'>
                {scenario.total === null ? 'Incomplete' : money(scenario.total)}
              </dd>
            </dl>
            {data.model.approval && (
              <p className='text-sm text-muted-foreground'>
                Assumption approval {data.model.approval}
              </p>
            )}
            {data.model.mode === 'working' && !matching && (
              <p className='text-sm text-muted-foreground'>
                This workbook belongs to a different tender.
              </p>
            )}
            <div className='flex flex-wrap gap-2'>
              <Button
                size='sm'
                variant='outline'
                disabled={blocked}
                onClick={download}
              >
                Download costing snapshot
              </Button>
              {matching && (
                <Button
                  size='sm'
                  disabled={blocked || scenario.total === null}
                  onClick={save}
                >
                  Save as pricing workbook version
                </Button>
              )}
            </div>
            <ActionError action={action} />
            {saved && (
              <p role='status' className='text-sm'>
                Pricing workbook version saved. Request review when ready.
              </p>
            )}
          </div>
        </>
      )}
    </details>
  )
}
