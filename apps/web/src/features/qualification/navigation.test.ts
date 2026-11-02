import { expect, it } from 'vitest'
import { workspaceDestination } from './navigation'

it('preserves the supported review tab and clean workspace destinations after sign-in', () => {
  expect(workspaceDestination('/tenders/one?section=questions')).toBe(
    '/tenders/one?section=questions'
  )
  expect(workspaceDestination('/reviews')).toBe('/reviews')
  expect(workspaceDestination('/company')).toBe('/company')
  expect(workspaceDestination('/settings/company-evidence')).toBe('/company')
  expect(workspaceDestination('/settings')).toBe('/settings')
  expect(workspaceDestination('/settings/preferences')).toBe('/settings')
  expect(workspaceDestination('/settings/profile')).toBe('/settings')
  expect(workspaceDestination('/settings/account')).toBe('/settings')
})

it('rejects external, removed and unsupported query destinations', () => {
  for (const path of [
    'https://example.com',
    '//example.com',
    '/company?redirect=https://example.com',
    '/tenders/one?redirect=https://example.com',
    '/tenders/one?section=questions&redirect=x',
    '/review',
    '/lndev-ui/agent',
  ]) {
    expect(workspaceDestination(path)).toBe('/tenders')
  }
})

it('keeps only supported shareable Inbox tabs', () => {
  expect(workspaceDestination('/inbox?tab=human')).toBe('/inbox?tab=human')
  expect(workspaceDestination('/inbox?tab=agent')).toBe('/inbox?tab=agent')
  for (const path of [
    '/inbox?tab=all',
    '/inbox?tab=agent&redirect=//example.com',
    '/inbox?tab=agent%26redirect=x',
  ]) {
    expect(workspaceDestination(path)).toBe('/tenders')
  }
})
