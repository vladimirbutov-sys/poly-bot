/**
 * Backtest v2: end_date priority with FULL config (reg + neg_risk together)
 *
 * Previous test was flawed: tested only regular markets, ignoring neg_risk load.
 * This test simulates Variant C: $600 bankroll, $15 reg, $8 neg, neg_cap=$250
 *
 * Tests:
 * 1. FIFO - no priority (current)
 * 2. PRIORITY_REG - regular bets sorted by end_date (short first)
 * 3. PRIORITY_ALL - ALL bets sorted by end_date (short first)
 * 4. PRIORITY_REG + lower neg_cap variations
 * 5. FIFO with various neg_caps (to isolate neg_risk effect)
 */

const fs = require('fs');

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const positions = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'));
const markets = scanner.markets;

// ============= RESOLVE TIMES FROM REAL DATA =============

const resolved = Object.values(positions).filter(p =>
  (p.status === 'won' || p.status === 'lost') && p.placed_at && p.resolved_at
);

function hours(p) { return (new Date(p.resolved_at) - new Date(p.placed_at)) / 3600000; }

const regTimes = resolved.filter(p => !p.neg_risk).map(hours).sort((a,b) => a-b);
const negTimes = resolved.filter(p => p.neg_risk).map(hours).sort((a,b) => a-b);

const regMedian = regTimes[Math.floor(regTimes.length/2)] || 4.4;
const negMedian = negTimes[Math.floor(negTimes.length/2)] || 52.2;

console.log('='.repeat(70));
console.log('  END_DATE PRIORITY v2: Full config (reg + neg_risk)');
console.log('='.repeat(70));
console.log(`\nResolve times: reg median=${regMedian.toFixed(1)}h (n=${regTimes.length}), neg median=${negMedian.toFixed(1)}h (n=${negTimes.length})`);

// ============= MARKET SUPPLY FROM SCANNER =============
// Count qualifying markets per day, with end_date info

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
  const negRisk = m.neg_risk || false;

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

  return { negRisk, daysToEnd: daysToEnd || 3, cat, price };
}

// Build daily market lists from scanner
const fullDates = ['2026-03-18', '2026-03-19', '2026-03-20', '2026-03-21'];
const dailyData = {};

for (const [mk, m] of Object.entries(markets)) {
  const date = m.first_seen ? m.first_seen.slice(0, 10) : null;
  if (!date || !fullDates.includes(date)) continue;

  const r = passesFilters(m);
  if (!r) continue;
  if (r.daysToEnd > 7) continue; // end_date=7 limit

  if (!dailyData[date]) dailyData[date] = { reg: [], neg: [] };
  const type = r.negRisk ? 'neg' : 'reg';
  dailyData[date][type].push({ daysToEnd: r.daysToEnd, price: r.price });
}

// Average daily supply
let avgReg = 0, avgNeg = 0;
const allRegDTE = [], allNegDTE = [];
for (const date of fullDates) {
  const d = dailyData[date] || { reg: [], neg: [] };
  avgReg += d.reg.length;
  avgNeg += d.neg.length;
  d.reg.forEach(m => allRegDTE.push(m.daysToEnd));
  d.neg.forEach(m => allNegDTE.push(m.daysToEnd));
}
avgReg /= fullDates.length;
avgNeg /= fullDates.length;

console.log(`\nMarket supply (end≤7d): reg=${avgReg.toFixed(0)}/day, neg=${avgNeg.toFixed(0)}/day`);

// Distribution of daysToEnd
const dteBuckets = [[0,1,'0-1d'],[1,2,'1-2d'],[2,3,'2-3d'],[3,5,'3-5d'],[5,7,'5-7d']];
console.log('\nDays-to-end distribution:');
console.log('Bucket | Regular | Neg_risk');
for (const [lo, hi, name] of dteBuckets) {
  const rc = allRegDTE.filter(d => d >= lo && d < hi).length / fullDates.length;
  const nc = allNegDTE.filter(d => d >= lo && d < hi).length / fullDates.length;
  console.log(`${name.padEnd(6)} | ${rc.toFixed(1).padStart(7)}/day | ${nc.toFixed(1).padStart(7)}/day`);
}

