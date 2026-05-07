/**
 * Backtest: limiting bets to max N per multi-outcome event
 *
 * Groups scanner markets and bot positions by "event" (removing bracket numbers
 * from questions to find siblings). Then simulates:
 *   - Unlimited (current): all qualifying bets
 *   - Max 2 per event: only first 2 bets per event
 *   - Max 1 per event: only 1 bet per event
 *
 * Uses correct P&L math:
 *   win:  shares * (1 - entry_price)  = cost * (1/entry_price - 1)
 *   loss: -cost
 */

const fs = require('fs');

// ============= LOAD DATA =============

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const posData = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'));
const positions = posData.positions;
const markets = scanner.markets;

// ============= EVENT GROUPING LOGIC =============

/**
 * Extract "event key" from a question by removing bracket-specific parts
 * e.g. "Will Elon Musk post 420-439 tweets from March 17 to March 24, 2026?"
 *   -> "will elon musk post _RANGE_ tweets from march 17 to march 24, 2026?"
 *
 * "Will there be exactly 2 earthquakes..." -> "will there be exactly _N_ earthquakes..."
 * "Exact Score: Bayern Munich 3-3 Real Madrid" -> "exact score: _TEAM_ _SCORE_ _TEAM_"
 */
function extractEventKey(question) {
  let q = question.toLowerCase().trim();

  // Replace number ranges like "420-439", "60-79", "2,100-2,200"
  q = q.replace(/[\d,]+\s*-\s*[\d,]+/g, '_RANGE_');

  // Replace standalone numbers that look like brackets/counts (but keep dates/years)
  // "exactly 2 earthquakes" -> "exactly _N_ earthquakes"
  q = q.replace(/\bexactly\s+\d+/g, 'exactly _N_');

  // Replace "score: Team1 N-N Team2" patterns
  q = q.replace(/(\d+)\s*-\s*(\d+)/g, '_SCORE_');

  // Normalize whitespace
  q = q.replace(/\s+/g, ' ').trim();

  return q;
}

// ============= PART 1: ANALYZE SCANNER DATA =============

console.log('=' .repeat(70));
console.log('  BACKTEST: Max bets per multi-outcome event');
console.log('  Date: 2026-03-21');
console.log('=' .repeat(70));

// Group scanner markets by event
const scannerByEvent = {};
const mkeys = Object.keys(markets);
let resolvedCount = 0;
let resolvedWon = 0;
let resolvedLost = 0;

for (const mk of mkeys) {
  const m = markets[mk];
  if (!m.first_price || m.first_price < 0.96) continue; // only 96%+ markets (bot's range)

  const eventKey = extractEventKey(m.question);
  if (!scannerByEvent[eventKey]) scannerByEvent[eventKey] = [];
  scannerByEvent[eventKey].push(m);

  if (m.resolved) {
    resolvedCount++;
    if (m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true) {
      resolvedWon++;
    } else {
      resolvedLost++;
    }
  }
}

const eventKeys = Object.keys(scannerByEvent);
const multiOutcomeEvents = eventKeys.filter(k => scannerByEvent[k].length > 1);
const singleOutcomeEvents = eventKeys.filter(k => scannerByEvent[k].length === 1);

console.log('\n--- SCANNER DATA (96%+ markets) ---');
console.log(`Total events (unique questions): ${eventKeys.length}`);
console.log(`Single-outcome events: ${singleOutcomeEvents.length}`);
console.log(`Multi-outcome events: ${multiOutcomeEvents.length}`);
console.log(`Resolved: ${resolvedCount} (won: ${resolvedWon}, lost: ${resolvedLost})`);

// Show top multi-outcome events
const sortedMulti = multiOutcomeEvents
  .map(k => ({ key: k, count: scannerByEvent[k].length, markets: scannerByEvent[k] }))
  .sort((a, b) => b.count - a.count);

