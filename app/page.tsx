import { supabase } from "@/lib/supabase";
import Link from "next/link";

async function getSureBotData() {
  const [statsRes, positionsRes] = await Promise.all([
    supabase.from("bot_stats").select("*").eq("bot_name", "sure_bot").single(),
    supabase
      .from("bot_positions")
      .select("*")
      .eq("bot_name", "sure_bot")
      .order("timestamp", { ascending: false })
      .limit(10),
  ]);
  return {
    stats: statsRes.data,
    recent: positionsRes.data ?? [],
  };
}

export default async function Home() {
  const { stats, recent } = await getSureBotData();

  const wins = stats?.wins ?? 0;
  const losses = stats?.losses ?? 0;
  const total = wins + losses;
  const wr = total > 0 ? (wins / total) * 100 : 0;
  const pnl = stats?.total_pnl ?? 0;
  const totalBets = stats?.total_bets ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">98_sure_bot</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Покупает высоковероятностные исходы на Polymarket · сканирует каждые 5 минут
        </p>
      </div>

      {/* Главные метрики */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Всего ставок"
          value={totalBets.toLocaleString()}
          sub="за всё время"
        />
        <StatCard
          label="Win Rate"
          value={`${wr.toFixed(1)}%`}
          sub={`${wins} побед / ${losses} потерь`}
          color={wr > 90 ? "green" : "yellow"}
        />
        <StatCard
          label="Общий P&L"
          value={`${pnl >= 0 ? "+" : ""}$${pnl.toFixed(0)}`}
          sub="реализованный"
          color={pnl >= 0 ? "green" : "red"}
        />
        <StatCard
          label="Стратегия"
          value="96–99.5¢"
          sub="диапазон входа"
          color="green"
        />
      </div>

      {/* Как работает */}
      <div className="grid grid-cols-3 gap-4">
        <InfoCard
          step="01"
          title="Сканирование"
          text="Каждые 5 минут проверяет все открытые рынки Polymarket через API"
        />
        <InfoCard
          step="02"
          title="Фильтрация"
          text="13 фильтров отсекают coin-flip, низколиквидные и рискованные рынки"
        />
        <InfoCard
          step="03"
          title="Вход и выход"
          text="Лимитный ордер. После резолюции — автоматический вывод выигрыша"
        />
      </div>

      {/* Последние позиции */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
            Последние позиции
          </h2>
          <Link href="/bots" className="text-xs text-zinc-500 hover:text-white">
            все позиции →
          </Link>
        </div>
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
              </tr>
            </thead>
            <tbody>
              {recent.map((p, i) => (
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
                    ) : (
                      <span className="text-zinc-600">открыта</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-4 py-2 text-xs text-zinc-600">{p.category || "—"}</td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-zinc-600">
                    Нет данных — запусти ETL-скрипт для синхронизации
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  color = "zinc",
}: {
  label: string;
  value: string;
  sub: string;
  color?: string;
}) {
  const valueColor =
    color === "green"
      ? "text-green-400"
      : color === "red"
      ? "text-red-400"
      : color === "yellow"
      ? "text-yellow-400"
      : "text-white";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-5 py-4">
      <p className="text-zinc-500 text-xs uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</p>
      <p className="text-zinc-600 text-xs mt-1">{sub}</p>
    </div>
  );
}

function InfoCard({ step, title, text }: { step: string; title: string; text: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-5 py-4 space-y-2">
      <p className="text-green-900 text-2xl font-black">{step}</p>
      <p className="text-white text-sm font-semibold">{title}</p>
      <p className="text-zinc-500 text-xs leading-relaxed">{text}</p>
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
