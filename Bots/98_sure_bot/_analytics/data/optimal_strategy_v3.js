/**
 * OPTIMAL STRATEGY FINDER v3
 *
 * Finds best combination of: bet_size × market_type × end_date_limit
 * Uses REAL resolve times from scanner (566 filtered markets)
 * Tests granular end_date limits separately for regular and neg_risk
 *
 * Key insight from previous analyses: end_date is the main driver of resolve time,
 * and long-tail regular markets (end_date 3-7d) freeze capital for 100h+.
 */
const fs = require('fs');

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const markets = scanner.markets;

// ============= FILTERS (exact copy from 98_sure_bot/filters.py) =============
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
  return { negRisk: m.neg_risk || false, daysToEnd: m.days_to_end, price, cat };
}

// ============= COLLECT DATA =============
console.log('='.repeat(70));
console.log('  OPTIMAL STRATEGY FINDER v3');
console.log('  Real resolve times from scanner + bot filters');
console.log('='.repeat(70));

const fullDates = ['2026-03-18', '2026-03-19', '2026-03-20', '2026-03-21'];

// Collect all filtered markets with their resolve times
const allMarkets = []; // {negRisk, daysToEnd, rt, price, cat, won, date}
const resolvedPool = { reg: [], neg: [] }; // for sampling resolve times

for (const [cid, m] of Object.entries(markets)) {
  const r = passesFilters(m);
  if (!r) continue;
  if (r.daysToEnd == null) continue;

  const date = m.first_seen ? m.first_seen.slice(0, 10) : null;
  const type = r.negRisk ? 'neg' : 'reg';

  if (date && fullDates.includes(date)) {
    allMarkets.push({ ...r, date, resolved: m.resolved || false });
  }

  if (m.resolved && m.resolve_time_hours != null && m.resolve_time_hours > 0) {
    resolvedPool[type].push({
      rt: m.resolve_time_hours,
      dte: r.daysToEnd,
      price: r.price,
      won: m.high_outcome_won === true,
    });
  }
}

// ============= ANALYZE DATA STRUCTURE =============

// Count markets by type and end_date bucket
const dteBuckets = [[0,1,'0-1d'],[1,2,'1-2d'],[2,3,'2-3d'],[3,5,'3-5d'],[5,7,'5-7d'],[7,14,'7-14d'],[14,999,'14+d']];

console.log('\n=== MARKET SUPPLY PER DAY (filtered, 4-day average) ===\n');
console.log('end_date  | Reg/day | Neg/day | Total | Reg resolve med | Neg resolve med');
console.log('-'.repeat(85));

for (const [lo, hi, name] of dteBuckets) {
  const regDaily = allMarkets.filter(m => !m.negRisk && m.daysToEnd >= lo && m.daysToEnd < hi);
  const negDaily = allMarkets.filter(m => m.negRisk && m.daysToEnd >= lo && m.daysToEnd < hi);
  const regPerDay = regDaily.length / fullDates.length;
  const negPerDay = negDaily.length / fullDates.length;

  const regRTs = resolvedPool.reg.filter(x => x.dte >= lo && x.dte < hi).map(x => x.rt).sort((a,b) => a-b);
  const negRTs = resolvedPool.neg.filter(x => x.dte >= lo && x.dte < hi).map(x => x.rt).sort((a,b) => a-b);
  const regMed = regRTs.length ? regRTs[Math.floor(regRTs.length/2)].toFixed(1) + 'h' : '-';
  const negMed = negRTs.length ? negRTs[Math.floor(negRTs.length/2)].toFixed(1) + 'h' : '-';

  console.log(`${name.padEnd(9)} | ${regPerDay.toFixed(1).padStart(7)} | ${negPerDay.toFixed(1).padStart(7)} | ${(regPerDay+negPerDay).toFixed(1).padStart(5)} | ${regMed.padStart(15)} | ${negMed.padStart(15)}`);
}

// Capital efficiency metric: profit per hour of capital frozen
console.log('\n=== CAPITAL EFFICIENCY: profit per $1 per hour frozen ===\n');
console.log('Segment                  | n   | Med resolve | Avg price | Profit/$ | $/hr frozen | WR');
console.log('-'.repeat(95));

