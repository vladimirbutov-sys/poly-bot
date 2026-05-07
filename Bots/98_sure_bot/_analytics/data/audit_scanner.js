const fs = require('fs');
const path = require('path');

// ---- Load data ----
console.log('Loading scanner_data.json...');
const scannerRaw = fs.readFileSync(path.join(__dirname, '..', '..', '..', '97_scanner', 'scanner_data.json'), 'utf8');
const scannerData = JSON.parse(scannerRaw);
console.log(`Scanner: loaded ${Object.keys(scannerData.markets).length} markets`);

const positionsRaw = fs.readFileSync(path.join(__dirname, '..', '..', 'positions.json'), 'utf8');
const positionsData = JSON.parse(positionsRaw);

const healthRaw = fs.readFileSync(path.join(__dirname, 'portfolio_health_2026-03-21.json'), 'utf8');
const healthData = JSON.parse(healthRaw);

// ---- Step 2: Build loss map from scanner ----
const markets = scannerData.markets;
const allMarkets = Object.values(markets);
const resolvedMarkets = allMarkets.filter(m => m.resolved === true);
const losses = resolvedMarkets.filter(m => m.high_outcome_won === false);
const wins = resolvedMarkets.filter(m => m.high_outcome_won === true);

console.log(`\nResolved markets: ${resolvedMarkets.length}`);
console.log(`Wins (high_outcome_won=true): ${wins.length}`);
console.log(`Losses (high_outcome_won=false): ${losses.length}`);
console.log(`Win rate: ${(wins.length / resolvedMarkets.length * 100).toFixed(2)}%`);

// ---- Price buckets ----
function getPriceBucket(price) {
  if (price >= 0.99) return '99+';
  if (price >= 0.98) return '98-99';
  if (price >= 0.97) return '97-98';
  if (price >= 0.96) return '96-97';
  if (price >= 0.95) return '95-96';
  return 'below-95';
}

// ---- Categorize losses by price bucket ----
const lossByBucket = {};
const winByBucket = {};
for (const m of losses) {
  const bucket = getPriceBucket(m.first_price || m.max_price_seen || 0);
  lossByBucket[bucket] = (lossByBucket[bucket] || 0) + 1;
}
for (const m of wins) {
  const bucket = getPriceBucket(m.first_price || m.max_price_seen || 0);
  winByBucket[bucket] = (winByBucket[bucket] || 0) + 1;
}

console.log('\n=== Loss rate by price bucket ===');
for (const bucket of ['99+', '98-99', '97-98', '96-97', '95-96', 'below-95']) {
  const l = lossByBucket[bucket] || 0;
  const w = winByBucket[bucket] || 0;
  const total = l + w;
  if (total > 0) {
    console.log(`  ${bucket}: ${l} losses / ${total} total = ${(l/total*100).toFixed(1)}% loss rate`);
  }
}

// ---- Categorize losses by category ----
const lossByCategory = {};
const winByCategory = {};
for (const m of losses) {
  const cat = m.category || 'unknown';
  lossByCategory[cat] = (lossByCategory[cat] || 0) + 1;
}
for (const m of wins) {
  const cat = m.category || 'unknown';
  winByCategory[cat] = (winByCategory[cat] || 0) + 1;
}

console.log('\n=== Loss rate by category (sorted by loss count) ===');
const catEntries = Object.entries(lossByCategory).sort((a,b) => b[1] - a[1]);
for (const [cat, lossCount] of catEntries) {
  const w = winByCategory[cat] || 0;
  const total = lossCount + w;
  console.log(`  ${cat}: ${lossCount} losses / ${total} total = ${(lossCount/total*100).toFixed(1)}% loss rate`);
}

