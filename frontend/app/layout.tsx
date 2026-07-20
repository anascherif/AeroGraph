import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Atkinson_Hyperlegible, Geist_Mono } from 'next/font/google'
import { Toaster } from '@/components/ui/sonner'
import './globals.css'

const atkinson = Atkinson_Hyperlegible({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-atkinson',
})

const geistMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-geist-mono',
})

export const metadata: Metadata = {
  title: 'AeroGraph — Spatial Memory Engine',
  description:
    'Spatial-temporal memory engine for visually impaired navigation: live object detection, environment change detection, and natural-language spatial recall.',
  generator: 'v0.app',
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#1a1d24',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`dark ${atkinson.variable} ${geistMono.variable}`}>
      <body className="bg-background font-sans antialiased">
        {children}
        <Toaster position="top-center" richColors />
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
