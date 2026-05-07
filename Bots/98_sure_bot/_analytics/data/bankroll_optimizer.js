/**
 * Bankroll Optimizer: find optimal neg_risk cap, bet sizes, end_date limits
 * for maximum monthly P&L with $600 bankroll.
 *
 * Uses REAL data from scanner_data.json (resolve times, categories, prices)
 * and positions.json (actual resolve times from bot).
 *
 * Simulates 30 days of trading, day-by-day capital flow.
 */

const fs = require('fs');

// ============= LOAD DATA =============

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const posData = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'));
const positions = Object.values(posData.positions);
const markets = scanner.markets;

// ============= STEP 1: Extract resolve times from REAL positions =============

console.log('='.repeat(70));
console.log('  BANKROLL OPTIMIZER');
console.log('  Bankroll: $600 | Data: scanner + positions');
console.log('='.repeat(70));

// Resolve times from actual bot positions (most reliable)
const wonPositions = positions.filter(p => p.status === 'won' && p.resolved_at);

function getResolveHours(p) {
  return (new Date(p.resolved_at) - new Date(p.timestamp)) / 3600000;
}

const regResolveTimes = wonPositions.filter(p => !p.neg_risk).map(getResolveHours).sort((a,b) => a-b);
const negResolveTimes = wonPositions.filter(p => p.neg_risk).map(getResolveHours).sort((a,b) => a-b);

function median(arr) { return arr.length ? arr[Math.floor(arr.length / 2)] : 0; }
function percentile(arr, p) { return arr.length ? arr[Math.floor(arr.length * p)] : 0; }

console.log('\n=== RESOLVE TIMES (from real positions) ===');
console.log('Regular: n=' + regResolveTimes.length +
  ' | median=' + median(regResolveTimes).toFixed(1) + 'h' +
  ' | p75=' + percentile(regResolveTimes, 0.75).toFixed(1) + 'h' +
  ' | p90=' + percentile(regResolveTimes, 0.9).toFixed(1) + 'h');
console.log('Neg_risk: n=' + negResolveTimes.length +
  ' | median=' + median(negResolveTimes).toFixed(1) + 'h' +
  ' | p75=' + percentile(negResolveTimes, 0.75).toFixed(1) + 'h' +
  ' | p90=' + percentile(negResolveTimes, 0.9).toFixed(1) + 'h');

// ============= STEP 2: Count qualifying markets per day from scanner =============

// Apply current filters (simplified but accurate)
const POLITICS = new Set(['politics', 'geopolitics']);
const ALL_SPORTS = new Set(['esports', 'sports_other', 'basketball', 'hockey',
  'american_football', 'tennis', 'fighting', 'cricket', 'soccer']);