// ---- Pattern detection on loss questions ----
const patterns = [
  { name: 'earthquake', regex: /earthquake|seismic|magnitude\s+\d/i },
  { name: 'tweet_bracket', regex: /\d+-\d+\s*(tweets?|posts?)|tweets?\s+from|posts?\s+from.*\d+-\d+/i },
  { name: 'post_bracket', regex: /post\s+\d+-\d+|how\s+many.*post|number\s+of\s+posts?/i },
  { name: 'temperature', regex: /temperature|highest\s+temp|\d+\s*[°]?\s*[FC]/i },
  { name: 'over_under', regex: /\bo\/u\b|over\/under|over\s*\/\s*under/i },
  { name: 'spread', regex: /\bspread\b/i },
  { name: 'exact_score', regex: /exact\s+score/i },
  { name: 'total_goals_kills', regex: /\btotal\s+(maps?|kills?|rounds?|points?|goals?)\b/i },
  { name: 'handicap', regex: /\bhandi?cap\b/i },
  { name: 'coin_flip_esports', regex: /\bfirst\s+(blood|kill|baron|dragon|tower|map|roshan)\b|\brampage\b|\bodd\s+or\s+even\b/i },
  { name: 'bitcoin_crypto', regex: /\bbitcoin\b|\beth\b|\bethereum\b|\bbtc\b|\bcrypto\b|\bsolana\b/i },
  { name: 'financial', regex: /\bclose\s+(above|below)\b|\bprice\s+of\b|\breach\b.*\$|\bhit\b.*\$/i },
  { name: 'shipping_strait', regex: /\bstrait\b|\bships?\b|\btransit\b/i },
  { name: 'election_win', regex: /\bwin\b.*\belection\b|\belection\b.*\bwin\b|\bmayoral\b|\bgubernatorial\b|\bprime\s+minister\b/i },
  { name: 'draw_market', regex: /end\s+in\s+a\s+draw|draw\?/i },
  { name: 'will_say_word', regex: /will\s+\w+\s+say\b|say\s+"[^"]+"/i },
  { name: 'weekly_counting', regex: /\bweek\b.*\d+-\d+|\d+-\d+.*\bweek\b/i },
  { name: 'bracket_range', regex: /\d+-\d+.*from\s+\w+\s+\d+\s+to/i },
  { name: 'sports_win', regex: /will\s+.+\s+win\s+on\s+\d{4}-\d{2}-\d{2}/i },
  { name: 'anytime_goalscorer', regex: /anytime\s+goalscorer/i },
  { name: 'dip_to', regex: /dip\s+to\b/i },
  { name: 'golf_win', regex: /win\s+the\s+\d{4}\s+.*championship|win\s+the\s+\d{4}\s+.*open/i },
  { name: 'seats_bracket', regex: /win\s+\d+-\d+\s+seats/i },
  { name: 'score_rating', regex: /score\s+at\s+least\s+\d+|rotten\s+tomatoes|tomatometer/i },
  { name: 'album_sales', regex: /album\s+sales|debut\s+week/i },
  { name: 'right_wing_wave', regex: /right.wing\s+wave|wave\s+in.*elections/i },
];

// Only count losses at 97%+ (relevant to bot)
const highPriceLosses = losses.filter(m => (m.first_price || m.max_price_seen || 0) >= 0.97);
const highPriceWins = wins.filter(m => (m.first_price || m.max_price_seen || 0) >= 0.97);

console.log(`\n=== High-price losses (97%+): ${highPriceLosses.length} / ${highPriceLosses.length + highPriceWins.length} resolved ===`);

const patternLossMap = {};
const patternWinMap = {};
const patternLossExamples = {};

for (const m of highPriceLosses) {
  const q = m.question || '';
  let matched = false;
  for (const p of patterns) {
    if (p.regex.test(q)) {
      patternLossMap[p.name] = (patternLossMap[p.name] || 0) + 1;
      if (!patternLossExamples[p.name]) patternLossExamples[p.name] = [];
      if (patternLossExamples[p.name].length < 3) {
        patternLossExamples[p.name].push({ question: q, price: m.first_price, category: m.category });
      }
      matched = true;
    }
  }
  if (!matched) {
    patternLossMap['_other'] = (patternLossMap['_other'] || 0) + 1;
    if (!patternLossExamples['_other']) patternLossExamples['_other'] = [];
    if (patternLossExamples['_other'].length < 5) {
      patternLossExamples['_other'].push({ question: q, price: m.first_price, category: m.category });
    }
  }
}
for (const m of highPriceWins) {
  const q = m.question || '';
  for (const p of patterns) {
    if (p.regex.test(q)) {
      patternWinMap[p.name] = (patternWinMap[p.name] || 0) + 1;
    }
  }
}

console.log('\n=== Pattern loss map (97%+ price, sorted by loss count) ===');
const patternEntries = Object.entries(patternLossMap).sort((a,b) => b[1] - a[1]);
for (const [name, count] of patternEntries) {
  const w = patternWinMap[name] || 0;
  const total = count + w;
  const lossRate = (count / total * 100).toFixed(1);
  console.log(`  ${name}: ${count} losses / ${total} total = ${lossRate}% loss rate`);
  if (patternLossExamples[name]) {
    for (const ex of patternLossExamples[name].slice(0, 2)) {
      console.log(`    ex: "${ex.question.slice(0, 80)}" (price=${ex.price}, cat=${ex.category})`);
    }
  }
}

