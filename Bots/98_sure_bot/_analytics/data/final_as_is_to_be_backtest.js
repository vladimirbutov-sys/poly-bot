/**
 * Final backtest: AS-IS vs TO-BE (negCap=$175)
 * Compares current config with proposed changes.
 * Runs detailed Monte Carlo with hourly granularity.
 */

const fs = require('fs');

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const positions = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'));
const markets = scanner.markets;

// ============= FILTERS =============

const POLITICS = new Set(['politics', 'geopolitics']);
const SPORTS = new Set(['esports', 'sports_other', 'basketball', 'hockey',
  'american_football', 'tennis', 'fighting', 'cricket', 'soccer']);
const TOXIC = [/\bearthquake/i, /\bseismic\b/i, /\bmagnitude\s+\d/i, /\btornado/i, /\btornadoes\b/i,
  /\btweets?\b/i, /\bposts?\b.*\d+-\d+/i, /\d+-\d+\s*(tweets?|posts?)/i, /\btweet\b/i, /\bretweet\b/i,
  /how\s+many.*\bpost/i, /how\s+many.*\btweet/i, /number\s+of\s+(tweets?|posts?)/i];
const SLOW = [/\btop\b/i, /\bseason\b/i, /\bmost\b/i, /\btransit\b/i, /\bstrait\b/i, /\bships?\b/i,
  /\bweekly\b/i, /\bmonthly\b/i];
const COIN_FLIP = [/\bodd\s+or\s+even\b/i, /\bodd\/even\b/i, /\bfirst\s+blood\b/i, /\bfirst\s+kill\b/i,
  /\bfirst\s+baron\b/i, /\bfirst\s+dragon\b/i, /\bfirst\s+tower\b/i, /\bcoin\s+flip\b/i, /\brampage\b/i,
  /\bfirst\s+roshan\b/i, /\bfirst\s+map\b/i, /\bup\s+or\s+down\b/i];
const FINANCIAL = [/\bbitcoin\b/i, /\bethereum\b/i, /\bsolana\b/i, /\bxrp\b/i, /\bbtc\b/i, /\beth\b/i,
  /\bs&p\s*500\b/i, /\bnasdaq\b/i, /\bcrude\s*oil\b/i, /\bgold\s*price\b/i, /\btreasury\b/i,
  /\baapl\b/i, /\bamzn\b/i, /\bgoogl\b/i, /\bmeta\b/i, /\btsla\b/i, /\bnvda\b/i,
  /\bapple\b/i, /\bamazon\b/i, /\bgoogle\b/i, /\btesla\b/i, /\bnvidia\b/i, /\bmicrostrategy\b/i];
const THRESHOLD = [/\bclose\s+above\b/i, /\bclose\s+below\b/i, /\bbe\s+above\b/i, /\bbe\s+below\b/i,
  /\breach\b.*\$[\d,]+/i, /\bhit\b.*\$[\d,]+/i];
const WEATHER = [/\btemperature\b.*\d+\s*[°]?\s*[FC]\b/i, /\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b/i];
const SPORTS_BAD = [/\bo\/u\s+\d/i, /\bover\/under\b/i, /\bspread:\s/i, /\bhandicap/i,
  /\btotal\s+(corners?|kills?|goals?|rounds?|sets?|games?|maps?|points?)\b/i,
  /\bfight\s+to\s+go\s+the\s+distance\b/i, /\bbarracks\b/i, /\broshan\b/i];

