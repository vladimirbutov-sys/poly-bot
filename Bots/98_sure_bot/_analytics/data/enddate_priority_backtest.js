/**
 * Backtest: Does prioritizing bets by end_date (shortest first) improve P&L?
 *
 * Compares 3 strategies:
 * 1. FIFO (current) - bet on whatever comes first
 * 2. END_DATE_PRIORITY - when capital is limited, prefer shorter end_date
 * 3. STRICT_SHORT - only bet on end_date <= 3 days
 *
 * Uses Monte Carlo simulation with real resolve time distributions by end_date bucket.
 */

const fs = require('fs');

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const positions = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'));
const markets = scanner.markets;

// ============= REAL RESOLVE TIMES BY END_DATE BUCKET =============

// From positions.json - actual resolve times grouped by days_to_end and neg_risk
const resolvedPositions = Object.values(positions).filter(p =>
  p.status === 'won' || p.status === 'lost'
);

function getResolveHours(p) {
  if (!p.placed_at || !p.resolved_at) return null;
  return (new Date(p.resolved_at) - new Date(p.placed_at)) / (1000*60*60);
}

function getDaysToEnd(p) {
  if (!p.end_date || !p.placed_at) return null;
  return (new Date(p.end_date) - new Date(p.placed_at)) / (1000*60*60*24);
}

// Build resolve time distributions by bucket for regular markets
const buckets = [
  { name: '0-1d', min: 0, max: 1 },
  { name: '1-2d', min: 1, max: 2 },
  { name: '2-3d', min: 2, max: 3 },
  { name: '3-5d', min: 3, max: 5 },
  { name: '5-7d', min: 5, max: 7 },
  { name: '7+d', min: 7, max: 999 },
];

const resolveTimesByBucket = {};
for (const b of buckets) {
  resolveTimesByBucket[b.name] = { reg: [], neg: [] };
}

for (const p of resolvedPositions) {
  const h = getResolveHours(p);
  const d = getDaysToEnd(p);
  if (h === null || d === null) continue;

  const isNeg = p.neg_risk || false;
  const type = isNeg ? 'neg' : 'reg';

  for (const b of buckets) {
    if (d >= b.min && d < b.max) {
      resolveTimesByBucket[b.name][type].push(h);
      break;
    }
  }
}

// Print resolve time summary
console.log('='.repeat(70));
console.log('  RESOLVE TIMES BY END_DATE BUCKET (from real positions)');
console.log('='.repeat(70));
console.log('\nBucket  | Reg n | Reg median | Neg n | Neg median');
console.log('-'.repeat(60));

for (const b of buckets) {
  const reg = resolveTimesByBucket[b.name].reg.sort((a,b) => a-b);
  const neg = resolveTimesByBucket[b.name].neg.sort((a,b) => a-b);
  const regMed = reg.length > 0 ? reg[Math.floor(reg.length/2)] : 0;
  const negMed = neg.length > 0 ? neg[Math.floor(neg.length/2)] : 0;
  console.log(`${b.name.padEnd(7)} | ${String(reg.length).padStart(5)} | ${regMed.toFixed(1).padStart(10)}h | ${String(neg.length).padStart(5)} | ${negMed.toFixed(1).padStart(10)}h`);
}

// ============= COUNT MARKETS BY END_DATE BUCKET =============

// Filters (same as non_neg_risk_backtest)
const POLITICS_CATEGORIES = new Set(['politics', 'geopolitics']);
const EARLY_SPORTS = new Set(['esports', 'sports_other', 'basketball', 'hockey',
  'american_football', 'tennis', 'fighting', 'cricket']);
const ALL_SPORTS = new Set([...EARLY_SPORTS, 'soccer']);

const COIN_FLIP = [/\bodd\s+or\s+even\b/i, /\bodd\/even\b/i, /\bfirst\s+blood\b/i, /\bfirst\s+kill\b/i,
  /\bfirst\s+baron\b/i, /\bfirst\s+dragon\b/i, /\bfirst\s+tower\b/i, /\bcoin\s+flip\b/i, /\brampage\b/i,
  /\bfirst\s+roshan\b/i, /\bfirst\s+map\b/i, /\bup\s+or\s+down\b/i];
const TOXIC = [/\bearthquake/i, /\bseismic\b/i, /\bmagnitude\s+\d/i, /\btornado/i, /\btornadoes\b/i,
  /\btweets?\b/i, /\bposts?\b.*\d+-\d+/i, /\d+-\d+\s*(tweets?|posts?)/i, /\btweet\b/i, /\bretweet\b/i,
  /how\s+many.*\bpost/i, /how\s+many.*\btweet/i, /number\s+of\s+(tweets?|posts?)/i];
