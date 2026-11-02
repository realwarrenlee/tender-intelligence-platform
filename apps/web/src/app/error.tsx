'use client'

import { Button } from '@/components/ui/button'

export default function WorkspaceError({ reset }: { reset: () => void }) {
  return (
    <main
      role='alert'
      className='grid min-h-svh place-content-center gap-4 text-center'
    >
      <h1 className='text-xl font-semibold'>The workspace could not load.</h1>
      <p className='text-muted-foreground'>Try loading this screen again.</p>
      <Button onClick={reset}>Try again</Button>
    </main>
  )
}
