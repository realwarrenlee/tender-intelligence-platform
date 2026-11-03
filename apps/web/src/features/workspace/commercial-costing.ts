import { read, utils, write, type WorkBook } from 'xlsx'

export const maxCostingBytes = 2 * 1024 * 1024
type Cell = string | number | null

const layout = {
  Assumptions: [
    'Package',
    'Mode',
    'Tender ID',
    'Risk %',
    'Markup %',
    'Approval reference',
  ],
  Scope: [
    'Item ID',
    'Service',
    'Quantity',
    'Unit',
    'Scope reference',
    'Estimate rate SGD',
    'Estimate basis',
    'Estimate approval',
  ],
  Suppliers: ['Supplier ID', 'Supplier', 'Quote date', 'Quote reference'],
  Quotes: [
    'Supplier ID',
    'Item ID',
    'Coverage',
    'Quoted unit',
    'Quoted quantity',
    'Rate SGD',
    'Notes',
  ],
} as const

function checkArchive(buffer: ArrayBuffer) {
  // Bound the ZIP directory before passing an imported workbook to the reader.
  const view = new DataView(buffer)
  if (
    view.byteLength > maxCostingBytes ||
    view.byteLength < 22 ||
    view.getUint32(0, true) !== 0x04034b50
  )
    throw new Error('Choose an XLSX workbook up to 2 MiB.')
  let end = view.byteLength - 22
  while (
    end >= Math.max(0, view.byteLength - 65557) &&
    (view.getUint32(end, true) !== 0x06054b50 ||
      end + 22 + view.getUint16(end + 20, true) !== view.byteLength)
  )
    end--
  if (end < Math.max(0, view.byteLength - 65557))
    throw new Error('The workbook archive is invalid.')
  const count = view.getUint16(end + 10, true)
  const start = view.getUint32(end + 16, true)
  if (!count || count > 64 || view.getUint32(end + 12, true) !== end - start)
    throw new Error('The workbook archive exceeds the supported layout.')
  let size = 0
  let offset = start
  for (let i = 0; i < count; i++) {
    if (offset + 46 > end || view.getUint32(offset, true) !== 0x02014b50)
      throw new Error('The workbook archive is invalid.')
    size += view.getUint32(offset + 24, true)
    if (size > 8 * 1024 * 1024)
      throw new Error('The workbook expands beyond 8 MiB.')
    offset +=
      46 +
      view.getUint16(offset + 28, true) +
      view.getUint16(offset + 30, true) +
      view.getUint16(offset + 32, true)
  }
  if (offset !== end) throw new Error('The workbook archive is invalid.')
}

function table(
  book: WorkBook,
  name: keyof typeof layout,
  maxRows: number
): Cell[][] {
  const sheet = book.Sheets[name]
  if (!sheet?.['!ref'])
    throw new Error('Add the ' + name + ' sheet from the example.')
  const headers = layout[name]
  const range = utils.decode_range(sheet['!fullref'] || sheet['!ref'])
  if (range.e.r > maxRows || range.e.c >= headers.length)
    throw new Error(name + ' exceeds the supported rows or columns.')
  const rows = Array.from({ length: range.e.r + 1 }, (_, row) =>
    headers.map((_, col): Cell => {
      const cell = sheet[utils.encode_cell({ r: row, c: col })]
      if (!cell) return null
      if (cell.f !== undefined || cell.F !== undefined)
        throw new Error(
          name + ' accepts values only. Replace formulas before importing.'
        )
      if (
        name === 'Assumptions' &&
        row > 0 &&
        (col === 3 || col === 4) &&
        cell.z?.includes('%')
      )
        throw new Error(
          'Enter risk and markup as plain numbers. Enter 5 for 5%.'
        )
      if (cell.v == null || cell.v === '') return null
      const value = cell.v
      if (
        value instanceof Date &&
        name === 'Suppliers' &&
        col === 2 &&
        Number.isFinite(value.getTime())
      )
        return value.toISOString().slice(0, 10)
      if (typeof value === 'string' && value.length <= 300)
        return value.trim() || null
      if (typeof value === 'number' && Number.isFinite(value)) return value
      throw new Error(
        name +
          ' contains an unsupported value at ' +
          utils.encode_cell({ r: row, c: col }) +
          '.'
      )
    })
  )
  if (!headers.every((value, col) => value === rows[0][col]))
    throw new Error(name + ' headers must match the example workbook.')
  return rows.slice(1).filter((row) => row.some((value) => value !== null))
}