// ============= RESOLVE TIME BY DAYS-TO-END (from positions) =============

// Build lookup: daysToEnd -> resolve hours (reg only)
const regByDTE = {};
for (const p of resolved) {
  if (p.neg_risk) continue;
  if (!p.end_date || !p.placed_at) continue;
  const dte = (new Date(p.end_date) - new Date(p.placed_at)) / 3600000 / 24;
  const h = hours(p);
  for (const [lo, hi, name] of dteBuckets) {
    if (dte >= lo && dte < hi) {
      if (!regByDTE[name]) regByDTE[name] = [];
      regByDTE[name].push(h);
      break;
    }
  }
}

console.log('\nResolve time by end_date bucket (regular, from positions):');
console.log('Bucket | n  | Median | Avg    | P25    | P75');
for (const [lo, hi, name] of dteBuckets) {
  const arr = (regByDTE[name] || []).sort((a,b) => a-b);
  if (arr.length === 0) { console.log(`${name.padEnd(6)} | no data`); continue; }
  const med = arr[Math.floor(arr.length/2)];
  const avg = arr.reduce((a,b) => a+b, 0) / arr.length;
  const p25 = arr[Math.floor(arr.length*0.25)];
  const p75 = arr[Math.floor(arr.length*0.75)];
  console.log(`${name.padEnd(6)} | ${String(arr.length).padStart(2)} | ${med.toFixed(1).padStart(6)}h | ${avg.toFixed(1).padStart(6)}h | ${p25.toFixed(1).padStart(6)}h | ${p75.toFixed(1).padStart(6)}h`);
}

// ============= SIMULATION =============

function sampleResolveTime(isNeg, daysToEnd) {
  if (isNeg) {
    // neg_risk: ~52h median, tight distribution
    return 40 + Math.random() * 25; // 40-65h
  }
  // Regular: depends on daysToEnd
  let median;
  if (daysToEnd < 1) median = 3.8;
  else if (daysToEnd < 2) median = 13.8;
  else if (daysToEnd < 3) median = 19;
  else if (daysToEnd < 5) median = 20;
  else median = 25;

  // Log-normal around median
  const logMed = Math.log(median);
  const sigma = 0.6;
  const u = Math.random();
  const v = Math.random();
  const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  return Math.max(0.5, Math.exp(logMed + sigma * z));
}

function generateMarkets(regPerDay, negPerDay, regDTEDist, negDTEDist) {
  const mkts = [];

  // Regular
  for (let i = 0; i < regPerDay; i++) {
    const dte = regDTEDist[Math.floor(Math.random() * regDTEDist.length)];
    const hour = Math.floor(6 + Math.random() * 16); // 6-22
    mkts.push({ isNeg: false, daysToEnd: dte, hour, betSize: 0 }); // betSize set later
  }

  // Neg_risk
  for (let i = 0; i < negPerDay; i++) {
    const dte = negDTEDist[Math.floor(Math.random() * negDTEDist.length)];
    const hour = Math.floor(6 + Math.random() * 16);
    mkts.push({ isNeg: true, daysToEnd: dte, hour, betSize: 0 });
  }

  return mkts;
}

const BANKROLL = 600;
const FILL_RATE = 0.82;
const WIN_RATE = 0.992;
const DAYS = 30;
const RUNS = 40;

