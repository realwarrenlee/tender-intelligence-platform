import { AppSidebar } from '@/components/layout/sidebar/app-sidebar'
import { SidebarProvider } from '@/components/ui/sidebar'

export default function MainLayout({
  children,
  header,
}: {
  children: React.ReactNode
  header?: React.ReactNode
}) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <div className='h-svh min-w-0 flex-1 overflow-hidden p-2'>
        <div className='flex h-full w-full flex-col overflow-hidden rounded-md border bg-container'>
          {header}
          <main id='main' className='min-h-0 flex-1 overflow-auto'>
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  )
}
