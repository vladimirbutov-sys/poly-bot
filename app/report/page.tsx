import fs from "fs";
import path from "path";

function loadJson(filePath: string) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function analyzeSureBot(data: any) {
  if (!data) return null;
  const positions = Object.values(data.positions) as any[];
  const stats = data.stats;

  const closed = positions.filter(
    (p) => p.status !== "open" && p.status !== "cancelled" && p.pnl != null
  );
  const totalPnl = closed.reduce((s: number, p: any) => s + p.pnl, 0);
  const wins = closed.filter((p) => p.pnl > 0);
  const losses = closed.filter((p) => p.pnl <= 0);

  const catMap: Record<string, { pnl: number; n: number; wins: number }> = {};
  for (const p of closed) {
    const cat = p.category || "unknown";
    if (!catMap[cat]) catMap[cat] = { pnl: 0, n: 0, wins: 0 };
    catMap[cat].pnl += p.pnl;
    catMap[cat].n += 1;
    if (p.pnl > 0) catMap[cat].wins += 1;
  }

  const topLosses = [...closed]
    .sort((a, b) => a.pnl - b.pnl)
    .slice(0, 5)
    .map((p) => ({ title: p.title?.slice(0, 70) || "—", pnl: p.pnl, cat: p.category }));

  const topWins = [...closed]
    .sort((a, b) => b.pnl - a.pnl)
    .slice(0, 5)
    .map((p) => ({ title: p.title?.slice(0, 70) || "—", pnl: p.pnl, cat: p.category }));

  const totalCost = positions.reduce((s, p) => s + (p.cost_usd || 0), 0);
  const avgCost = totalCost / (positions.length || 1);
  const negRisk = positions.filter((p) => p.neg_risk);
  const negRiskClosed = closed.filter((p) => p.neg_risk);
  const negRiskWr = negRiskClosed.length
    ? (negRiskClosed.filter((p) => p.pnl > 0).length / negRiskClosed.length) * 100
    : 0;

  // Средняя прибыль за сделку и ROI
  const avgWin = wins.length ? wins.reduce((s, p) => s + p.pnl, 0) / wins.length : 0;
  const avgLoss = losses.length ? losses.reduce((s, p) => s + p.pnl, 0) / losses.length : 0;
  const roi = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;

  return {
    total: positions.length,
    closed: closed.length,
    open: positions.filter((p) => p.status === "open").length,
    totalPnl,
    winRate: closed.length ? (wins.length / closed.length) * 100 : 0,
    wins: wins.length,
    losses_count: losses.length,
    avgWin,
    avgLoss,
    avgCost,
    roi,
    negRiskCount: negRisk.length,
    negRiskWr,
    catMap,
    topLosses,
    topWins,
    peakBalance: stats?.peak_balance || 0,
    currentBalance: stats?.current_balance || 0,
  };
}

