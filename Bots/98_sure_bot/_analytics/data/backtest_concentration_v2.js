/**
 * Backtest v2: Honest concentration limit impact analysis
 *
 * Simulates chronological buying/resolving with frozen capital.
 * Tests multiple concentration limit scenarios.
 *
 * Math:
 *   Buy: cost = BET_SIZE ($5), shares = cost / entry_price
 *   Win:  payout = shares * $1.00, profit = payout - cost
 *   Loss: payout = $0, loss = -cost
 */

const fs = require('fs');
const path = require('path');

// === CONFIG ===
const BET_SIZE = 5.0;
const STARTING_BALANCE = 600;
const SCANNER_PATH = path.join(__dirname, '..', '..', '..', '97_scanner', 'scanner_data.json');

// === LOAD DATA ===
const raw = JSON.parse(fs.readFileSync(SCANNER_PATH, 'utf8'));
const allMarkets = raw.markets;

// === CLASSIFY MARKET TYPE ===
function classifyMarket(question) {
  const q = question.toLowerCase();

  // tweet_post — but NOT "Quinten Post" (surname)
  if (/\btweet\b|\bretweet\b|\btruth\s+social\b/.test(q)) {
    // Check it's not just a surname
    if (!/\bquinten\s+post\b/i.test(q)) return 'tweet_post';
  }
  if (/\bpost\b/.test(q) && /\d+-\d+/.test(q)) {
    if (!/\bquinten\s+post\b/i.test(q)) return 'tweet_post';
  }

  // earthquake
  if (/\bearthquake\b|\bseismic\b|\bmagnitude\s+\d/.test(q)) return 'earthquake';

  // temperature
  if (/\btemperature\b|°[cf]\b|\bdegrees?\s+(celsius|fahrenheit)\b/.test(q)) return 'temperature';

  // crypto
  if (/\bbitcoin\b|\bethereum\b|\bsolana\b|\bbtc\b|\beth\b|\bcrypto\b/.test(q)) return 'crypto';

  // election
  if (/\bpresident\b|\belection\b|\bvote\b|\bgovernor\b|\bmayor\b|\bsenator\b|\bprime\s+minister\b/.test(q)) return 'election';

  // exact_score
  if (/\bexact\s+score\b/.test(q)) return 'exact_score';

  // esports
  if (/\bcounter-?strike\b|\bvalorant\b|\bdota\b|\bleague\s+of\s+legends\b|\blol\b|\bcs2?\b/.test(q)) return 'esports';

  // sports — "vs." or league names or spread/o-u
  if (/\bvs\.?\b|\bnba\b|\bnhl\b|\bmlb\b|\bnfl\b|\bo\/u\b|\bspread\b|\bufc\b|\bmma\b/.test(q)) return 'sports';

  return 'other';
}

// === GATHER RESOLVED MARKETS ===
const resolvedMarkets = [];
for (const [condId, m] of Object.entries(allMarkets)) {
  if (m.high_outcome_won !== true && m.high_outcome_won !== false) continue;

  const firstSeen = new Date(m.first_seen);
  let closedTime;
  if (m.resolution && m.resolution.closed_time) {
    closedTime = new Date(m.resolution.closed_time);
  } else {
    closedTime = new Date(m.end_date);
  }

  // Sanity: closed must be after first_seen
  if (closedTime <= firstSeen) {
    closedTime = new Date(firstSeen.getTime() + 3600000); // 1 hour after
  }

  resolvedMarkets.push({
    conditionId: condId,
    question: m.question,
    firstPrice: m.first_price,
    firstSeen,
    closedTime,
    won: m.high_outcome_won === true,
    category: m.category || '',
    marketType: classifyMarket(m.question),
  });
}

console.log(`Total resolved markets: ${resolvedMarkets.length}`);
console.log(`  Won: ${resolvedMarkets.filter(m => m.won).length}`);
console.log(`  Lost: ${resolvedMarkets.filter(m => !m.won).length}`);

