import Link from 'next/link'

type PositionStatus = 'won' | 'open' | 'lost' | 'cancelled' | 'sold' | 'resolved' | string

interface Position {
  title: string
  entry_price?: number | null
  cost_usd?: number | null
  pnl?: number | null
  status: PositionStatus
  category?: string | null
  outcome?: string | null
}

const statusConfig: Record<string, { color: string; label: string }> = {
  won:      { color: 'bg-green-500',  label: 'Выигран' },
  open:     { color: 'bg-yellow-500', label: 'Открыт' },
  lost:     { color: 'bg-red-500',    label: 'Проигран' },
  sold:     { color: 'bg-blue-500',   label: 'Продан' },
  resolved: { color: 'bg-zinc-500',   label: 'Закрыт' },
  cancelled:{ color: 'bg-zinc-600',   label: 'Отменён' },
}

export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <section className="py-12">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-white flex items-center gap-3">
          <span className="w-1 h-6 bg-gradient-to-b from-blue-500 to-cyan-400 rounded-full" />
          Последние позиции
        </h2>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-white/40">
            <span className="w-2 h-2 bg-green-500 rounded-full" /><span>Выигран</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-white/40">
            <span className="w-2 h-2 bg-yellow-500 rounded-full" /><span>Открыт</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-white/40">
            <span className="w-2 h-2 bg-red-500 rounded-full" /><span>Проигран</span>
          </div>
          <Link href="/bots" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
            все позиции →
          </Link>
        </div>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-6 py-4 text-sm font-medium text-white/40">Рынок</th>
                <th className="text-right px-6 py-4 text-sm font-medium text-white/40">Вход</th>
                <th className="text-right px-6 py-4 text-sm font-medium text-white/40">Сумма</th>
                <th className="text-right px-6 py-4 text-sm font-medium text-white/40">P&L</th>
                <th className="text-center px-6 py-4 text-sm font-medium text-white/40">Статус</th>
                <th className="text-right px-6 py-4 text-sm font-medium text-white/40">Категория</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => {
                const pnlColor = (p.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
                const status = statusConfig[p.status] ?? { color: 'bg-zinc-500', label: p.status }
                return (
                  <tr key={i} className={`border-b border-white/5 hover:bg-white/[0.02] transition-colors ${i === positions.length - 1 ? 'border-b-0' : ''}`}>
                    <td className="px-6 py-4">
                      <span className="text-sm text-white/90 font-medium line-clamp-1">{p.title}</span>
                      {p.outcome && <span className="text-xs text-white/30 block">{p.outcome}</span>}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="font-mono text-sm text-cyan-400">
                        {p.entry_price != null ? `${Math.round(p.entry_price * 100)}¢` : '—'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="font-mono text-sm text-white/70">
                        {p.cost_usd != null ? `$${p.cost_usd.toFixed(2)}` : '—'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {p.pnl != null ? (
                        <span className={`font-mono text-sm font-medium ${pnlColor}`}>
                          {p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-white/20 text-sm">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${status.color} ${p.status === 'open' ? 'animate-pulse-dot' : ''}`} />
                        <span className="text-sm text-white/60">{status.label}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="inline-flex px-3 py-1 rounded-lg bg-white/5 text-xs text-white/50 font-medium">
                        {p.category || '—'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
