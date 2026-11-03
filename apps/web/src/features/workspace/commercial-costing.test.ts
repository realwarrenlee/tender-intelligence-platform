import { beforeAll, expect, it } from 'vitest'
import { read, utils, write } from 'xlsx'
import {
  compareQuotes,
  costScenario,
  exportCosting,
  readCosting,
} from './commercial-costing'

let example: ArrayBuffer
beforeAll(async () => {
  const response = await fetch('/examples/hvac-costing-example.xlsx')
  expect(response.ok).toBe(true)
  example = await response.arrayBuffer()
})

it('compares identical scope and leaves missing, excluded and incomparable rates out of totals', () => {
  const model = readCosting(example)
  const [alpha, beta, gamma] = compareQuotes(model)
  expect(alpha.total).toBe(430000n)
  expect(beta.lines.map((line) => line.status)).toEqual([
    'Quoted',
    'Unit mismatch',
    'Excluded',
  ])
  expect(beta.subtotal).toBe(228000n)
  expect(beta.total).toBeNull()
  expect(gamma.lines.every((line) => line.status === 'Missing')).toBe(true)
  expect(gamma.subtotal).toBeNull()
  expect(gamma.total).toBeNull()
})

it('prices the selected supplier with documented estimates only when requested', () => {
  const model = readCosting(example)
  expect(costScenario(model, 'ALPHA', false)).toMatchObject({
    base: 430000n,
    risk: 21500n,
    markup: 45150n,
    total: 496650n,
  })
  expect(costScenario(model, 'BETA', false).total).toBeNull()
  const estimated = costScenario(model, 'BETA', true)
  expect(estimated.lines.map((line) => line.basis)).toEqual([
    'Quote',
    'Estimate',
    'Estimate',
  ])
  expect(estimated).toMatchObject({
    base: 434000n,
    risk: 21700n,
    markup: 45570n,
    total: 501270n,
  })
  expect(costScenario(model, 'GAMMA', true).total).toBeNull()
  const result = read(exportCosting(model, 'BETA', true))
  const estimate = utils.sheet_to_json(result.Sheets.Estimate, { header: 1 })
  expect(estimate).toContainEqual(['Total before tax (SGD)', 5012.7])
  expect(estimate).toContainEqual(['Mode', 'example'])
  expect(
    readCosting(write(result, { type: 'array', bookType: 'xlsx' })).suppliers
  ).toEqual(model.suppliers)
})

it('rejects a cached formula and duplicate supplier lines rather than pricing either', () => {
  const book = read(example)
  book.Sheets.Quotes.F2 = { t: 'n', f: '25*4', v: 100 }
  expect(() =>
    readCosting(write(book, { type: 'array', bookType: 'xlsx' }))
  ).toThrow(/formulas/i)
  const duplicate = read(example)
  utils.sheet_add_aoa(
    duplicate.Sheets.Quotes,
    [['ALPHA', 'AHU', 'included', 'visit', 24, 3]],
    { origin: -1 }
  )
  expect(() =>
    readCosting(write(duplicate, { type: 'array', bookType: 'xlsx' }))
  ).toThrow(/duplicate/i)
})

it('rejects a quantity mismatch and rounds a half cent exactly', () => {
  const book = read(example)
  book.Sheets.Quotes.E2 = { t: 'n', v: 23 }
  const mismatch = readCosting(write(book, { type: 'array', bookType: 'xlsx' }))
  expect(compareQuotes(mismatch)[0].lines[0].status).toBe('Quantity mismatch')
  expect(costScenario(mismatch, 'ALPHA', false).total).toBeNull()
  book.Sheets.Quotes.E2 = { t: 'n', v: 0.005 }
  book.Sheets.Quotes.F2 = { t: 'n', v: 1 }
  book.Sheets.Scope.C2 = { t: 'n', v: 0.005 }
  const fractional = readCosting(
    write(book, { type: 'array', bookType: 'xlsx' })
  )
  expect(costScenario(fractional, 'ALPHA', false)).toMatchObject({
    base: 190001n,
    total: 219451n,
  })
})

it('rejects Excel percentage formatting that would otherwise understate the allowance', () => {
  const book = read(example)
  book.Sheets.Assumptions.D2 = { t: 'n', v: 0.05, z: '0%' }
  expect(() =>
    readCosting(write(book, { type: 'array', bookType: 'xlsx' }))
  ).toThrow(/enter 5 for 5%/i)
})
