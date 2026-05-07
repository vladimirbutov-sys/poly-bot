/**
 * Backtest: how many non-neg_risk bets per day pass all current filters?
 * Simulates filters from filters.py on scanner_data.json
 */

const fs = require('fs');

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const markets = scanner.markets;

// ============= FILTER PATTERNS (from filters.py) =============

const POLITICS_CATEGORIES = new Set(['politics', 'geopolitics']);
const EARLY_SPORTS_CATEGORIES = new Set(['esports', 'sports_other', 'basketball', 'hockey',
  'american_football', 'tennis', 'fighting', 'cricket']);
const ALL_SPORTS_CATEGORIES = new Set([...EARLY_SPORTS_CATEGORIES, 'soccer']);

const PRICE_THRESHOLD_DEFAULT = 0.975;
const PRICE_THRESHOLD_POLITICS = 0.96;
const MAX_PRICE = 0.995;
const MIN_LIQUIDITY = 500;
const MIN_VOLUME = 3000;
const MAX_END_DATE_DAYS = 7;
const MAX_END_DATE_DAYS_POLITICS = 7;
const MAX_END_DATE_DAYS_SPORTS = 3;

const COIN_FLIP_PATTERNS = [
  /\bodd\s+or\s+even\b/i, /\bodd\/even\b/i,
  /\bfirst\s+blood\b/i, /\bfirst\s+kill\b/i,
  /\bfirst\s+baron\b/i, /\bfirst\s+dragon\b/i,
  /\bfirst\s+tower\b/i, /\bfirst\s+rift\s+herald\b/i,
  /\bcoin\s+flip\b/i, /\brampage\b/i,
  /\bfirst\s+roshan\b/i, /\bfirst\s+map\b/i,
  /\bup\s+or\s+down\b/i,
];

const THRESHOLD_PATTERNS = [
  /\bclose\s+above\b/i, /\bclose\s+below\b/i,
  /\bbe\s+above\b/i, /\bbe\s+below\b/i,
  /\bbe\s+between\b/i, /\bbe\s+greater\s+than\b/i,
  /\bbe\s+less\s+than\b/i, /\bprice\s+of\b/i,
  /\breach\b.*\$[\d,]+/i, /\bhit\b.*\$[\d,]+/i,
  /\bfall\s+(to|below)\b.*\$[\d,]+/i,
  /\bdrop\s+(to|below)\b.*\$[\d,]+/i,
  /\brise\s+(to|above)\b.*\$[\d,]+/i,
];

const WEATHER_PATTERNS = [
  /\btemperature\b.*\d+\s*[°]?\s*[FC]\b/i,
  /\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b/i,
  /\d+\s*[°]?\s*[FC]\b.*\btemperature\b/i,
  /\d+\s*[°]?\s*[FC]\b.*\bhighest\s+temp\b/i,
];

const TOXIC_KEYWORDS = [
  /\bearthquake/i, /\bseismic\b/i, /\bmagnitude\s+\d/i,
  /\btornado/i, /\btornadoes\b/i,
  /\btweets?\b/i, /\bposts?\b.*\d+-\d+/i,
  /\d+-\d+\s*(tweets?|posts?)/i,
  /\btweet\b/i, /\bretweet\b/i,
  /how\s+many.*\bpost/i, /how\s+many.*\btweet/i,
  /number\s+of\s+(tweets?|posts?)/i,
];

const SLOW_KEYWORDS = [
  /\btop\b/i, /\bseason\b/i, /\bmost\b/i,
  /\btransit\b/i, /\bstrait\b/i, /\bships?\b/i,
  /\bweekly\b/i, /\bmonthly\b/i,
];

const FINANCIAL_ASSETS = [
  /\bbitcoin\b/i, /\bethereum\b/i, /\bsolana\b/i, /\bxrp\b/i,
  /\bbtc\b/i, /\beth\b/i, /\bsol\b/i, /\bdogecoin\b/i, /\bcardano\b/i,
  /\bpolygon\b/i, /\bavalanch\b/i, /\blitecoin\b/i, /\bpolkadot\b/i,
  /\bchainlink\b/i, /\buniswap\b/i, /\bshiba\b/i,
  /\baapl\b/i, /\bamzn\b/i, /\bgoogl\b/i, /\bmeta\b/i, /\bnflx\b/i,
  /\bmsft\b/i, /\btsla\b/i, /\bnvda\b/i, /\bapple\b/i, /\bamazon\b/i,
  /\bgoogle\b/i, /\bnetflix\b/i, /\bmicrosoft\b/i, /\btesla\b/i,
  /\bnvidia\b/i, /\bopendoor\b/i,
  /\bs&p\s*500\b/i, /\bnasdaq\b/i, /\bnyse\b/i, /\bdow\s*jones\b/i,
  /\bdjia\b/i, /\bndx\b/i, /\bspx\b/i, /\bhang\s*seng\b/i, /\bhsi\b/i,
  /\brussell\b/i, /\bnikkei\b/i, /\bftse\b/i,
  /\bcrude\s*oil\b/i, /\bgold\s*price\b/i, /\bsilver\s*price\b/i,
  /\bnatural\s*gas\b/i, /\bwti\b/i, /\bbrent\b/i,
  /\btreasury\s*yield\b/i, /\bfed\s*rate\b/i, /\bmicrostrategy\b/i,
];

