import { supabase } from "@/lib/supabase";

async function getAlerts() {
  const { data } = await supabase
    .from("alerts")
    .select("*")
    .order("ts", { ascending: false })
    .limit(100);
  return data ?? [];
}

export default async function AlertsPage() {
  const alerts = await getAlerts();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Spike Alerts</h1>
        <p className="text-zinc-500 text-sm mt-1">Last 100 alerts • sorted by time</p>
      </div>

      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500 text-xs bg-zinc-900/50">
              <th className="px-4 py-3 text-left">Market</th>
              <th className="px-4 py-3 text-right">Move</th>
              <th className="px-4 py-3 text-right">Price</th>
              <th className="px-4 py-3 text-right">Volume</th>
              <th className="px-4 py-3 text-left">Strategy</th>
              <th className="px-4 py-3 text-left">Orderbook</th>
              <th className="px-4 py-3 text-center">Whale</th>
              <th className="px-4 py-3 text-right">Days left</th>
              <th className="px-4 py-3 text-left">Time</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.alert_id} className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors">
                <td className="px-4 py-3 max-w-sm">
                  <div className="truncate text-zinc-200">{a.question}</div>
                  {a.tier && <div className="text-xs text-zinc-600 mt-0.5">{a.tier} tier · {a.window_min}min</div>}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  <span className={a.direction === "UP" ? "text-green-400" : "text-red-400"}>
                    {a.direction === "UP" ? "↑" : "↓"} {a.move_pct?.toFixed(1)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-zinc-400 font-mono text-xs">
                  {Math.round((a.price_from ?? 0) * 100)}¢ → {Math.round((a.price_to ?? 0) * 100)}¢
                </td>
                <td className="px-4 py-3 text-right text-zinc-400 font-mono text-xs">
                  ${((a.volume_24h ?? 0) / 1000).toFixed(0)}K
                </td>
                <td className="px-4 py-3">
                  <div>
                    <StrategyBadge strategy={a.strategy} />
                  </div>
                  {a.strategy_reason && (
                    <div className="text-xs text-zinc-600 mt-1 max-w-xs truncate">{a.strategy_reason}</div>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-zinc-500">{a.orderbook_pattern ?? "—"}</td>
                <td className="px-4 py-3 text-center">
                  {a.whale_active ? (
                    <span className="text-orange-400 text-xs">🐋 YES</span>
                  ) : (
                    <span className="text-zinc-700 text-xs">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-zinc-500 text-xs">{a.days_left ?? "—"}d</td>
                <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                  {new Date(a.ts).toLocaleString("en-GB", {
                    day: "2-digit", month: "short",
                    hour: "2-digit", minute: "2-digit",
                  })}
                </td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-12 text-center text-zinc-600">
                  No alerts yet — run the ETL script to sync data from SQLite
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StrategyBadge({ strategy }: { strategy: string }) {
  if (strategy === "A_MOMENTUM")
    return <span className="text-xs bg-green-900/50 text-green-400 px-2 py-0.5 rounded">MOMENTUM</span>;
  if (strategy === "B_FADE")
    return <span className="text-xs bg-blue-900/50 text-blue-400 px-2 py-0.5 rounded">FADE</span>;
  return <span className="text-xs bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded">SKIP</span>;
}
