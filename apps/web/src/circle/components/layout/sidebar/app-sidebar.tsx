'use client'
/* eslint-disable @tanstack/query/exhaustive-deps -- API identity is stable for a session; session changes clear the shared query cache. */
import { useQuery } from '@tanstack/react-query'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/circle/components/ui/sidebar'
import {
  ClipboardCheck,
  Files,
  Inbox,
  LogOut,
  Settings,
  Users,
  Building2,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ActionError, useAction } from '@/features/qualification/actions'
import { type Member } from '@/features/qualification/api'
import { memberName } from '@/features/qualification/identity'
import { useSession } from '@/features/qualification/session'

const links = [
  { name: 'Inbox', href: '/inbox', icon: Inbox },
  { name: 'Reviews', href: '/reviews', icon: ClipboardCheck },
  { name: 'Tenders', href: '/tenders', icon: Files },
  {
    name: 'Company',
    href: '/company',
    icon: Building2,
  },
  { name: 'Members', href: '/members', icon: Users },
]
export function AppSidebar() {
  const pathname = usePathname()
  const { actor, api, session, signOut } = useSession()
  const action = useAction()
  const members = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<{ items: Member[] }>('/members'),
    enabled: !!actor,
  })
  const name = memberName(
    members.data?.items.find((m) => m.user_id === actor?.user_id)
      ?.display_name ||
      session?.user.user_metadata.full_name ||
      session?.user.user_metadata.name ||
      session?.user.email ||
      'Workspace member'
  )
  return (
    <Sidebar collapsible='offcanvas'>
      <SidebarHeader className='px-4 py-5'>
        <span className='text-sm font-semibold tracking-tight'>CBM Tender</span>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <nav aria-label='Workspace'>
            <SidebarMenu>
              {links.map(({ name, href, icon: Icon }) => {
                const active =
                  pathname === href ||
                  (href === '/tenders' && pathname.startsWith('/tenders/'))
                return (
                  <SidebarMenuItem key={href}>
                    <SidebarMenuButton asChild isActive={active}>
                      <Link
                        href={href}
                        aria-current={active ? 'page' : undefined}
                      >
                        <Icon />
                        <span>{name}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </nav>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className='gap-1 px-3 pb-4'>
        <ActionError action={action} />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={pathname === '/settings'}
            >
              <Link href='/settings'>
                <Settings />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              disabled={action.busy}
              onClick={() => action.run(signOut)}
            >
              <LogOut />
              <span>{action.busy ? 'Logging out…' : 'Log out'}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <div
          className='mt-3 flex items-center gap-2.5 px-1'
          aria-label='Signed-in profile'
        >
          <span
            aria-hidden='true'
            className='grid size-8 shrink-0 place-items-center rounded-full border bg-accent text-xs'
          >
            {name.charAt(0).toUpperCase()}
          </span>
          <span className='min-w-0 truncate text-sm'>{name}</span>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
