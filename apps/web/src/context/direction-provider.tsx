import { useEffect, useState } from 'react'
import { DirectionProvider as RdxDirProvider } from '@radix-ui/react-direction'
import { getCookie } from '@/lib/cookies'

type Direction = 'ltr' | 'rtl'

export function DirectionProvider({ children }: { children: React.ReactNode }) {
  const [dir] = useState<Direction>(
    () => (getCookie('dir') as Direction) || 'ltr'
  )

  useEffect(() => {
    document.documentElement.setAttribute('dir', dir)
  }, [dir])

  return <RdxDirProvider dir={dir}>{children}</RdxDirProvider>
}
