'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, BarChart3, Layers, Terminal } from 'lucide-react'

const navItems = [
  { href: '/', label: 'Overview', icon: Activity },
  { href: '/bots', label: 'Позиции', icon: Layers },
  { href: '/report', label: 'Аналитика', icon: BarChart3 },
  { href: '/control', label: 'Управление', icon: Terminal },
]

export function Navbar() {
  const pathname = usePathname()

  return (
    <nav className="glass-navbar sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-3">
            <div className="relative">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
                <span className="font-mono font-bold text-white text-sm">98</span>
              </div>
              <div className="absolute -bottom-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-[#0a0f1e] animate-pulse-dot" />
            </div>
            <span className="text-xl font-bold gradient-text tracking-tight">
              98_SURE_BOT
            </span>
          </Link>

          <div className="flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href
              const Icon = item.icon
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                    isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </Link>
              )
            })}
          </div>

          <div className="glass-card px-4 py-2 flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse-dot" />
            <span className="text-xs text-white/60">Live</span>
          </div>
        </div>
      </div>
    </nav>
  )
}