// === Quick P&L sanity check (no limits, instant resolution) ===
{
  let totalProfit = 0;
  let wins = 0, losses = 0;
  for (const m of resolvedMarkets) {
    const shares = BET_SIZE / m.firstPrice;
    if (m.won) {
      totalProfit += shares * 1.0 - BET_SIZE;
      wins++;
    } else {
      totalProfit -= BET_SIZE;
      losses++;
    }
  }
  console.log(`\n=== SANITY CHECK (instant, no balance limit) ===`);
  console.log(`Wins: ${wins}, Losses: ${losses}, WR: ${(wins / (wins + losses) * 100).toFixed(2)}%`);
  console.log(`Total P&L: $${totalProfit.toFixed(2)}`);
  console.log(`Avg profit per bet: $${(totalProfit / (wins + losses)).toFixed(4)}`);
  console.log(`Total invested: $${((wins + losses) * BET_SIZE).toFixed(2)}`);
  console.log(`ROI: ${(totalProfit / ((wins + losses) * BET_SIZE) * 100).toFixed(2)}%`);
}

// === BUILD TIMELINE ===
// For each market: buy event at firstSeen, resolve event at closedTime
function buildTimeline(markets) {
  const events = [];
  for (let i = 0; i < markets.length; i++) {
    const m = markets[i];
    events.push({ time: m.firstSeen, type: 'buy', idx: i });
    events.push({ time: m.closedTime, type: 'resolve', idx: i });
  }
  // Sort by time, with resolves before buys at same timestamp (free up money first)
  events.sort((a, b) => {
    const dt = a.time.getTime() - b.time.getTime();
    if (dt !== 0) return dt;
    // Resolve before buy at same time
    if (a.type === 'resolve' && b.type === 'buy') return -1;
    if (a.type === 'buy' && b.type === 'resolve') return 1;
    return 0;
  });
  return events;
}

// === RUN SIMULATION ===
function simulate(markets, concentrationLimit, limitType) {
  // limitType: 'count' (max N positions per type) or 'dollar' (max $X per type)
  const timeline = buildTimeline(markets);

  let balance = STARTING_BALANCE;
  let minBalance = STARTING_BALANCE;
  let maxBalance = STARTING_BALANCE;

  // Track open positions per market type
  const openCountByType = {};   // type -> count of open positions
  const openDollarByType = {};  // type -> total $ invested in open positions

  // Track per-market state
  const marketState = new Array(markets.length).fill(null); // null = not bought, 'open', 'resolved'
  const marketShares = new Array(markets.length).fill(0);

  let totalBets = 0;
  let wins = 0, losses = 0;
  let totalProfit = 0;
  let totalInvested = 0;

  let skippedBalance = 0;
  let skippedConcentration = 0;
  let skippedBalanceWins = 0, skippedBalanceLosses = 0;
  let skippedConcWins = 0, skippedConcLosses = 0;

  for (const event of timeline) {
    const m = markets[event.idx];

    if (event.type === 'buy') {
      // Already processed? (shouldn't happen)
      if (marketState[event.idx] !== null) continue;

      const mType = m.marketType;

      // Check balance
      if (balance < BET_SIZE) {
        if (m.won) skippedBalanceWins++;
        else skippedBalanceLosses++;
        skippedBalance++;
        marketState[event.idx] = 'skipped';
        continue;
      }

      // Check concentration limit
      if (concentrationLimit !== null) {
        const currentCount = openCountByType[mType] || 0;
        const currentDollar = openDollarByType[mType] || 0;

        let blocked = false;
        if (limitType === 'count' && currentCount >= concentrationLimit) {
          blocked = true;
        } else if (limitType === 'dollar' && currentDollar >= concentrationLimit) {
          blocked = true;
        }

        if (blocked) {
          if (m.won) skippedConcWins++;
          else skippedConcLosses++;
          skippedConcentration++;
          marketState[event.idx] = 'skipped';
          continue;
        }
      }

      // Buy
      balance -= BET_SIZE;
      totalInvested += BET_SIZE;
      totalBets++;

      const shares = BET_SIZE / m.firstPrice;
      marketShares[event.idx] = shares;
      marketState[event.idx] = 'open';

      openCountByType[mType] = (openCountByType[mType] || 0) + 1;
      openDollarByType[mType] = (openDollarByType[mType] || 0) + BET_SIZE;

      if (balance < minBalance) minBalance = balance;

    } else if (event.type === 'resolve') {
      // Only resolve if we actually bought it
      if (marketState[event.idx] !== 'open') continue;

      const mType = m.marketType;
      const shares = marketShares[event.idx];

      if (m.won) {
        const payout = shares * 1.0;
        balance += payout;
        totalProfit += payout - BET_SIZE;
        wins++;
      } else {
        // Payout = $0
        totalProfit -= BET_SIZE;
        losses++;
      }

      marketState[event.idx] = 'resolved';
      openCountByType[mType] = Math.max(0, (openCountByType[mType] || 0) - 1);
      openDollarByType[mType] = Math.max(0, (openDollarByType[mType] || 0) - BET_SIZE);

      if (balance > maxBalance) maxBalance = balance;
      if (balance < minBalance) minBalance = balance;
    }
  }

  const pnl = balance - STARTING_BALANCE;
  const roi = totalInvested > 0 ? (pnl / totalInvested * 100) : 0;
  const wr = (wins + losses) > 0 ? (wins / (wins + losses) * 100) : 0;

  return {
    totalBets,
    wins,
    losses,
    winRate: wr,
    skippedBalance,
    skippedConcentration,
    skippedBalanceWins,
    skippedBalanceLosses,
    skippedConcWins,
    skippedConcLosses,
    finalBalance: balance,
    pnl,
    totalInvested,
    roi,
    maxDrawdown: STARTING_BALANCE - minBalance,
    minBalance,
    maxBalance,
    avgProfitPerBet: totalBets > 0 ? (pnl / totalBets) : 0,
  };
}