const COIN_FLIP = [/\bodd\s+or\s+even\b/i, /\bodd\/even\b/i, /\bfirst\s+blood\b/i, /\bfirst\s+kill\b/i, /\bfirst\s+baron\b/i, /\bfirst\s+dragon\b/i, /\bfirst\s+tower\b/i, /\brampage\b/i, /\bfirst\s+roshan\b/i, /\bfirst\s+map\b/i];
const TOXIC = [/\bearthquake/i, /\bseismic\b/i, /\bmagnitude\s+\d/i, /\btornado/i, /\btweets?\b/i, /\bposts?\b.*\d+-\d+/i, /\d+-\d+\s*(tweets?|posts?)/i, /\btweet\b/i, /\bretweet\b/i, /how\s+many.*\bpost/i, /how\s+many.*\btweet/i, /number\s+of\s+(tweets?|posts?)/i];
const SLOW = [/\btop\b/i, /\bseason\b/i, /\bmost\b/i, /\btransit\b/i, /\bstrait\b/i, /\bships?\b/i, /\bweekly\b/i, /\bmonthly\b/i];
const FINANCIAL = [/\bbitcoin\b/i, /\bethereum\b/i, /\bsolana\b/i, /\bxrp\b/i, /\bbtc\b/i, /\beth\b/i, /\bsol\b/i, /\bdogecoin\b/i, /\bcardano\b/i, /\bnasdaq\b/i, /\bs&p\s*500\b/i, /\bcrude\s*oil\b/i, /\bgold\s*price\b/i, /\bnatural\s*gas\b/i, /\bwti\b/i, /\bbrent\b/i, /\btreasury\s*yield\b/i, /\bnvidia\b/i, /\btesla\b/i, /\bapple\b/i, /\bamazon\b/i, /\bmicrosoft\b/i, /\baapl\b/i, /\bamzn\b/i, /\bgoogl\b/i, /\btsla\b/i, /\bnvda\b/i, /\bmsft\b/i];
const THRESHOLD = [/\bclose\s+above\b/i, /\bclose\s+below\b/i, /\bbe\s+above\b/i, /\bbe\s+below\b/i, /\bbe\s+between\b/i, /\bprice\s+of\b/i, /\breach\b.*\$[\d,]+/i, /\bhit\b.*\$[\d,]+/i];
const WEATHER = [/\btemperature\b.*\d+\s*[°]?\s*[FC]\b/i];
const SPORTS_BAD = [/\bo\/u\s+\d/i, /\bover\/under\b/i, /\bspread:\s/i, /\bhandicap/i, /\btotal\s+(corners?|kills?|goals?|rounds?|sets?|games?|maps?|points?)\b/i, /\bbarracks\b/i, /\broshan\b/i, /\bpenta\s*kill\b/i];

function passesFilters(m, maxEndDays) {
  const q = m.question || '';
  const price = m.first_price || 0;
  const cat = (m.category || '').toLowerCase();

  // Price
  if (POLITICS.has(cat)) { if (price < 0.96 || price > 0.995) return null; }
  else { if (price < 0.975 || price > 0.995) return null; }

  // Volume & liquidity
  if ((m.volume || 0) < 3000) return null;
  const liq = m.liquidity || (m.snapshots && m.snapshots.length > 0 ? m.snapshots[m.snapshots.length-1].liquidity : 0) || 0;
  if (liq > 0 && liq < 500) return null;

  // End date
  if (m.end_date && m.first_seen) {
    const daysToEnd = (new Date(m.end_date) - new Date(m.first_seen)) / (1000*60*60*24);
    if (daysToEnd > maxEndDays) return null;
  }

  // Keyword filters
  if (COIN_FLIP.some(p => p.test(q))) return null;
  if (TOXIC.some(p => p.test(q))) return null;
  if (SLOW.some(p => p.test(q))) return null;
  if (FINANCIAL.some(p => p.test(q)) && THRESHOLD.some(p => p.test(q))) return null;
  if (WEATHER.some(p => p.test(q))) return null;
  if (ALL_SPORTS.has(cat) && SPORTS_BAD.some(p => p.test(q))) return null;

  return {
    negRisk: m.neg_risk || false,
    price: price,
    category: cat,
    resolved: m.resolved || false,
    won: m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true
  };
}

// ============= STEP 3: SIMULATION ENGINE =============

/**
 * Simulate 30 days of trading.
 *
 * Params:
 *  - bankroll: starting capital
 *  - negRiskCap: max $ in neg_risk open positions (0 = no neg_risk)
 *  - betSizeReg: bet size for regular markets
 *  - betSizeNeg: bet size for neg_risk markets
 *  - maxEndDays: max end_date days for filtering
 *  - fillRate: order fill probability
 *  - lossRate: probability of losing a bet
 *  - regResolveH: median resolve hours for regular
 *  - negResolveH: median resolve hours for neg_risk
 *  - regMarketsPerDay: avg qualifying regular markets per day
 *  - negMarketsPerDay: avg qualifying neg_risk markets per day
 */