const SLOW = [/\btop\b/i, /\bseason\b/i, /\bmost\b/i, /\btransit\b/i, /\bstrait\b/i, /\bships?\b/i,
  /\bweekly\b/i, /\bmonthly\b/i];
const FINANCIAL = [/\bbitcoin\b/i, /\bethereum\b/i, /\bsolana\b/i, /\bxrp\b/i, /\bbtc\b/i, /\beth\b/i,
  /\bs&p\s*500\b/i, /\bnasdaq\b/i, /\bnyse\b/i, /\bdow\s*jones\b/i, /\bcrude\s*oil\b/i,
  /\bgold\s*price\b/i, /\btreasury\s*yield\b/i, /\bfed\s*rate\b/i, /\bmicrostrategy\b/i,
  /\baapl\b/i, /\bamzn\b/i, /\bgoogl\b/i, /\bmeta\b/i, /\bnflx\b/i, /\bmsft\b/i, /\btsla\b/i, /\bnvda\b/i,
  /\bapple\b/i, /\bamazon\b/i, /\bgoogle\b/i, /\bnetflix\b/i, /\bmicrosoft\b/i, /\btesla\b/i, /\bnvidia\b/i];
const THRESHOLD = [/\bclose\s+above\b/i, /\bclose\s+below\b/i, /\bbe\s+above\b/i, /\bbe\s+below\b/i,
  /\breach\b.*\$[\d,]+/i, /\bhit\b.*\$[\d,]+/i, /\bfall\s+(to|below)\b.*\$[\d,]+/i];
const WEATHER = [/\btemperature\b.*\d+\s*[°]?\s*[FC]\b/i, /\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b/i];
const SPORTS_BAD = [/\bo\/u\s+\d/i, /\bover\/under\b/i, /\bspread:\s/i, /\bhandicap/i,
  /\btotal\s+(corners?|kills?|goals?|rounds?|sets?|games?|maps?|points?)\b/i,
  /\bfight\s+to\s+go\s+the\s+distance\b/i, /\bbarracks\b/i, /\broshan\b/i, /\bpenta\s*kill\b/i];

function passesFilters(m, maxEndDays) {
  const q = m.question || '';
  const price = m.first_price || 0;
  const cat = (m.category || '').toLowerCase();

  if (m.neg_risk) return null; // skip neg_risk for this analysis

  const threshold = POLITICS_CATEGORIES.has(cat) ? 0.96 : 0.975;
  if (price < threshold || price > 0.995) return null;

  const liq = m.liquidity || 0;
  if (liq > 0 && liq < 500) return null;
  if ((m.volume || 0) < 3000) return null;

  // end_date check
  let daysToEnd = null;
  if (m.end_date && m.first_seen) {
    daysToEnd = (new Date(m.end_date) - new Date(m.first_seen)) / (1000*60*60*24);
    if (daysToEnd > maxEndDays) return null;
  }

  for (const p of COIN_FLIP) if (p.test(q)) return null;
  for (const p of TOXIC) if (p.test(q)) return null;
  for (const p of SLOW) if (p.test(q)) return null;

  const isFin = FINANCIAL.some(p => p.test(q));
  const isThr = THRESHOLD.some(p => p.test(q));
  if (isFin && isThr) return null;

  for (const p of WEATHER) if (p.test(q)) return null;

  if (ALL_SPORTS.has(cat)) {
    for (const p of SPORTS_BAD) if (p.test(q)) return null;
  }

  return { daysToEnd: daysToEnd || 3 }; // default 3 if no end_date
}

// Count markets per day per end_date bucket
const dailyMarkets = {}; // date -> [{daysToEnd, resolved, won}]
const fullDates = ['2026-03-18', '2026-03-19', '2026-03-20', '2026-03-21'];

for (const [mk, m] of Object.entries(markets)) {
  const date = m.first_seen ? m.first_seen.slice(0, 10) : null;
  if (!date || !fullDates.includes(date)) continue;

  const result = passesFilters(m, 14); // wide filter, we'll bucket ourselves
  if (!result) continue;

  if (!dailyMarkets[date]) dailyMarkets[date] = [];
  dailyMarkets[date].push({
    daysToEnd: result.daysToEnd,
    resolved: m.resolved || false,
    won: m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true,
    price: m.first_price
  });
}