function passesFilters(m) {
  const q = m.question || '';
  const price = m.first_price || 0;
  const cat = (m.category || '').toLowerCase();

  const threshold = POLITICS.has(cat) ? 0.96 : 0.975;
  if (price < threshold || price > 0.995) return null;
  const liq = m.liquidity || 0;
  if (liq > 0 && liq < 500) return null;
  if ((m.volume || 0) < 3000) return null;
  for (const p of COIN_FLIP) if (p.test(q)) return null;
  for (const p of TOXIC) if (p.test(q)) return null;
  for (const p of SLOW) if (p.test(q)) return null;
  const isFin = FINANCIAL.some(p => p.test(q));
  const isThr = THRESHOLD.some(p => p.test(q));
  if (isFin && isThr) return null;
  for (const p of WEATHER) if (p.test(q)) return null;
  if (SPORTS.has(cat)) { for (const p of SPORTS_BAD) if (p.test(q)) return null; }

  let daysToEnd = null;
  if (m.end_date && m.first_seen) {
    daysToEnd = (new Date(m.end_date) - new Date(m.first_seen)) / (1000*60*60*24);
  }
  return { negRisk: m.neg_risk || false, daysToEnd: daysToEnd || 3, price };
}

// ============= MARKET DATA =============

const fullDates = ['2026-03-18', '2026-03-19', '2026-03-20', '2026-03-21'];
const allRegDTE = [], allNegDTE = [];

for (const [mk, m] of Object.entries(markets)) {
  const date = m.first_seen ? m.first_seen.slice(0, 10) : null;
  if (!date || !fullDates.includes(date)) continue;
  const r = passesFilters(m);
  if (!r || r.daysToEnd > 7) continue;
  (r.negRisk ? allNegDTE : allRegDTE).push(r.daysToEnd);
}

const regPerDay = allRegDTE.length / fullDates.length;
const negPerDay = allNegDTE.length / fullDates.length;

console.log('='.repeat(70));
console.log('  FINAL BACKTEST: AS-IS vs TO-BE');
console.log('='.repeat(70));
console.log(`\nMarket supply: reg=${regPerDay.toFixed(0)}/day, neg=${negPerDay.toFixed(0)}/day (end≤7d)`);

// ============= SIMULATION ENGINE =============

function sampleResolveTime(isNeg, daysToEnd) {
  if (isNeg) return 40 + Math.random() * 25; // 40-65h
  let median;
  if (daysToEnd < 1) median = 3.8;
  else if (daysToEnd < 2) median = 13.8;
  else if (daysToEnd < 3) median = 19;
  else if (daysToEnd < 5) median = 20;
  else median = 25;
  const logMed = Math.log(median);
  const sigma = 0.6;
  const u = Math.random(), v = Math.random();
  const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  return Math.max(0.5, Math.exp(logMed + sigma * z));
}

function generateMarkets(regN, negN) {
  const mkts = [];
  for (let i = 0; i < regN; i++) {
    const dte = allRegDTE[Math.floor(Math.random() * allRegDTE.length)];
    mkts.push({ isNeg: false, daysToEnd: dte, hour: Math.floor(6 + Math.random() * 16) });
  }
  for (let i = 0; i < negN; i++) {
    const dte = allNegDTE[Math.floor(Math.random() * allNegDTE.length)];
    mkts.push({ isNeg: true, daysToEnd: dte, hour: Math.floor(6 + Math.random() * 16) });
  }
  return mkts;
}

const BANKROLL = 600;
const FILL_RATE = 0.82;
const WIN_RATE = 0.992;
const DAYS = 30;
const RUNS = 50;

