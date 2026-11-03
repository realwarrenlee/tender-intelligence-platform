'use client'

import { ChevronRight } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import MainLayout from '@/components/layout/main-layout'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { SessionGate } from '@/features/workspace/session'

export function AuthenticatedLayout({
  children,
}: {
  children?: React.ReactNode
}) {
  const pathname = usePathname()
  const labels: Record<string, string> = {
    '/inbox': 'Inbox',
    '/reviews': 'Reviews',
    '/tenders': 'Tenders',
    '/members': 'Members',
    '/company': 'Company',
    '/settings': 'Settings',
  }
  return (
    <SessionGate>
      <a
        href='#main'
        className='sr-only focus:not-sr-only focus:fixed focus:z-50 focus:bg-background focus:p-4'
      >
        Skip to content
      </a>
      <MainLayout
        header={
          <header className='flex h-10 shrink-0 items-center gap-3 border-b px-4 text-sm'>
            <SidebarTrigger className='size-7 text-muted-foreground' />
            <nav aria-label='Breadcrumb' className='flex items-center gap-3'>
              <Link
                href='/tenders'
                className='text-muted-foreground hover:text-foreground'
              >
                Workspace
              </Link>
              <ChevronRight
                aria-hidden='true'
                className='size-3 text-muted-foreground'
              />
              {pathname.startsWith('/tenders/') && (
                <>
                  <Link
                    href='/tenders'
                    className='text-muted-foreground hover:text-foreground'
                  >
                    Tenders
                  </Link>
                  <ChevronRight
                    aria-hidden='true'
                    className='size-3 text-muted-foreground'
                  />
                </>
              )}
              <span aria-current='page' className='font-medium'>
                {labels[pathname] || 'Tender review'}
              </span>
            </nav>
          </header>
        }
      >
        {children}
      </MainLayout>
    </SessionGate>
  )
}