console.log('\nTop 20 multi-outcome events by bracket count:');
for (const e of sortedMulti.slice(0, 20)) {
  const resolved = e.markets.filter(m => m.resolved);
  const won = resolved.filter(m => m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true).length;
  const lost = resolved.length - won;
  console.log(`  [${e.count} brackets] ${e.key.slice(0, 80)} | resolved: ${resolved.length} (W:${won} L:${lost})`);
}

// ============= PART 2: ANALYZE BOT POSITIONS =============

console.log('\n--- BOT POSITIONS ---');

const posByEvent = {};
const posKeys = Object.keys(positions);

for (const pk of posKeys) {
  const p = positions[pk];
  const eventKey = extractEventKey(p.title);
  if (!posByEvent[eventKey]) posByEvent[eventKey] = [];
  posByEvent[eventKey].push(p);
}

const posEventKeys = Object.keys(posByEvent);
const posMulti = posEventKeys.filter(k => posByEvent[k].length > 1);

console.log(`Total position events: ${posEventKeys.length}`);
console.log(`Multi-position events: ${posMulti.length}`);

const sortedPosMulti = posMulti
  .map(k => ({ key: k, positions: posByEvent[k] }))
  .sort((a, b) => b.positions.length - a.positions.length);

console.log('\nAll multi-position events in portfolio:');
for (const e of sortedPosMulti) {
  const totalCost = e.positions.reduce((s, p) => s + p.cost_usd, 0);
  const statuses = {};
  for (const p of e.positions) statuses[p.status] = (statuses[p.status] || 0) + 1;
  const statusStr = Object.entries(statuses).map(([k, v]) => `${k}:${v}`).join(' ');
  console.log(`  [${e.positions.length} bets, $${totalCost.toFixed(2)}] ${statusStr} | ${e.key.slice(0, 70)}`);
}

// ============= PART 3: BACKTEST ON SCANNER DATA =============

console.log('\n--- BACKTEST: Scanner resolved markets at 96%+ ---');

// For each resolved market, simulate betting with a fixed $5 cost
// Group by event, then apply limits

const BET_COST = 5.00;

function simulatePnL(maxPerEvent) {
  let totalBets = 0;
  let totalWins = 0;
  let totalLosses = 0;
  let totalPnL = 0;
  let totalInvested = 0;
  let skippedByLimit = 0;
  let eventsWithSkips = 0;

  // Details for multi-outcome events
  const eventDetails = [];

  for (const eventKey of eventKeys) {
    const eventMarkets = scannerByEvent[eventKey];
    const resolved = eventMarkets.filter(m => m.resolved);
    if (resolved.length === 0) continue;

    // Sort by first_seen (chronological order - bot sees them in order)
    resolved.sort((a, b) => new Date(a.first_seen) - new Date(b.first_seen));

    let eventBets = 0;
    let eventSkipped = 0;
    let eventPnL = 0;
    let eventWins = 0;
    let eventLosses = 0;

    for (const m of resolved) {
      if (maxPerEvent > 0 && eventBets >= maxPerEvent) {
        skippedByLimit++;
        eventSkipped++;
        // Track what we skipped
        const isWin = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
        if (!isWin) {
          // We skipped a loss — that's good!
        }
        continue;
      }

      const entryPrice = m.first_price;
      const shares = BET_COST / entryPrice;
      const isWin = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;

      if (isWin) {
        const profit = shares * (1 - entryPrice); // = BET_COST * (1/entryPrice - 1)
        totalPnL += profit;
        eventPnL += profit;
        totalWins++;
        eventWins++;
      } else {
        totalPnL -= BET_COST;
        eventPnL -= BET_COST;
        totalLosses++;
        eventLosses++;
      }

      totalBets++;
      totalInvested += BET_COST;
      eventBets++;
    }

    if (eventSkipped > 0) eventsWithSkips++;

    if (resolved.length > 1) {
      eventDetails.push({
        key: eventKey,
        total: resolved.length,
        betsMade: eventBets,
        skipped: eventSkipped,
        wins: eventWins,
        losses: eventLosses,
        pnl: eventPnL
      });
    }
  }

  return {
    maxPerEvent: maxPerEvent || 'unlimited',
    totalBets,
    totalWins,
    totalLosses,
    winRate: (totalWins / (totalWins + totalLosses) * 100).toFixed(3),
    totalPnL: totalPnL.toFixed(2),
    totalInvested: totalInvested.toFixed(2),
    roi: (totalPnL / totalInvested * 100).toFixed(3),
    skippedByLimit,
    eventsWithSkips,
    eventDetails
  };
}