function runSim(config) {
  const { betReg, betNeg, negCap, sortStrategy, label } = config;

  const runResults = [];

  for (let run = 0; run < RUNS; run++) {
    let cash = BANKROLL;
    let openPos = [];
    let pnl = 0, regBets = 0, negBets = 0, skipCap = 0, skipNeg = 0;
    let wins = 0, losses = 0;
    let cashSamples = 0, cashSum = 0, regFrzSum = 0, negFrzSum = 0;
    let maxFrozen = 0;
    // Track daily PnL
    const dailyPnL = [];
    let dayPnL = 0;

    for (let day = 0; day < DAYS; day++) {
      dayPnL = 0;
      let dayMkts = generateMarkets(Math.round(regPerDay), Math.round(negPerDay));
      dayMkts = dayMkts.filter(m => m.daysToEnd <= 7);

      if (sortStrategy === 'priority_short') {
        dayMkts.sort((a, b) => a.daysToEnd - b.daysToEnd);
      }

      for (let hour = 0; hour < 24; hour++) {
        // Resolve
        const newOpen = [];
        for (const pos of openPos) {
          if (day * 24 + hour >= pos.resolveAt) {
            if (Math.random() < WIN_RATE) {
              const profit = pos.amount * 0.025;
              pnl += profit;
              dayPnL += profit;
              wins++;
            } else {
              pnl -= pos.amount;
              dayPnL -= pos.amount;
              losses++;
            }
            cash += pos.amount;
          } else {
            newOpen.push(pos);
          }
        }
        openPos = newOpen;

        // Track capital
        const regFrz = openPos.filter(p => !p.isNeg).reduce((s, p) => s + p.amount, 0);
        const negFrz = openPos.filter(p => p.isNeg).reduce((s, p) => s + p.amount, 0);
        cashSamples++;
        cashSum += cash;
        regFrzSum += regFrz;
        negFrzSum += negFrz;
        if (regFrz + negFrz > maxFrozen) maxFrozen = regFrz + negFrz;

        // Place bets
        const hourMkts = dayMkts.filter(m => m.hour === hour);
        for (const m of hourMkts) {
          if (Math.random() > FILL_RATE) continue;
          const betSize = m.isNeg ? betNeg : betReg;
          if (m.isNeg) {
            const curNeg = openPos.filter(p => p.isNeg).reduce((s, p) => s + p.amount, 0);
            if (curNeg + betSize > negCap) { skipNeg++; continue; }
          }
          if (cash < betSize) { skipCap++; continue; }
          cash -= betSize;
          if (m.isNeg) negBets++; else regBets++;
          openPos.push({
            amount: betSize,
            resolveAt: day * 24 + hour + sampleResolveTime(m.isNeg, m.daysToEnd),
            isNeg: m.isNeg, daysToEnd: m.daysToEnd
          });
        }
      }
      dailyPnL.push(dayPnL);
    }

    runResults.push({
      pnl, regBets, negBets, skipCap, skipNeg, wins, losses,
      avgCash: cashSum / cashSamples,
      avgRegFrz: regFrzSum / cashSamples,
      avgNegFrz: negFrzSum / cashSamples,
      maxFrozen,
      dailyPnL,
    });
  }

  // Aggregate
  const avg = (arr, fn) => arr.reduce((s, r) => s + fn(r), 0) / arr.length;
  const allDaily = runResults.flatMap(r => r.dailyPnL);
  allDaily.sort((a, b) => a - b);

  return {
    label,
    pnl: avg(runResults, r => r.pnl),
    regPerDay: avg(runResults, r => r.regBets) / DAYS,
    negPerDay: avg(runResults, r => r.negBets) / DAYS,
    betsPerDay: avg(runResults, r => r.regBets + r.negBets) / DAYS,
    skipCap: avg(runResults, r => r.skipCap),
    skipNeg: avg(runResults, r => r.skipNeg),
    wins: avg(runResults, r => r.wins),
    losses: avg(runResults, r => r.losses),
    winRate: avg(runResults, r => r.wins) / avg(runResults, r => r.wins + r.losses) * 100,
    avgCash: avg(runResults, r => r.avgCash),
    avgRegFrz: avg(runResults, r => r.avgRegFrz),
    avgNegFrz: avg(runResults, r => r.avgNegFrz),
    maxFrozen: avg(runResults, r => r.maxFrozen),
    dailyPnLMedian: allDaily[Math.floor(allDaily.length / 2)],
    dailyPnLP5: allDaily[Math.floor(allDaily.length * 0.05)],
    dailyPnLP95: allDaily[Math.floor(allDaily.length * 0.95)],
    worstDay: allDaily[0],
    bestDay: allDaily[allDaily.length - 1],
  };
}

// ============= CONFIGS =============

const asIs = {
  label: 'AS-IS (текущая)',
  betReg: 10, betNeg: 10, negCap: 420,
  sortStrategy: 'fifo',
};

