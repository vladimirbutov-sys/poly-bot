import { supabase } from "@/lib/supabase";

async function getBotStats() {
  const { data } = await supabase
    .from("bot_stats")
    .select("*")
    .eq("bot_name", "sure_bot")
    .single();
  return data;
}

async function getPositions(status?: string) {
  let q = supabase
    .from("bot_positions")
    .select("*")
    .eq("bot_name", "sure_bot")
    .order("timestamp", { ascending: false })
    .limit(100);
  if (status) q = q.eq("status", status);
  const { data } = await q;
  return data ?? [];
}

export default async function BotsPage() {
  const [stats, openPositions, allPositions] = await Promise.all([
    getBotStats(),
    getPositions("open"),
    getPositions(),
  ]);

  const wins = stats?.wins ?? 0;
  const losses = stats?.losses ?? 0;
  const total = wins + losses;
  const wr = total > 0 ? ((wins / total) * 100).toFixed(1) : "—";
  const pnl = stats?.total_pnl ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">98_sure_bot</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Покупает высоковероятностные исходы (96–99.5¢). Сканирует рынок каждые 5 минут.
        </p>
      </div>

      {/* KPI карточки */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPI label="Всего ставок" value={String(stats?.total_bets ?? "—")} />
        <KPI label="Win Rate" value={`${wr}%`} color={Number(wr) > 80 ? "green" : "yellow"} />
        <KPI
          label="Общий P&L"
          value={`${pnl >= 0 ? "+" : ""}$${pnl.toFixed(0)}`}
          color={pnl >= 0 ? "green" : "red"}
        />
        <KPI label="Побед" value={String(wins)} color="green" />
        <KPI label="Открытых" value={String(openPositions.length)} color="yellow" />
      </div>

      {/* Открытые позиции */}
      <Section title="Открытые позиции" count={openPositions.length} color="green">
        <PositionsTable rows={openPositions} />
      </Section>

      {/* История */}
      <Section title="История позиций (последние 100)" count={allPositions.length} color="zinc">
        <PositionsTable rows={allPositions} />
      </Section>
    </div>
  );
}

function KPI({ label, value, color }: { label: string; value: string; color?: string }) {
  const c =
    color === "green"
      ? "text-green-400"
      : color === "red"
      ? "text-red-400"
      : color === "yellow"
      ? "text-yellow-400"
      : "text-white";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
      <p className="text-zinc-600 text-xs">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${c}`}>{value}</p>
    </div>
  );
}

function Section({
  title,
  count,
  color,
  children,
}: {
  title: string;
  count: number;
  color: string;
  children: React.ReactNode;
}) {
  const c =
    color === "green"
      ? "text-green-400"
      : color === "yellow"
      ? "text-yellow-400"
      : "text-zinc-400";
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <h2 className={`text-sm font-semibold ${c} uppercase tracking-wider`}>{title}</h2>
        <span className="text-zinc-600 text-xs">{count} записей</span>
      </div>
      {children}
    </div>
  );
}

function PositionsTable({ rows }: { rows: any[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 px-4 py-8 text-center text-zinc-600 text-sm">
        Нет позиций — запусти ETL-скрипт для синхронизации данных
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-zinc-500 text-xs bg-zinc-900/50">
            <th className="px-4 py-2 text-left">Рынок</th>
            <th className="px-4 py-2 text-right">Вход</th>
            <th className="px-4 py-2 text-right">Сумма</th>
            <th className="px-4 py-2 text-right">P&L</th>
            <th className="px-4 py-2 text-left">Статус</th>
            <th className="px-4 py-2 text-left">Категория</th>
            <th className="px-4 py-2 text-left">Дата</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => (
            <tr
              key={i}
              className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors"
            >
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
                ) : (
                  <span className="text-zinc-600">открыта</span>
                )}
              </td>
              <td className="px-4 py-2">
                <StatusBadge status={p.status} />
              </td>
              <td className="px-4 py-2 text-xs text-zinc-600">{p.category || "—"}</td>
              <td className="px-4 py-2 text-zinc-600 text-xs whitespace-nowrap">
                {p.timestamp
                  ? new Date(p.timestamp).toLocaleString("ru-RU", {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
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
