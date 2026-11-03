import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <main className='grid min-h-svh place-content-center gap-3 p-6 text-center'>
      <h1 className='text-xl font-medium'>Page not found</h1>
      <p className='text-sm text-muted-foreground'>
        This page is not part of the workspace.
      </p>
      <Button asChild size='sm' className='justify-self-center'>
        <Link href='/tenders'>Back to Tenders</Link>
      </Button>
    </main>
  )
}