const unlimited = simulatePnL(0);
const max2 = simulatePnL(2);
const max1 = simulatePnL(1);

console.log('\n=== RESULTS COMPARISON ===\n');
console.log('| Metric                | Unlimited    | Max 2/event  | Max 1/event  |');
console.log('|---|---|---|---|');
console.log(`| Total bets            | ${unlimited.totalBets}          | ${max2.totalBets}          | ${max1.totalBets}          |`);
console.log(`| Wins                  | ${unlimited.totalWins}          | ${max2.totalWins}          | ${max1.totalWins}          |`);
console.log(`| Losses                | ${unlimited.totalLosses}            | ${max2.totalLosses}            | ${max1.totalLosses}            |`);
console.log(`| Win rate              | ${unlimited.winRate}%    | ${max2.winRate}%    | ${max1.winRate}%    |`);
console.log(`| Total P&L             | $${unlimited.totalPnL}     | $${max2.totalPnL}     | $${max1.totalPnL}     |`);
console.log(`| Total invested        | $${unlimited.totalInvested}  | $${max2.totalInvested}  | $${max1.totalInvested}  |`);
console.log(`| ROI                   | ${unlimited.roi}%     | ${max2.roi}%     | ${max1.roi}%     |`);
console.log(`| Skipped by limit      | 0            | ${max2.skippedByLimit}          | ${max1.skippedByLimit}          |`);
console.log(`| Events affected       | 0            | ${max2.eventsWithSkips}          | ${max1.eventsWithSkips}          |`);

// ============= PART 4: DID THE LIMIT HELP WITH THE 7 LOSSES? =============

console.log('\n\n=== LOSS ANALYSIS: Which losses would be avoided? ===\n');

// Find all losses in each scenario
function findLosses(maxPerEvent) {
  const losses = [];

  for (const eventKey of eventKeys) {
    const eventMarkets = scannerByEvent[eventKey];
    const resolved = eventMarkets.filter(m => m.resolved);
    if (resolved.length === 0) continue;

    resolved.sort((a, b) => new Date(a.first_seen) - new Date(b.first_seen));

    let eventBets = 0;

    for (const m of resolved) {
      if (maxPerEvent > 0 && eventBets >= maxPerEvent) continue;

      const isWin = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
      if (!isWin) {
        losses.push({
          question: m.question,
          price: m.first_price,
          category: m.category,
          eventKey: eventKey,
          positionInEvent: eventBets + 1,
          totalInEvent: resolved.length
        });
      }
      eventBets++;
    }
  }
  return losses;
}

const unlimitedLosses = findLosses(0);
const max2Losses = findLosses(2);
const max1Losses = findLosses(1);

console.log(`Losses with unlimited: ${unlimitedLosses.length}`);
for (const l of unlimitedLosses) {
  console.log(`  [${l.positionInEvent}/${l.totalInEvent} in event] ${l.question.slice(0, 70)} (${l.price}, ${l.category})`);
}

console.log(`\nLosses with max 2/event: ${max2Losses.length}`);
for (const l of max2Losses) {
  console.log(`  [${l.positionInEvent}/${l.totalInEvent} in event] ${l.question.slice(0, 70)} (${l.price}, ${l.category})`);
}

console.log(`\nLosses with max 1/event: ${max1Losses.length}`);
for (const l of max1Losses) {
  console.log(`  [${l.positionInEvent}/${l.totalInEvent} in event] ${l.question.slice(0, 70)} (${l.price}, ${l.category})`);
}