function runSim(config) {
  const { betReg, betNeg, negCap, sortStrategy, endDateLimit } = config;

  let totPnL = 0, totBets = 0, totRegBets = 0, totNegBets = 0;
  let totSkipCap = 0, totSkipNeg = 0;
  let totFrozenSamples = 0, totFrozenSum = 0;
  let totRegFrozen = 0, totNegFrozen = 0;

  // Filter DTE distributions by endDateLimit
  const regDTE = allRegDTE.filter(d => d <= endDateLimit);
  const negDTE = allNegDTE.filter(d => d <= endDateLimit);
  const regPerDay = regDTE.length / fullDates.length;
  const negPerDay = negDTE.length / fullDates.length;

  for (let run = 0; run < RUNS; run++) {
    let cash = BANKROLL;
    let openPos = []; // {amount, resolveAt, isNeg, daysToEnd}
    let pnl = 0, bets = 0, regBets = 0, negBets = 0;
    let skipCap = 0, skipNeg = 0;

    for (let day = 0; day < DAYS; day++) {
      let dayMkts = generateMarkets(
        Math.round(regPerDay), Math.round(negPerDay), regDTE, negDTE
      );

      // Apply sort strategy
      if (sortStrategy === 'priority_short') {
        dayMkts.sort((a, b) => a.daysToEnd - b.daysToEnd);
      } else if (sortStrategy === 'priority_long') {
        dayMkts.sort((a, b) => b.daysToEnd - a.daysToEnd);
      } else if (sortStrategy === 'priority_reg_first') {
        // Regular first (all sorted by DTE), then neg
        const reg = dayMkts.filter(m => !m.isNeg).sort((a,b) => a.daysToEnd - b.daysToEnd);
        const neg = dayMkts.filter(m => m.isNeg).sort((a,b) => a.daysToEnd - b.daysToEnd);
        dayMkts = [...reg, ...neg];
      }
      // 'fifo' = no sort

      for (let hour = 0; hour < 24; hour++) {
        // Resolve
        const newOpen = [];
        for (const pos of openPos) {
          if (day * 24 + hour >= pos.resolveAt) {
            if (Math.random() < WIN_RATE) {
              pnl += pos.amount * 0.025;
            } else {
              pnl -= pos.amount;
            }
            cash += pos.amount;
          } else {
            newOpen.push(pos);
          }
        }
        openPos = newOpen;

        // Track frozen capital
        const regFrozen = openPos.filter(p => !p.isNeg).reduce((s, p) => s + p.amount, 0);
        const negFrozen = openPos.filter(p => p.isNeg).reduce((s, p) => s + p.amount, 0);
        totFrozenSamples++;
        totFrozenSum += (BANKROLL - cash);
        totRegFrozen += regFrozen;
        totNegFrozen += negFrozen;

        // Place bets
        const hourMkts = dayMkts.filter(m => m.hour === hour);

        for (const m of hourMkts) {
          if (Math.random() > FILL_RATE) continue;

          const betSize = m.isNeg ? betNeg : betReg;

          // Check neg_risk cap
          if (m.isNeg) {
            const currentNegFrozen = openPos.filter(p => p.isNeg).reduce((s, p) => s + p.amount, 0);
            if (currentNegFrozen + betSize > negCap) {
              skipNeg++;
              continue;
            }
          }

          // Check cash
          if (cash < betSize) {
            skipCap++;
            continue;
          }

          cash -= betSize;
          bets++;
          if (m.isNeg) negBets++; else regBets++;

          const resolveH = sampleResolveTime(m.isNeg, m.daysToEnd);
          openPos.push({
            amount: betSize,
            resolveAt: day * 24 + hour + resolveH,
            isNeg: m.isNeg,
            daysToEnd: m.daysToEnd
          });
        }
      }
    }

    totPnL += pnl;
    totBets += bets;
    totRegBets += regBets;
    totNegBets += negBets;
    totSkipCap += skipCap;
    totSkipNeg += skipNeg;
  }

  return {
    pnl: totPnL / RUNS,
    betsPerDay: totBets / RUNS / DAYS,
    regPerDay: totRegBets / RUNS / DAYS,
    negPerDay: totNegBets / RUNS / DAYS,
    skipCap: totSkipCap / RUNS,
    skipNeg: totSkipNeg / RUNS,
    avgFrozen: totFrozenSum / totFrozenSamples,
    avgRegFrozen: totRegFrozen / totFrozenSamples,
    avgNegFrozen: totNegFrozen / totFrozenSamples,
  };
}