// Market supply by bucket per day
console.log('\n' + '='.repeat(70));
console.log('  MARKET SUPPLY BY END_DATE BUCKET (regular only, per day)');
console.log('='.repeat(70));
console.log('\nDate       | 0-1d | 1-2d | 2-3d | 3-5d | 5-7d | 7+d  | Total');
console.log('-'.repeat(75));

const avgByBucket = {};
for (const b of buckets) avgByBucket[b.name] = [];

for (const date of fullDates) {
  const mkts = dailyMarkets[date] || [];
  const counts = {};
  for (const b of buckets) counts[b.name] = 0;

  for (const m of mkts) {
    for (const b of buckets) {
      if (m.daysToEnd >= b.min && m.daysToEnd < b.max) {
        counts[b.name]++;
        break;
      }
    }
  }

  let row = date + ' |';
  let total = 0;
  for (const b of buckets) {
    row += ` ${String(counts[b.name]).padStart(4)} |`;
    avgByBucket[b.name].push(counts[b.name]);
    total += counts[b.name];
  }
  console.log(row + ` ${total}`);
}

// Averages
let avgRow = 'Average    |';
const avgCounts = {};
for (const b of buckets) {
  const avg = avgByBucket[b.name].reduce((a,b) => a+b, 0) / fullDates.length;
  avgCounts[b.name] = avg;
  avgRow += ` ${avg.toFixed(0).padStart(4)} |`;
}
console.log(avgRow);

// ============= MONTE CARLO SIMULATION: FIFO vs PRIORITY =============

console.log('\n' + '='.repeat(70));
console.log('  MONTE CARLO: FIFO vs END_DATE PRIORITY');
console.log('='.repeat(70));

// Resolve time distributions by bucket (for regular markets)
// Use real data where available, interpolate where not
function getResolveTime(daysToEnd) {
  // Based on real position data:
  // 0-1d: median 3.8h, spread 1-15h
  // 1-2d: median 13.8h, spread 2-50h
  // 2-3d: median 19h (interpolated), spread 5-55h
  // 3-5d: median 20h, spread 3-60h
  // 5-7d: median 25h (interpolated), spread 5-80h
  // 7+d: median 3.9h (surprising - sports events), spread 1-40h

  let median, spread;
  if (daysToEnd < 1) { median = 3.8; spread = 4; }
  else if (daysToEnd < 2) { median = 13.8; spread = 12; }
  else if (daysToEnd < 3) { median = 19; spread = 15; }
  else if (daysToEnd < 5) { median = 20; spread = 18; }
  else if (daysToEnd < 7) { median = 25; spread = 22; }
  else { median = 5; spread = 10; } // 7+d: often sports that resolve fast

  // Log-normal-ish: median + random spread
  const r = Math.random();
  return Math.max(0.5, median + (r - 0.5) * spread * 2);
}

const BANKROLL = 600;
const BET_REG = 15;
const NEG_CAP = 250;
const BET_NEG = 8;
const FILL_RATE = 0.82;
const WIN_RATE = 0.992;
const DAYS = 30;
const RUNS = 30;

// Generate daily market arrivals (distributed across hours)
function generateDailyMarkets() {
  const mkts = [];
  // Use real average counts per bucket
  for (const b of buckets) {
    const count = avgCounts[b.name] || 0;
    for (let i = 0; i < count; i++) {
      // Random daysToEnd within bucket
      const dte = b.min + Math.random() * (Math.min(b.max, 14) - b.min);
      // Random hour of arrival (weighted toward active hours 6-22)
      const hour = Math.floor(6 + Math.random() * 16);
      mkts.push({ daysToEnd: dte, hour });
    }
  }
  return mkts;
}