const segments = [
  { name: 'Reg 0-1d', filter: x => !x.negRisk && x.dte < 1, pool: 'reg' },
  { name: 'Reg 1-2d', filter: x => !x.negRisk && x.dte >= 1 && x.dte < 2, pool: 'reg' },
  { name: 'Reg 2-3d', filter: x => !x.negRisk && x.dte >= 2 && x.dte < 3, pool: 'reg' },
  { name: 'Reg 3-7d', filter: x => !x.negRisk && x.dte >= 3 && x.dte < 7, pool: 'reg' },
  { name: 'Neg 0-1d', filter: x => x.negRisk && x.dte < 1, pool: 'neg' },
  { name: 'Neg 1-2d', filter: x => x.negRisk && x.dte >= 1 && x.dte < 2, pool: 'neg' },
  { name: 'Neg 2-3d', filter: x => x.negRisk && x.dte >= 2 && x.dte < 3, pool: 'neg' },
  { name: 'Neg 3-7d', filter: x => x.negRisk && x.dte >= 3 && x.dte < 7, pool: 'neg' },
];

for (const seg of segments) {
  const items = resolvedPool[seg.pool].filter(seg.filter);
  if (!items.length) { console.log(`${seg.name.padEnd(25)}| no resolved data`); continue; }
  const rts = items.map(x => x.rt).sort((a,b) => a-b);
  const medRT = rts[Math.floor(rts.length/2)];
  const avgPrice = items.reduce((s, x) => s + x.price, 0) / items.length;
  const profitPerDollar = 1 / avgPrice - 1; // profit per $1 invested
  const profitPerHour = profitPerDollar / medRT;
  const wr = items.filter(x => x.won).length / items.length * 100;
  console.log(`${seg.name.padEnd(25)}| ${String(items.length).padStart(3)} | ${medRT.toFixed(1).padStart(10)}h | ${avgPrice.toFixed(4).padStart(9)} | ${(profitPerDollar*100).toFixed(2).padStart(7)}% | $${(profitPerHour*1000).toFixed(3).padStart(7)}/k·h | ${wr.toFixed(1)}%`);
}

// ============= MONTE CARLO WITH GRANULAR END_DATE CONTROL =============

const BANKROLL = 600;
const FILL_RATE = 0.82;
const DAYS = 30;
const RUNS = 40;

// Build resolve time pools per segment
const rtPools = {};
for (const seg of segments) {
  const items = resolvedPool[seg.pool].filter(seg.filter);
  rtPools[seg.name] = items.length ? items.map(x => x.rt) : null;
}

// Fallback: if no resolve data for a segment, use overall pool
function sampleRT(segName, pool) {
  if (rtPools[segName] && rtPools[segName].length) {
    return rtPools[segName][Math.floor(Math.random() * rtPools[segName].length)];
  }
  // fallback to overall pool
  const overall = pool === 'reg' ? resolvedPool.reg : resolvedPool.neg;
  return overall.length ? overall[Math.floor(Math.random() * overall.length)].rt : 10;
}

