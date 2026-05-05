import { supabase } from "@/lib/supabase";

async function getMarkets() {
  const { data } = await supabase
    .from("war_markets")
    .select("*")
    .order("volume_24h", { ascending: false })
    .limit(100);
  return data ?? [];
}

export default async function MarketsPage() {
  const markets = await getMarkets();

  const categories = ["iran", "ukraine", "china"];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">War Markets</h1>
        <p className="text-zinc-500 text-sm mt-1">
          {markets.length} active markets · sorted by volume
        </p>
      </div>

      {categories.map((cat) => {
        const group = markets.filter(
          (m) => (m.category ?? "").toLowerCase() === cat
        );
        if (group.length === 0) return null;
        return (
          <div key={cat}>
            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-3">
              {cat} · {group.length} markets
            </h2>
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 text-xs bg-zinc-900/50">
                    <th className="px-4 py-2 text-left">Question</th>
                    <th className="px-4 py-2 text-right">YES</th>
                    <th className="px-4 py-2 text-right">NO</th>
                    <th className="px-4 py-2 text-right">Volume 24h</th>
                    <th className="px-4 py-2 text-right">Days left</th>
                    <th className="px-4 py-2 text-left">Resolves</th>
                  </tr>
                </thead>
                <tbody>
                  {group.map((m) => {
                    const yes = m.yes_price ?? m.price ?? 0;
                    const no = m.no_price ?? (1 - yes);
                    const daysLeft = m.end_date
                      ? Math.ceil(
                          (new Date(m.end_date).getTime() - Date.now()) /
                            86400000
                        )
                      : null;
                    return (
                      <tr
                        key={m.condition_id ?? m.id}
                        className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors"
                      >
                        <td className="px-4 py-2 max-w-sm">
                          <div className="truncate text-zinc-200">{m.question}</div>
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          <PricePill value={yes} />
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          <span className="text-zinc-400 text-xs">
                            {Math.round(no * 100)}¢
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right text-zinc-400 text-xs font-mono">
                          {m.volume_24h
                            ? `$${((m.volume_24h as number) / 1000).toFixed(0)}K`
                            : "—"}
                        </td>
                        <td className="px-4 py-2 text-right">
                          <span
                            className={
                              daysLeft !== null && daysLeft < 7
                                ? "text-orange-400 text-xs"
                                : "text-zinc-500 text-xs"
                            }
                          >
                            {daysLeft !== null ? `${daysLeft}d` : "—"}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-zinc-600 text-xs">
                          {m.end_date
                            ? new Date(m.end_date).toLocaleDateString("en-GB", {
                                day: "2-digit",
                                month: "short",
                                year: "numeric",
                              })
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      {markets.length === 0 && (
        <div className="rounded-lg border border-zinc-800 px-4 py-12 text-center text-zinc-600">
          No war markets yet — run the ETL script to sync data
        </div>
      )}
    </div>
  );
}

function PricePill({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70
      ? "text-green-400"
      : pct >= 40
      ? "text-yellow-400"
      : "text-red-400";
  return <span className={`text-xs font-semibold ${color}`}>{pct}¢</span>;
}