function runSimulation(strategy, endDateLimit) {
  let totalPnL = 0;
  let totalBets = 0;
  let totalSkipCap = 0;
  let totalSkipEnd = 0;
  let capitalUsedHours = 0; // for utilization tracking

  for (let run = 0; run < RUNS; run++) {
    let bankroll = BANKROLL;
    let openPositions = []; // {amount, resolveAtHour, daysToEnd}
    let pnl = 0;
    let bets = 0;
    let skipCap = 0;
    let skipEnd = 0;

    for (let day = 0; day < DAYS; day++) {
      let dayMarkets = generateDailyMarkets();

      // Filter by end_date limit
      dayMarkets = dayMarkets.filter(m => m.daysToEnd <= endDateLimit);

      // Apply strategy ordering
      if (strategy === 'PRIORITY') {
        // Sort by daysToEnd ascending (shortest first)
        dayMarkets.sort((a, b) => a.daysToEnd - b.daysToEnd);
      } else if (strategy === 'REVERSE') {
        // Anti-pattern: longest first
        dayMarkets.sort((a, b) => b.daysToEnd - a.daysToEnd);
      }
      // FIFO: no sort (random arrival order)

      for (let hour = 0; hour < 24; hour++) {
        // Resolve completed positions
        const newOpen = [];
        for (const pos of openPositions) {
          if (day * 24 + hour >= pos.resolveAtHour) {
            // Resolved
            if (Math.random() < WIN_RATE) {
              pnl += pos.amount * 0.025; // ~2.5% profit on avg
            } else {
              pnl -= pos.amount;
            }
            bankroll += pos.amount;
          } else {
            newOpen.push(pos);
          }
        }
        openPositions = newOpen;

        // Place bets for this hour
        const hourMarkets = dayMarkets.filter(m => m.hour === hour);

        for (const m of hourMarkets) {
          if (Math.random() > FILL_RATE) continue; // not filled

          const betSize = BET_REG;

          if (bankroll < betSize) {
            skipCap++;
            continue;
          }

          bankroll -= betSize;
          bets++;

          const resolveHours = getResolveTime(m.daysToEnd);
          openPositions.push({
            amount: betSize,
            resolveAtHour: day * 24 + hour + resolveHours,
            daysToEnd: m.daysToEnd
          });
        }
      }
    }

    totalPnL += pnl;
    totalBets += bets;
    totalSkipCap += skipCap;
  }

  return {
    avgPnL: totalPnL / RUNS,
    avgBets: totalBets / RUNS / DAYS,
    avgSkipCap: totalSkipCap / RUNS,
  };
}

// Run all strategies
const strategies = [
  { name: 'FIFO (current)', strategy: 'FIFO', endDate: 7 },
  { name: 'END_DATE PRIORITY (short first)', strategy: 'PRIORITY', endDate: 7 },
  { name: 'REVERSE (long first, anti-pattern)', strategy: 'REVERSE', endDate: 7 },
  { name: 'PRIORITY + end≤5d', strategy: 'PRIORITY', endDate: 5 },
  { name: 'PRIORITY + end≤3d', strategy: 'PRIORITY', endDate: 3 },
  { name: 'FIFO + end≤3d', strategy: 'FIFO', endDate: 3 },
];

console.log('\nConfig: $600 bankroll, $15/bet regular, 82% fill, 30 days, ' + RUNS + ' runs\n');
console.log('Strategy                          | PnL/mo  | Bets/d | SkipCap/mo | vs FIFO');
console.log('-'.repeat(85));

let basePnl = 0;
for (const s of strategies) {
  const r = runSimulation(s.strategy, s.endDate);
  if (s.name.includes('FIFO (current)')) basePnl = r.avgPnL;
  const delta = r.avgPnL - basePnl;
  const deltaStr = delta >= 0 ? `+$${delta.toFixed(0)}` : `-$${Math.abs(delta).toFixed(0)}`;
  console.log(
    `${s.name.padEnd(33)} | $${r.avgPnL.toFixed(0).padStart(5)} | ${r.avgBets.toFixed(1).padStart(5)} | ${String(r.avgSkipCap.toFixed(0)).padStart(10)} | ${deltaStr}`
  );
}

// ============= DEEPER ANALYSIS: Capital utilization by hour =============

console.log('\n' + '='.repeat(70));
console.log('  CAPITAL UTILIZATION: FIFO vs PRIORITY (hourly snapshot)');
console.log('='.repeat(70));

function runDetailedSim(strategy, endDateLimit) {
  const hourlyFree = new Array(24).fill(0);
  const hourlyBets = new Array(24).fill(0);
  const hourlySkips = new Array(24).fill(0);
  let runs = 10;

  for (let run = 0; run < runs; run++) {
    let bankroll = BANKROLL;
    let openPositions = [];

    for (let day = 0; day < DAYS; day++) {
      let dayMarkets = generateDailyMarkets().filter(m => m.daysToEnd <= endDateLimit);

      if (strategy === 'PRIORITY') {
        dayMarkets.sort((a, b) => a.daysToEnd - b.daysToEnd);
      }

      for (let hour = 0; hour < 24; hour++) {
        // Resolve
        const newOpen = [];
        for (const pos of openPositions) {
          if (day * 24 + hour >= pos.resolveAtHour) {
            bankroll += pos.amount;
          } else {
            newOpen.push(pos);
          }
        }
        openPositions = newOpen;

        hourlyFree[hour] += bankroll;

        const hourMarkets = dayMarkets.filter(m => m.hour === hour);
        for (const m of hourMarkets) {
          if (Math.random() > FILL_RATE) continue;
          if (bankroll < BET_REG) { hourlySkips[hour]++; continue; }
          bankroll -= BET_REG;
          hourlyBets[hour]++;
          openPositions.push({
            amount: BET_REG,
            resolveAtHour: day * 24 + hour + getResolveTime(m.daysToEnd),
            daysToEnd: m.daysToEnd
          });
        }
      }
    }
  }

  return {
    avgFree: hourlyFree.map(v => v / (runs * DAYS)),
    avgBets: hourlyBets.map(v => v / (runs * DAYS)),
    avgSkips: hourlySkips.map(v => v / (runs * DAYS)),
  };
}

