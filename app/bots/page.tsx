import fs from "fs";
import path from "path";

function loadPositions() {
  try {
    const raw = fs.readFileSync(
      path.join(process.cwd(), "data", "sure_bot_positions.json"),
      "utf-8"
    );
    const data = JSON.parse(raw);
    const positions = Object.values(data.positions) as any[];
    const stats = data.stats;
    return { positions, stats };
  } catch {
    return { positions: [], stats: null };
  }
}

export default function BotsPage() {
  const { positions, stats } = loadPositions();

  const closed = positions.filter(
    (p) => p.status !== "open" && p.status !== "cancelled" && p.pnl != null
  );
  const open = positions.filter((p) => p.status === "open");
  const wins = closed.filter((p) => p.pnl > 0);
  const losses = closed.filter((p) => p.pnl <= 0);
  const totalPnl = closed.reduce((s: number, p: any) => s + p.pnl, 0);
  const wr = closed.length ? (wins.length / closed.length) * 100 : 0;

  const sorted = [...positions].sort((a, b) => {
    if (!a.timestamp) return 1;
    if (!b.timestamp) return -1;
    return b.timestamp.localeCompare(a.timestamp);
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">98_sure_bot — Позиции</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Покупает высоковероятностные исходы (96–99.5¢) · сканирует каждые 5 минут
        </p>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPI label="Всего позиций" value={positions.length.toString()} />
        <KPI label="Закрытых" value={closed.length.toString()} />
        <KPI
          label="Win Rate"
          value={`${wr.toFixed(1)}%`}
          color={wr > 90 ? "green" : "yellow"}
        />
        <KPI
          label="Общий P&L"
          value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(0)}`}
          color={totalPnl >= 0 ? "green" : "red"}
        />
        <KPI label="Открытых" value={open.length.toString()} color="yellow" />
      </div>

      {/* Открытые */}
      {open.length > 0 && (
        <Section title="Открытые позиции" count={open.length} color="green">
          <PositionsTable rows={open} />
        </Section>
      )}

      {/* История */}
      <Section title="Все позиции" count={sorted.length} color="zinc">
        <PositionsTable rows={sorted} />
      </Section>
    </div>
  );
}

function KPI({ label, value, color }: { label: string; value: string; color?: string }) {
  const c =
    color === "green" ? "text-green-400" :
    color === "red" ? "text-red-400" :
    color === "yellow" ? "text-yellow-400" : "text-white";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
      <p className="text-zinc-600 text-xs">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${c}`}>{value}</p>
    </div>
  );
}

function Section({ title, count, color, children }: {
  title: string; count: number; color: string; children: React.ReactNode;
}) {
  const c =
    color === "green" ? "text-green-400" :
    color === "yellow" ? "text-yellow-400" : "text-zinc-400";
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
  if (rows.length === 0) return null;

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
                {p.pnl != null ? (
                  <span className={p.pnl >= 0 ? "text-green-400" : "text-red-400"}>
                    {p.pnl >= 0 ? "+" : ""}${p.pnl.toFixed(2)}
                  </span>
                ) : (
                  <span className="text-zinc-600">открыта</span>
                )}
              </td>
              <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
              <td className="px-4 py-2 text-xs text-zinc-600">{p.category || "—"}</td>
              <td className="px-4 py-2 text-zinc-600 text-xs whitespace-nowrap">
                {p.timestamp
                  ? new Date(p.timestamp).toLocaleString("ru-RU", {
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
    cancelled: "bg-zinc-800 text-zinc-600",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${map[status] ?? "bg-zinc-800 text-zinc-500"}`}>
      {status}
    </span>
  );
}