function runSim(config) {
  const { betReg, betNeg, negCap, regMaxDTE, negMaxDTE, sortStrategy, label } = config;

  // Filter daily supply by end_date limits
  const dailyReg = allMarkets.filter(m => !m.negRisk && m.daysToEnd <= regMaxDTE);
  const dailyNeg = allMarkets.filter(m => m.negRisk && m.daysToEnd <= negMaxDTE);
  const regN = Math.round(dailyReg.length / fullDates.length);
  const negN = Math.round(dailyNeg.length / fullDates.length);

  // Price pools for profit calculation
  const regPrices = dailyReg.map(m => m.price);
  const negPrices = dailyNeg.map(m => m.price);
  // DTE pools for resolve time sampling
  const regDTEs = dailyReg.map(m => m.daysToEnd);
  const negDTEs = dailyNeg.map(m => m.daysToEnd);

  // Win rates from resolved data filtered by same DTE limits
  const regResolved = resolvedPool.reg.filter(x => x.dte <= regMaxDTE);
  const negResolved = resolvedPool.neg.filter(x => x.dte <= negMaxDTE);
  const regWR = regResolved.length ? regResolved.filter(x => x.won).length / regResolved.length : 0.998;
  const negWR = negResolved.length ? negResolved.filter(x => x.won).length / negResolved.length : 0.997;

  let totPnL = 0, totBets = 0, totRegBets = 0, totNegBets = 0;
  let totSkipCap = 0, totSkipNeg = 0;
  let totCashSum = 0, totCashN = 0;

  for (let run = 0; run < RUNS; run++) {
    let cash = BANKROLL;
    let openPos = [];
    let pnl = 0, regBets = 0, negBets = 0, skipCap = 0, skipNeg = 0;

    for (let day = 0; day < DAYS; day++) {
      // Generate markets for this day
      let dayMkts = [];
      for (let i = 0; i < regN; i++) {
        const dte = regDTEs[Math.floor(Math.random() * regDTEs.length)] || 0.5;
        const price = regPrices[Math.floor(Math.random() * regPrices.length)] || 0.98;
        dayMkts.push({ isNeg: false, dte, price, hour: Math.floor(6 + Math.random() * 16) });
      }
      for (let i = 0; i < negN; i++) {
        const dte = negDTEs[Math.floor(Math.random() * negDTEs.length)] || 1;
        const price = negPrices[Math.floor(Math.random() * negPrices.length)] || 0.98;
        dayMkts.push({ isNeg: true, dte, price, hour: Math.floor(6 + Math.random() * 16) });
      }

      if (sortStrategy === 'short') dayMkts.sort((a, b) => a.dte - b.dte);

      for (let hour = 0; hour < 24; hour++) {
        // Resolve
        const newOpen = [];
        for (const pos of openPos) {
          if (day * 24 + hour >= pos.resolveAt) {
            const wr = pos.isNeg ? negWR : regWR;
            if (Math.random() < wr) {
              pnl += pos.amount * (1 / pos.price - 1);
            } else {
              pnl -= pos.amount;
            }
            cash += pos.amount;
          } else newOpen.push(pos);
        }
        openPos = newOpen;

        totCashSum += cash;
        totCashN++;

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

          // Sample resolve time from matching segment
          let segName;
          if (m.dte < 1) segName = (m.isNeg ? 'Neg' : 'Reg') + ' 0-1d';
          else if (m.dte < 2) segName = (m.isNeg ? 'Neg' : 'Reg') + ' 1-2d';
          else if (m.dte < 3) segName = (m.isNeg ? 'Neg' : 'Reg') + ' 2-3d';
          else segName = (m.isNeg ? 'Neg' : 'Reg') + ' 3-7d';
          const rt = sampleRT(segName, m.isNeg ? 'neg' : 'reg');

          openPos.push({ amount: betSize, resolveAt: day * 24 + hour + rt, isNeg: m.isNeg, price: m.price });
        }
      }
    }
    totPnL += pnl;
    totBets += regBets + negBets;
    totRegBets += regBets;
    totNegBets += negBets;
    totSkipCap += skipCap;
    totSkipNeg += skipNeg;
  }

  return {
    label, pnl: totPnL / RUNS, betsPerDay: totBets / RUNS / DAYS,
    regPerDay: totRegBets / RUNS / DAYS, negPerDay: totNegBets / RUNS / DAYS,
    skipCap: totSkipCap / RUNS, skipNeg: totSkipNeg / RUNS,
    avgCash: totCashSum / totCashN,
    regSupply: regN, negSupply: negN,
  };
}

// ============= TEST MATRIX =============

console.log('\n' + '='.repeat(70));
console.log('  MONTE CARLO: Testing all combinations');
console.log('  ' + RUNS + ' runs × ' + DAYS + ' days | fill=' + FILL_RATE);
console.log('='.repeat(70));

// Test: regMaxDTE × negMaxDTE × negCap × betReg
const testConfigs = [];

const regDTEOptions = [1, 2, 3, 5, 7];
const negDTEOptions = [0, 1, 2, 3, 7]; // 0 = no neg_risk
const negCapOptions = [0, 100, 175, 250]; // 0 matches negMaxDTE=0
const betRegOptions = [10, 15, 20];

for (const regDTE of regDTEOptions) {
  for (const negDTE of negDTEOptions) {
    for (const negCap of negCapOptions) {
      // Skip illogical combos
      if (negDTE === 0 && negCap > 0) continue; // no neg markets but cap > 0
      if (negDTE > 0 && negCap === 0) continue; // neg markets but cap = 0

      for (const betReg of betRegOptions) {
        testConfigs.push({
          label: `reg≤${regDTE}d neg≤${negDTE}d cap$${negCap} bet$${betReg}`,
          betReg, betNeg: 8, negCap, regMaxDTE: regDTE, negMaxDTE: negDTE,
          sortStrategy: 'short',
        });
      }
    }
  }
}