function label(value: Cell, field: string) {
  if (typeof value !== 'string' || !value)
    throw new Error('Enter ' + field + ' as text.')
  return value
}

function unique(id: string, seen: Set<string>, field: string) {
  if (seen.has(id)) throw new Error('Duplicate ' + field + '.')
  seen.add(id)
}

function scaled(value: Cell, decimals: number, maximum: number, field: string) {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(String(value))
  if (!match || (match[2]?.length || 0) > decimals || Number(value) > maximum)
    throw new Error(
      'Enter ' +
        field +
        ' from 0 to ' +
        maximum +
        ' with up to ' +
        decimals +
        ' decimal places.'
    )
  return BigInt(match[1] + (match[2] || '').padEnd(decimals, '0'))
}

export function readCosting(buffer: ArrayBuffer) {
  checkArchive(buffer)
  const book = read(buffer, {
    sheetRows: 302,
    sheetStubs: true,
    cellFormula: true,
    cellNF: true,
    cellHTML: false,
    cellDates: true,
  })
  const allowed = [...Object.keys(layout), 'Estimate', 'Comparison']
  if (book.SheetNames.some((name) => !allowed.includes(name)))
    throw new Error(
      'Use the example workbook layout with its four input sheets.'
    )
  const tables = {
    Assumptions: table(book, 'Assumptions', 1),
    Scope: table(book, 'Scope', 30),
    Suppliers: table(book, 'Suppliers', 10),
    Quotes: table(book, 'Quotes', 300),
  }
  if (
    !tables.Assumptions.length ||
    !tables.Scope.length ||
    !tables.Suppliers.length
  )
    throw new Error(
      'Enter package assumptions, at least one scope item and at least one supplier.'
    )
  const [title, mode, tenderId, riskInput, markupInput, approval] =
    tables.Assumptions[0]
  if (mode !== 'example' && mode !== 'working')
    throw new Error('Mode must be example or working.')
  if (
    mode === 'working' &&
    (typeof tenderId !== 'string' ||
      !/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(tenderId))
  )
    throw new Error(
      'Enter the tender ID from the tender workspace for a working workbook.'
    )
  const riskRate = scaled(riskInput, 2, 100, 'Risk %')
  const markupRate = scaled(markupInput, 2, 100, 'Markup %')
  if (riskRate || markupRate)
    label(approval, 'an assumption approval reference')
  const itemIds = new Set<string>()
  const scope = tables.Scope.map(
    ([
      idInput,
      description,
      qty,
      unit,
      reference,
      rate,
      basis,
      estimateApproval,
    ]) => {
      const id = label(idInput, 'a scope item ID')
      unique(id, itemIds, 'scope item ' + id)
      const quantity = scaled(qty, 3, 10000, 'quantity for ' + id)
      if (!quantity)
        throw new Error('Quantity must be greater than zero for ' + id + '.')
      const estimate = [rate, basis, estimateApproval].every(
        (value) => value === null
      )
        ? null
        : {
            rate: scaled(rate, 2, 100000, 'estimate rate for ' + id),
            basis: label(basis, 'an estimate basis for ' + id),
            approval: label(
              estimateApproval,
              'an estimate approval reference for ' + id
            ),
          }
      return {
        id,
        name: label(description, 'a service description'),
        quantity,
        unit: label(unit, 'a scope unit'),
        reference: label(reference, 'a scope reference'),
        estimate,
      }
    }
  )
  const supplierIds = new Set<string>()
  const suppliers = tables.Suppliers.map(([idInput, name, date, reference]) => {
    const id = label(idInput, 'a supplier ID')
    unique(id, supplierIds, 'supplier ' + id)
    if (date !== null || reference !== null) {
      const value = label(date, 'a quote date for ' + id)
      const parsed = new Date(value)
      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
        !Number.isFinite(parsed.getTime()) ||
        parsed.toISOString().slice(0, 10) !== value
      )
        throw new Error('Use a valid YYYY-MM-DD quote date for ' + id + '.')
      label(reference, 'a quote reference for ' + id)
    }
    return { id, name: label(name, 'a supplier name'), date, reference }
  })
  const lines = new Set<string>()
  const quotes = tables.Quotes.map(
    ([supplierId, itemId, coverage, unit, qty, rate, notes]) => {
      const supplier = suppliers.find((item) => item.id === supplierId)
      if (
        !supplier?.reference ||
        typeof itemId !== 'string' ||
        !itemIds.has(itemId)
      )
        throw new Error(
          'Each quote line needs a known supplier with a dated source and a known scope item.'
        )
      unique(
        JSON.stringify([supplier.id, itemId]),
        lines,
        'quote for ' + supplier.id + ' / ' + itemId
      )
      if (
        coverage !== 'included' &&
        coverage !== 'partial' &&
        coverage !== 'excluded'
      )
        throw new Error('Coverage must be included, partial or excluded.')
      if (coverage !== 'included') label(notes, 'coverage notes for ' + itemId)
      const quotedUnit =
        unit === null && coverage !== 'included'
          ? null
          : label(unit, 'a quoted unit for ' + itemId)
      const quantity =
        qty === null && coverage !== 'included'
          ? null
          : scaled(qty, 3, 10000, 'quoted quantity for ' + itemId)
      if (quantity === 0n)
        throw new Error(
          'Quoted quantity must be greater than zero for ' + itemId + '.'
        )
      const quotedRate =
        rate === null && coverage !== 'included'
          ? null
          : scaled(rate, 2, 100000, 'quoted rate for ' + itemId)
      return {
        supplierId: supplier.id,
        itemId,
        coverage,
        unit: quotedUnit,
        quantity,
        rate: quotedRate,
        notes,
      }
    }
  )
  return {
    title: label(title, 'a package name'),
    mode,
    tenderId,
    riskRate,
    markupRate,
    approval,
    scope,
    suppliers,
    quotes,
    tables,
  }
}

