import { AuthenticatedLayout } from '@/components/layout/authenticated-layout'
import { Providers } from '../providers'

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <Providers>
      <AuthenticatedLayout>{children}</AuthenticatedLayout>
    </Providers>
  )
}
