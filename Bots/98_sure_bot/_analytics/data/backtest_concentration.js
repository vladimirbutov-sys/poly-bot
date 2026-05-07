/**
 * Backtest: Impact of concentration limits on 98_sure_bot ROI
 *
 * Simulates different concentration limit scenarios using resolved markets
 * from scanner_data.json to see how limiting exposure to one market type
 * affects overall performance.
 */

const fs = require('fs');
const path = require('path');

// ========== CONFIG ==========
const INITIAL_BANKROLL = 600;
const BET_SIZE = 5;
const SCANNER_PATH = path.join(__dirname, '..', '..', '..', '97_scanner', 'scanner_data.json');
const OUTPUT_PATH = path.join(__dirname, 'backtest_concentration_results.json');

// ========== MARKET TYPE CLASSIFICATION ==========
function classifyMarket(question) {
  const q = question.toLowerCase();

  // Order matters — more specific first
  if (/\btweet\b|\bpost\b|\btruth social\b/.test(q)) return 'tweet_post';
  if (/\bearthquake\b|\bseismic\b|\bmagnitude\b/.test(q)) return 'earthquake';
  if (/\btemperature\b|°[cf]|\bhighest temp\b/.test(q)) return 'temperature';
  if (/\b(bitcoin|ethereum|solana|btc|eth)\b/.test(q) && /\b(price|above|below|dip)\b/.test(q)) return 'crypto_price';
  if (/\bpresident\b|\belection\b|\bvote\b|\bgovernor\b|\bsenate\b/.test(q)) return 'election';
  if (/\bexact score\b/.test(q)) return 'exact_score';
  if (/\bcounter-strike\b|\bcs2\b|\bvalorant\b|\bdota\b|\blol\b|\bleague of legends\b/.test(q)) return 'esports';
  if (/\bfc\b|\bunited\b|\bmls\b|\bpremier league\b|\bla liga\b|\bserie a\b|\bbundesliga\b|\bligue 1\b|\bchampions league\b|\bucl\b|\buefa\b/.test(q)) return 'soccer';
  if (/\bvs\.?\b|\bnba\b|\bnhl\b|\bmlb\b|\bspread\b|\bo\/u\b|\bnfl\b|\bncaa\b|\bmma\b|\bufc\b|\bboxing\b/.test(q)) return 'sports_other';

  return 'other';
}

// ========== LOAD DATA ==========
console.log('Loading scanner data...');
const rawData = JSON.parse(fs.readFileSync(SCANNER_PATH, 'utf8'));
const allMarkets = rawData.markets;
console.log(`Total markets in scanner: ${Object.keys(allMarkets).length}`);

// Filter to resolved markets only (high_outcome_won is true or false)
const resolvedMarkets = [];
for (const [tokenId, m] of Object.entries(allMarkets)) {
  if (m.high_outcome_won === true || m.high_outcome_won === false) {
    const closedTime = m.resolution?.closed_time
      ? new Date(m.resolution.closed_time).getTime()
      : m.end_date
        ? new Date(m.end_date).getTime()
        : null;

    if (!closedTime || !m.first_seen || !m.first_price) continue;

    resolvedMarkets.push({
      tokenId,
      question: m.question,
      category: m.category,
      type: classifyMarket(m.question),
      firstSeen: new Date(m.first_seen).getTime(),
      firstSeenStr: m.first_seen,
      entryPrice: m.first_price,
      won: m.high_outcome_won === true,
      closedTime,
      closedTimeStr: m.resolution?.closed_time || m.end_date,
      shares: BET_SIZE / m.first_price, // how many shares $5 buys
    });
  }
}

console.log(`Resolved markets with valid data: ${resolvedMarkets.length}`);
console.log(`  Won: ${resolvedMarkets.filter(m => m.won).length}`);
console.log(`  Lost: ${resolvedMarkets.filter(m => !m.won).length}`);

// Sort by first_seen (chronological order)
resolvedMarkets.sort((a, b) => a.firstSeen - b.firstSeen);

// Show type distribution
const typeDist = {};
for (const m of resolvedMarkets) {
  typeDist[m.type] = typeDist[m.type] || { total: 0, won: 0, lost: 0 };
  typeDist[m.type].total++;
  if (m.won) typeDist[m.type].won++;
  else typeDist[m.type].lost++;
}
console.log('\nMarket type distribution:');
for (const [type, stats] of Object.entries(typeDist).sort((a,b) => b[1].total - a[1].total)) {
  console.log(`  ${type}: ${stats.total} (won: ${stats.won}, lost: ${stats.lost})`);
}

// ========== SIMULATION ENGINE ==========

/**
 * Events:
 * - OPEN: market first seen (try to bet)
 * - CLOSE: market resolved (collect winnings or mark loss)
 */