export default function ReportPage() {
  const surePath = path.join(process.cwd(), "data", "sure_bot_positions.json");
  const sure = analyzeSureBot(loadJson(surePath));

  return (
    <div className="space-y-12 pb-16">
      {/* Заголовок */}
      <div className="border-b border-zinc-800 pb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">98_sure_bot — Аналитика</h1>
            <p className="text-zinc-500 mt-2">
              Фактические результаты · Разбор по категориям · Рекомендации
            </p>
          </div>
          <span className="text-xs text-zinc-600 mt-1">
            {new Date().toLocaleDateString("ru-RU")}
          </span>
        </div>
      </div>

      {/* Стратегия */}
      <Section title="Стратегия" accent="green">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StratCard
            title="Принцип"
            text="Покупает исходы с ценой 96–99.5¢. Из 3 737 рынков выше 97¢ — 3 736 завершились победой. Win rate ~99.97%."
          />
          <StratCard
            title="Как работает"
            text="Сканирует все рынки Polymarket каждые 5 минут через API. Применяет 13 фильтров. Размещает лимитный ордер. Автоматически выводит выигрыш после резолюции."
          />
          <StratCard
            title="Размеры ставок"
            text="Обычный рынок: $20 · Neg-risk: $15 · Погода: $10. Макс. заморозка капитала: $1 000 одновременно."
          />
        </div>
      </Section>

      {/* KPI */}
      {sure && (
        <>
          <Section title="Ключевые показатели" accent="green">
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
              <KPI label="Всего ставок" value={sure.total.toString()} />
              <KPI label="Закрытых" value={sure.closed.toString()} />
              <KPI
                label="Win Rate"
                value={`${sure.winRate.toFixed(1)}%`}
                color="green"
              />
              <KPI
                label="Общий P&L"
                value={`+$${sure.totalPnl.toFixed(0)}`}
                color="green"
              />
              <KPI label="Avg ставка" value={`$${sure.avgCost.toFixed(1)}`} />
              <KPI
                label="ROI"
                value={`${sure.roi.toFixed(1)}%`}
                color={sure.roi > 0 ? "green" : "red"}
              />
            </div>

            <div className="grid grid-cols-3 gap-4 mt-4">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
                <p className="text-zinc-600 text-xs">Средняя прибыль / сделка</p>
                <p className="text-green-400 text-lg font-bold mt-1">+${sure.avgWin.toFixed(2)}</p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
                <p className="text-zinc-600 text-xs">Средний убыток / сделка</p>
                <p className="text-red-400 text-lg font-bold mt-1">${sure.avgLoss.toFixed(2)}</p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
                <p className="text-zinc-600 text-xs">Neg-risk позиций</p>
                <p className="text-white text-lg font-bold mt-1">
                  {sure.negRiskCount}{" "}
                  <span className="text-xs text-zinc-500 font-normal">
                    WR {sure.negRiskWr.toFixed(0)}%
                  </span>
                </p>
              </div>
            </div>
          </Section>

          {/* P&L по категориям */}
          <Section title="P&L по категориям" accent="green">
            <div className="grid grid-cols-2 gap-8">
              <div className="space-y-2">
                {Object.entries(sure.catMap)
                  .sort((a, b) => b[1].pnl - a[1].pnl)
                  .map(([cat, d]) => (
                    <CategoryRow
                      key={cat}
                      cat={cat}
                      pnl={d.pnl}
                      n={d.n}
                      wr={(d.wins / d.n) * 100}
                    />
                  ))}
              </div>

              <div className="space-y-6">
                <div>
                  <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                    Лучшие сделки
                  </h3>
                  {sure.topWins.map((t, i) => (
                    <div key={i} className="flex gap-3 py-2 border-b border-zinc-900">
                      <span className="text-green-400 font-mono text-sm shrink-0">
                        +${t.pnl.toFixed(2)}
                      </span>
                      <div>
                        <p className="text-zinc-300 text-xs">{t.title}</p>
                        <p className="text-zinc-600 text-xs">{t.cat}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div>
                  <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                    Крупнейшие потери
                  </h3>
                  {sure.topLosses.map((t, i) => (
                    <div key={i} className="flex gap-3 py-2 border-b border-zinc-900">
                      <span className="text-red-400 font-mono text-sm shrink-0">
                        ${t.pnl.toFixed(2)}
                      </span>
                      <div>
                        <p className="text-zinc-300 text-xs">{t.title}</p>
                        <p className="text-zinc-600 text-xs">{t.cat}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Section>

          {/* Рекомендации */}
          <Section title="Рекомендации по улучшению" accent="yellow">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Rec
                priority="P0"
                title="Убрать esports sub-match маркеты"
                detail="Dota 2 Map 2, Valorant Map 1 — ставки на отдельные карты/игры в серии дают убыток при 13% от всех ставок. Добавить фильтр на слова 'Game N', 'Map N', 'Set N' в названии рынка."
                impact="+$19/цикл"
                color="red"
              />
              <Rec
                priority="P0"
                title="Увеличить ставки на politics + geopolitics"
                detail="Politics: 96% WR, +$27. Geopolitics: 99% WR, +$14. Текущий средний размер $10–20 даёт низкий абсолютный P&L. Удвоение ставок в этих категориях даст +$80 без изменения логики."
                impact="×2 к P&L в этих категориях"
                color="green"
              />
              <Rec
                priority="P1"
                title="Динамический размер по entry price"
                detail="При цене 96–97¢ вероятность потери выше чем при 99¢. Логика: BET_SIZE × (entry_price − 0.96) / 0.035. Защита от редких падений на нижней границе диапазона."
                impact="Снижение avg loss"
                color="yellow"
              />
              <Rec
                priority="P1"
                title="Снизить ставки на 'other' и 'unknown'"
                detail="Категории без достаточной статистики дают убыток. Ограничить до минимального BET_SIZE ($5) пока не накопится 50+ ставок в категории."
                impact="+$9 экономии"
                color="yellow"
              />
              <Rec
                priority="P2"
                title="Учащённый polling для geopolitics"
                detail="Geopolitics маркеты (99% WR) закрываются быстро после событий. Увеличить частоту сканирования для этой категории с 300s до 60s — больше входов."
                impact="+40–60 ставок/мес"
                color="blue"
              />
              <Rec
                priority="P2"
                title="Авто-стоп при серии потерь в категории"
                detail="3 поражения подряд в одной категории = пауза на 24ч в этой категории. Предотвращает серийные убытки в периоды повышенной неопределённости."
                impact="Защита капитала"
                color="blue"
              />
            </div>
          </Section>
        </>
      )}

      {/* Следующие шаги */}
      <Section title="Следующие шаги">
        <div className="grid grid-cols-3 gap-4">
          <NextStep
            n="1"
            title="sure_bot v2 — динамический sizing"
            detail="Категорийные коэффициенты ставок + блок esports sub-match + удвоение на politics/geo"
            sprint="Backlog P0"
          />
          <NextStep
            n="2"
            title="Claude Function Calling"
            detail="Автоматический AI-анализ каждого спайка — объяснение причины движения, не только цифры"
            sprint="Sprint 8"
          />
          <NextStep
            n="3"
            title="Mobile-приложение"
            detail="React Native дашборд с пуш-уведомлениями при срабатывании алертов и резолюции позиций"
            sprint="Sprint 9"
          />
        </div>
      </Section>
    </div>
  );
}

// ─── Компоненты ───────────────────────────────────────────

function Section({
  title,
  accent,
  children,
}: {
  title: string;
  accent?: string;
  children: React.ReactNode;
}) {
  const border =
    accent === "green"
      ? "border-green-900"
      : accent === "yellow"
      ? "border-yellow-900"
      : "border-zinc-800";
  const text =
    accent === "green"
      ? "text-green-400"
      : accent === "yellow"
      ? "text-yellow-400"
      : "text-zinc-300";

  return (
    <div className={`border-l-2 ${border} pl-5`}>
      <h2 className={`text-lg font-bold ${text} mb-5`}>{title}</h2>
      {children}
    </div>
  );
}

function StratCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border border-green-900/40 bg-green-900/10 p-4 space-y-2">
      <p className="text-green-400 text-xs font-semibold uppercase tracking-wider">{title}</p>
      <p className="text-zinc-300 text-sm leading-relaxed">{text}</p>
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
      <p className={`text-xl font-bold mt-1 ${c}`}>{value}</p>
    </div>
  );
}

function CategoryRow({ cat, pnl, n, wr }: { cat: string; pnl: number; n: number; wr: number }) {
  const barColor = pnl >= 0 ? "bg-green-600" : "bg-red-600";
  const maxBar = 30;
  const barW = Math.min(Math.abs(pnl), maxBar) / maxBar;

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-zinc-400 w-28 text-xs truncate">{cat}</span>
      <div className="flex-1 bg-zinc-900 rounded h-1.5">
        <div className={`${barColor} h-1.5 rounded`} style={{ width: `${barW * 100}%` }} />
      </div>
      <span className={`w-16 text-right font-mono text-xs ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
        {pnl >= 0 ? "+" : ""}${pnl.toFixed(1)}
      </span>
      <span className="text-zinc-600 text-xs w-10 text-right">{wr.toFixed(0)}%</span>
      <span className="text-zinc-700 text-xs w-8 text-right">×{n}</span>
    </div>
  );
}

function Rec({ priority, title, detail, impact, color }: {
  priority: string; title: string; detail: string; impact: string; color: string;
}) {
  const pColor =
    color === "red"
      ? "bg-red-900/40 text-red-400 border-red-900"
      : color === "green"
      ? "bg-green-900/40 text-green-400 border-green-900"
      : color === "yellow"
      ? "bg-yellow-900/40 text-yellow-400 border-yellow-900"
      : "bg-blue-900/40 text-blue-400 border-blue-900";

  const prioColor =
    priority === "P0"
      ? "bg-red-900/60 text-red-300"
      : priority === "P1"
      ? "bg-yellow-900/60 text-yellow-300"
      : "bg-zinc-800 text-zinc-400";

  return (
    <div className={`rounded-lg border p-4 space-y-2 ${pColor}`}>
      <div className="flex items-center gap-2">
        <span className={`text-xs px-2 py-0.5 rounded font-bold ${prioColor}`}>{priority}</span>
        <p className="text-sm font-semibold text-white">{title}</p>
      </div>
      <p className="text-xs text-zinc-400 leading-relaxed">{detail}</p>
      <p className="text-xs font-semibold text-zinc-300">Эффект: {impact}</p>
    </div>
  );
}

function NextStep({ n, title, detail, sprint }: {
  n: string; title: string; detail: string; sprint: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-zinc-600 text-xs bg-zinc-800 w-6 h-6 rounded-full flex items-center justify-center font-bold">
          {n}
        </span>
        <p className="text-sm font-semibold text-white">{title}</p>
      </div>
      <p className="text-xs text-zinc-500">{detail}</p>
      <span className="text-xs text-zinc-600 bg-zinc-800 px-2 py-0.5 rounded">{sprint}</span>
    </div>
  );
}