// ============= PART 5: IMPACT ON CURRENT PORTFOLIO =============

console.log('\n\n=== IMPACT ON CURRENT PORTFOLIO (positions.json) ===\n');

function simulatePortfolio(maxPerEvent) {
  let totalBets = 0;
  let skipped = 0;
  let totalCost = 0;
  let totalPnL = 0;
  let wonCount = 0;
  let lostCount = 0;
  let openCount = 0;
  let soldCount = 0;
  const skippedPositions = [];

  for (const eventKey of posEventKeys) {
    const eventPos = posByEvent[eventKey];
    // Sort by timestamp
    eventPos.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    let eventBets = 0;

    for (const p of eventPos) {
      if (maxPerEvent > 0 && eventBets >= maxPerEvent) {
        skipped++;
        skippedPositions.push(p);
        continue;
      }

      totalBets++;
      totalCost += p.cost_usd;

      if (p.status === 'won') {
        totalPnL += p.pnl;
        wonCount++;
      } else if (p.status === 'lost') {
        totalPnL += p.pnl;
        lostCount++;
      } else if (p.status === 'sold') {
        totalPnL += (p.pnl || 0);
        soldCount++;
      } else {
        openCount++;
      }

      eventBets++;
    }
  }

  return { totalBets, skipped, totalCost, totalPnL, wonCount, lostCount, openCount, soldCount, skippedPositions };
}

const pUnlimited = simulatePortfolio(0);
const pMax2 = simulatePortfolio(2);
const pMax1 = simulatePortfolio(1);

console.log('| Metric           | Unlimited | Max 2/event | Max 1/event |');
console.log('|---|---|---|---|');
console.log(`| Positions taken  | ${pUnlimited.totalBets}       | ${pMax2.totalBets}          | ${pMax1.totalBets}          |`);
console.log(`| Skipped          | ${pUnlimited.skipped}         | ${pMax2.skipped}           | ${pMax1.skipped}           |`);
console.log(`| Won              | ${pUnlimited.wonCount}        | ${pMax2.wonCount}          | ${pMax1.wonCount}          |`);
console.log(`| Lost             | ${pUnlimited.lostCount}         | ${pMax2.lostCount}           | ${pMax1.lostCount}           |`);
console.log(`| Open             | ${pUnlimited.openCount}        | ${pMax2.openCount}          | ${pMax1.openCount}          |`);
console.log(`| Realized P&L     | $${pUnlimited.totalPnL.toFixed(2)}   | $${pMax2.totalPnL.toFixed(2)}      | $${pMax1.totalPnL.toFixed(2)}      |`);
console.log(`| Total invested   | $${pUnlimited.totalCost.toFixed(2)} | $${pMax2.totalCost.toFixed(2)}   | $${pMax1.totalCost.toFixed(2)}   |`);

if (pMax2.skippedPositions.length > 0) {
  console.log('\nPositions that would be SKIPPED with max 2/event:');
  for (const p of pMax2.skippedPositions) {
    console.log(`  ${p.title.slice(0, 60)} | ${p.status} | $${p.cost_usd.toFixed(2)} | pnl: ${p.pnl ? '$' + p.pnl.toFixed(2) : 'open'}`);
  }
}

if (pMax1.skippedPositions.length > 0) {
  console.log('\nADDITIONAL positions skipped with max 1/event (beyond max 2):');
  const max2Set = new Set(pMax2.skippedPositions.map(p => p.order_id));
  const additional = pMax1.skippedPositions.filter(p => !max2Set.has(p.order_id));
  for (const p of additional) {
    console.log(`  ${p.title.slice(0, 60)} | ${p.status} | $${p.cost_usd.toFixed(2)} | pnl: ${p.pnl ? '$' + p.pnl.toFixed(2) : 'open'}`);
  }
}

// ============= PART 6: THEORETICAL ANALYSIS =============