export type Costing = ReturnType<typeof readCosting>
const rounded = (value: bigint, divisor: bigint) =>
  (value + divisor / 2n) / divisor

export function compareQuotes(model: Costing) {
  return model.suppliers.map((supplier) => {
    const lines = model.scope.map((item) => {
      const quote = model.quotes.find(
        (quote) => quote.supplierId === supplier.id && quote.itemId === item.id
      )
      const status = !quote
        ? 'Missing'
        : quote.coverage === 'excluded'
          ? 'Excluded'
          : quote.coverage === 'partial'
            ? 'Partial'
            : quote.unit?.toLowerCase() !== item.unit.toLowerCase()
              ? 'Unit mismatch'
              : quote.quantity !== item.quantity
                ? 'Quantity mismatch'
                : 'Quoted'
      const amount =
        status === 'Quoted'
          ? rounded(item.quantity * quote!.rate!, 1000n)
          : null
      return { item, quote, status, amount }
    })
    const amounts = lines.flatMap((line) =>
      line.amount === null ? [] : [line.amount]
    )
    const subtotal = amounts.length
      ? amounts.reduce((sum, amount) => sum + amount, 0n)
      : null
    return {
      supplier,
      lines,
      subtotal,
      total: amounts.length === lines.length ? subtotal : null,
    }
  })
}