function runSimulation(markets, limitCheck) {
  // Build event timeline
  const events = [];
  for (let i = 0; i < markets.length; i++) {
    const m = markets[i];
    events.push({ time: m.firstSeen, action: 'open', idx: i });
    events.push({ time: m.closedTime, action: 'close', idx: i });
  }
  // Sort by time, opens before closes at same time
  events.sort((a, b) => a.time - b.time || (a.action === 'open' ? -1 : 1));

  let bankroll = INITIAL_BANKROLL;
  let maxBankroll = bankroll;
  let minBankroll = bankroll;
  let totalBets = 0;
  let wins = 0;
  let losses = 0;
  let skippedTotal = 0;
  let skippedWouldWin = 0;
  let skippedWouldLose = 0;
  let skippedByBankroll = 0;

  // Track open positions per type
  const openByType = {};   // type -> count
  const openCostByType = {}; // type -> total $ invested
  const isOpen = new Set(); // set of market indices currently open

  for (const event of events) {
    const m = markets[event.idx];

    if (event.action === 'open') {
      // Check bankroll
      if (bankroll < BET_SIZE) {
        skippedByBankroll++;
        if (m.won) skippedWouldWin++;
        else skippedWouldLose++;
        skippedTotal++;
        continue;
      }

      // Check concentration limit
      const currentCount = openByType[m.type] || 0;
      const currentCost = openCostByType[m.type] || 0;

      if (!limitCheck(m.type, currentCount, currentCost, bankroll)) {
        // Skipped due to concentration limit
        if (m.won) skippedWouldWin++;
        else skippedWouldLose++;
        skippedTotal++;
        continue;
      }

      // Place bet
      bankroll -= BET_SIZE;
      openByType[m.type] = currentCount + 1;
      openCostByType[m.type] = currentCost + BET_SIZE;
      isOpen.add(event.idx);
      totalBets++;

      minBankroll = Math.min(minBankroll, bankroll);

    } else if (event.action === 'close') {
      // Only process if we actually bet on this market
      if (!isOpen.has(event.idx)) continue;
      isOpen.delete(event.idx);

      openByType[m.type] = (openByType[m.type] || 1) - 1;
      openCostByType[m.type] = (openCostByType[m.type] || BET_SIZE) - BET_SIZE;

      if (m.won) {
        bankroll += m.shares; // shares = $5 / entry_price, each share pays $1
        wins++;
      } else {
        // Lost — get nothing back
        losses++;
      }

      maxBankroll = Math.max(maxBankroll, bankroll);
      minBankroll = Math.min(minBankroll, bankroll);
    }
  }

  const finalBalance = bankroll;
  const pnl = finalBalance - INITIAL_BANKROLL;
  const roi = (pnl / INITIAL_BANKROLL) * 100;
  const maxDrawdown = maxBankroll - minBankroll;
  const winRate = totalBets > 0 ? (wins / totalBets) * 100 : 0;
  const preventedLosses = skippedWouldLose;

  return {
    totalBets,
    wins,
    losses,
    winRate: Math.round(winRate * 100) / 100,
    finalBalance: Math.round(finalBalance * 100) / 100,
    pnl: Math.round(pnl * 100) / 100,
    roi: Math.round(roi * 100) / 100,
    maxDrawdown: Math.round(maxDrawdown * 100) / 100,
    skippedTotal,
    skippedWouldWin,
    skippedWouldLose,
    preventedLosses,
    skippedByBankroll,
  };
}

// ========== SCENARIOS ==========

const scenarios = [
  {
    name: 'A: No limit (current)',
    check: () => true, // always allow
  },
  {
    name: 'B: Max 10 positions/type',
    check: (type, count) => count < 10,
  },
  {
    name: 'C: Max 15 positions/type',
    check: (type, count) => count < 15,
  },
  {
    name: 'D: Max 20 positions/type',
    check: (type, count) => count < 20,
  },
  {
    name: 'E: Max 15% bankroll/type',
    check: (type, count, cost, bankroll) => cost < (INITIAL_BANKROLL * 0.15), // $90
  },
  {
    name: 'F: Max 25% bankroll/type',
    check: (type, count, cost, bankroll) => cost < (INITIAL_BANKROLL * 0.25), // $150
  },
];

// ========== RUN ==========
console.log('\n========================================');
console.log('BACKTEST: Concentration Limit Impact');
console.log('========================================');
console.log(`Bankroll: $${INITIAL_BANKROLL} | Bet size: $${BET_SIZE}`);
console.log(`Resolved markets: ${resolvedMarkets.length}`);
console.log('========================================\n');

const results = [];

