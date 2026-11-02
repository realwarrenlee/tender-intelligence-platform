import assert from 'node:assert/strict'

const base = process.argv[2] || 'http://127.0.0.1:3000'
for (const [path, destination] of [
  ['/', '/tenders'],
  ['/lndev-ui/inbox', '/inbox'],
  ['/lndev-ui/reviews', '/reviews'],
  ['/lndev-ui/projects', '/tenders'],
  ['/lndev-ui/settings/profile', '/settings'],
  ['/settings/account', '/settings'],
  ['/settings/company-evidence', '/company'],
  ['/settings/profile', '/settings'],
  ['/settings/preferences', '/settings'],
  ['/lndev-ui/team/CORE/all', '/tenders'],
]) {
  const response = await fetch(base + path, { redirect: 'manual' })
  assert.equal(response.status, 307, path + ' must redirect')
  assert.equal(response.headers.get('location'), destination)
}

for (const path of [
  '/sign-in',
  '/inbox',
  '/reviews',
  '/members',
  '/tenders',
  '/tenders/route-smoke',
  '/settings',
  '/company',
]) {
  const response = await fetch(base + path)
  assert.equal(response.status, 200, path + ' must load directly')
}

for (const path of [
  '/this-page-does-not-exist',
  '/review',
  '/lndev-ui/agent',
  '/lndev-ui/initiatives',
  '/lndev-ui/settings/notifications',
  '/settings/notifications',
  '/settings/code-and-reviews',
  '/settings/integrations',
]) {
  const response = await fetch(base + path)
  assert.equal(response.status, 404, path + ' must return HTTP 404')
}

const anonymous = await fetch(base + '/api/v1/tenders')
assert.equal(
  anonymous.status,
  401,
  'The API proxy must preserve authentication failures'
)
assert.equal((await anonymous.json()).code, 'UNAUTHENTICATED')
console.log(
  'Route checks passed: clean routes, redirects, removed features, and protected API.'
)