// ============= TEST CONFIGURATIONS =============

console.log('\n' + '='.repeat(80));
console.log('  SIMULATION: Variant C ($15 reg, $8 neg, various neg_caps and priorities)');
console.log('  ' + RUNS + ' runs × 30 days each');
console.log('='.repeat(80));

const configs = [
  // Baseline: Variant C with FIFO
  { name: 'C: FIFO (no priority)', betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'fifo', endDateLimit: 7 },

  // Priority variations
  { name: 'C: SHORT FIRST (all)', betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'priority_short', endDateLimit: 7 },
  { name: 'C: LONG FIRST (anti)', betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'priority_long', endDateLimit: 7 },
  { name: 'C: REG FIRST + short', betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'priority_reg_first', endDateLimit: 7 },

  // What if neg_cap is different?
  { name: 'FIFO negCap=$100', betReg: 15, betNeg: 8, negCap: 100, sortStrategy: 'fifo', endDateLimit: 7 },
  { name: 'SHORT negCap=$100', betReg: 15, betNeg: 8, negCap: 100, sortStrategy: 'priority_short', endDateLimit: 7 },
  { name: 'FIFO negCap=$350', betReg: 15, betNeg: 8, negCap: 350, sortStrategy: 'fifo', endDateLimit: 7 },
  { name: 'SHORT negCap=$350', betReg: 15, betNeg: 8, negCap: 350, sortStrategy: 'priority_short', endDateLimit: 7 },
  { name: 'FIFO negCap=$420', betReg: 15, betNeg: 8, negCap: 420, sortStrategy: 'fifo', endDateLimit: 7 },
  { name: 'SHORT negCap=$420', betReg: 15, betNeg: 8, negCap: 420, sortStrategy: 'priority_short', endDateLimit: 7 },

  // Current config for comparison
  { name: 'CURRENT ($10/$10 neg420)', betReg: 10, betNeg: 10, negCap: 420, sortStrategy: 'fifo', endDateLimit: 7 },
  { name: 'CURRENT + SHORT PRIO', betReg: 10, betNeg: 10, negCap: 420, sortStrategy: 'priority_short', endDateLimit: 7 },

  // Extreme: no neg, just regular
  { name: 'NO NEG FIFO', betReg: 15, betNeg: 8, negCap: 0, sortStrategy: 'fifo', endDateLimit: 7 },
  { name: 'NO NEG SHORT', betReg: 15, betNeg: 8, negCap: 0, sortStrategy: 'priority_short', endDateLimit: 7 },
];

console.log('\n' + 'Config'.padEnd(28) + '| PnL/mo | Bets/d | reg/d | neg/d | SkipCap | SkipNeg | AvgFrozen | RegFrz | NegFrz | Free$');
console.log('-'.repeat(140));

const results = [];
for (const c of configs) {
  const r = runSim(c);
  const free = BANKROLL - r.avgFrozen;
  const line = `${c.name.padEnd(28)}| $${r.pnl.toFixed(0).padStart(4)} | ${r.betsPerDay.toFixed(1).padStart(5)} | ${r.regPerDay.toFixed(1).padStart(5)} | ${r.negPerDay.toFixed(1).padStart(5)} | ${String(r.skipCap.toFixed(0)).padStart(7)} | ${String(r.skipNeg.toFixed(0)).padStart(7)} | $${r.avgFrozen.toFixed(0).padStart(7)} | $${r.avgRegFrozen.toFixed(0).padStart(4)} | $${r.avgNegFrozen.toFixed(0).padStart(4)} | $${free.toFixed(0).padStart(4)}`;
  console.log(line);
  results.push({ ...c, ...r });
}