for (const scenario of scenarios) {
  console.log(`Running: ${scenario.name}...`);
  const result = runSimulation(resolvedMarkets, scenario.check);
  results.push({ scenario: scenario.name, ...result });
}

// ========== OUTPUT TABLE ==========
console.log('\n' + '='.repeat(140));
console.log('RESULTS');
console.log('='.repeat(140));

// Header
const header = [
  'Scenario'.padEnd(28),
  'Bets'.padStart(6),
  'Wins'.padStart(6),
  'Losses'.padStart(7),
  'WR%'.padStart(7),
  'Final$'.padStart(10),
  'P&L'.padStart(10),
  'ROI%'.padStart(8),
  'Skipped'.padStart(8),
  'Skip Win'.padStart(9),
  'Skip Loss'.padStart(10),
  'Prevented'.padStart(10),
];
console.log(header.join(' | '));
console.log('-'.repeat(140));

for (const r of results) {
  const row = [
    r.scenario.padEnd(28),
    String(r.totalBets).padStart(6),
    String(r.wins).padStart(6),
    String(r.losses).padStart(7),
    r.winRate.toFixed(2).padStart(7),
    ('$' + r.finalBalance.toFixed(2)).padStart(10),
    ((r.pnl >= 0 ? '+$' : '-$') + Math.abs(r.pnl).toFixed(2)).padStart(10),
    (r.roi.toFixed(2) + '%').padStart(8),
    String(r.skippedTotal).padStart(8),
    String(r.skippedWouldWin).padStart(9),
    String(r.skippedWouldLose).padStart(10),
    String(r.preventedLosses).padStart(10),
  ];
  console.log(row.join(' | '));
}

console.log('='.repeat(140));

// ========== MARKDOWN TABLE ==========
console.log('\n\nMarkdown table:\n');
console.log('| Сценарий | Ставок | Побед | Поражений | WR% | P&L | ROI% | Пропущено | Предотвр. поражений |');
console.log('|---|---|---|---|---|---|---|---|---|');
for (const r of results) {
  const pnlStr = r.pnl >= 0 ? `+$${r.pnl.toFixed(2)}` : `-$${Math.abs(r.pnl).toFixed(2)}`;
  console.log(`| ${r.scenario} | ${r.totalBets} | ${r.wins} | ${r.losses} | ${r.winRate}% | ${pnlStr} | ${r.roi}% | ${r.skippedTotal} | ${r.preventedLosses} |`);
}

// ========== ADDITIONAL ANALYSIS ==========
console.log('\n\n========================================');
console.log('DETAILED: What gets skipped in scenario B (max 10/type)?');
console.log('========================================');

// Run scenario B again with tracking
{
  const events = [];
  for (let i = 0; i < resolvedMarkets.length; i++) {
    const m = resolvedMarkets[i];
    events.push({ time: m.firstSeen, action: 'open', idx: i });
    events.push({ time: m.closedTime, action: 'close', idx: i });
  }
  events.sort((a, b) => a.time - b.time || (a.action === 'open' ? -1 : 1));

  let bankroll = INITIAL_BANKROLL;
  const openByType = {};
  const isOpen = new Set();
  const skippedByType = {};

  for (const event of events) {
    const m = resolvedMarkets[event.idx];
    if (event.action === 'open') {
      if (bankroll < BET_SIZE) continue;
      const count = openByType[m.type] || 0;
      if (count >= 10) {
        skippedByType[m.type] = skippedByType[m.type] || { total: 0, wins: 0, losses: 0 };
        skippedByType[m.type].total++;
        if (m.won) skippedByType[m.type].wins++;
        else skippedByType[m.type].losses++;
        continue;
      }
      bankroll -= BET_SIZE;
      openByType[m.type] = count + 1;
      isOpen.add(event.idx);
    } else if (event.action === 'close') {
      if (!isOpen.has(event.idx)) continue;
      isOpen.delete(event.idx);
      openByType[m.type] = (openByType[m.type] || 1) - 1;
      if (m.won) bankroll += m.shares;
    }
  }

  console.log('\nSkipped bets by type in scenario B:');
  for (const [type, s] of Object.entries(skippedByType).sort((a,b) => b[1].total - a[1].total)) {
    console.log(`  ${type}: ${s.total} skipped (${s.wins} would win, ${s.losses} would lose)`);
  }
}

// ========== SAVE RESULTS ==========
const output = {
  config: { initialBankroll: INITIAL_BANKROLL, betSize: BET_SIZE, totalResolvedMarkets: resolvedMarkets.length },
  typeDistribution: typeDist,
  scenarios: results,
  generated: new Date().toISOString(),
};

fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
console.log(`\nResults saved to: ${OUTPUT_PATH}`);
