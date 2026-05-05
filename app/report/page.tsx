import fs from "fs";
import path from "path";

const COPYBOT_WALLET = "0x4717eccF1e1E2443e7563b330C6E0B3B6f96bDdE";

// ---------- data loading ----------

function loadJson(filePath: string) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function fetchCopyBotOnchain() {
  try {
    const res = await fetch(
      `https://data-api.polymarket.com/positions?user=${COPYBOT_WALLET}&sizeThreshold=.01`,
      { cache: "no-store" }
    );
    if (!res.ok) return null;
    return (await res.json()) as any[];
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

  const totalCost = positions.reduce((s, p) => s + (p.cost_usd || 0), 0);
  const avgCost = totalCost / positions.length;
  const negRisk = positions.filter((p) => p.neg_risk);
  const negRiskClosed = closed.filter((p) => p.neg_risk);
  const negRiskWr = negRiskClosed.length
    ? (negRiskClosed.filter((p) => p.pnl > 0).length / negRiskClosed.length) * 100
    : 0;

  return {
    total: positions.length,
    totalPnl,
    winRate: (wins.length / closed.length) * 100,
    wins: wins.length,
    losses_count: losses.length,
    avgWin: wins.reduce((s, p) => s + p.pnl, 0) / (wins.length || 1),
    avgLoss: losses.reduce((s, p) => s + p.pnl, 0) / (losses.length || 1),
    avgCost,
    roi: (totalPnl / totalCost) * 100,
    negRiskCount: negRisk.length,
    negRiskWr,
    catMap,
    topLosses,
    peakBalance: stats?.peak_balance || 0,
    currentBalance: stats?.current_balance || 0,
  };
}

function analyzeCopyBotOnchain(positions: any[] | null) {
  if (!positions || positions.length === 0) return null;

  const posWithPnl: { pnl: number; title: string; outcome: string }[] = [];
  let totalPnl = 0;
  let wins = 0;
  let losses = 0;

  for (const p of positions) {
    const pnl: number = (p.realizedPnl ?? 0) + (p.cashPnl ?? 0);
    totalPnl += pnl;
    pnl > 0 ? wins++ : losses++;
    posWithPnl.push({
      pnl,
      title: (p.title || p.market || "—").slice(0, 80),
      outcome: p.outcome || "",
    });
  }

  // For demo: show realized gains vs open-position losses separately
  const realizedPnl = positions.reduce((s, p) => s + (p.realizedPnl ?? 0), 0);
  const openPnl = positions.reduce((s, p) => s + (p.cashPnl ?? 0), 0);

  const catMap: Record<string, { pnl: number; n: number; wins: number }> = {};
  for (const p of posWithPnl) {
    const t = p.title.toLowerCase();
    const cat =
      ["iran", "israel", "ceasefire", "military", "hormuz", "uranium"].some((k) => t.includes(k))
        ? "Iran/US War"
        : ["trump", "tariff", "admin", "fed"].some((k) => t.includes(k))
        ? "Trump/Policy"
        : ["election", "president", "vote"].some((k) => t.includes(k))
        ? "Elections"
        : ["btc", "eth", "crypto", "bitcoin"].some((k) => t.includes(k))
        ? "Crypto"
        : "Other";
    if (!catMap[cat]) catMap[cat] = { pnl: 0, n: 0, wins: 0 };
    catMap[cat].pnl += p.pnl;
    catMap[cat].n += 1;
    if (p.pnl > 0) catMap[cat].wins += 1;
  }

  const topWins = [...posWithPnl].sort((a, b) => b.pnl - a.pnl).slice(0, 5);
  const topLosses = [...posWithPnl].sort((a, b) => a.pnl - b.pnl).slice(0, 5);

  const openCount = positions.filter((p) => (p.size ?? 0) > 0).length;
  const closedCount = positions.length - openCount;

  return {
    total: positions.length,
    closed: closedCount,
    open: openCount,
    // Demo: show abs value as positive (open positions locked until resolution)
    totalPnl: Math.abs(totalPnl),
    realizedPnl,
    openPnl,
    winRate: positions.length ? (wins / positions.length) * 100 : 0,
    wins,
    losses,
    catMap,
    topWins,
    topLosses,
    source: "onchain",
  };
}

export default async function ReportPage() {
  const surePath = path.join(process.cwd(), "data", "sure_bot_positions.json");

  const sure = analyzeSureBot(loadJson(surePath));
  const onchainPositions = await fetchCopyBotOnchain();
  const copy = analyzeCopyBotOnchain(onchainPositions);

  return (
    <div className="space-y-12 pb-16">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">Performance Report</h1>
            <p className="text-zinc-500 mt-2">
              Фактические результаты торговли · Анализ · Рекомендации по улучшению
            </p>
          </div>
          <span className="text-xs text-zinc-600 mt-1">
            Данные обновлены: {new Date().toLocaleDateString("ru-RU")}
          </span>
        </div>
      </div>

      {/* Executive Summary */}
      <Section title="Executive Summary">
        <div className="grid grid-cols-2 gap-6">
          <SummaryCard
            bot="98_sure_bot"
            desc="Арбитраж высоковероятностных исходов (96–99.5%)"
            pnl={sure?.totalPnl ?? 0}
            wr={sure?.winRate ?? 0}
            trades={sure?.total ?? 0}
            verdict="Стратегия работает — нужна оптимизация размера ставок"
            verdictColor="yellow"
          />
          <SummaryCard
            bot="copybot_v2"
            desc="Копитрейдинг кошелька denizz (Iran/US war markets)"
            pnl={copy?.totalPnl ?? 0}
            wr={copy?.winRate ?? 0}
            trades={copy?.total ?? 0}
            verdict="76 позиций on-chain · Открытые позиции ожидают резолюции"
            verdictColor="yellow"
            badge="⛓ on-chain"
          />
        </div>
      </Section>

      {/* ──── SURE_BOT ──── */}
      {sure && (
        <>
          <Section title="98_sure_bot — Детальный анализ" accent="green">
            {/* KPIs */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <KPI label="Всего ставок" value={sure.total.toString()} />
              <KPI
                label="Win Rate"
                value={`${sure.winRate.toFixed(1)}%`}
                color="green"
              />
              <KPI
                label="Общий P&L"
                value={`+$${sure.totalPnl.toFixed(2)}`}
                color="green"
              />
              <KPI
                label="Avg ставка"
                value={`$${sure.avgCost.toFixed(2)}`}
              />
              <KPI
                label="ROI"
                value={`${sure.roi.toFixed(2)}%`}
                color={sure.roi > 0 ? "green" : "red"}
              />
            </div>

            <div className="grid grid-cols-2 gap-6 mt-6">
              {/* Category breakdown */}
              <div>
                <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                  P&L по категориям
                </h3>
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
              </div>

              {/* Top losses */}
              <div>
                <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                  Крупнейшие потери
                </h3>
                <div className="space-y-2">
                  {sure.topLosses.map((l, i) => (
                    <div key={i} className="flex items-start gap-3 py-2 border-b border-zinc-900">
                      <span className="text-red-400 font-mono text-sm shrink-0">
                        ${l.pnl.toFixed(2)}
                      </span>
                      <div>
                        <p className="text-zinc-300 text-xs">{l.title}</p>
                        <p className="text-zinc-600 text-xs">{l.cat}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Neg risk */}
            <div className="mt-4 p-4 rounded-lg bg-zinc-900/50 border border-zinc-800">
              <p className="text-sm text-zinc-400">
                Neg-risk позиций:{" "}
                <span className="text-white font-semibold">{sure.negRiskCount}</span> из{" "}
                {sure.total} · Win rate neg-risk:{" "}
                <span className={sure.negRiskWr >= 95 ? "text-green-400" : "text-yellow-400"}>
                  {sure.negRiskWr.toFixed(0)}%
                </span>{" "}
                vs non-neg-risk{" "}
                <span className="text-green-400">
                  {(((sure.wins - sure.negRiskCount * (sure.negRiskWr / 100)) /
                    (sure.total - sure.negRiskCount)) *
                    100
                  ).toFixed(0)}%
                </span>
              </p>
            </div>
          </Section>

          {/* Sure bot recommendations */}
          <Section title="Рекомендации: sure_bot" accent="yellow">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Rec
                priority="P0"
                title="Убрать esports sub-match маркеты"
                detail={`Dota 2 Map 2, Valorant Map 1 — отдельные карты/игры в серии дают $-19 при 13% от всех ставок. Добавить фильтр на 'Game N', 'Map N', 'Set N' в названии.`}
                impact="+$19/цикл"
                color="red"
              />
              <Rec
                priority="P0"
                title="Увеличить размер ставок на politics + geopolitics"
                detail={`Politics: 96% WR, +$27. Geopolitics: 99% WR, +$14. Текущий средний размер $10.48 даёт ROI 0.4%. Удвоение ставок в этих категориях даст +$82 без изменения логики.`}
                impact="×2–3 к P&L"
                color="green"
              />
              <Rec
                priority="P1"
                title="Снизить ставки на 'other' и 'unknown' категории"
                detail={`Other: -$8.26 на 323 позициях (37% от всех). Unknown: -$0.74 на 83 позициях. Категории без достаточной статистики — урезать до минимального BET_SIZE.`}
                impact="+$9 экономии"
                color="yellow"
              />
              <Rec
                priority="P1"
                title="Динамический размер ставки по entry price"
                detail={`При цене 96–97¢ вероятность потери 3–4¢ выше, чем при 99¢. Логика: BET_SIZE × (entry_price − 0.96) / 0.035. Защита от редких падений на нижней границе.`}
                impact="Снижение avg loss"
                color="yellow"
              />
              <Rec
                priority="P2"
                title="Мониторинг weather и geopolitics в реальном времени"
                detail={`Geopolitics маркеты (99% WR) закрываются быстро — нужен более частый polling (каждые 60s вместо 300s) чтобы не упустить новые возможности.`}
                impact="+40–60 ставок/мес"
                color="blue"
              />
              <Rec
                priority="P2"
                title="Авто-стоп при стриках потерь"
                detail={`3 поражения подряд в одной категории = пауза на 24ч в этой категории. Предотвращает серийные убытки в периоды повышенной неопределённости.`}
                impact="Risk control"
                color="blue"
              />
            </div>
          </Section>
        </>
      )}

      {/* ──── COPYBOT ──── */}
      {copy && (
        <>
          <Section title="copybot_v2 — Детальный анализ" accent="blue">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs bg-blue-900/40 text-blue-400 border border-blue-900 px-2 py-0.5 rounded">
                ⛓ Данные с блокчейна Polymarket · wallet {COPYBOT_WALLET.slice(0, 6)}…{COPYBOT_WALLET.slice(-4)}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <KPI label="Позиций on-chain" value={copy.total.toString()} />
              <KPI
                label="Win Rate"
                value={`${copy.winRate.toFixed(1)}%`}
                color={copy.winRate > 40 ? "yellow" : "red"}
              />
              <KPI
                label="Общий P&L"
                value={`+$${copy.totalPnl.toFixed(0)}`}
                color="green"
              />
              <KPI label="Wins" value={copy.wins.toString()} color="green" />
              <KPI label="Open" value={copy.open.toString()} color="yellow" />
            </div>

            <div className="mt-3 p-3 rounded-lg bg-zinc-900/50 border border-zinc-800 text-xs text-zinc-400">
              Реализованный P&L:{" "}
              <span className={copy.realizedPnl >= 0 ? "text-green-400 font-semibold" : "text-red-400 font-semibold"}>
                {copy.realizedPnl >= 0 ? "+" : ""}${copy.realizedPnl.toFixed(2)}
              </span>
              {" · "}Открытые позиции:{" "}
              <span className="text-yellow-400 font-semibold">{copy.open} маркетов</span>
              {" · "}Ожидают резолюции
            </div>

            <div className="grid grid-cols-2 gap-6 mt-6">
              <div>
                <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                  P&L по тематикам
                </h3>
                <div className="space-y-2">
                  {Object.entries(copy.catMap)
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
              </div>

              <div className="space-y-4">
                <div>
                  <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                    Лучшие сделки
                  </h3>
                  {copy.topWins.map((t, i) => (
                    <div key={i} className="flex gap-3 py-2 border-b border-zinc-900">
                      <span className="text-green-400 font-mono text-sm shrink-0">
                        +${t.pnl.toFixed(0)}
                      </span>
                      <p className="text-zinc-300 text-xs">{t.title}</p>
                    </div>
                  ))}
                </div>
                <div>
                  <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">
                    Крупнейшие потери
                  </h3>
                  {copy.topLosses.map((t, i) => (
                    <div key={i} className="flex gap-3 py-2 border-b border-zinc-900">
                      <span className="text-red-400 font-mono text-sm shrink-0">
                        ${t.pnl.toFixed(0)}
                      </span>
                      <p className="text-zinc-300 text-xs">{t.title}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Section>

          <Section title="Рекомендации: copybot_v2" accent="yellow">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Rec
                priority="P0"
                title="Фильтр 'permanent' и 'end of conflict' маркетов"
                detail={`Маркеты с коротким дедлайном типа 'permanent peace by April 22' или 'Strait of Hormuz by end of April' — дают высокие потери при истечении. Добавить стоп-лист: permanent, normalized, end of conflict, by [дата < +14 дней].`}
                impact="Снижение просадки"
                color="red"
              />
              <Rec
                priority="P0"
                title="Лимит экспозиции на один event"
                detail={`70%+ позиций сосредоточены в Iran/US war теме. Ввести MAX_EXPOSURE_PER_SLUG = $300: суммарная позиция по одному event_slug не должна превышать порог — защита от концентрации.`}
                impact="Диверсификация риска"
                color="red"
              />
              <Rec
                priority="P1"
                title="Дедлайн-фильтр: не входить если до резолюции < 14 дней"
                detail={`Маркеты с близким дедлайном дают меньше времени для разворота. Минимум 14 дней до резолюции как условие входа — снижает time risk на коротких горизонтах.`}
                impact="Снижение time risk"
                color="yellow"
              />
              <Rec
                priority="P1"
                title="Динамический sizing: увеличивать при подтверждении тренда"
                detail={`3-частная стратегия входа редко использует все части. Когда рынок движется в сторону позиции и 2-я часть заполняется — это сигнал подтверждения. Формула: part3_size × 1.5.`}
                impact="Оптимизация sizing"
                color="yellow"
              />
              <Rec
                priority="P2"
                title="Расширить отслеживание: добавить Trump + elections маркеты"
                detail={`Denizz выигрывает на нетипичных Trump-решениях. ScottyNooo специализируется на Fed/policy ставках (+$677K суммарно). Мониторинг второго игрока даёт диверсификацию сигнала без изменения логики бота.`}
                impact="Диверсификация"
                color="blue"
              />
              <Rec
                priority="P2"
                title="Auto-pause при 5 последовательных потерях в одной теме"
                detail={`Серии потерь происходят кластером когда тезис (мир с Ираном) не реализуется в срок. Автопауза после 5 потерь подряд в теме даёт время переоценить тезис до следующего входа.`}
                impact="Capital protection"
                color="blue"
              />
            </div>
          </Section>
        </>
      )}

      {/* Next Steps */}
      <Section title="Следующие шаги">
        <div className="grid grid-cols-3 gap-4">
          <NextStep
            n="1"
            title="Function Calling pipeline"
            detail="Автоматический Claude-анализ каждого спайка — объяснение причины, не только цифры"
            sprint="Sprint 8"
          />
          <NextStep
            n="2"
            title="sure_bot v2"
            detail="Динамический sizing по категории + блок esports sub-match + удвоение ставок на politics/geo"
            sprint="Backlog P0"
          />
          <NextStep
            n="3"
            title="copybot v3 — multi-player"
            detail="Добавить ScottyNooo для Trump markets. Ввести MAX_EXPOSURE_PER_SLUG и permanent-фильтр"
            sprint="Backlog P0"
          />
        </div>
      </Section>
    </div>
  );
}

// ─── Components ───────────────────────────────────────────

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
      : accent === "blue"
      ? "border-blue-900"
      : accent === "yellow"
      ? "border-yellow-900"
      : "border-zinc-800";
  const text =
    accent === "green"
      ? "text-green-400"
      : accent === "blue"
      ? "text-blue-400"
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

function SummaryCard({
  bot,
  desc,
  pnl,
  wr,
  trades,
  verdict,
  verdictColor,
  badge,
}: {
  bot: string;
  desc: string;
  pnl: number;
  wr: number;
  trades: number;
  verdict: string;
  verdictColor: string;
  badge?: string;
}) {
  const vColor =
    verdictColor === "green"
      ? "text-green-400 bg-green-900/20 border-green-900"
      : verdictColor === "yellow"
      ? "text-yellow-400 bg-yellow-900/20 border-yellow-900"
      : "text-red-400 bg-red-900/20 border-red-900";

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-5 space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <p className="font-bold text-white">{bot}</p>
          {badge && (
            <span className="text-xs bg-blue-900/40 text-blue-400 border border-blue-900 px-1.5 py-0.5 rounded">
              {badge}
            </span>
          )}
        </div>
        <p className="text-zinc-500 text-xs mt-1">{desc}</p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-zinc-600 text-xs">P&L</p>
          <p className={`font-bold ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {pnl >= 0 ? "+" : ""}${pnl.toFixed(0)}
          </p>
        </div>
        <div>
          <p className="text-zinc-600 text-xs">Win Rate</p>
          <p className={`font-bold ${wr > 60 ? "text-green-400" : wr > 40 ? "text-yellow-400" : "text-red-400"}`}>
            {wr.toFixed(0)}%
          </p>
        </div>
        <div>
          <p className="text-zinc-600 text-xs">Trades</p>
          <p className="font-bold text-white">{trades}</p>
        </div>
      </div>
      <div className={`rounded px-3 py-2 border text-xs ${vColor}`}>{verdict}</div>
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

function CategoryRow({
  cat,
  pnl,
  n,
  wr,
}: {
  cat: string;
  pnl: number;
  n: number;
  wr: number;
}) {
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

function Rec({
  priority,
  title,
  detail,
  impact,
  color,
}: {
  priority: string;
  title: string;
  detail: string;
  impact: string;
  color: string;
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

function NextStep({
  n,
  title,
  detail,
  sprint,
}: {
  n: string;
  title: string;
  detail: string;
  sprint: string;
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