// === SCENARIOS ===
const scenarios = [
  { name: 'A: No limit', limit: null, type: null },
  { name: 'B: Max 5 per type', limit: 5, type: 'count' },
  { name: 'C: Max 10 per type', limit: 10, type: 'count' },
  { name: 'D: Max 15 per type', limit: 15, type: 'count' },
  { name: 'E: Max 20 per type', limit: 20, type: 'count' },
  { name: 'F: Max $50 per type', limit: 50, type: 'dollar' },
  { name: 'G: Max $75 per type', limit: 75, type: 'dollar' },
  { name: 'H: Max $100 per type', limit: 100, type: 'dollar' },
];

// Sort markets by firstSeen for the simulation
resolvedMarkets.sort((a, b) => a.firstSeen.getTime() - b.firstSeen.getTime());

// Show market type distribution
{
  const typeCounts = {};
  const typeWins = {};
  const typeLosses = {};
  for (const m of resolvedMarkets) {
    typeCounts[m.marketType] = (typeCounts[m.marketType] || 0) + 1;
    if (m.won) typeWins[m.marketType] = (typeWins[m.marketType] || 0) + 1;
    else typeLosses[m.marketType] = (typeLosses[m.marketType] || 0) + 1;
  }
  console.log('\n=== MARKET TYPE DISTRIBUTION ===');
  for (const [t, c] of Object.entries(typeCounts).sort((a, b) => b[1] - a[1])) {
    const w = typeWins[t] || 0;
    const l = typeLosses[t] || 0;
    console.log(`  ${t.padEnd(15)} ${String(c).padStart(6)} markets | ${w} wins, ${l} losses | WR ${(w / c * 100).toFixed(2)}%`);
  }
}

// Run all scenarios
const results = {};
console.log('\n' + '='.repeat(120));
console.log('BACKTEST RESULTS (BET_SIZE=$5, START=$600)');
console.log('='.repeat(120));

const header = [
  'Scenario'.padEnd(22),
  'Bets'.padStart(6),
  'Wins'.padStart(6),
  'Loss'.padStart(5),
  'WR%'.padStart(7),
  'Skip$'.padStart(6),
  'SkipC'.padStart(6),
  'SkCWin'.padStart(7),
  'SkCLos'.padStart(7),
  'Final$'.padStart(9),
  'P&L'.padStart(9),
  'ROI%'.padStart(8),
  'MaxDD'.padStart(8),
  '$/bet'.padStart(8),
].join(' | ');
console.log(header);
console.log('-'.repeat(header.length));

