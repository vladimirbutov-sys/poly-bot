import { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: string | number
  icon?: ReactNode
  trend?: 'up' | 'down' | 'neutral'
  glow?: 'green' | 'blue' | 'none'
  subValue?: string
}

export function StatCard({ label, value, icon, trend, glow = 'none', subValue }: StatCardProps) {
  const glowClass = glow === 'green' ? 'glow-green' : glow === 'blue' ? 'glow-blue' : ''
  const valueColor = trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-white'

  return (
    <div className={`glass-card p-6 ${glowClass} transition-all duration-300 hover:bg-white/[0.08]`}>
      <div className="flex items-start justify-between mb-4">
        <span className="text-sm text-white/60 font-medium">{label}</span>
        {icon && (
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-400/20 flex items-center justify-center text-cyan-400">
            {icon}
          </div>
        )}
      </div>
      <div className="space-y-1">
        <p className={`text-3xl font-mono font-bold tracking-tight ${valueColor}`}>{value}</p>
        {subValue && <p className="text-sm text-white/40 font-mono">{subValue}</p>}
      </div>
    </div>
  )
}
