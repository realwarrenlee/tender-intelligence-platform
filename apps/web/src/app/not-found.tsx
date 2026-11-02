import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <main className='grid min-h-svh place-content-center gap-4 text-center'>
      <p className='text-sm text-muted-foreground'>404</p>
      <h1 className='text-2xl font-semibold'>Page not found</h1>
      <p className='text-muted-foreground'>
        This page is not part of the workspace.
      </p>
      <Button asChild>
        <Link href='/tenders'>Back to work inbox</Link>
      </Button>
    </main>
  )
}
