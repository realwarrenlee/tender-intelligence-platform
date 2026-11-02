import path from 'node:path'
import { loadEnvConfig } from '@next/env'
import type { NextConfig } from 'next'

// The API and frontend share the ignored repository-root environment file.
loadEnvConfig(
  path.resolve(import.meta.dirname, '../..'),
  process.env.NODE_ENV !== 'production',
  undefined,
  true
)

const config: NextConfig = {
  experimental: {
    // Preserve the API's 100 MiB pack + 64 KiB multipart request allowance.
    proxyClientMaxBodySize: 100 * 1024 * 1024 + 64 * 1024,
    // The assistant has a 360-second budget; allow time for API overhead.
    proxyTimeout: 390_000,
  },
  env: {
    NEXT_PUBLIC_SUPABASE_URL:
      process.env.NEXT_PUBLIC_SUPABASE_URL ||
      process.env.VITE_SUPABASE_URL ||
      '',
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
      process.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
      '',
  },
  async redirects() {
    return [
      { source: '/', destination: '/tenders', permanent: false },
      ...[
        ['/settings/account', '/settings'],
        ['/settings/company-evidence', '/company'],
        ['/settings/preferences', '/settings'],
        ['/settings/profile', '/settings'],
        ['/lndev-ui', '/tenders'],
        ['/lndev-ui/inbox', '/inbox'],
        ['/lndev-ui/projects', '/tenders'],
        ['/lndev-ui/my-issues', '/reviews'],
        ['/lndev-ui/reviews', '/reviews'],
        ['/lndev-ui/members', '/members'],
        ['/lndev-ui/settings', '/settings'],
        ['/lndev-ui/settings/preferences', '/settings'],
        ['/lndev-ui/settings/profile', '/settings'],
        ['/lndev-ui/team/:teamId/all', '/tenders'],
      ].map(([source, destination]) => ({
        source,
        destination,
        permanent: false,
      })),
    ]
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination:
          (process.env.API_ORIGIN || 'http://127.0.0.1:8765') + '/api/:path*',
      },
    ]
  },
}
export default config
