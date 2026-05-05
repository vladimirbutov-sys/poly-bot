import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: '98_sure_bot',
  description: 'Automated high-probability trading on Polymarket',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className={`${inter.variable} font-sans bg-[#0a0f1e] text-white antialiased`}>
        {children}
      </body>
    </html>
  )
}
