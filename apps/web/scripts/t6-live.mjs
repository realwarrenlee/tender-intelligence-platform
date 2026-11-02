// Explicit paid, real-Auth browser evaluation. All business writes use visible UI controls.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const root = resolve(import.meta.dirname, '../../..')
const local = resolve(root, 'evals/runs/local')
const output = resolve(root, 'output/playwright')
mkdirSync(output, { recursive: true })
const accounts = JSON.parse(
  readFileSync(resolve(local, 't6-ui-accounts.json'))
).accounts
const statePath = resolve(local, 't6-ui-state.json')
let state
try {
  state = JSON.parse(readFileSync(statePath))
} catch {
  state = { stages: [] }
}
const save = () => writeFileSync(statePath, JSON.stringify(state, null, 2))
const browser = await chromium.launch({ headless: true })
const pages = []
async function login(role, existing) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1080 },
    acceptDownloads: true,
  })
  const page = await context.newPage()
  pages.push(page)
  page.on('pageerror', (e) =>
    console.log('Browser error:', e.message.slice(0, 180))
  )
  const account = existing || accounts[role]
  await page.goto('http://127.0.0.1:3000/sign-in')
  await page.getByLabel('Email', { exact: true }).fill(account.email)
  await page.getByLabel('Password', { exact: true }).fill(account.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page
    .getByRole('heading', { name: 'Work inbox', exact: true })
    .waitFor({ timeout: 45000 })
  return page
}
async function get(page, path) {
  return page.evaluate(async (path) => {
    const raw = Object.entries(localStorage).find(([key]) =>
      /^sb-.*-auth-token$/.test(key)
    )?.[1]
    const token = raw && JSON.parse(raw).access_token
    const response = await fetch('/api/v1' + path, {
      headers: { Authorization: 'Bearer ' + token },
    })
    return { status: response.status, body: await response.json() }
  }, path)
}
async function snapshot(page, label) {
  const data = await get(page, '/tenders/' + state.tender)
  assert.equal(data.status, 200)
  state.stages.push({ label, view: data.body })
  save()
  await page.screenshot({
    path: resolve(output, label + '.png'),
    fullPage: true,
  })
  console.log(
    label,
    JSON.stringify({
      revision: data.body.input_revision,
      status: data.body.jobs[0]?.status,
      recommendation: data.body.assessment?.candidate.recommendation.decision,
      blockers: data.body.assessment?.blockers.length,
    })
  )
  return data.body
}
async function waitJob(page, minimumRevision = 0) {
  for (let i = 0; i < 300; i++) {
    let result
    try {
      result = await get(page, '/tenders/' + state.tender)
    } catch {
      await page.waitForTimeout(2000)
      continue
    }
    const { body } = result
    if (
      body.input_revision >= minimumRevision &&
      body.jobs[0]?.input_revision === body.input_revision &&
      !['queued', 'running'].includes(body.jobs[0].status)
    )
      return body
    await page.waitForTimeout(2000)
  }
  throw new Error('Live worker did not finish within ten minutes.')
}
async function desk(page) {
  await page.goto('http://127.0.0.1:3000/tenders/' + state.tender)
  await page
    .getByRole('heading', {
      name: 'D1 fictional campus qualification',
      exact: true,
    })
    .waitFor()
}
const fixture = resolve(root, 'evals/fixtures/development/D1-qualification')
try {
  const phase = process.argv[2]
  if (phase === 'initial') {
    const page = await login('owner')
    await page
      .getByRole('link', { name: 'Company profile', exact: true })
      .click()
    await page
      .getByLabel('Company reference file')
      .setInputFiles(resolve(fixture, 'inputs/initial/company-profile.pdf'))
    await page.getByLabel('Effective on', { exact: true }).fill('2026-01-01')
    await page.getByLabel('Expires on (optional)').fill('2027-12-31')
    await page
      .getByLabel('Acceptance reason')
      .fill('Fictional reference reviewed for the T6 browser evaluation.')
    await page.getByRole('checkbox').check()
    await page
      .getByRole('button', { name: 'Accept company evidence', exact: true })
      .click()
    await page
      .getByText(
        'Company evidence accepted. Previous tender readiness must be reassessed.'
      )
      .waitFor({ timeout: 90000 })
    await page.goto('http://127.0.0.1:3000/tenders')
    await page
      .getByRole('button', { name: 'Create tender', exact: true })
      .click()
    await page
      .getByLabel('Tender title')
      .fill('D1 fictional campus qualification')
    await page
      .getByRole('button', { name: 'Create and upload files', exact: true })
      .click()
    await page.waitForURL(/\/tenders\/[a-f0-9-]+$/)
    state.tender = page.url().split('/').at(-1)
    save()
    await page.getByText('Add documents or amendment', { exact: true }).click()
    await page
      .getByLabel('Tender files')
      .setInputFiles(resolve(fixture, 'inputs/initial/tender.pdf'))
    await page
      .getByRole('button', { name: 'Upload sources', exact: true })
      .click()
    await page.getByRole('button', { name: 'Analyse', exact: true }).click()
    await waitJob(page)
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await page.getByRole('tab', { name: 'Requirements', exact: true }).click()
    await page
      .getByRole('button', { name: 'Tender source 1', exact: true })
      .first()
      .click()
    await snapshot(page, 't6-initial')
  } else if (phase === 'initial-resume') {
    const page = await login('owner')
    await desk(page)
    await waitJob(page)
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await page.getByRole('tab', { name: 'Requirements', exact: true }).click()
    await page
      .getByRole('button', { name: 'Tender source 1', exact: true })
      .first()
      .click()
    await snapshot(page, 't6-initial')
  } else if (phase === 'answer') {
    const owner = await login('owner')
    await desk(owner)
    await owner.getByRole('tab', { name: 'Questions', exact: true }).click()
    const view = (await get(owner, '/tenders/' + state.tender)).body
    const drafts = view.assessment.candidate.review_requests
    const draft = drafts.find((d) =>
      /Saturday|two.*technician/i.test(d.question)
    )
    assert(draft, 'Model did not draft a staffing question.')
    const form = owner.locator('form').filter({ hasText: draft.question })
    await form
      .getByLabel('Assign reviewer')
      .selectOption(accounts.reviewer.user_id)
    await form
      .getByRole('button', { name: 'Create review request', exact: true })
      .click()
    await owner
      .getByText('Assigned to Fictional reviewer', { exact: false })
      .waitFor()
    const reviewer = await login('reviewer')
    await desk(reviewer)
    await reviewer.getByRole('tab', { name: 'Questions', exact: true }).click()
    const answer = JSON.parse(
      readFileSync(resolve(fixture, 'events/engineering-answer.json'))
    )
    await reviewer.getByLabel('Your answer').fill(answer.text)
    await reviewer
      .getByRole('button', { name: 'Save answer and reassess', exact: true })
      .click()
    await waitJob(reviewer, view.input_revision + 1)
    await reviewer.getByRole('button', { name: 'Refresh', exact: true }).click()
    await snapshot(reviewer, 't6-answered')
  } else if (phase === 'answer-resume') {
    const page = await login('reviewer')
    await desk(page)
    await waitJob(page, 3)
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await page.getByRole('tab', { name: 'Requirements', exact: true }).click()
    await snapshot(page, 't6-answered-final')
  } else if (phase === 'decision') {
    const page = await login('approver')
    await desk(page)
    await page
      .getByRole('tab', { name: 'Decision & history', exact: true })
      .click()
    await page.getByLabel('Decision', { exact: true }).selectOption('hold')
    await page.getByRole('checkbox').check()
    await page
      .getByLabel('Decision reason')
      .fill(
        'Human hold: staffing is confirmed for two people; remaining scope and reconciliation require review.'
      )
    await page
      .getByRole('button', { name: 'Record decision', exact: true })
      .click()
    await page.getByText(/hold · Current human decision/i).waitFor()
    const downloaded = page.waitForEvent('download')
    await page
      .getByRole('button', { name: 'Export qualification brief', exact: true })
      .click()
    const file = await downloaded
    await file.saveAs(resolve(output, 't6-human-hold.md'))
    await snapshot(page, 't6-human-decision')
  } else if (phase === 'amendment') {
    const page = await login('owner')
    await desk(page)
    const view = (await get(page, '/tenders/' + state.tender)).body
    await page.getByText('Add documents or amendment', { exact: true }).click()
    await page
      .getByLabel('Source role', { exact: true })
      .selectOption('addendum')
    await page
      .getByLabel('Amends source', { exact: true })
      .selectOption(view.documents.find((d) => d.role === 'tender').id)
    await page
      .getByLabel('Tender files')
      .setInputFiles(resolve(fixture, 'inputs/updates/addendum.pdf'))
    await page
      .getByRole('button', { name: 'Upload sources', exact: true })
      .click()
    await page
      .getByText('Human decision: non-current hold', { exact: true })
      .waitFor()
    await snapshot(page, 't6-amendment-stale')
    await page.getByRole('button', { name: 'Reassess', exact: true }).click()
    await waitJob(page)
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await snapshot(page, 't6-amended')
  } else if (phase === 'reconcile') {
    const page = await login('owner')
    await desk(page)
    const view = (await get(page, '/tenders/' + state.tender)).body
    const older = view.assessment.requirements.find(
      (r) => r.carried_forward && /two.*technician/i.test(r.requirement.text)
    )
    const target = view.assessment.requirements.find(
      (r) => !r.carried_forward && /three.*technician/i.test(r.requirement.text)
    )
    assert(older && target, 'No staffing amendment pair to reconcile.')
    await page.getByRole('tab', { name: 'Requirements', exact: true }).click()
    await page.getByText(/Review changed or missing obligations/).click()
    await page
      .getByLabel('Affected obligation', { exact: true })
      .selectOption(older.id)
    await page.getByLabel(target.requirement.text, { exact: true }).check()
    const citations = [
      ...new Map(
        [
          ...older.requirement.tender_citations,
          ...target.requirement.tender_citations,
        ].map((c) => [c.anchor_id + '|' + c.quote, c])
      ).values(),
    ]
    for (const [i, cite] of citations.entries()) {
      if (i)
        await page
          .getByRole('button', { name: 'Add supporting citation', exact: true })
          .click()
      const fields = page.getByRole('group', {
        name: 'Supporting citation ' + (i + 1),
        exact: true,
      })
      await fields
        .getByLabel('Supporting source', { exact: true })
        .selectOption(cite.anchor_id)
      await fields
        .getByLabel('Exact supporting quote', { exact: true })
        .fill(cite.quote)
    }
    await page
      .getByLabel('Reason for reconciliation', { exact: true })
      .fill(
        'Reviewed original two-person clause and explicitly replacing three-person addendum. Three-person availability remains unconfirmed.'
      )
    await page
      .getByRole('button', { name: 'Save reviewed mapping', exact: true })
      .click()
    for (let i = 0; i < 20; i++) {
      const current = (await get(page, '/tenders/' + state.tender)).body
      if (current.assessment.id !== view.assessment.id) break
      await page.waitForTimeout(1000)
    }
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    const corrected = await snapshot(page, 't6-reconciled')
    assert(
      corrected.assessment.reconciliation.some(
        (r) => r.requirement_id === older.id && r.resolved
      )
    )
  } else if (phase === 'unreadable') {
    const page = await login('owner')
    const mainTender = state.tender
    await page
      .getByRole('button', { name: 'Create tender', exact: true })
      .click()
    await page
      .getByLabel('Tender title')
      .fill('Fictional unreadable source check')
    await page
      .getByRole('button', { name: 'Create and upload files', exact: true })
      .click()
    await page.waitForURL(/\/tenders\/[a-f0-9-]+$/)
    state.unreadable_tender = page.url().split('/').at(-1)
    state.tender = state.unreadable_tender
    save()
    await page.getByText('Add documents or amendment', { exact: true }).click()
    await page
      .getByLabel('Tender files')
      .setInputFiles(resolve(local, 't6-blank.pdf'))
    await page
      .getByRole('button', { name: 'Upload sources', exact: true })
      .click()
    await page.getByRole('button', { name: 'Analyse', exact: true }).click()
    await waitJob(page)
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await page.getByText('SOURCE_INCOMPLETE', { exact: true }).first().waitFor()
    const result = await snapshot(page, 't6-unreadable')
    assert.equal(result.assessment, null)
    assert.equal(result.jobs[0].status, 'needs_input')
    state.tender = mainTender
    save()
  } else if (phase === 'source-final') {
    const page = await login('owner')
    await desk(page)
    const view = (await get(page, '/tenders/' + state.tender)).body
    const target = view.assessment.requirements.find(
      (r) => !r.carried_forward && /three.*technician/i.test(r.requirement.text)
    )
    await page.getByRole('tab', { name: 'Requirements', exact: true }).click()
    const article = page.locator('article').filter({
      has: page.getByRole('heading', {
        name: target.requirement.text,
        exact: true,
      }),
    })
    await article
      .getByRole('button', { name: 'Tender source 2', exact: true })
      .click()
    await page.getByText('Extracted page 1 text', { exact: true }).waitFor()
    await page.screenshot({
      path: resolve(output, 't6-source-final.png'),
      fullPage: false,
    })
    state.extracted_page_view_verified = true
    save()
  } else if (phase === 'export-history') {
    const page = await login('approver')
    await desk(page)
    await page
      .getByRole('tab', { name: 'Decision & history', exact: true })
      .click()
    await page.getByRole('button', { name: /Revision 3 · Historical/ }).click()
    await page
      .getByText('Viewing a historical assessment.', { exact: false })
      .waitFor()
    const downloaded = page.waitForEvent('download')
    await page
      .getByRole('button', { name: 'Export qualification brief', exact: true })
      .click()
    const file = await downloaded
    await file.saveAs(resolve(output, 't6-non-current.md'))
    const text = readFileSync(resolve(output, 't6-non-current.md'), 'utf8')
    assert(text.includes('NON-CURRENT'))
    state.historical_export_non_current = true
    save()
    await page.screenshot({
      path: resolve(output, 't6-history-final.png'),
      fullPage: false,
    })
  } else if (phase === 'access') {
    const foreign = await login('foreign')
    assert.equal(
      await foreign
        .getByRole('button', { name: 'Create tender', exact: true })
        .count(),
      0
    )
    state.access = {}
    state.anonymous_status = (
      await foreign.request.get('http://127.0.0.1:3000/api/v1/tenders')
    ).status()
    assert.equal(state.anonymous_status, 401)
    for (const path of [
      '/tenders/' + state.tender,
      '/tenders/' + state.tender + '/history',
      '/assessments/' + state.stages[0].view.assessment.id + '/sources',
      '/sources/' + state.stages[0].view.documents[0].id,
    ]) {
      const response = await get(foreign, path)
      assert.equal(response.status, 404)
      state.access[path] = response.status
    }
    const user = JSON.parse(
      readFileSync(resolve(local, 'development-sign-in.json'))
    )
    const warren = await login('owner', user)
    await warren.screenshot({
      path: resolve(output, 'development-inbox.png'),
      fullPage: true,
    })
    state.development_sign_in_verified = true
    save()
    console.log(
      'Foreign workspace reads denied; development user sign-in verified.'
    )
  } else throw new Error('Unknown explicit evaluation phase.')
} catch (error) {
  for (const [i, page] of pages.entries()) {
    await page
      .screenshot({
        path: resolve(output, 't6-failure-' + i + '.png'),
        fullPage: true,
      })
      .catch(() => {})
    writeFileSync(
      resolve(output, 't6-failure-' + i + '.txt'),
      await page
        .locator('body')
        .innerText()
        .catch(() => 'Unavailable')
    )
  }
  throw error
} finally {
  save()
  await browser.close()
}