// ---- Step 3: Map open positions against loss patterns ----
console.log('\n\n========================================');
console.log('=== STEP 3: OPEN POSITIONS vs SCANNER LOSS PATTERNS ===');
console.log('========================================\n');

const openPositions = healthData.positions; // already open

const positionRisks = [];
for (const pos of openPositions) {
  const q = pos.market_question || pos.title || '';
  const matchedPatterns = [];

  for (const p of patterns) {
    if (p.regex.test(q)) {
      const losses = patternLossMap[p.name] || 0;
      const wins = patternWinMap[p.name] || 0;
      const total = losses + wins;
      const lossRate = total > 0 ? (losses / total * 100) : 0;
      matchedPatterns.push({
        pattern: p.name,
        losses,
        wins,
        total,
        lossRate
      });
    }
  }

  const maxLossRate = matchedPatterns.length > 0
    ? Math.max(...matchedPatterns.map(p => p.lossRate))
    : 0;

  positionRisks.push({
    title: q,
    order_id: pos.order_id,
    entry_price: pos.entry_price,
    current_price: pos.current_price,
    unrealized_pnl: pos.unrealized_pnl,
    cost_usd: pos.cost_usd,
    risk_level: pos.risk_level,
    matchedPatterns,
    maxLossRate,
  });
}

// Sort by max loss rate descending
positionRisks.sort((a,b) => b.maxLossRate - a.maxLossRate);

console.log('Open positions sorted by scanner loss rate of their pattern:\n');
for (const pos of positionRisks) {
  if (pos.matchedPatterns.length > 0) {
    console.log(`[${pos.risk_level}] "${pos.title.slice(0, 70)}" | entry=${pos.entry_price} cur=${pos.current_price} pnl=${pos.unrealized_pnl?.toFixed(2)}`);
    for (const mp of pos.matchedPatterns) {
      console.log(`   -> pattern "${mp.pattern}": ${mp.losses}L/${mp.total}T = ${mp.lossRate.toFixed(1)}% loss rate`);
    }
  } else {
    console.log(`[${pos.risk_level}] "${pos.title.slice(0, 70)}" | entry=${pos.entry_price} cur=${pos.current_price} pnl=${pos.unrealized_pnl?.toFixed(2)} => NO PATTERN MATCH`);
  }
}

// ---- Step 4: Filter gap analysis ----
console.log('\n\n========================================');
console.log('=== STEP 4: FILTER GAP ANALYSIS ===');
console.log('========================================\n');

// Current filters in the bot
const currentFilterPatterns = {
  earthquake: true,
  tweet_post_bracket: true, // TOXIC_KEYWORDS
  temperature: true, // WEATHER_PATTERNS
  over_under: true, // SPORTS_BAD_PATTERNS
  spread: true, // SPORTS_BAD_PATTERNS
  handicap: true, // SPORTS_BAD_PATTERNS
  total_goals_kills: true, // SPORTS_BAD_PATTERNS
  coin_flip_esports: true, // COIN_FLIP_PATTERNS
  financial_threshold: true, // THRESHOLD_PATTERNS + FINANCIAL_ASSETS
  shipping_strait: true, // SLOW_KEYWORDS (transit, strait, ships)
  slow_keywords: true, // top, season, most
};