console.log(`\nTesting ${testConfigs.length} configurations...\n`);

const results = [];
for (const c of testConfigs) {
  results.push(runSim(c));
}

// Sort by PnL
results.sort((a, b) => b.pnl - a.pnl);

// Top 30
console.log('=== TOP 30 CONFIGURATIONS ===\n');
console.log('Rank | Config                                    | PnL/mo | ROI%  | bets/d | reg/d | neg/d | Skip$ | SkipN | Free$ | Supply(r+n)');
console.log('-'.repeat(145));

for (let i = 0; i < Math.min(30, results.length); i++) {
  const r = results[i];
  console.log(
    `${String(i + 1).padStart(4)} | ${r.label.padEnd(41)} | $${r.pnl.toFixed(0).padStart(4)} | ${(r.pnl/600*100).toFixed(1).padStart(5)}% | ${r.betsPerDay.toFixed(1).padStart(5)} | ${r.regPerDay.toFixed(1).padStart(5)} | ${r.negPerDay.toFixed(1).padStart(5)} | ${String(r.skipCap.toFixed(0)).padStart(5)} | ${String(r.skipNeg.toFixed(0)).padStart(5)} | $${r.avgCash.toFixed(0).padStart(4)} | ${r.regSupply}+${r.negSupply}`
  );
}

// Bottom 5
console.log('\n=== BOTTOM 5 ===');
for (let i = results.length - 5; i < results.length; i++) {
  const r = results[i];
  console.log(`${String(i + 1).padStart(4)} | ${r.label.padEnd(41)} | $${r.pnl.toFixed(0).padStart(4)}`);
}

// Current config
const current = runSim({
  label: 'CURRENT', betReg: 10, betNeg: 10, negCap: 420, regMaxDTE: 7, negMaxDTE: 7, sortStrategy: 'fifo',
});
console.log(`\n=== CURRENT CONFIG: $${current.pnl.toFixed(0)}/mo | ${current.betsPerDay.toFixed(1)} bets/d | skip=${current.skipCap.toFixed(0)} | free=$${current.avgCash.toFixed(0)} ===`);

// Best per strategy type
console.log('\n=== BEST PER STRATEGY TYPE ===\n');

const strategies = {
  'No neg_risk at all': r => r.label.includes('neg≤0d'),
  'Neg only 0-1d': r => r.label.includes('neg≤1d'),
  'Reg only 0-1d': r => r.label.includes('reg≤1d') && r.label.includes('neg≤0d'),
  'Reg ≤ 2d': r => r.label.includes('reg≤2d'),
  'Reg ≤ 3d': r => r.label.includes('reg≤3d'),
  'Everything ≤ 7d': r => r.label.includes('reg≤7d') && r.label.includes('neg≤7d'),
  'Reg ≤ 1d + Neg ≤ 1d': r => r.label.includes('reg≤1d') && r.label.includes('neg≤1d'),
  'Best $10 bet': r => r.label.includes('bet$10'),
  'Best $15 bet': r => r.label.includes('bet$15'),
  'Best $20 bet': r => r.label.includes('bet$20'),
};

for (const [name, filter] of Object.entries(strategies)) {
  const matching = results.filter(filter);
  if (matching.length) {
    const best = matching[0]; // already sorted by PnL
    console.log(`${name.padEnd(30)}: $${best.pnl.toFixed(0)}/mo | ${best.label}`);
  }
}

// Save
fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/optimal_strategy_v3_2026-03-22.json',
  JSON.stringify({
    timestamp: new Date().toISOString(),
    resolveData: {
      regCount: resolvedPool.reg.length, negCount: resolvedPool.neg.length,
    },
    top30: results.slice(0, 30).map(r => ({ label: r.label, pnl: r.pnl, betsPerDay: r.betsPerDay, skipCap: r.skipCap, avgCash: r.avgCash })),
    current: { pnl: current.pnl, betsPerDay: current.betsPerDay, skipCap: current.skipCap },
    allResults: results.map(r => ({ label: r.label, pnl: Math.round(r.pnl), skip: Math.round(r.skipCap) })),
  }, null, 2));
console.log('\nData saved.');