// ============= DETAILED HOURLY COMPARISON =============

console.log('\n' + '='.repeat(80));
console.log('  HOURLY CAPITAL: FIFO vs SHORT PRIORITY (Variant C, negCap=$250)');
console.log('='.repeat(80));

function runHourlySim(config) {
  const { betReg, betNeg, negCap, sortStrategy, endDateLimit } = config;
  const regDTE = allRegDTE.filter(d => d <= endDateLimit);
  const negDTE = allNegDTE.filter(d => d <= endDateLimit);
  const regPerDay = regDTE.length / fullDates.length;
  const negPerDay = negDTE.length / fullDates.length;

  const hourlyData = Array.from({length: 24}, () => ({
    cash: 0, frozen: 0, regFrz: 0, negFrz: 0, bets: 0, skips: 0, count: 0
  }));

  for (let run = 0; run < 20; run++) {
    let cash = BANKROLL;
    let openPos = [];

    for (let day = 0; day < DAYS; day++) {
      let dayMkts = generateMarkets(Math.round(regPerDay), Math.round(negPerDay), regDTE, negDTE);
      if (sortStrategy === 'priority_short') dayMkts.sort((a,b) => a.daysToEnd - b.daysToEnd);

      for (let hour = 0; hour < 24; hour++) {
        // Resolve
        const newOpen = [];
        for (const pos of openPos) {
          if (day * 24 + hour >= pos.resolveAt) {
            cash += pos.amount;
          } else {
            newOpen.push(pos);
          }
        }
        openPos = newOpen;

        const hd = hourlyData[hour];
        hd.cash += cash;
        hd.frozen += (BANKROLL - cash);
        hd.regFrz += openPos.filter(p => !p.isNeg).reduce((s,p) => s+p.amount, 0);
        hd.negFrz += openPos.filter(p => p.isNeg).reduce((s,p) => s+p.amount, 0);
        hd.count++;

        const hourMkts = dayMkts.filter(m => m.hour === hour);
        for (const m of hourMkts) {
          if (Math.random() > FILL_RATE) continue;
          const betSize = m.isNeg ? betNeg : betReg;
          if (m.isNeg) {
            const curNeg = openPos.filter(p => p.isNeg).reduce((s,p) => s+p.amount, 0);
            if (curNeg + betSize > negCap) continue;
          }
          if (cash < betSize) { hd.skips++; continue; }
          cash -= betSize;
          hd.bets++;
          openPos.push({
            amount: betSize,
            resolveAt: day * 24 + hour + sampleResolveTime(m.isNeg, m.daysToEnd),
            isNeg: m.isNeg,
            daysToEnd: m.daysToEnd
          });
        }
      }
    }
  }

  return hourlyData.map(h => ({
    cash: h.cash / h.count,
    frozen: h.frozen / h.count,
    regFrz: h.regFrz / h.count,
    negFrz: h.negFrz / h.count,
    bets: h.bets / (20 * DAYS),
    skips: h.skips / (20 * DAYS),
  }));
}

const fifoH = runHourlySim({ betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'fifo', endDateLimit: 7 });
const prioH = runHourlySim({ betReg: 15, betNeg: 8, negCap: 250, sortStrategy: 'priority_short', endDateLimit: 7 });

console.log('\nHour | FIFO cash | PRIO cash | FIFO regFrz | PRIO regFrz | FIFO negFrz | PRIO negFrz | FIFO skip | PRIO skip');
console.log('-'.repeat(110));
for (let h = 6; h < 23; h++) {
  console.log(
    `  ${String(h).padStart(2)} | $${fifoH[h].cash.toFixed(0).padStart(7)} | $${prioH[h].cash.toFixed(0).padStart(7)} | $${fifoH[h].regFrz.toFixed(0).padStart(9)} | $${prioH[h].regFrz.toFixed(0).padStart(9)} | $${fifoH[h].negFrz.toFixed(0).padStart(9)} | $${prioH[h].negFrz.toFixed(0).padStart(9)} | ${fifoH[h].skips.toFixed(2).padStart(9)} | ${prioH[h].skips.toFixed(2).padStart(9)}`
  );
}

