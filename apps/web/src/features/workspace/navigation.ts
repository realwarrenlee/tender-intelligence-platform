// Keep post-login navigation local and limited to supported workspace routes.
export function workspaceDestination(path: string) {
  if (path === '/settings/company-evidence') return '/company'
  if (
    [
      '/settings/preferences',
      '/settings/profile',
      '/settings/account',
    ].includes(path)
  )
    return '/settings'
  return /^\/tenders(?:\/[^/?#\\]+(?:\?section=(?:questions|preparation|submission))?)?$/.test(
    path
  ) ||
    /^\/inbox(?:\?tab=(?:human|agent))?$/.test(path) ||
    ['/oversight', '/members', '/settings', '/company'].includes(path)
    ? path
    : '/tenders'
}
