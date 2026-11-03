'use client'

import { Button } from '@/components/ui/button'

export default function WorkspaceError({ reset }: { reset: () => void }) {
  return (
    <main
      role='alert'
      className='grid min-h-svh place-content-center gap-3 p-6 text-center'
    >
      <h1 className='text-xl font-medium'>The workspace could not load.</h1>
      <p className='text-sm text-muted-foreground'>
        Try loading this screen again.
      </p>
      <Button size='sm' className='justify-self-center' onClick={reset}>
        Try again
      </Button>
    </main>
  )
}