console.log('\n\n=== THEORETICAL ANALYSIS ===\n');

// For a 98c entry with $5 bet:
// Win profit: $5 * (1/0.98 - 1) = $5 * 0.0204 = $0.102
// Loss: -$5.00
// Break-even: need 5.00/5.102 = 98.0% win rate

// With N bets on same event, if event "fails" all N lose simultaneously
// Expected value per bet = WR * profit - (1-WR) * loss

console.log('Key insight: In multi-outcome bracket events (e.g., "Musk tweets 420-439, 440-459, 460-479"):');
console.log('- Only ONE bracket wins (they are mutually exclusive outcomes)');
console.log('- But bot bets on MULTIPLE brackets saying "this exact range won\'t happen" (buying NO)');
console.log('- Most brackets resolve as wins (NO wins), because only 1 bracket can be YES');
console.log('- The losing bracket is the one that actually happened');
console.log('');
console.log('So if bot bets on 10 brackets of same event:');
console.log('  - 9 win: 9 × $0.10 = +$0.90 profit');
console.log('  - 1 loses: -$5.00 loss');
console.log('  - Net: -$4.10 per event IF the bracket we bet on is the one that happens');
console.log('');
console.log('Wait — the bot bets on HIGH-PRICED outcomes (97%+). Let me check what side...');

// Check actual positions - are they YES or NO bets?
console.log('\nChecking position titles for bet direction...');
const sampleTitles = posKeys.slice(0, 20).map(k => positions[k].title);
for (const t of sampleTitles) {
  console.log('  ' + t.slice(0, 80));
}

// ============= PART 7: CORRELATION ANALYSIS =============

console.log('\n\n=== CORRELATION: How correlated are brackets in the same event? ===\n');

// In scanner, find multi-bracket events where ALL are resolved
// Check: do they all win or do some lose?
let eventsAllWon = 0;
let eventsSomeLost = 0;
let lossesInMultiBracket = 0;

for (const e of sortedMulti) {
  const resolved = e.markets.filter(m => m.resolved);
  if (resolved.length < 2) continue;

  const lost = resolved.filter(m => {
    const isWin = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
    return !isWin;
  });

  if (lost.length > 0) {
    eventsSomeLost++;
    lossesInMultiBracket += lost.length;
    console.log(`EVENT WITH LOSSES: "${e.key.slice(0, 70)}" (${resolved.length} resolved, ${lost.length} lost)`);
    for (const l of lost) {
      console.log(`  LOST: ${l.question.slice(0, 70)} | price=${l.first_price}`);
    }
  } else {
    eventsAllWon++;
  }
}

console.log(`\nMulti-bracket events: all won=${eventsAllWon}, some lost=${eventsSomeLost}`);
console.log(`Losses within multi-bracket events: ${lossesInMultiBracket}`);

// Save results
const results = {
  timestamp: new Date().toISOString(),
  scanner: {
    totalEvents: eventKeys.length,
    multiOutcomeEvents: multiOutcomeEvents.length,
    singleOutcomeEvents: singleOutcomeEvents.length,
    topMultiOutcome: sortedMulti.slice(0, 30).map(e => ({
      key: e.key.slice(0, 100),
      count: e.count,
      resolved: e.markets.filter(m => m.resolved).length
    }))
  },
  backtest: { unlimited, max2, max1 },
  portfolio: {
    unlimited: { ...pUnlimited, skippedPositions: undefined },
    max2: { ...pMax2, skippedPositions: pMax2.skippedPositions.map(p => p.title) },
    max1: { ...pMax1, skippedPositions: pMax1.skippedPositions.map(p => p.title) }
  },
  losses: {
    unlimited: unlimitedLosses,
    max2: max2Losses,
    max1: max1Losses
  }
};

fs.writeFileSync(
  'C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/event_limit_backtest_2026-03-21.json',
  JSON.stringify(results, null, 2)
);

console.log('\n\nData saved to _analytics/data/event_limit_backtest_2026-03-21.json');