for (const s of scenarios) {
  const r = simulate(resolvedMarkets, s.limit, s.type);
  results[s.name] = r;

  const row = [
    s.name.padEnd(22),
    String(r.totalBets).padStart(6),
    String(r.wins).padStart(6),
    String(r.losses).padStart(5),
    r.winRate.toFixed(2).padStart(7),
    String(r.skippedBalance).padStart(6),
    String(r.skippedConcentration).padStart(6),
    String(r.skippedConcWins).padStart(7),
    String(r.skippedConcLosses).padStart(7),
    ('$' + r.finalBalance.toFixed(2)).padStart(9),
    ('$' + r.pnl.toFixed(2)).padStart(9),
    (r.roi.toFixed(2) + '%').padStart(8),
    ('$' + r.maxDrawdown.toFixed(2)).padStart(8),
    ('$' + r.avgProfitPerBet.toFixed(4)).padStart(8),
  ].join(' | ');
  console.log(row);
}

// === SANITY CHECK ===
console.log('\n=== SANITY CHECK (Scenario A) ===');
const a = results['A: No limit'];
const expectedWinProfit = a.wins * (BET_SIZE / 0.985 - BET_SIZE); // rough avg at 98.5c
const expectedLossAmount = a.losses * BET_SIZE;
console.log(`Wins: ${a.wins} × ~$${(BET_SIZE / 0.985 - BET_SIZE).toFixed(4)} avg profit ≈ $${expectedWinProfit.toFixed(2)}`);
console.log(`Losses: ${a.losses} × $${BET_SIZE.toFixed(2)} = -$${expectedLossAmount.toFixed(2)}`);
console.log(`Expected rough P&L ≈ $${(expectedWinProfit - expectedLossAmount).toFixed(2)}`);
console.log(`Actual P&L: $${a.pnl.toFixed(2)}`);

// Detailed profit breakdown
let exactProfit = 0;
for (const m of resolvedMarkets) {
  const shares = BET_SIZE / m.firstPrice;
  if (m.won) exactProfit += shares - BET_SIZE;
  else exactProfit -= BET_SIZE;
}
console.log(`\nExact theoretical P&L (all markets, no balance limit): $${exactProfit.toFixed(2)}`);
console.log(`  = sum of (shares - cost) for wins + sum of (-cost) for losses`);

// Show what scenario A missed due to balance
if (a.skippedBalance > 0) {
  console.log(`\nScenario A skipped ${a.skippedBalance} bets due to insufficient balance`);
  console.log(`  Of those: ${a.skippedBalanceWins} would have won, ${a.skippedBalanceLosses} would have lost`);
}

// === CONCENTRATION IMPACT ANALYSIS ===
console.log('\n=== CONCENTRATION IMPACT ===');
for (const s of scenarios) {
  if (s.limit === null) continue;
  const r = results[s.name];
  const noLimit = results['A: No limit'];
  const pnlDiff = r.pnl - noLimit.pnl;
  const betsLost = noLimit.totalBets - r.totalBets;
  console.log(`${s.name}: ${r.skippedConcentration} blocked (${r.skippedConcWins}W/${r.skippedConcLosses}L) → P&L ${pnlDiff >= 0 ? '+' : ''}$${pnlDiff.toFixed(2)} vs no-limit`);
}

// === SAVE RESULTS ===
const outputPath = path.join(__dirname, 'backtest_concentration_v2_results.json');
fs.writeFileSync(outputPath, JSON.stringify({
  config: { betSize: BET_SIZE, startingBalance: STARTING_BALANCE },
  totalResolved: resolvedMarkets.length,
  totalWon: resolvedMarkets.filter(m => m.won).length,
  totalLost: resolvedMarkets.filter(m => !m.won).length,
  scenarios: results,
  generated: new Date().toISOString(),
}, null, 2));
console.log(`\nResults saved to: ${outputPath}`);
