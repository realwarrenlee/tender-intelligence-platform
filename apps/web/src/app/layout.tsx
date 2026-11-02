import { ThemeProvider } from '@/circle/components/layout/theme-provider'
import { Toaster } from '@/circle/components/ui/sonner'
import '@/circle/globals.css'
import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'

const geist = Geist({ subsets: ['latin'], variable: '--font-geist-sans' })
const mono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' })

export const metadata: Metadata = {
  title: 'CBM Tender',
  description:
    'Review tender evidence, resolve questions and record decisions.',
}
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang='en' suppressHydrationWarning>
      <body
        className={
          geist.variable + ' ' + mono.variable + ' font-sans antialiased'
        }
      >
        <ThemeProvider attribute='class' defaultTheme='dark' enableSystem>
          {children}
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  )
}