function simulate(params) {
  const {
    bankroll, negRiskCap, betSizeReg, betSizeNeg,
    maxEndDays, fillRate, lossRate,
    regResolveH, negResolveH,
    regMarketsPerDay, negMarketsPerDay
  } = params;

  let balance = bankroll;
  let totalPnL = 0;
  let totalBets = 0;
  let totalRegBets = 0;
  let totalNegBets = 0;
  let totalSkippedCapital = 0;
  let totalSkippedNegCap = 0;
  let totalLosses = 0;

  // Open positions: {resolveTime (hours from start), cost, isNeg, pnl}
  let openPositions = [];

  const HOURS_PER_DAY = 24;
  const TOTAL_HOURS = 30 * HOURS_PER_DAY; // 30 days

  // Distribute markets across hours (simplified: uniform with some peak at 19 UTC)
  // From real data: peak at 19:00 UTC, quieter 04-10 UTC
  const hourWeights = [
    0.8, 0.7, 0.8, 1.2, 0.9, 0.7, 0.6, 1.0,  // 0-7
    0.3, 0.5, 0.4, 0.6, 0.6, 0.8, 0.6, 1.4,  // 8-15
    1.2, 0.9, 1.3, 3.2, 1.0, 1.1, 1.1, 1.2   // 16-23
  ];
  const weightSum = hourWeights.reduce((s,w) => s+w, 0);

  for (let hour = 0; hour < TOTAL_HOURS; hour++) {
    const hourOfDay = hour % 24;

    // Resolve completed positions
    const stillOpen = [];
    for (const pos of openPositions) {
      if (pos.resolveHour <= hour) {
        balance += pos.cost + pos.pnl;
        totalPnL += pos.pnl;
      } else {
        stillOpen.push(pos);
      }
    }
    openPositions = stillOpen;

    // Calculate current neg_risk frozen
    const negFrozen = openPositions.filter(p => p.isNeg).reduce((s,p) => s + p.cost, 0);

    // Markets arriving this hour
    const weight = hourWeights[hourOfDay] / weightSum;
    const regThisHour = Math.round(regMarketsPerDay * weight * 10) / 10; // fractional
    const negThisHour = Math.round(negMarketsPerDay * weight * 10) / 10;

    // Use probability for fractional markets
    const regCount = Math.floor(regThisHour) + (Math.random() < (regThisHour % 1) ? 1 : 0);
    const negCount = Math.floor(negThisHour) + (Math.random() < (negThisHour % 1) ? 1 : 0);

    // Place regular bets
    for (let i = 0; i < regCount; i++) {
      if (Math.random() > fillRate) continue; // not filled
      if (balance < betSizeReg) { totalSkippedCapital++; continue; }

      const isLoss = Math.random() < lossRate;
      const entryPrice = 0.985; // avg entry
      const profit = isLoss ? -betSizeReg : betSizeReg * (1/entryPrice - 1);
      if (isLoss) totalLosses++;

      // Random resolve time (sample from distribution)
      const resolveH = regResolveH * (0.5 + Math.random() * 1.5); // rough spread around median

      balance -= betSizeReg;
      openPositions.push({
        resolveHour: hour + resolveH,
        cost: betSizeReg,
        pnl: profit,
        isNeg: false
      });
      totalBets++;
      totalRegBets++;
    }

    // Place neg_risk bets
    for (let i = 0; i < negCount; i++) {
      if (Math.random() > fillRate) continue;
      if (balance < betSizeNeg) { totalSkippedCapital++; continue; }

      // Check neg_risk cap
      const currentNegFrozen = openPositions.filter(p => p.isNeg).reduce((s,p) => s + p.cost, 0);
      if (currentNegFrozen + betSizeNeg > negRiskCap) { totalSkippedNegCap++; continue; }

      const isLoss = Math.random() < lossRate;
      const entryPrice = 0.985;
      const profit = isLoss ? -betSizeNeg : betSizeNeg * (1/entryPrice - 1);
      if (isLoss) totalLosses++;

      const resolveH = negResolveH * (0.5 + Math.random() * 1.5);

      balance -= betSizeNeg;
      openPositions.push({
        resolveHour: hour + resolveH,
        cost: betSizeNeg,
        pnl: profit,
        isNeg: true
      });
      totalBets++;
      totalNegBets++;
    }
  }

  // Resolve remaining
  for (const pos of openPositions) {
    totalPnL += pos.pnl;
  }

  return {
    totalPnL: totalPnL,
    totalBets,
    totalRegBets,
    totalNegBets,
    totalLosses,
    skippedCapital: totalSkippedCapital,
    skippedNegCap: totalSkippedNegCap,
    avgBetsPerDay: totalBets / 30,
    monthlyROI: (totalPnL / bankroll * 100),
  };
}

