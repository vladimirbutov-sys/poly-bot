import fs from 'fs'
import path from 'path'
import { TrendingUp, Trophy, DollarSign, Target } from 'lucide-react'
import { Navbar } from '@/components/navbar'
import { StatCard } from '@/components/stat-card'
import { HowItWorks } from '@/components/how-it-works'
import { PositionsTable } from '@/components/positions-table'

function loadData() {
  try {
    const raw = fs.readFileSync(path.join(process.cwd(), 'data', 'sure_bot_positions.json'), 'utf-8')
    return JSON.parse(raw)
  } catch { return null }
}

export default function OverviewPage() {
  const data = loadData()
  const positions = data ? Object.values(data.positions) as any[] : []

  const closed = positions.filter((p) => p.status !== 'open' && p.status !== 'cancelled' && p.pnl != null)
  const wins = closed.filter((p) => p.pnl > 0)
  const totalPnl = closed.reduce((s: number, p: any) => s + p.pnl, 0)
  const wr = closed.length ? (wins.length / closed.length) * 100 : 0

  const recent = [...positions]
    .filter((p) => p.timestamp)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
    .slice(0, 10)

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px]" />
      </div>

      <div className="relative z-10">
        <Navbar />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <section className="mb-12">
            <div className="mb-8">
              <h1 className="text-3xl font-bold text-white mb-2">Панель управления</h1>
              <p className="text-white/50">Автоматизированный трейдинг на Polymarket с высокой точностью</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Всего ставок"
                value={positions.length.toLocaleString()}
                icon={<TrendingUp className="w-5 h-5" />}
                subValue="За всё время"
              />
              <StatCard
                label="Win Rate"
                value={`${wr.toFixed(1)}%`}
                icon={<Trophy className="w-5 h-5" />}
                trend="up"
                glow="green"
                subValue={`${wins.length} побед`}
              />
              <StatCard
                label="Общий P&L"
                value={`${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(0)}`}
                icon={<DollarSign className="w-5 h-5" />}
                trend={totalPnl >= 0 ? 'up' : 'down'}
                subValue="Чистая прибыль"
              />
              <StatCard
                label="Стратегия"
                value="96–99.5¢"
                icon={<Target className="w-5 h-5" />}
                glow="blue"
                subValue="Диапазон входа"
              />
            </div>
          </section>

          <HowItWorks />
          <PositionsTable positions={recent} />

          <footer className="mt-16 pb-8 border-t border-white/10 pt-8">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
                  <span className="font-mono font-bold text-white text-xs">98</span>
                </div>
                <span className="text-sm text-white/40">© 2025 98_SURE_BOT</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse-dot" />
                <span className="text-sm text-white/40">Система активна</span>
              </div>
            </div>
          </footer>
        </main>
      </div>
    </div>
  )
}
