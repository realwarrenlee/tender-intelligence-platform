import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { playwright } from '@vitest/browser-playwright'
import path from 'path'
import { defineConfig } from 'vitest/config'

// Vite is used only by the browser test runner.
export default defineConfig({
  envDir: '../..',
  define: { 'process.env': JSON.stringify({ NODE_ENV: 'test' }) },
  optimizeDeps: {
    include: [
      '@radix-ui/react-tabs',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-select',
      '@radix-ui/react-dialog',
      'next/link',
      'next/navigation',
      'react-resizable-panels',
      'next-themes',
      'pdfjs-dist',
      '@supabase/supabase-js',
    ],
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    silent: 'passed-only',
    unstubEnvs: true,
    browser: {
      enabled: true,
      provider: playwright(),
      instances: [
        { browser: 'chromium', viewport: { width: 1440, height: 900 } },
      ],
    },
    coverage: {
      // include: ['src/**/*.{js,jsx,ts,tsx}'], // Uncomment to expand the report to all src/**/* so untested modules appear as 0% coverage.
      exclude: ['src/components/ui/**', 'src/test-utils/**'],
    },
  },
})
