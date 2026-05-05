import { supabase } from "@/lib/supabase";
import Link from "next/link";

async function getStats() {
  const [alertsRes, tradesRes, warRes] = await Promise.all([
    supabase.from("alerts").select("strategy, move_pct", { count: "exact" }).limit(1000),
    supabase.from("trades").select("pnl_usd, closed_at"),
    supabase.from("war_markets").select("id", { count: "exact" }).limit(1),
  ]);

  const alerts = alertsRes.data ?? [];
  const trades = tradesRes.data ?? [];
  const totalAlerts = alertsRes.count ?? 0;
  const totalWarMarkets = warRes.count ?? 0;

  const closedTrades = trades.filter((t) => t.closed_at && t.pnl_usd !== null);
  const totalPnl = closedTrades.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);
  const wins = closedTrades.filter((t) => (t.pnl_usd ?? 0) > 0);
  const winRate = closedTrades.length > 0 ? (wins.length / closedTrades.length) * 100 : 0;

  const momentumCount = alerts.filter((a) => a.strategy === "A_MOMENTUM").length;
  const fadeCount = alerts.filter((a) => a.strategy === "B_FADE").length;
  const skipCount = alerts.filter((a) => a.strategy === "SKIP").length;

  return { totalAlerts, totalWarMarkets, totalPnl, winRate, closedTrades: closedTrades.length, momentumCount, fadeCount, skipCount };
}

async function getRecentAlerts() {
  const { data } = await supabase
    .from("alerts")
    .select("alert_id, ts, question, direction, price_from, price_to, move_pct, volume_24h, strategy, tier")
    .order("ts", { ascending: false })
    .limit(8);
  return data ?? [];
}

export default async function Home() {
  const [stats, alerts] = await Promise.all([getStats(), getRecentAlerts()]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Overview</h1>
        <p className="text-zinc-500 text-sm mt-1">Polymarket spike detection &amp; smart money tracking</p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Alerts" value={stats.totalAlerts.toLocaleString()} sub="all time" />
        <StatCard label="Closed Trades" value={stats.closedTrades.toString()} sub={`Win rate ${stats.winRate.toFixed(0)}%`} color={stats.winRate > 50 ? "green" : "red"} />
        <StatCard label="Total P&amp;L" value={`$${stats.totalPnl >= 0 ? "+" : ""}${stats.totalPnl.toFixed(0)}`} sub="realized" color={stats.totalPnl >= 0 ? "green" : "red"} />
        <StatCard label="War Markets" value={stats.totalWarMarkets.toLocaleString()} sub="tracked" />
      </div>

      {/* Strategy breakdown */}
      <div className="grid grid-cols-3 gap-4">
        <StratCard label="A — Momentum" count={stats.momentumCount} color="green" desc="confirmed news + whale" />
        <StratCard label="B — Fade" count={stats.fadeCount} color="blue" desc="no news, single order" />
        <StratCard label="SKIP" count={stats.skipCount} color="zinc" desc="mixed signals" />
      </div>

      {/* Recent alerts */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Recent Alerts</h2>
          <Link href="/alerts" className="text-xs text-zinc-500 hover:text-white">view all →</Link>
        </div>
        <div className="rounded-lg border border-zinc-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-500 text-xs">
                <th className="px-4 py-2 text-left">Market</th>
                <th className="px-4 py-2 text-right">Move</th>
                <th className="px-4 py-2 text-right">Price</th>
                <th className="px-4 py-2 text-right">Volume</th>
                <th className="px-4 py-2 text-left">Strategy</th>
                <th className="px-4 py-2 text-left">Time</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.alert_id} className="border-b border-zinc-900 hover:bg-zinc-900/50">
                  <td className="px-4 py-2 max-w-xs truncate text-zinc-200">{a.question}</td>
                  <td className="px-4 py-2 text-right">
                    <span className={a.direction === "UP" ? "text-green-400" : "text-red-400"}>
                      {a.direction === "UP" ? "↑" : "↓"} +{a.move_pct?.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-400">
                    {Math.round((a.price_from ?? 0) * 100)}¢→{Math.round((a.price_to ?? 0) * 100)}¢
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-400">
                    ${((a.volume_24h ?? 0) / 1000).toFixed(0)}K
                  </td>
                  <td className="px-4 py-2">
                    <StrategyBadge strategy={a.strategy} />
                  </td>
                  <td className="px-4 py-2 text-zinc-500 text-xs">
                    {new Date(a.ts).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </td>
                </tr>
              ))}
              {alerts.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600">No alerts yet — run the ETL script first</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color = "zinc" }: { label: string; value: string; sub: string; color?: string }) {
  const valueColor = color === "green" ? "text-green-400" : color === "red" ? "text-red-400" : "text-white";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-5 py-4">
      <p className="text-zinc-500 text-xs uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</p>
      <p className="text-zinc-600 text-xs mt-1">{sub}</p>
    </div>
  );
}

function StratCard({ label, count, color, desc }: { label: string; count: number; color: string; desc: string }) {
  const border = color === "green" ? "border-green-900" : color === "blue" ? "border-blue-900" : "border-zinc-800";
  const text = color === "green" ? "text-green-400" : color === "blue" ? "text-blue-400" : "text-zinc-400";
  return (
    <div className={`rounded-lg border ${border} bg-zinc-900/30 px-5 py-4`}>
      <p className={`text-xs font-semibold ${text} uppercase tracking-wider`}>{label}</p>
      <p className="text-3xl font-bold text-white mt-1">{count}</p>
      <p className="text-zinc-600 text-xs mt-1">{desc}</p>
    </div>
  );
}

function StrategyBadge({ strategy }: { strategy: string }) {
  if (strategy === "A_MOMENTUM") return <span className="text-xs bg-green-900/50 text-green-400 px-2 py-0.5 rounded">MOMENTUM</span>;
  if (strategy === "B_FADE") return <span className="text-xs bg-blue-900/50 text-blue-400 px-2 py-0.5 rounded">FADE</span>;
  return <span className="text-xs bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded">SKIP</span>;
}
