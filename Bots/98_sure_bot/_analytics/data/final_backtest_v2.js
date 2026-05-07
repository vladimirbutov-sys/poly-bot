/**
 * FINAL BACKTEST v2: AS-IS vs TO-BE
 * Uses REAL resolve times from scanner_data.json (19K markets) filtered by bot criteria.
 * Fixes the key flaw: previous simulations used resolve times from bot's 36 neg_risk positions
 * instead of 4,168 from scanner.
 */
const fs = require('fs');

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const markets = scanner.markets;

// ============= FILTERS (same as 98_sure_bot) =============

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
  if (FINANCIAL.some(p => p.test(q)) && THRESHOLD.some(p => p.test(q))) return null;
  for (const p of WEATHER) if (p.test(q)) return null;
  if (SPORTS.has(cat)) { for (const p of SPORTS_BAD) if (p.test(q)) return null; }
  return { negRisk: m.neg_risk || false, daysToEnd: m.days_to_end || 3, price, cat };
}

// ============= EXTRACT REAL RESOLVE TIMES =============

console.log('='.repeat(70));
console.log('  FINAL BACKTEST v2: Real resolve times from 19K scanner markets');
console.log('='.repeat(70));

// Step 1: Get all resolved markets that pass bot's filters
const filteredResolved = { reg: [], neg: [] };
const filteredAll = { reg: [], neg: [] };
const fullDates = ['2026-03-18', '2026-03-19', '2026-03-20', '2026-03-21'];
let totalResolved = 0, totalFiltered = 0;
let regWins = 0, regLosses = 0, negWins = 0, negLosses = 0;

for (const [cid, m] of Object.entries(markets)) {
  const r = passesFilters(m);
  if (!r) continue;
  if (r.daysToEnd > 7) continue; // end_date <= 7d

  const type = r.negRisk ? 'neg' : 'reg';

  // Count daily supply
  const date = m.first_seen ? m.first_seen.slice(0, 10) : null;
  if (date && fullDates.includes(date)) {
    filteredAll[type].push({ daysToEnd: r.daysToEnd, cat: r.cat, price: r.price });
  }

  // Collect resolve times
  if (m.resolved && m.resolve_time_hours != null && m.resolve_time_hours > 0) {
    totalResolved++;
    filteredResolved[type].push({
      rt: m.resolve_time_hours,
      dte: r.daysToEnd,
      cat: r.cat,
      won: m.high_outcome_won === true,
    });
    if (r.negRisk) {
      if (m.high_outcome_won === true) negWins++; else negLosses++;
    } else {
      if (m.high_outcome_won === true) regWins++; else regLosses++;
    }
  }
}

const regPerDay = filteredAll.reg.length / fullDates.length;
const negPerDay = filteredAll.neg.length / fullDates.length;

console.log(`\n=== FILTERED MARKET SUPPLY (bot's filters, end≤7d) ===`);
console.log(`Regular: ${regPerDay.toFixed(1)}/day (${filteredAll.reg.length} over ${fullDates.length} days)`);
console.log(`Neg_risk: ${negPerDay.toFixed(1)}/day (${filteredAll.neg.length} over ${fullDates.length} days)`);

console.log(`\n=== FILTERED RESOLVE TIMES (bot's filters applied to scanner) ===`);
console.log(`Regular resolved: ${filteredResolved.reg.length} (${regWins}W/${regLosses}L = ${(regWins/(regWins+regLosses)*100).toFixed(2)}% WR)`);
console.log(`Neg_risk resolved: ${filteredResolved.neg.length} (${negWins}W/${negLosses}L = ${(negWins/(negWins+negLosses)*100).toFixed(2)}% WR)`);

// Sort and show stats
function showStats(label, arr) {
  if (!arr.length) { console.log(`  ${label}: no data`); return; }
  const sorted = [...arr].sort((a, b) => a - b);
  const n = sorted.length;
  console.log(`  ${label} (n=${n}): median=${sorted[Math.floor(n/2)].toFixed(1)}h, P25=${sorted[Math.floor(n*0.25)].toFixed(1)}h, P75=${sorted[Math.floor(n*0.75)].toFixed(1)}h, min=${sorted[0].toFixed(1)}h, max=${sorted[n-1].toFixed(1)}h`);
}