const SPORTS_BAD_PATTERNS = [
  /\bo\/u\s+\d/i, /\bover\/under\b/i,
  /\bspread:\s/i, /\bhandicap/i,
  /\btotal\s+(corners?|kills?|goals?|rounds?|sets?|games?|maps?|points?)\b/i,
  /\bfight\s+to\s+go\s+the\s+distance\b/i,
  /\bo\/u\s+\d.*rounds?\b/i,
  /\bbarracks\b/i, /\broshan\b/i, /\bpenta\s*kill\b/i,
];

// ============= APPLY FILTERS =============

function applyFilters(m) {
  const q = m.question || '';
  const price = m.first_price || 0;
  const cat = (m.category || '').toLowerCase();
  const negRisk = m.neg_risk || false;
  const reasons = [];

  // Filter: neg_risk
  if (negRisk) return { passed: false, reason: 'neg_risk' };

  // Filter: min price (category-specific)
  if (POLITICS_CATEGORIES.has(cat)) {
    if (price < PRICE_THRESHOLD_POLITICS) return { passed: false, reason: 'price_low_politics' };
  } else {
    if (price < PRICE_THRESHOLD_DEFAULT) return { passed: false, reason: 'price_low' };
  }
  if (price > MAX_PRICE) return { passed: false, reason: 'price_high' };

  // Filter: liquidity
  const liq = m.liquidity || (m.snapshots && m.snapshots.length > 0 ? m.snapshots[m.snapshots.length-1].liquidity : 0) || 0;
  if (liq > 0 && liq < MIN_LIQUIDITY) return { passed: false, reason: 'low_liquidity' };

  // Filter: volume
  const vol = m.volume || 0;
  if (vol < MIN_VOLUME) return { passed: false, reason: 'low_volume' };

  // Filter: end_date
  if (m.end_date) {
    const firstSeen = new Date(m.first_seen);
    const endDate = new Date(m.end_date);
    const daysToEnd = (endDate - firstSeen) / (1000*60*60*24);

    let maxDays = MAX_END_DATE_DAYS;
    if (POLITICS_CATEGORIES.has(cat)) maxDays = MAX_END_DATE_DAYS_POLITICS;
    else if (EARLY_SPORTS_CATEGORIES.has(cat) && m.game_start_time) maxDays = MAX_END_DATE_DAYS_SPORTS;

    if (daysToEnd > maxDays) return { passed: false, reason: 'end_date_too_far' };
  }

  // Filter: coin flip
  for (const p of COIN_FLIP_PATTERNS) {
    if (p.test(q)) return { passed: false, reason: 'coin_flip' };
  }

  // Filter: toxic keywords
  for (const p of TOXIC_KEYWORDS) {
    if (p.test(q)) return { passed: false, reason: 'toxic_keyword' };
  }

  // Filter: slow keywords
  for (const p of SLOW_KEYWORDS) {
    if (p.test(q)) return { passed: false, reason: 'slow_keyword' };
  }

  // Filter: financial asset + threshold
  const isFinancial = FINANCIAL_ASSETS.some(p => p.test(q));
  const isThreshold = THRESHOLD_PATTERNS.some(p => p.test(q));
  if (isFinancial && isThreshold) return { passed: false, reason: 'financial_threshold' };

  // Filter: weather
  for (const p of WEATHER_PATTERNS) {
    if (p.test(q)) return { passed: false, reason: 'weather' };
  }

  // Filter: sports bad patterns (only for sports)
  if (ALL_SPORTS_CATEGORIES.has(cat)) {
    for (const p of SPORTS_BAD_PATTERNS) {
      if (p.test(q)) return { passed: false, reason: 'sports_bad' };
    }
  }

  return { passed: true, reason: '' };
}

// ============= RUN BACKTEST =============

console.log('='.repeat(70));
console.log('  BACKTEST: Non-neg_risk bets per day (current filters)');
console.log('='.repeat(70));

const byDate = {};
const filterReasons = {};
let totalPassed = 0;
let totalFiltered = 0;
let totalNegRisk = 0;

for (const [mk, m] of Object.entries(markets)) {
  const date = m.first_seen ? m.first_seen.slice(0, 10) : 'unknown';
  if (date === 'unknown') continue;

  if (!byDate[date]) byDate[date] = {
    total: 0, passed: 0, negRisk: 0, filtered: 0,
    passedByCategory: {}, filteredReasons: {},
    passedResolved: 0, passedWon: 0, passedLost: 0
  };

  byDate[date].total++;

  const result = applyFilters(m);

  if (result.passed) {
    totalPassed++;
    byDate[date].passed++;
    const cat = (m.category || 'unknown').toLowerCase();
    byDate[date].passedByCategory[cat] = (byDate[date].passedByCategory[cat] || 0) + 1;

    // Check resolution
    if (m.resolved) {
      byDate[date].passedResolved++;
      const won = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
      if (won) byDate[date].passedWon++;
      else byDate[date].passedLost++;
    }
  } else {
    if (result.reason === 'neg_risk') {
      totalNegRisk++;
      byDate[date].negRisk++;
    } else {
      totalFiltered++;
      byDate[date].filtered++;
    }
    filterReasons[result.reason] = (filterReasons[result.reason] || 0) + 1;
  }
}

