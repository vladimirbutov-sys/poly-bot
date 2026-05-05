import { supabase } from "@/lib/supabase";

async function getBotStats() {
  const { data } = await supabase.from("bot_stats").select("*");
  return data ?? [];
}

async function getPositions(botName: string, status?: string) {
  let q = supabase
    .from("bot_positions")
    .select("*")
    .eq("bot_name", botName)
    .order("timestamp", { ascending: false })
    .limit(50);
  if (status) q = q.eq("status", status);
  const { data } = await q;
  return data ?? [];
}

export default async function BotsPage() {
  const [stats, sureOpen, sureClosed, copyOpen, copyClosed] = await Promise.all([
    getBotStats(),
    getPositions("sure_bot", "open"),
    getPositions("sure_bot"),
    getPositions("copybot_v2", "open"),
    getPositions("copybot_v2"),
  ]);

  const sure = stats.find((s) => s.bot_name === "sure_bot");
  const copy = stats.find((s) => s.bot_name === "copybot_v2");

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-bold text-white">Bots</h1>
        <p className="text-zinc-500 text-sm mt-1">Live bot performance and positions</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-6">
        <BotCard
          name="98_sure_bot"
          desc="Buys high-probability outcomes (96–99.5%). Auto-scans every 5 min."
          stats={sure}
          openCount={sureOpen.length}
          color="green"
        />
        <BotCard
          name="copybot_v2"
          desc="Follows denizz wallet. 3-part staggered entry, log-scaled sizing."
          stats={copy}
          openCount={copyOpen.length}
          color="blue"
        />
      </div>

      {/* sure_bot positions */}
      <Section title="sure_bot — Open Positions" count={sureOpen.length} color="green">
        <PositionsTable rows={sureOpen} showPlayer={false} />
      </Section>

      <Section title="sure_bot — Last 50 Positions" count={sureClosed.length} color="zinc">
        <PositionsTable rows={sureClosed} showPlayer={false} />
      </Section>

      {/* copybot positions */}
      <Section title="copybot_v2 — Open Positions" count={copyOpen.length} color="blue">
        <PositionsTable rows={copyOpen} showPlayer={true} />
      </Section>

      <Section title="copybot_v2 — Last 50 Positions" count={copyClosed.length} color="zinc">
        <PositionsTable rows={copyClosed} showPlayer={true} />
      </Section>
    </div>
  );
}

function BotCard({ name, desc, stats, openCount, color }: {
  name: string; desc: string; stats: any; openCount: number; color: string;
}) {
  const border = color === "green" ? "border-green-900" : "border-blue-900";
  const accent = color === "green" ? "text-green-400" : "text-blue-400";
  const wins = stats?.wins ?? 0;
  const losses = stats?.losses ?? 0;
  const total = wins + losses;
  const wr = total > 0 ? ((wins / total) * 100).toFixed(0) : "—";
  const pnl = stats?.total_pnl ?? 0;

  return (
    <div className={`rounded-lg border ${border} bg-zinc-900/30 p-5 space-y-4`}>
      <div>
        <p className={`text-sm font-bold ${accent}`}>{name}</p>
        <p className="text-zinc-500 text-xs mt-1">{desc}</p>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <Metric label="P&L" value={`${pnl >= 0 ? "+" : ""}$${pnl.toFixed(0)}`} color={pnl >= 0 ? "green" : "red"} />
        <Metric label="Win rate" value={`${wr}%`} />
        <Metric label="Trades" value={String(stats?.total_bets ?? "—")} />
        <Metric label="Open" value={String(openCount)} />
      </div>
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  const c = color === "green" ? "text-green-400" : color === "red" ? "text-red-400" : "text-white";
  return (
    <div>
      <p className="text-zinc-600 text-xs">{label}</p>
      <p className={`text-lg font-bold ${c}`}>{value}</p>
    </div>
  );
}

function Section({ title, count, color, children }: {
  title: string; count: number; color: string; children: React.ReactNode;
}) {
  const c = color === "green" ? "text-green-400" : color === "blue" ? "text-blue-400" : "text-zinc-400";
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <h2 className={`text-sm font-semibold ${c} uppercase tracking-wider`}>{title}</h2>
        <span className="text-zinc-600 text-xs">{count} rows</span>
      </div>
      {children}
    </div>
  );
}

function PositionsTable({ rows, showPlayer }: { rows: any[]; showPlayer: boolean }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 px-4 py-8 text-center text-zinc-600 text-sm">
        No positions — run the ETL script to sync data
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-zinc-500 text-xs bg-zinc-900/50">
            <th className="px-4 py-2 text-left">Market</th>
            <th className="px-4 py-2 text-right">Entry</th>
            <th className="px-4 py-2 text-right">Cost</th>
            <th className="px-4 py-2 text-right">P&L</th>
            <th className="px-4 py-2 text-left">Status</th>
            {showPlayer && <th className="px-4 py-2 text-left">Player</th>}
            <th className="px-4 py-2 text-left">Category</th>
            <th className="px-4 py-2 text-left">Time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => (
            <tr key={i} className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors">
              <td className="px-4 py-2 max-w-xs">
                <div className="truncate text-zinc-200">{p.title}</div>
                {p.outcome && <div className="text-xs text-zinc-600">{p.outcome}</div>}
              </td>
              <td className="px-4 py-2 text-right font-mono text-xs text-zinc-400">
                {p.entry_price != null ? `${Math.round(p.entry_price * 100)}¢` : "—"}
              </td>
              <td className="px-4 py-2 text-right font-mono text-xs text-zinc-400">
                {p.cost_usd != null ? `$${p.cost_usd.toFixed(2)}` : "—"}
              </td>
              <td className="px-4 py-2 text-right font-mono text-xs">
                {p.final_pnl != null ? (
                  <span className={p.final_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                    {p.final_pnl >= 0 ? "+" : ""}${p.final_pnl.toFixed(2)}
                  </span>
                ) : <span className="text-zinc-600">open</span>}
              </td>
              <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
              {showPlayer && (
                <td className="px-4 py-2 text-xs text-blue-400">{p.signal_player || "—"}</td>
              )}
              <td className="px-4 py-2 text-xs text-zinc-600">{p.category || "—"}</td>
              <td className="px-4 py-2 text-zinc-600 text-xs whitespace-nowrap">
                {p.timestamp
                  ? new Date(p.timestamp).toLocaleString("en-GB", {
                      day: "2-digit", month: "short",
                      hour: "2-digit", minute: "2-digit",
                    })
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    open: "bg-green-900/40 text-green-400",
    won: "bg-green-900/40 text-green-300",
    sold: "bg-blue-900/40 text-blue-400",
    resolved: "bg-zinc-800 text-zinc-400",
    lost: "bg-red-900/40 text-red-400",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${map[status] ?? "bg-zinc-800 text-zinc-500"}`}>
      {status}
    </span>
  );
}