// ============= STEP 4: COUNT ACTUAL MARKETS PER DAY =============

// Count by end_date limit
function countMarketsPerDay(maxEndDays) {
  let regTotal = 0, negTotal = 0;
  let regResolved = 0, negResolved = 0, regWon = 0, negWon = 0, regLost = 0, negLost = 0;

  // Only count full days (March 17-21)
  const fullDays = ['2026-03-17', '2026-03-18', '2026-03-19', '2026-03-20', '2026-03-21'];
  const byDate = {};

  for (const [mk, m] of Object.entries(markets)) {
    const date = m.first_seen ? m.first_seen.slice(0, 10) : null;
    if (!date || !fullDays.includes(date)) continue;

    const result = passesFilters(m, maxEndDays);
    if (!result) continue;

    if (!byDate[date]) byDate[date] = { reg: 0, neg: 0 };

    if (result.negRisk) {
      negTotal++;
      byDate[date].neg++;
      if (result.resolved) { negResolved++; if (result.won) negWon++; else negLost++; }
    } else {
      regTotal++;
      byDate[date].reg++;
      if (result.resolved) { regResolved++; if (result.won) regWon++; else regLost++; }
    }
  }

  const numDays = fullDays.length;
  return {
    regPerDay: regTotal / numDays,
    negPerDay: negTotal / numDays,
    regWinRate: regResolved > 0 ? regWon / regResolved : 0.995,
    negWinRate: negResolved > 0 ? negWon / negResolved : 0.995,
    regLossRate: regResolved > 0 ? regLost / regResolved : 0.005,
    negLossRate: negResolved > 0 ? negLost / negResolved : 0.005,
    regResolved, negResolved, regWon, negWon, regLost, negLost,
    byDate
  };
}

// ============= STEP 5: RUN OPTIMIZATION =============

console.log('\n=== MARKET SUPPLY BY END_DATE LIMIT ===');
for (const maxEnd of [3, 5, 7, 10, 14]) {
  const c = countMarketsPerDay(maxEnd);
  console.log('end_date<=' + maxEnd + 'd: reg=' + c.regPerDay.toFixed(1) + '/day, neg=' + c.negPerDay.toFixed(1) + '/day' +
    ' | reg resolved: ' + c.regWon + 'W/' + c.regLost + 'L, neg resolved: ' + c.negWon + 'W/' + c.negLost + 'L');
}

// Run many configurations
const configs = [];
const END_DATES = [3, 5, 7];
const NEG_CAPS = [0, 100, 150, 200, 250, 300, 350, 420];
const BET_SIZES_REG = [5, 8, 10, 12, 15];
const BET_SIZES_NEG = [5, 8, 10];
const FILL_RATE = 0.82;
const BANKROLL = 600;
const NUM_RUNS = 20; // Monte Carlo runs per config

console.log('\n=== RUNNING OPTIMIZATION (' +
  (END_DATES.length * NEG_CAPS.length * BET_SIZES_REG.length * BET_SIZES_NEG.length) + ' configs × ' + NUM_RUNS + ' runs) ===\n');

