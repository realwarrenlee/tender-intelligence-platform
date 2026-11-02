import type { KnipConfig } from 'knip'

const config: KnipConfig = {
  entry: ['scripts/t6-live.mjs'],
  ignoreExportsUsedInFile: true,
  // The Tailwind PostCSS plugin owns its PostCSS dependency.
  ignoreDependencies: ['postcss'],
  // Retain complete primitive APIs and generated contract types.
  ignoreIssues: {
    'src/**/components/ui/**': ['exports', 'types'],
    'src/features/qualification/api.generated.ts': ['types'],
  },
}
export default config