export function costScenario(
  model: Costing,
  supplierId: string,
  allowEstimates: boolean
) {
  const comparison = compareQuotes(model).find(
    ({ supplier }) => supplier.id === supplierId
  )
  if (!comparison) throw new Error('Choose a supplier.')
  const lines = comparison.lines.map((line) => {
    if (line.amount !== null)
      return { ...line, basis: 'Quote', amount: line.amount }
    if (allowEstimates && line.item.estimate)
      return {
        ...line,
        basis: 'Estimate',
        amount: rounded(line.item.quantity * line.item.estimate.rate, 1000n),
      }
    return { ...line, basis: 'Unpriced', amount: null }
  })
  const base = lines.every((line) => line.amount !== null)
    ? lines.reduce((sum, line) => sum + (line.amount ?? 0n), 0n)
    : null
  const risk = base === null ? null : rounded(base * model.riskRate, 10000n)
  const markup =
    base === null || risk === null
      ? null
      : rounded((base + risk) * model.markupRate, 10000n)
  const total =
    base === null || risk === null || markup === null
      ? null
      : base + risk + markup
  return { supplier: comparison.supplier, lines, base, risk, markup, total }
}

const dollars = (cents: bigint | null | undefined) =>
  cents == null ? null : Number(cents) / 100

export function exportCosting(
  model: Costing,
  supplierId: string,
  allowEstimates: boolean
): ArrayBuffer {
  const scenario = costScenario(model, supplierId, allowEstimates)
  const book = utils.book_new()
  function add(name: string, rows: Cell[][], widths: number[]) {
    const sheet = utils.aoa_to_sheet(rows)
    sheet['!cols'] = widths.map((wch) => ({ wch }))
    utils.book_append_sheet(book, sheet, name)
  }
  add(
    'Estimate',
    [
      ['Package', model.title],
      ['Mode', model.mode],
      ['Tender ID', model.tenderId],
      ['Supplier scenario', scenario.supplier.name],
      ['Estimates allowed', allowEstimates ? 'Yes' : 'No'],
      [
        'Costing status',
        scenario.total === null
          ? 'Incomplete'
          : scenario.lines.some((line) => line.basis === 'Estimate')
            ? 'Complete with estimates'
            : 'Complete from quote',
      ],
      ['Base cost (SGD)', dollars(scenario.base)],
      ['Risk allowance (SGD)', dollars(scenario.risk)],
      ['Markup (SGD)', dollars(scenario.markup)],
      ['Total before tax (SGD)', dollars(scenario.total)],
      ['Assumption approval reference', model.approval],
      [
        'Calculation',
        'Risk on base; markup on base plus risk; rounded to cents.',
      ],
      [
        'Item ID',
        'Service',
        'Basis',
        'Cost SGD',
        'Source or estimate basis',
        'Estimate approval',
      ],
      ...scenario.lines.map((line) => [
        line.item.id,
        line.item.name,
        line.basis,
        dollars(line.amount),
        line.basis === 'Estimate'
          ? line.item.estimate!.basis
          : line.basis === 'Quote'
            ? scenario.supplier.reference
            : null,
        line.basis === 'Estimate' ? line.item.estimate!.approval : null,
      ]),
    ],
    [32, 63, 14, 17, 43, 24]
  )
  add(
    'Comparison',
    [
      [
        'Supplier',
        'Quote date',
        'Quote reference',
        'Item ID',
        'Status',
        'Scope quantity',
        'Scope unit',
        'Quoted unit',
        'Quoted quantity',
        'Rate SGD',
        'Comparable cost SGD',
        'Notes',
      ],
      ...compareQuotes(model).flatMap(({ supplier, lines }) =>
        lines.map((line) => [
          supplier.name,
          supplier.date,
          supplier.reference,
          line.item.id,
          line.status,
          Number(line.item.quantity) / 1000,
          line.item.unit,
          line.quote?.unit ?? null,
          line.quote?.quantity == null
            ? null
            : Number(line.quote.quantity) / 1000,
          dollars(line.quote?.rate),
          dollars(line.amount),
          line.quote?.notes ?? null,
        ])
      ),
    ],
    [29, 14, 20, 13, 18, 17, 13, 14, 17, 13, 23, 35]
  )
  for (const name of Object.keys(layout) as (keyof typeof layout)[])
    add(
      name,
      [[...layout[name]], ...model.tables[name]],
      layout[name].map((header) => Math.max(header.length + 4, 20))
    )
  return write(book, { bookType: 'xlsx', type: 'array', compression: true })
}