showStats('Regular', filteredResolved.reg.map(x => x.rt));
showStats('Neg_risk', filteredResolved.neg.map(x => x.rt));

// By days_to_end bucket
const buckets = [[0,1,'0-1d'],[1,2,'1-2d'],[2,3,'2-3d'],[3,5,'3-5d'],[5,7,'5-7d']];
console.log('\n  Resolve time by days_to_end (FILTERED):');
console.log('  ' + 'Bucket'.padEnd(8) + '| Reg n | Reg med  | Neg n | Neg med');
console.log('  ' + '-'.repeat(55));
for (const [lo, hi, name] of buckets) {
  const regB = filteredResolved.reg.filter(x => x.dte >= lo && x.dte < hi).map(x => x.rt).sort((a,b)=>a-b);
  const negB = filteredResolved.neg.filter(x => x.dte >= lo && x.dte < hi).map(x => x.rt).sort((a,b)=>a-b);
  const regMed = regB.length ? regB[Math.floor(regB.length/2)].toFixed(1) + 'h' : '-';
  const negMed = negB.length ? negB[Math.floor(negB.length/2)].toFixed(1) + 'h' : '-';
  console.log(`  ${name.padEnd(8)}| ${String(regB.length).padStart(5)} | ${regMed.padStart(8)} | ${String(negB.length).padStart(5)} | ${negMed.padStart(7)}`);
}

// By category
console.log('\n  Resolve time by category (FILTERED):');
console.log('  ' + 'Category'.padEnd(20) + '| n    | Median   | WR');
console.log('  ' + '-'.repeat(50));
const catStats = {};
for (const x of [...filteredResolved.reg, ...filteredResolved.neg]) {
  if (!catStats[x.cat]) catStats[x.cat] = { rts: [], wins: 0, total: 0 };
  catStats[x.cat].rts.push(x.rt);
  catStats[x.cat].total++;
  if (x.won) catStats[x.cat].wins++;
}
for (const [cat, s] of Object.entries(catStats).sort((a,b) => b[1].rts.length - a[1].rts.length)) {
  const med = [...s.rts].sort((a,b)=>a-b)[Math.floor(s.rts.length/2)];
  const wr = (s.wins / s.total * 100).toFixed(1);
  console.log(`  ${cat.padEnd(20)}| ${String(s.rts.length).padStart(4)} | ${med.toFixed(1).padStart(7)}h | ${wr}%`);
}

// ============= BUILD RESOLVE TIME DISTRIBUTIONS =============
// Use actual resolve times from filtered scanner data for sampling

const regRTs = filteredResolved.reg.map(x => x.rt);
const negRTs = filteredResolved.neg.map(x => x.rt);

function sampleRT(isNeg) {
  const pool = isNeg ? negRTs : regRTs;
  if (!pool.length) return isNeg ? 30 : 3; // fallback
  return pool[Math.floor(Math.random() * pool.length)];
}

// Win rates from filtered scanner
const regWR = regWins / (regWins + regLosses);
const negWR = negWins / (negWins + negLosses);
console.log(`\nWin rates for simulation: reg=${(regWR*100).toFixed(2)}%, neg=${(negWR*100).toFixed(2)}%`);

// ============= MONTE CARLO =============

const BANKROLL = 600;
const FILL_RATE = 0.82;
const DAYS = 30;
const RUNS = 50;

function generateMarkets(regN, negN) {
  const mkts = [];
  const regDTEs = filteredAll.reg.map(x => x.daysToEnd);
  const negDTEs = filteredAll.neg.map(x => x.daysToEnd);
  for (let i = 0; i < regN; i++) {
    mkts.push({ isNeg: false, daysToEnd: regDTEs[Math.floor(Math.random() * regDTEs.length)] || 1, hour: Math.floor(6 + Math.random() * 16) });
  }
  for (let i = 0; i < negN; i++) {
    mkts.push({ isNeg: true, daysToEnd: negDTEs[Math.floor(Math.random() * negDTEs.length)] || 2, hour: Math.floor(6 + Math.random() * 16) });
  }
  return mkts;
}