const notCoveredPatterns = {};
for (const [pName, lossCount] of patternEntries) {
  if (pName === '_other') continue;

  // Check if covered
  let covered = false;
  if (pName === 'earthquake') covered = true;
  if (pName === 'tweet_bracket') covered = true;
  if (pName === 'post_bracket') covered = true; // partially by TOXIC_KEYWORDS
  if (pName === 'temperature') covered = true;
  if (pName === 'over_under') covered = true; // SPORTS_BAD_PATTERNS (only in sports)
  if (pName === 'spread') covered = true; // SPORTS_BAD_PATTERNS (only in sports)
  if (pName === 'exact_score') covered = false; // NOT covered!
  if (pName === 'total_goals_kills') covered = true;
  if (pName === 'handicap') covered = true;
  if (pName === 'coin_flip_esports') covered = true;
  if (pName === 'bitcoin_crypto') covered = true; // FINANCIAL_ASSETS
  if (pName === 'financial') covered = true; // THRESHOLD_PATTERNS
  if (pName === 'shipping_strait') covered = true; // SLOW_KEYWORDS
  if (pName === 'election_win') covered = false; // NOT covered
  if (pName === 'draw_market') covered = false; // NOT covered
  if (pName === 'will_say_word') covered = false; // NOT covered
  if (pName === 'weekly_counting') covered = false; // partially SLOW_KEYWORDS
  if (pName === 'bracket_range') covered = true; // TOXIC_KEYWORDS
  if (pName === 'sports_win') covered = false; // This is the "good" one, not filtered
  if (pName === 'anytime_goalscorer') covered = false; // NOT covered
  if (pName === 'dip_to') covered = false; // NOT covered
  if (pName === 'golf_win') covered = false; // NOT covered
  if (pName === 'seats_bracket') covered = false; // NOT covered
  if (pName === 'score_rating') covered = false;
  if (pName === 'album_sales') covered = false;
  if (pName === 'right_wing_wave') covered = false;

  const winCount = patternWinMap[pName] || 0;
  const total = lossCount + winCount;
  const lossRate = total > 0 ? (lossCount / total * 100) : 0;

  if (!covered && lossCount > 0) {
    notCoveredPatterns[pName] = { losses: lossCount, wins: winCount, total, lossRate };
  }
}

console.log('Patterns with losses NOT covered by current filters:\n');
const gapEntries = Object.entries(notCoveredPatterns).sort((a,b) => b[1].losses - a[1].losses);
for (const [name, data] of gapEntries) {
  console.log(`  ${name}: ${data.losses} losses / ${data.total} total = ${data.lossRate.toFixed(1)}% loss rate`);
  if (patternLossExamples[name]) {
    for (const ex of patternLossExamples[name].slice(0, 2)) {
      console.log(`    ex: "${ex.question.slice(0, 90)}"`);
    }
  }
}

// ---- Count how many open positions would be affected ----
console.log('\n\n========================================');
console.log('=== STEP 5: SPECIFIC RECOMMENDATIONS ===');
console.log('========================================\n');

// Count open positions in bot matching uncovered patterns
const openInBot = Object.values(positionsData.positions).filter(p => p.status === 'open');
console.log(`Total open positions in bot: ${openInBot.length}`);

for (const [name, data] of gapEntries) {
  const matchingPattern = patterns.find(p => p.name === name);
  if (!matchingPattern) continue;

  const affectedOpen = openInBot.filter(p => {
    const q = (p.title || '').toLowerCase();
    return matchingPattern.regex.test(p.title || '');
  });

  console.log(`\n--- ${name} ---`);
  console.log(`  Scanner: ${data.losses} losses / ${data.total} total (${data.lossRate.toFixed(1)}% loss rate)`);
  console.log(`  Open positions affected: ${affectedOpen.length}`);
  for (const ap of affectedOpen) {
    const healthEntry = openPositions.find(h => h.order_id === ap.order_id);
    const curPrice = healthEntry ? healthEntry.current_price : '?';
    const pnl = healthEntry ? healthEntry.unrealized_pnl : '?';
    console.log(`    - "${(ap.title || '').slice(0, 60)}" entry=${ap.entry_price} cur=${curPrice} pnl=${typeof pnl === 'number' ? pnl.toFixed(2) : pnl}`);
  }
  console.log(`  Would lose from filter: ${data.wins} good bets`);
  console.log(`  Would prevent: ${data.losses} bad bets`);
  console.log(`  Net benefit: prevent ${data.losses} losses, lose ${data.wins} wins`);
}

// ---- Also check: exact_score is in bot but not filtered ----
console.log('\n\n--- SPECIAL: Exact Score markets (bot has them open!) ---');
const exactScoreOpen = openInBot.filter(p => /exact\s+score/i.test(p.title || ''));
console.log(`  Open exact_score positions: ${exactScoreOpen.length}`);
for (const p of exactScoreOpen) {
  const h = openPositions.find(hp => hp.order_id === p.order_id);
  console.log(`    - "${(p.title || '').slice(0, 60)}" entry=${p.entry_price} cur=${h?.current_price || '?'}`);
}
const exactLosses = highPriceLosses.filter(m => /exact\s+score/i.test(m.question || ''));
const exactWins = highPriceWins.filter(m => /exact\s+score/i.test(m.question || ''));
console.log(`  Scanner: ${exactLosses.length} losses / ${exactLosses.length + exactWins.length} total = ${(exactLosses.length / (exactLosses.length + exactWins.length) * 100).toFixed(1)}% loss rate`);