const toBe = {
  label: 'TO-BE (новая)',
  betReg: 15, betNeg: 8, negCap: 175,
  sortStrategy: 'priority_short',
};

// Also test nearby negCap values for sensitivity
const variants = [
  { ...toBe, negCap: 100, label: 'TO-BE negCap=$100' },
  { ...toBe, negCap: 125, label: 'TO-BE negCap=$125' },
  { ...toBe, negCap: 150, label: 'TO-BE negCap=$150' },
  { ...toBe, negCap: 175, label: 'TO-BE negCap=$175 ★' },
  { ...toBe, negCap: 200, label: 'TO-BE negCap=$200' },
  { ...toBe, negCap: 250, label: 'TO-BE negCap=$250' },
  { ...toBe, negCap: 175, sortStrategy: 'fifo', label: 'TO-BE negCap=$175 FIFO' },
];

console.log(`\n${RUNS} runs × ${DAYS} days | fill=${FILL_RATE} | winRate=${WIN_RATE}\n`);

// Run AS-IS
console.log('=== AS-IS ===');
const asIsResult = runSim(asIs);

// Run TO-BE
console.log('=== TO-BE ===');
const toBeResult = runSim(toBe);

// Run variants
console.log('=== VARIANTS ===');
const varResults = variants.map(v => runSim(v));

// ============= OUTPUT =============

function printResult(r) {
  console.log(`\n--- ${r.label} ---`);
  console.log(`PnL/мес:       $${r.pnl.toFixed(1)}`);
  console.log(`ROI/мес:       ${(r.pnl / BANKROLL * 100).toFixed(1)}%`);
  console.log(`Ставок/день:   ${r.betsPerDay.toFixed(1)} (reg: ${r.regPerDay.toFixed(1)}, neg: ${r.negPerDay.toFixed(1)})`);
  console.log(`Wins: ${r.wins.toFixed(0)}, Losses: ${r.losses.toFixed(1)} | Win rate: ${r.winRate.toFixed(2)}%`);
  console.log(`Skip (капитал): ${r.skipCap.toFixed(0)}/мес | Skip (neg cap): ${r.skipNeg.toFixed(0)}/мес`);
  console.log(`Капитал средн:  free=$${r.avgCash.toFixed(0)} | regFrz=$${r.avgRegFrz.toFixed(0)} | negFrz=$${r.avgNegFrz.toFixed(0)}`);
  console.log(`Max frozen:     $${r.maxFrozen.toFixed(0)}`);
  console.log(`Daily PnL:      median=$${r.dailyPnLMedian.toFixed(2)} | P5=$${r.dailyPnLP5.toFixed(2)} | P95=$${r.dailyPnLP95.toFixed(2)}`);
  console.log(`                worst=$${r.worstDay.toFixed(2)} | best=$${r.bestDay.toFixed(2)}`);
}

printResult(asIsResult);
printResult(toBeResult);

console.log('\n' + '='.repeat(70));
console.log('  SENSITIVITY: negCap $100-$250 (all with SHORT priority, $15/$8)');
console.log('='.repeat(70));

console.log('\nnegCap | PnL/mo | ROI%  | reg/d | neg/d | SkipCap | Free$ | NegFrz$');
console.log('-'.repeat(80));

for (const r of varResults) {
  const negCap = r.label.match(/\$(\d+)/)?.[1] || '?';
  const star = r.label.includes('★') ? ' ★' : r.label.includes('FIFO') ? ' (FIFO)' : '';
  console.log(
    `  $${negCap.padStart(3)}${star.padEnd(8)} | $${r.pnl.toFixed(0).padStart(4)} | ${(r.pnl/BANKROLL*100).toFixed(1).padStart(5)}% | ${r.regPerDay.toFixed(1).padStart(5)} | ${r.negPerDay.toFixed(1).padStart(5)} | ${String(r.skipCap.toFixed(0)).padStart(7)} | $${r.avgCash.toFixed(0).padStart(4)} | $${r.avgNegFrz.toFixed(0).padStart(5)}`
  );
}

