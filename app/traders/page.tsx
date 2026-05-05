import { supabase } from "@/lib/supabase";

async function getTraders() {
  const { data } = await supabase
    .from("good_traders")
    .select("*")
    .order("war_pnl", { ascending: false })
    .limit(50);
  return data ?? [];
}

export default async function TradersPage() {
  const traders = await getTraders();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Smart Money</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Top war market traders · scored by P&amp;L and trade count
        </p>
      </div>

      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500 text-xs bg-zinc-900/50">
              <th className="px-4 py-3 text-left w-8">#</th>
              <th className="px-4 py-3 text-left">Wallet</th>
              <th className="px-4 py-3 text-left">Username</th>
              <th className="px-4 py-3 text-right">War P&amp;L</th>
              <th className="px-4 py-3 text-right">ROI</th>
              <th className="px-4 py-3 text-right">Trades</th>
              <th className="px-4 py-3 text-left">Category</th>
            </tr>
          </thead>
          <tbody>
            {traders.map((t, i) => (
              <tr key={t.wallet} className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors">
                <td className="px-4 py-3 text-zinc-600 text-xs">{i + 1}</td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-400">
                  {t.wallet ? `${t.wallet.slice(0, 6)}...${t.wallet.slice(-4)}` : "—"}
                </td>
                <td className="px-4 py-3 text-zinc-300">
                  {t.username ? (
                    <span className="text-blue-400">@{t.username}</span>
                  ) : (
                    <span className="text-zinc-600">anonymous</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right font-mono font-semibold">
                  <span className={t.war_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                    {t.war_pnl >= 0 ? "+" : ""}${t.war_pnl?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-zinc-400 font-mono text-xs">
                  {t.roi != null ? `${t.roi.toFixed(0)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-right text-zinc-400">{t.war_trades_count ?? "—"}</td>
                <td className="px-4 py-3">
                  <CategoryBadge category={t.category} />
                </td>
              </tr>
            ))}
            {traders.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-zinc-600">
                  No traders yet — run the ETL script to sync data
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CategoryBadge({ category }: { category?: string }) {
  const map: Record<string, string> = {
    iran: "bg-red-900/40 text-red-400",
    ukraine: "bg-yellow-900/40 text-yellow-400",
    china: "bg-orange-900/40 text-orange-400",
  };
  const cls = map[category?.toLowerCase() ?? ""] ?? "bg-zinc-800 text-zinc-500";
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>
      {category ?? "—"}
    </span>
  );
}