// ---- SPECIAL: Draw markets ----
console.log('\n--- SPECIAL: Draw markets ---');
const drawOpen = openInBot.filter(p => /draw\?|end\s+in\s+a\s+draw/i.test(p.title || ''));
console.log(`  Open draw positions: ${drawOpen.length}`);
for (const p of drawOpen) {
  const h = openPositions.find(hp => hp.order_id === p.order_id);
  console.log(`    - "${(p.title || '').slice(0, 60)}" entry=${p.entry_price} cur=${h?.current_price || '?'}`);
}
const drawLosses = highPriceLosses.filter(m => /draw\?|end\s+in\s+a\s+draw/i.test(m.question || ''));
const drawWins = highPriceWins.filter(m => /draw\?|end\s+in\s+a\s+draw/i.test(m.question || ''));
console.log(`  Scanner: ${drawLosses.length} losses / ${drawLosses.length + drawWins.length} total = ${drawLosses.length + drawWins.length > 0 ? (drawLosses.length / (drawLosses.length + drawWins.length) * 100).toFixed(1) : 0}% loss rate`);

// ---- SPECIAL: "dip to" Bitcoin markets ----
console.log('\n--- SPECIAL: "dip to" / crypto threshold markets ---');
const dipOpen = openInBot.filter(p => /dip\s+to/i.test(p.title || ''));
console.log(`  Open "dip to" positions: ${dipOpen.length}`);
for (const p of dipOpen) {
  const h = openPositions.find(hp => hp.order_id === p.order_id);
  console.log(`    - "${(p.title || '').slice(0, 60)}" entry=${p.entry_price} cur=${h?.current_price || '?'}`);
}
const dipLosses = highPriceLosses.filter(m => /dip\s+to/i.test(m.question || ''));
const dipWins = highPriceWins.filter(m => /dip\s+to/i.test(m.question || ''));
console.log(`  Scanner: ${dipLosses.length} losses / ${dipLosses.length + dipWins.length} total = ${dipLosses.length + dipWins.length > 0 ? (dipLosses.length / (dipLosses.length + dipWins.length) * 100).toFixed(1) : 0}% loss rate`);

// ---- Build output JSON for saving ----
const outputData = {
  generated_at: new Date().toISOString(),
  scanner_stats: {
    total_markets: allMarkets.length,
    resolved: resolvedMarkets.length,
    wins: wins.length,
    losses: losses.length,
    win_rate: (wins.length / resolvedMarkets.length * 100).toFixed(2) + '%',
    high_price_losses_97plus: highPriceLosses.length,
    high_price_wins_97plus: highPriceWins.length,
  },
  loss_by_bucket: Object.fromEntries(
    ['99+', '98-99', '97-98', '96-97', '95-96', 'below-95'].map(b => [
      b, { losses: lossByBucket[b] || 0, wins: winByBucket[b] || 0, total: (lossByBucket[b] || 0) + (winByBucket[b] || 0) }
    ])
  ),
  loss_by_category: Object.fromEntries(
    catEntries.map(([cat, lc]) => [cat, { losses: lc, wins: winByCategory[cat] || 0 }])
  ),
  pattern_loss_map_97plus: Object.fromEntries(
    patternEntries.map(([name, lc]) => [name, {
      losses: lc,
      wins: patternWinMap[name] || 0,
      total: lc + (patternWinMap[name] || 0),
      loss_rate: ((lc / (lc + (patternWinMap[name] || 0))) * 100).toFixed(1) + '%',
      examples: (patternLossExamples[name] || []).slice(0, 3)
    }])
  ),
  uncovered_filter_gaps: Object.fromEntries(gapEntries),
  open_position_risk_assessment: positionRisks.filter(p => p.matchedPatterns.length > 0).map(p => ({
    title: p.title,
    entry_price: p.entry_price,
    current_price: p.current_price,
    unrealized_pnl: p.unrealized_pnl,
    risk_level: p.risk_level,
    patterns: p.matchedPatterns.map(mp => `${mp.pattern}(${mp.lossRate.toFixed(1)}%)`).join(', '),
    max_pattern_loss_rate: p.maxLossRate,
  })),
};

fs.writeFileSync(
  path.join(__dirname, 'loss_patterns_2026-03-21.json'),
  JSON.stringify(outputData, null, 2)
);
console.log('\n\nSaved: loss_patterns_2026-03-21.json');