// ============= STRESS TEST: What if market supply doubles? =============

console.log('\n' + '='.repeat(80));
console.log('  STRESS TEST: 2x market supply (when would priority matter?)');
console.log('='.repeat(80));

// Override market counts
const stressRegDTE = [...allRegDTE, ...allRegDTE].filter(d => d <= 7); // double
const stressNegDTE = [...allNegDTE, ...allNegDTE].filter(d => d <= 7);

function runStressSim(sortStrategy) {
  const regPerDay = stressRegDTE.length / fullDates.length;
  const negPerDay = stressNegDTE.length / fullDates.length;

  let totPnL = 0, totSkipCap = 0, totBets = 0;

  for (let run = 0; run < RUNS; run++) {
    let cash = BANKROLL;
    let openPos = [];
    let pnl = 0, bets = 0, skipCap = 0;

    for (let day = 0; day < DAYS; day++) {
      let dayMkts = generateMarkets(Math.round(regPerDay), Math.round(negPerDay), stressRegDTE, stressNegDTE);
      if (sortStrategy === 'priority_short') dayMkts.sort((a,b) => a.daysToEnd - b.daysToEnd);

      for (let hour = 0; hour < 24; hour++) {
        const newOpen = [];
        for (const pos of openPos) {
          if (day * 24 + hour >= pos.resolveAt) {
            if (Math.random() < WIN_RATE) pnl += pos.amount * 0.025;
            else pnl -= pos.amount;
            cash += pos.amount;
          } else newOpen.push(pos);
        }
        openPos = newOpen;

        const hourMkts = dayMkts.filter(m => m.hour === hour);
        for (const m of hourMkts) {
          if (Math.random() > FILL_RATE) continue;
          const betSize = m.isNeg ? 8 : 15;
          if (m.isNeg) {
            const curNeg = openPos.filter(p => p.isNeg).reduce((s,p) => s+p.amount, 0);
            if (curNeg + betSize > 250) continue;
          }
          if (cash < betSize) { skipCap++; continue; }
          cash -= betSize;
          bets++;
          openPos.push({
            amount: betSize,
            resolveAt: day * 24 + hour + sampleResolveTime(m.isNeg, m.daysToEnd),
            isNeg: m.isNeg,
            daysToEnd: m.daysToEnd
          });
        }
      }
    }
    totPnL += pnl;
    totSkipCap += skipCap;
    totBets += bets;
  }

  return { pnl: totPnL/RUNS, skipCap: totSkipCap/RUNS, betsPerDay: totBets/RUNS/DAYS };
}

const stressFIFO = runStressSim('fifo');
const stressPRIO = runStressSim('priority_short');

console.log(`\n2x supply (~${Math.round(stressRegDTE.length / fullDates.length * 2)} mkts/day):`);
console.log(`FIFO:     PnL=$${stressFIFO.pnl.toFixed(0)}/mo | bets=${stressFIFO.betsPerDay.toFixed(1)}/day | skipCap=${stressFIFO.skipCap.toFixed(0)}/mo`);
console.log(`PRIORITY: PnL=$${stressPRIO.pnl.toFixed(0)}/mo | bets=${stressPRIO.betsPerDay.toFixed(1)}/day | skipCap=${stressPRIO.skipCap.toFixed(0)}/mo`);
console.log(`Delta:    +$${(stressPRIO.pnl - stressFIFO.pnl).toFixed(0)}/mo from priority`);

// Save
fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/enddate_priority_v2_2026-03-22.json',
  JSON.stringify({ results, timestamp: new Date().toISOString() }, null, 2));
console.log('\nData saved.');