const fifoDetail = runDetailedSim('FIFO', 7);
const prioDetail = runDetailedSim('PRIORITY', 7);

console.log('\nHour | FIFO free$ | PRIO free$ | FIFO bets | PRIO bets | FIFO skip | PRIO skip');
console.log('-'.repeat(85));
for (let h = 6; h < 23; h++) {
  console.log(
    `  ${String(h).padStart(2)} | $${fifoDetail.avgFree[h].toFixed(0).padStart(8)} | $${prioDetail.avgFree[h].toFixed(0).padStart(8)} | ${fifoDetail.avgBets[h].toFixed(1).padStart(9)} | ${prioDetail.avgBets[h].toFixed(1).padStart(9)} | ${fifoDetail.avgSkips[h].toFixed(1).padStart(9)} | ${prioDetail.avgSkips[h].toFixed(1).padStart(9)}`
  );
}

// ============= KEY INSIGHT: How much capital is freed faster =============

console.log('\n' + '='.repeat(70));
console.log('  KEY INSIGHT: CAPITAL TURNOVER SPEED');
console.log('='.repeat(70));

// Simulate placing 40 bets, track when capital returns
function trackCapitalReturn(strategy) {
  const returns = [];

  for (let run = 0; run < 100; run++) {
    let mkts = generateDailyMarkets().filter(m => m.daysToEnd <= 7);
    if (strategy === 'PRIORITY') mkts.sort((a, b) => a.daysToEnd - b.daysToEnd);

    // Take first 40 markets
    const placed = mkts.slice(0, 40);
    const resolveTimes = placed.map(m => getResolveTime(m.daysToEnd));

    // How many resolved by hour X?
    for (let h = 1; h <= 48; h++) {
      const resolved = resolveTimes.filter(t => t <= h).length;
      if (!returns[h]) returns[h] = [];
      returns[h].push(resolved);
    }
  }

  return returns;
}

const fifoReturn = trackCapitalReturn('FIFO');
const prioReturn = trackCapitalReturn('PRIORITY');

console.log('\nAfter X hours, how many of 40 bets have resolved (= capital returned)?');
console.log('\nHours | FIFO avg | PRIO avg | PRIO advantage');
console.log('-'.repeat(55));
for (const h of [2, 4, 6, 8, 12, 16, 24, 36, 48]) {
  const fifoAvg = fifoReturn[h] ? fifoReturn[h].reduce((a,b) => a+b, 0) / fifoReturn[h].length : 0;
  const prioAvg = prioReturn[h] ? prioReturn[h].reduce((a,b) => a+b, 0) / prioReturn[h].length : 0;
  const adv = prioAvg - fifoAvg;
  console.log(
    `   ${String(h).padStart(2)}h | ${fifoAvg.toFixed(1).padStart(8)} | ${prioAvg.toFixed(1).padStart(8)} | ${adv >= 0 ? '+' : ''}${adv.toFixed(1)} bets (${(adv * BET_REG).toFixed(0)} freed)`
  );
}

console.log('\n' + '='.repeat(70));
console.log('  SUMMARY');
console.log('='.repeat(70));
console.log('\nDoes end_date priority help? See results above.');
console.log('Key question: how many bets are skipped due to capital, and does priority reduce that?');

// Save results
const results = {
  timestamp: new Date().toISOString(),
  resolveTimesByBucket: {},
  strategies: strategies.map(s => ({ name: s.name, strategy: s.strategy, endDate: s.endDate })),
};
for (const b of buckets) {
  results.resolveTimesByBucket[b.name] = {
    regCount: resolveTimesByBucket[b.name].reg.length,
    regMedian: resolveTimesByBucket[b.name].reg.length > 0
      ? resolveTimesByBucket[b.name].reg.sort((a,b) => a-b)[Math.floor(resolveTimesByBucket[b.name].reg.length/2)]
      : null,
  };
}
fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/enddate_priority_2026-03-22.json',
  JSON.stringify(results, null, 2));
console.log('\nData saved.');