function runSim(config) {
  const { betReg, betNeg, negCap, sortStrategy, label } = config;
  const runResults = [];

  for (let run = 0; run < RUNS; run++) {
    let cash = BANKROLL;
    let openPos = [];
    let pnl = 0, regBets = 0, negBets = 0, skipCap = 0, skipNeg = 0;
    let wins = 0, losses = 0;
    let cashSamples = 0, cashSum = 0, regFrzSum = 0, negFrzSum = 0;
    const dailyPnL = [];

    for (let day = 0; day < DAYS; day++) {
      let dayPnL = 0;
      let dayMkts = generateMarkets(Math.round(regPerDay), Math.round(negPerDay));
      if (sortStrategy === 'priority_short') dayMkts.sort((a, b) => a.daysToEnd - b.daysToEnd);

      for (let hour = 0; hour < 24; hour++) {
        // Resolve
        const newOpen = [];
        for (const pos of openPos) {
          if (day * 24 + hour >= pos.resolveAt) {
            const wr = pos.isNeg ? negWR : regWR;
            if (Math.random() < wr) {
              const profit = pos.amount * (1 / pos.price - 1); // actual profit = shares * (1 - price)
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

        // Track frozen
        const regFrz = openPos.filter(p => !p.isNeg).reduce((s, p) => s + p.amount, 0);
        const negFrz = openPos.filter(p => p.isNeg).reduce((s, p) => s + p.amount, 0);
        cashSamples++;
        cashSum += cash;
        regFrzSum += regFrz;
        negFrzSum += negFrz;

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

          // Sample from real resolve time distribution
          const resolveH = sampleRT(m.isNeg);
          // Sample a realistic price for profit calculation
          const pricePool = m.isNeg ? filteredAll.neg : filteredAll.reg;
          const price = pricePool.length ? pricePool[Math.floor(Math.random() * pricePool.length)].price : 0.98;

          openPos.push({
            amount: betSize, resolveAt: day * 24 + hour + resolveH,
            isNeg: m.isNeg, daysToEnd: m.daysToEnd, price,
          });
        }
      }
      dailyPnL.push(dayPnL);
    }
    runResults.push({ pnl, regBets, negBets, skipCap, skipNeg, wins, losses,
      avgCash: cashSum / cashSamples, avgRegFrz: regFrzSum / cashSamples, avgNegFrz: negFrzSum / cashSamples, dailyPnL });
  }

  const avg = (fn) => runResults.reduce((s, r) => s + fn(r), 0) / RUNS;
  const allDaily = runResults.flatMap(r => r.dailyPnL).sort((a, b) => a - b);
  return {
    label, pnl: avg(r => r.pnl), regPerDay: avg(r => r.regBets) / DAYS,
    negPerDay: avg(r => r.negBets) / DAYS, betsPerDay: avg(r => r.regBets + r.negBets) / DAYS,
    skipCap: avg(r => r.skipCap), skipNeg: avg(r => r.skipNeg),
    wins: avg(r => r.wins), losses: avg(r => r.losses),
    winRate: avg(r => r.wins) / (avg(r => r.wins) + avg(r => r.losses)) * 100,
    avgCash: avg(r => r.avgCash), avgRegFrz: avg(r => r.avgRegFrz), avgNegFrz: avg(r => r.avgNegFrz),
    dailyMedian: allDaily[Math.floor(allDaily.length / 2)],
    dailyP5: allDaily[Math.floor(allDaily.length * 0.05)],
    dailyP95: allDaily[Math.floor(allDaily.length * 0.95)],
    worstDay: allDaily[0], bestDay: allDaily[allDaily.length - 1],
  };
}

// ============= RUN ALL CONFIGS =============

console.log('\n' + '='.repeat(70));
console.log(`  MONTE CARLO: ${RUNS} runs × ${DAYS} days | fill=${FILL_RATE}`);
console.log('='.repeat(70));

const configs = [
  // AS-IS
  { label: 'AS-IS ($10/$10, neg420, FIFO)', betReg: 10, betNeg: 10, negCap: 420, sortStrategy: 'fifo' },
  { label: 'AS-IS + SHORT PRIO', betReg: 10, betNeg: 10, negCap: 420, sortStrategy: 'priority_short' },

  // TO-BE candidate: negCap=$175
  { label: 'TO-BE ($15/$8, neg175, SHORT)', betReg: 15, betNeg: 8, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'TO-BE FIFO', betReg: 15, betNeg: 8, negCap: 175, sortStrategy: 'fifo' },

  // Sensitivity: negCap
  { label: 'negCap=$0 (no neg)', betReg: 15, betNeg: 8, negCap: 0, sortStrategy: 'priority_short' },
  { label: 'negCap=$50', betReg: 15, betNeg: 8, negCap: 50, sortStrategy: 'priority_short' },
  { label: 'negCap=$100', betReg: 15, betNeg: 8, negCap: 100, sortStrategy: 'priority_short' },
  { label: 'negCap=$150', betReg: 15, betNeg: 8, negCap: 150, sortStrategy: 'priority_short' },
  { label: 'negCap=$175 ★', betReg: 15, betNeg: 8, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'negCap=$200', betReg: 15, betNeg: 8, negCap: 200, sortStrategy: 'priority_short' },
  { label: 'negCap=$250', betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'priority_short' },
  { label: 'negCap=$350', betReg: 15, betNeg: 8, negCap: 350, sortStrategy: 'priority_short' },

  // Sensitivity: bet size
  { label: 'betReg=$10', betReg: 10, betNeg: 8, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'betReg=$12', betReg: 12, betNeg: 8, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'betReg=$15 ★', betReg: 15, betNeg: 8, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'betReg=$20', betReg: 20, betNeg: 8, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'betNeg=$5', betReg: 15, betNeg: 5, negCap: 175, sortStrategy: 'priority_short' },
  { label: 'betNeg=$10', betReg: 15, betNeg: 10, negCap: 175, sortStrategy: 'priority_short' },
];

console.log('\n' + 'Config'.padEnd(35) + '| PnL/mo | ROI%  | bets/d | reg/d | neg/d | SkipCap | SkipNeg | Free$ | RegFrz | NegFrz');
console.log('-'.repeat(140));

const results = [];
for (const c of configs) {
  const r = runSim(c);
  const free = BANKROLL - r.avgRegFrz - r.avgNegFrz;
  console.log(
    `${r.label.padEnd(35)}| $${r.pnl.toFixed(0).padStart(4)} | ${(r.pnl/600*100).toFixed(1).padStart(5)}% | ${r.betsPerDay.toFixed(1).padStart(5)} | ${r.regPerDay.toFixed(1).padStart(5)} | ${r.negPerDay.toFixed(1).padStart(5)} | ${String(r.skipCap.toFixed(0)).padStart(7)} | ${String(r.skipNeg.toFixed(0)).padStart(7)} | $${free.toFixed(0).padStart(4)} | $${r.avgRegFrz.toFixed(0).padStart(4)} | $${r.avgNegFrz.toFixed(0).padStart(4)}`
  );
  results.push({ ...c, ...r });
}

// ============= DETAILED COMPARISON =============

const asIs = results[0];
const toBe = results[2];

console.log('\n' + '='.repeat(70));
console.log('  AS-IS vs TO-BE COMPARISON');
console.log('='.repeat(70));

console.log(`\n| Метрика | AS-IS | TO-BE | Δ |`);
console.log(`|---|---|---|---|`);
console.log(`| BET_SIZE regular | $10 | $15 | +50% |`);
console.log(`| BET_SIZE neg_risk | $10 | $8 | -20% |`);
console.log(`| MAX_NEG_RISK_FROZEN | $420 | $175 | -58% |`);
console.log(`| Приоритизация | FIFO | SHORT FIRST | новое |`);
console.log(`| PnL/мес | $${asIs.pnl.toFixed(0)} | $${toBe.pnl.toFixed(0)} | +$${(toBe.pnl - asIs.pnl).toFixed(0)} (${((toBe.pnl - asIs.pnl) / asIs.pnl * 100).toFixed(0)}%) |`);
console.log(`| ROI/мес | ${(asIs.pnl/600*100).toFixed(1)}% | ${(toBe.pnl/600*100).toFixed(1)}% | +${((toBe.pnl - asIs.pnl)/600*100).toFixed(1)}п.п. |`);
console.log(`| Ставок/день | ${asIs.betsPerDay.toFixed(1)} | ${toBe.betsPerDay.toFixed(1)} | ${(toBe.betsPerDay - asIs.betsPerDay).toFixed(1)} |`);
console.log(`| Regular/день | ${asIs.regPerDay.toFixed(1)} | ${toBe.regPerDay.toFixed(1)} | ${(toBe.regPerDay - asIs.regPerDay).toFixed(1)} |`);
console.log(`| Neg_risk/день | ${asIs.negPerDay.toFixed(1)} | ${toBe.negPerDay.toFixed(1)} | ${(toBe.negPerDay - asIs.negPerDay).toFixed(1)} |`);
console.log(`| Win rate | ${asIs.winRate.toFixed(2)}% | ${toBe.winRate.toFixed(2)}% | |`);
console.log(`| Пропуски (капитал) | ${asIs.skipCap.toFixed(0)}/мес | ${toBe.skipCap.toFixed(0)}/мес | ${(toBe.skipCap - asIs.skipCap).toFixed(0)} |`);
console.log(`| Свободный капитал | $${(600 - asIs.avgRegFrz - asIs.avgNegFrz).toFixed(0)} | $${(600 - toBe.avgRegFrz - toBe.avgNegFrz).toFixed(0)} | +$${((600 - toBe.avgRegFrz - toBe.avgNegFrz) - (600 - asIs.avgRegFrz - asIs.avgNegFrz)).toFixed(0)} |`);
console.log(`| Замор. в neg_risk | $${asIs.avgNegFrz.toFixed(0)} | $${toBe.avgNegFrz.toFixed(0)} | ${(toBe.avgNegFrz - asIs.avgNegFrz).toFixed(0)} |`);
console.log(`| Замор. в regular | $${asIs.avgRegFrz.toFixed(0)} | $${toBe.avgRegFrz.toFixed(0)} | +$${(toBe.avgRegFrz - asIs.avgRegFrz).toFixed(0)} |`);
console.log(`| Median day PnL | $${asIs.dailyMedian.toFixed(2)} | $${toBe.dailyMedian.toFixed(2)} | +$${(toBe.dailyMedian - asIs.dailyMedian).toFixed(2)} |`);
console.log(`| Worst day | $${asIs.worstDay.toFixed(2)} | $${toBe.worstDay.toFixed(2)} | |`);
console.log(`| Best day | $${asIs.bestDay.toFixed(2)} | $${toBe.bestDay.toFixed(2)} | |`);

// Save
fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/final_backtest_v2_2026-03-22.json',
  JSON.stringify({
    timestamp: new Date().toISOString(),
    dataSource: 'scanner_data.json (19K resolved, filtered by bot criteria)',
    resolveTimesUsed: {
      regCount: filteredResolved.reg.length, regMedian: [...regRTs].sort((a,b)=>a-b)[Math.floor(regRTs.length/2)],
      negCount: filteredResolved.neg.length, negMedian: [...negRTs].sort((a,b)=>a-b)[Math.floor(negRTs.length/2)],
    },
    winRates: { reg: regWR, neg: negWR, regSample: regWins + regLosses, negSample: negWins + negLosses },
    marketSupply: { regPerDay, negPerDay },
    results: results.map(r => ({ label: r.label, pnl: r.pnl, betsPerDay: r.betsPerDay, skipCap: r.skipCap, avgCash: r.avgCash })),
  }, null, 2));
console.log('\nData saved to _analytics/data/final_backtest_v2_2026-03-22.json');