for (const maxEnd of END_DATES) {
  const supply = countMarketsPerDay(maxEnd);

  for (const negCap of NEG_CAPS) {
    for (const betReg of BET_SIZES_REG) {
      for (const betNeg of BET_SIZES_NEG) {
        // Skip impossible: neg cap but 0 neg markets
        if (negCap === 0 && betNeg > 0) { /* still run with 0 neg markets */ }

        let totalPnL = 0;
        let totalBets = 0;
        let totalReg = 0;
        let totalNeg = 0;
        let totalSkipCap = 0;
        let totalSkipNeg = 0;

        for (let run = 0; run < NUM_RUNS; run++) {
          const result = simulate({
            bankroll: BANKROLL,
            negRiskCap: negCap,
            betSizeReg: betReg,
            betSizeNeg: betNeg,
            maxEndDays: maxEnd,
            fillRate: FILL_RATE,
            lossRate: supply.regLossRate || 0.005,
            regResolveH: median(regResolveTimes) || 5,
            negResolveH: median(negResolveTimes) || 52,
            regMarketsPerDay: supply.regPerDay,
            negMarketsPerDay: negCap > 0 ? supply.negPerDay : 0,
          });

          totalPnL += result.totalPnL;
          totalBets += result.totalBets;
          totalReg += result.totalRegBets;
          totalNeg += result.totalNegBets;
          totalSkipCap += result.skippedCapital;
          totalSkipNeg += result.skippedNegCap;
        }

        configs.push({
          maxEnd, negCap, betReg, betNeg,
          pnl: totalPnL / NUM_RUNS,
          bets: totalBets / NUM_RUNS,
          regBets: totalReg / NUM_RUNS,
          negBets: totalNeg / NUM_RUNS,
          skipCap: totalSkipCap / NUM_RUNS,
          skipNeg: totalSkipNeg / NUM_RUNS,
          roi: (totalPnL / NUM_RUNS / BANKROLL * 100),
          betsPerDay: totalBets / NUM_RUNS / 30,
        });
      }
    }
  }
}

// Sort by P&L
configs.sort((a, b) => b.pnl - a.pnl);

console.log('=== TOP 20 CONFIGURATIONS BY MONTHLY P&L ===\n');
console.log('Rank | end_d | negCap | betReg | betNeg | PnL/mo  | ROI%  | bets/d | reg/d | neg/d | skipCap | skipNeg');
console.log('-'.repeat(115));

for (let i = 0; i < Math.min(20, configs.length); i++) {
  const c = configs[i];
  console.log(
    String(i+1).padStart(4) + ' | ' +
    String(c.maxEnd).padStart(5) + ' | ' +
    ('$'+c.negCap).padStart(6) + ' | ' +
    ('$'+c.betReg).padStart(6) + ' | ' +
    ('$'+c.betNeg).padStart(6) + ' | ' +
    ('$'+c.pnl.toFixed(1)).padStart(7) + ' | ' +
    (c.roi.toFixed(1)+'%').padStart(5) + ' | ' +
    c.betsPerDay.toFixed(1).padStart(6) + ' | ' +
    (c.regBets/30).toFixed(1).padStart(5) + ' | ' +
    (c.negBets/30).toFixed(1).padStart(5) + ' | ' +
    c.skipCap.toFixed(0).padStart(7) + ' | ' +
    c.skipNeg.toFixed(0).padStart(7)
  );
}

// Show WORST configs too
console.log('\n=== BOTTOM 5 (worst configs) ===\n');
for (let i = configs.length - 5; i < configs.length; i++) {
  const c = configs[i];
  console.log(
    String(i+1).padStart(4) + ' | end=' + c.maxEnd + ' negCap=$' + c.negCap +
    ' betReg=$' + c.betReg + ' betNeg=$' + c.betNeg +
    ' | PnL=$' + c.pnl.toFixed(1) + ' | bets/d=' + c.betsPerDay.toFixed(1) +
    ' | skipCap=' + c.skipCap.toFixed(0)
  );
}

