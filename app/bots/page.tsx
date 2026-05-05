import fs from 'fs'
import path from 'path'
import { Navbar } from '@/components/navbar'
import { PositionsTable } from '@/components/positions-table'

function loadPositions() {
  try {
    const raw = fs.readFileSync(path.join(process.cwd(), 'data', 'sure_bot_positions.json'), 'utf-8')
    const data = JSON.parse(raw)
    return Object.values(data.positions) as any[]
  } catch { return [] }
}

export default function PositionsPage() {
  const positions = loadPositions()

  const closed = positions.filter((p) => p.status !== 'open' && p.status !== 'cancelled' && p.pnl != null)
  const open = positions.filter((p) => p.status === 'open')
  const wins = closed.filter((p) => p.pnl > 0)
  const totalPnl = closed.reduce((s: number, p: any) => s + p.pnl, 0)
  const wr = closed.length ? (wins.length / closed.length) * 100 : 0

  const sorted = [...positions]
    .filter((p) => p.timestamp)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px]" />
      </div>

      <div className="relative z-10">
        <Navbar />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Позиции</h1>
            <p className="text-white/50">Все сделки 98_sure_bot — история и открытые позиции</p>
          </div>

          {/* KPI */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-10">
            {[
              { label: 'Всего позиций', value: positions.length.toString() },
              { label: 'Закрытых', value: closed.length.toString() },
              { label: 'Win Rate', value: `${wr.toFixed(1)}%`, green: true },
              { label: 'Общий P&L', value: `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(0)}`, green: totalPnl >= 0 },
              { label: 'Открытых', value: open.length.toString(), yellow: true },
            ].map((k) => (
              <div key={k.label} className="glass-card px-4 py-4">
                <p className="text-white/40 text-xs mb-2">{k.label}</p>
                <p className={`text-2xl font-mono font-bold ${k.green ? 'text-green-400' : k.yellow ? 'text-yellow-400' : 'text-white'}`}>
                  {k.value}
                </p>
              </div>
            ))}
          </div>

          <PositionsTable positions={sorted} />
        </main>
      </div>
    </div>
  )
}