// ============= COMPARISON TABLE =============

console.log('\n' + '='.repeat(70));
console.log('  AS-IS vs TO-BE: СРАВНЕНИЕ');
console.log('='.repeat(70));

const a = asIsResult;
const b = toBeResult;

console.log('\n| Метрика | AS-IS | TO-BE | Δ |');
console.log('|---|---|---|---|');
console.log(`| BET_SIZE regular | $10 | $15 | +50% |`);
console.log(`| BET_SIZE neg_risk | $10 | $8 | -20% |`);
console.log(`| MAX_NEG_RISK_FROZEN | $420 | $175 | -58% |`);
console.log(`| Приоритизация | нет | SHORT FIRST | новое |`);
console.log(`| MAX_END_DATE_DAYS | 7 | 7 | без изменений |`);
console.log(`| PnL/мес | $${a.pnl.toFixed(0)} | $${b.pnl.toFixed(0)} | +$${(b.pnl-a.pnl).toFixed(0)} (+${((b.pnl-a.pnl)/a.pnl*100).toFixed(0)}%) |`);
console.log(`| ROI/мес | ${(a.pnl/600*100).toFixed(1)}% | ${(b.pnl/600*100).toFixed(1)}% | +${((b.pnl-a.pnl)/600*100).toFixed(1)}п.п. |`);
console.log(`| Ставок/день | ${a.betsPerDay.toFixed(1)} | ${b.betsPerDay.toFixed(1)} | ${(b.betsPerDay-a.betsPerDay)>0?'+':''}${(b.betsPerDay-a.betsPerDay).toFixed(1)} |`);
console.log(`| Regular/день | ${a.regPerDay.toFixed(1)} | ${b.regPerDay.toFixed(1)} | ${(b.regPerDay-a.regPerDay)>0?'+':''}${(b.regPerDay-a.regPerDay).toFixed(1)} |`);
console.log(`| Neg_risk/день | ${a.negPerDay.toFixed(1)} | ${b.negPerDay.toFixed(1)} | ${(b.negPerDay-a.negPerDay).toFixed(1)} |`);
console.log(`| Пропуски (капитал)/мес | ${a.skipCap.toFixed(0)} | ${b.skipCap.toFixed(0)} | ${(b.skipCap-a.skipCap).toFixed(0)} |`);
console.log(`| Свободный капитал (средн) | $${a.avgCash.toFixed(0)} | $${b.avgCash.toFixed(0)} | +$${(b.avgCash-a.avgCash).toFixed(0)} |`);
console.log(`| Заморожено в neg_risk | $${a.avgNegFrz.toFixed(0)} | $${b.avgNegFrz.toFixed(0)} | -$${(a.avgNegFrz-b.avgNegFrz).toFixed(0)} |`);
console.log(`| Заморожено в regular | $${a.avgRegFrz.toFixed(0)} | $${b.avgRegFrz.toFixed(0)} | +$${(b.avgRegFrz-a.avgRegFrz).toFixed(0)} |`);
console.log(`| Worst day | $${a.worstDay.toFixed(2)} | $${b.worstDay.toFixed(2)} | |`);
console.log(`| Best day | $${a.bestDay.toFixed(2)} | $${b.bestDay.toFixed(2)} | |`);
console.log(`| Median day PnL | $${a.dailyPnLMedian.toFixed(2)} | $${b.dailyPnLMedian.toFixed(2)} | +$${(b.dailyPnLMedian-a.dailyPnLMedian).toFixed(2)} |`);

// Save
const output = {
  timestamp: new Date().toISOString(),
  config: { BANKROLL, FILL_RATE, WIN_RATE, DAYS, RUNS },
  marketSupply: { regPerDay, negPerDay },
  asIs: { config: asIs, result: asIsResult },
  toBe: { config: toBe, result: toBeResult },
  variants: varResults.map((r, i) => ({ config: variants[i], result: r })),
};
fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/final_as_is_to_be_2026-03-22.json',
  JSON.stringify(output, null, 2));
console.log('\nData saved.');