// Show the CURRENT config for comparison
console.log('\n=== CURRENT CONFIG (for comparison) ===');
const currentSupply = countMarketsPerDay(7);
const currentResults = [];
for (let run = 0; run < NUM_RUNS; run++) {
  currentResults.push(simulate({
    bankroll: 600, negRiskCap: 420, betSizeReg: 10, betSizeNeg: 10,
    maxEndDays: 7, fillRate: 0.82, lossRate: 0.005,
    regResolveH: median(regResolveTimes), negResolveH: median(negResolveTimes),
    regMarketsPerDay: currentSupply.regPerDay, negMarketsPerDay: currentSupply.negPerDay,
  }));
}
const avgCurrent = {
  pnl: currentResults.reduce((s,r) => s+r.totalPnL, 0) / NUM_RUNS,
  bets: currentResults.reduce((s,r) => s+r.totalBets, 0) / NUM_RUNS,
  skipCap: currentResults.reduce((s,r) => s+r.skippedCapital, 0) / NUM_RUNS,
};
console.log('Current: end=7, negCap=$420, bet=$10/$10 | PnL=$' + avgCurrent.pnl.toFixed(1) +
  ' | bets/d=' + (avgCurrent.bets/30).toFixed(1) + ' | skipCap=' + avgCurrent.skipCap.toFixed(0));

// Find best in each "strategy type"
console.log('\n=== BEST CONFIG PER STRATEGY TYPE ===\n');
const strategies = [
  { name: 'A: No neg_risk (safest)', filter: c => c.negCap === 0 },
  { name: 'B: Low neg_risk ($100-150)', filter: c => c.negCap >= 100 && c.negCap <= 150 },
  { name: 'C: Medium neg_risk ($200-300)', filter: c => c.negCap >= 200 && c.negCap <= 300 },
  { name: 'D: High neg_risk ($350-420)', filter: c => c.negCap >= 350 },
  { name: 'E: Aggressive bet size ($12-15)', filter: c => c.betReg >= 12 },
  { name: 'F: Short end_date (3 days)', filter: c => c.maxEnd === 3 },
];

for (const s of strategies) {
  const filtered = configs.filter(s.filter).sort((a,b) => b.pnl - a.pnl);
  if (filtered.length === 0) continue;
  const best = filtered[0];
  console.log(s.name);
  console.log('  Best: end=' + best.maxEnd + ', negCap=$' + best.negCap +
    ', betReg=$' + best.betReg + ', betNeg=$' + best.betNeg +
    ' | PnL=$' + best.pnl.toFixed(1) + '/mo | ROI=' + best.roi.toFixed(1) + '%' +
    ' | bets/d=' + best.betsPerDay.toFixed(1) +
    ' | skipCap=' + best.skipCap.toFixed(0) + ' | skipNeg=' + best.skipNeg.toFixed(0));
  console.log();
}

// Save full results
const top50 = configs.slice(0, 50).map(c => ({
  maxEndDays: c.maxEnd, negRiskCap: c.negCap,
  betSizeRegular: c.betReg, betSizeNegRisk: c.betNeg,
  monthlyPnL: +c.pnl.toFixed(2), monthlyROI: +c.roi.toFixed(2),
  betsPerDay: +c.betsPerDay.toFixed(1),
  regBetsPerDay: +(c.regBets/30).toFixed(1),
  negBetsPerDay: +(c.negBets/30).toFixed(1),
  skippedCapital: +c.skipCap.toFixed(0),
  skippedNegCap: +c.skipNeg.toFixed(0),
}));

fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/bankroll_optimizer_2026-03-22.json',
  JSON.stringify({
    timestamp: new Date().toISOString(),
    params: { bankroll: 600, fillRate: 0.82, monteCarloRuns: NUM_RUNS },
    resolveTimesUsed: {
      regMedian: median(regResolveTimes),
      negMedian: median(negResolveTimes),
      regCount: regResolveTimes.length,
      negCount: negResolveTimes.length,
    },
    marketSupply: {
      end3: countMarketsPerDay(3),
      end5: countMarketsPerDay(5),
      end7: countMarketsPerDay(7),
    },
    top50configs: top50,
  }, null, 2)
);

console.log('\nResults saved to _analytics/data/bankroll_optimizer_2026-03-22.json');