const dates = Object.keys(byDate).filter(d => d !== 'unknown').sort();

console.log('\n=== DAILY BREAKDOWN ===\n');
console.log('Date       | Total | NegRisk | Filtered | PASSED | Categories');
console.log('-'.repeat(100));

let sumPassed = 0;
let fullDays = 0;

for (const date of dates) {
  const d = byDate[date];
  const catStr = Object.entries(d.passedByCategory)
    .sort((a,b) => b[1] - a[1])
    .map(([k,v]) => k + ':' + v)
    .join(', ');

  const isFullDay = date !== dates[0] && date !== dates[dates.length - 1]; // exclude first/last partial
  if (isFullDay) { sumPassed += d.passed; fullDays++; }

  const marker = isFullDay ? '' : ' (partial)';
  console.log(date + ' | ' + String(d.total).padStart(5) + ' | ' +
    String(d.negRisk).padStart(7) + ' | ' + String(d.filtered).padStart(8) + ' | ' +
    String(d.passed).padStart(6) + ' | ' + catStr + marker);
}

console.log('\n=== AVERAGES (full days only: ' + dates.slice(1, -1).join(', ') + ') ===');
console.log('Average non-neg_risk bets per day: ' + (sumPassed / fullDays).toFixed(1));

console.log('\n=== FILTER BREAKDOWN (all dates) ===');
const sortedReasons = Object.entries(filterReasons).sort((a,b) => b[1] - a[1]);
for (const [reason, count] of sortedReasons) {
  console.log('  ' + reason + ': ' + count + ' (' + (count / (totalPassed + totalFiltered + totalNegRisk) * 100).toFixed(1) + '%)');
}

// P&L for passed markets
console.log('\n=== P&L FOR PASSED MARKETS (resolved only) ===');
let passedWon = 0, passedLost = 0, passedPnL = 0;
for (const [mk, m] of Object.entries(markets)) {
  const result = applyFilters(m);
  if (!result.passed) continue;
  if (!m.resolved) continue;

  const won = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
  const cost = 10; // $10 per bet
  const shares = cost / m.first_price;

  if (won) {
    passedWon++;
    passedPnL += shares * (1 - m.first_price);
  } else {
    passedLost++;
    passedPnL -= cost;
  }
}

console.log('Won: ' + passedWon + ', Lost: ' + passedLost);
console.log('Win rate: ' + (passedWon / (passedWon + passedLost) * 100).toFixed(3) + '%');
console.log('P&L: $' + passedPnL.toFixed(2));
console.log('Avg profit per win: $' + (passedPnL / passedWon).toFixed(3));

// Capital constraint simulation
console.log('\n=== CAPITAL CONSTRAINT: How many can $600 bankroll handle? ===');
// Assume $10 per bet, resolve in ~5h median for regular
// In 24h we can turn over capital 24/5 = 4.8 times
// $600 / $10 = 60 bets outstanding at once
// With 4.8 turnovers per day: 60 * 4.8 = 288 bets/day capacity
// But we see ~200-300 qualifying markets - so capacity is NOT the bottleneck for non-neg

const avgPassedPerDay = sumPassed / fullDays;
const betSize = 10;
const medianResolveHours = 5; // from earlier analysis of regular markets
const turnoversPerDay = 24 / medianResolveHours;
const maxConcurrentBets = 600 / betSize;
const maxBetsPerDay = maxConcurrentBets * turnoversPerDay;

console.log('Avg qualifying markets per day: ' + avgPassedPerDay.toFixed(0));
console.log('Median resolve time (regular): ' + medianResolveHours + 'h');
console.log('Capital turnovers per day: ' + turnoversPerDay.toFixed(1));
console.log('Max concurrent bets ($600/$10): ' + maxConcurrentBets);
console.log('Theoretical max bets/day: ' + maxBetsPerDay.toFixed(0));
console.log('Bottleneck: ' + (avgPassedPerDay < maxBetsPerDay ? 'MARKET SUPPLY (' + avgPassedPerDay.toFixed(0) + ' markets)' : 'CAPITAL'));

// Fill rate adjustment
const fillRate = 0.82;
console.log('\nWith 82% fill rate: ' + (avgPassedPerDay * fillRate).toFixed(0) + ' filled bets/day');
console.log('Expected daily PnL: $' + (avgPassedPerDay * fillRate * 0.102).toFixed(2));
console.log('Expected monthly PnL: $' + (avgPassedPerDay * fillRate * 0.102 * 30).toFixed(2));

// Save
fs.writeFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/non_neg_risk_backtest_2026-03-22.json',
  JSON.stringify({ dates: byDate, filterReasons, avgPassedPerDay, passedWon, passedLost }, null, 2));
console.log('\nData saved.');
