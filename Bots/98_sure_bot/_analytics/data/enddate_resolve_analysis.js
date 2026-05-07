/**
 * End-date vs Resolve-time Analysis
 *
 * Question: Does shorter end_date mean faster resolution?
 *
 * Part 1: Scanner data (resolved markets passing filters) — bucket by days_to_end
 * Part 2: Positions data (actual resolve times from bot) — bucket by days_to_end
 */

const fs = require('fs');

// ============= LOAD DATA =============

const scanner = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json', 'utf8'));
const posData = JSON.parse(fs.readFileSync('C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'));
const markets = scanner.markets;
const positions = Object.values(posData.positions);

// ============= FILTER PATTERNS (from non_neg_risk_backtest.js) =============

const POLITICS_CATEGORIES = new Set(['politics', 'geopolitics']);
const EARLY_SPORTS_CATEGORIES = new Set(['esports', 'sports_other', 'basketball', 'hockey',
  'american_football', 'tennis', 'fighting', 'cricket']);
const ALL_SPORTS_CATEGORIES = new Set([...EARLY_SPORTS_CATEGORIES, 'soccer']);

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

// ============= FILTER FUNCTION (same as non_neg_risk_backtest) =============

function passesNonNegFilters(m) {
  const q = m.question || '';
  const price = m.first_price || 0;
  const cat = (m.category || '').toLowerCase();

  // Must NOT be neg_risk
  if (m.neg_risk) return false;

  // Price thresholds
  if (POLITICS_CATEGORIES.has(cat)) {
    if (price < 0.96 || price > 0.995) return false;
  } else {
    if (price < 0.975 || price > 0.995) return false;
  }

  // Volume & liquidity
  if ((m.volume || 0) < 3000) return false;
  const liq = m.liquidity || (m.snapshots && m.snapshots.length > 0 ? m.snapshots[m.snapshots.length - 1].liquidity : 0) || 0;
  if (liq > 0 && liq < 500) return false;

  // End date filter (max 7d, 3d for sports with game_start_time)
  if (m.end_date && m.first_seen) {
    const daysToEnd = (new Date(m.end_date) - new Date(m.first_seen)) / (1000 * 60 * 60 * 24);
    let maxDays = 7;
    if (POLITICS_CATEGORIES.has(cat)) maxDays = 7;
    else if (EARLY_SPORTS_CATEGORIES.has(cat) && m.game_start_time) maxDays = 3;
    if (daysToEnd > maxDays) return false;
  }

  // Keyword filters
  if (COIN_FLIP_PATTERNS.some(p => p.test(q))) return false;
  if (TOXIC_KEYWORDS.some(p => p.test(q))) return false;
  if (SLOW_KEYWORDS.some(p => p.test(q))) return false;
  if (FINANCIAL_ASSETS.some(p => p.test(q)) && THRESHOLD_PATTERNS.some(p => p.test(q))) return false;
  if (WEATHER_PATTERNS.some(p => p.test(q))) return false;
  if (ALL_SPORTS_CATEGORIES.has(cat) && SPORTS_BAD_PATTERNS.some(p => p.test(q))) return false;

  return true;
}

// ============= HELPERS =============

function median(arr) {
  if (arr.length === 0) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function average(arr) {
  if (arr.length === 0) return null;
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}

function percentile(arr, p) {
  if (arr.length === 0) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length * p)];
}

// Bucket definitions: [label, minDays, maxDays]
const BUCKETS = [
  ['0-1d',   0, 1],
  ['1-2d',   1, 2],
  ['2-3d',   2, 3],
  ['3-5d',   3, 5],
  ['5-7d',   5, 7],
  ['7-14d',  7, 14],
  ['14+d',  14, 9999],
];

function getBucket(daysToEnd) {
  for (const [label, min, max] of BUCKETS) {
    if (daysToEnd >= min && daysToEnd < max) return label;
  }
  return '14+d';
}

// ============= PART 1: Scanner data — resolved markets passing filters =============

console.log('='.repeat(80));
console.log('  END-DATE vs RESOLVE-TIME ANALYSIS');
console.log('  Does shorter end_date = faster resolution?');
console.log('='.repeat(80));

// Build condition_id -> market map from scanner for cross-referencing
// Scanner keys ARE the condition_ids that positions reference
const conditionToMarket = {};
for (const [key, m] of Object.entries(markets)) {
  conditionToMarket[key] = m; // scanner key = position's condition_id
}

// Part 1: Scanner markets passing filters, bucketed by days_to_end
console.log('\n' + '='.repeat(80));
console.log('  PART 1: Scanner resolved markets (passing non-neg filters)');
console.log('  Bucketed by days_to_end = (end_date - first_seen)');
console.log('='.repeat(80));

const scannerBuckets = {};
for (const label of BUCKETS.map(b => b[0])) {
  scannerBuckets[label] = { total: 0, resolved: 0, won: 0, lost: 0, resolveTimes: [] };
}

// Also track markets WITHOUT end_date
let noEndDate = { total: 0, resolved: 0, won: 0, lost: 0 };

for (const [key, m] of Object.entries(markets)) {
  // Remove the end_date filter to see ALL markets across all buckets
  // But apply all other filters (not neg_risk, price, volume, liquidity, keywords)
  const q = m.question || '';
  const price = m.first_price || 0;
  const cat = (m.category || '').toLowerCase();

  if (m.neg_risk) continue;
  if (POLITICS_CATEGORIES.has(cat)) {
    if (price < 0.96 || price > 0.995) continue;
  } else {
    if (price < 0.975 || price > 0.995) continue;
  }
  if ((m.volume || 0) < 3000) continue;
  const liq = m.liquidity || (m.snapshots && m.snapshots.length > 0 ? m.snapshots[m.snapshots.length - 1].liquidity : 0) || 0;
  if (liq > 0 && liq < 500) continue;
  if (COIN_FLIP_PATTERNS.some(p => p.test(q))) continue;
  if (TOXIC_KEYWORDS.some(p => p.test(q))) continue;
  if (SLOW_KEYWORDS.some(p => p.test(q))) continue;
  if (FINANCIAL_ASSETS.some(p => p.test(q)) && THRESHOLD_PATTERNS.some(p => p.test(q))) continue;
  if (WEATHER_PATTERNS.some(p => p.test(q))) continue;
  if (ALL_SPORTS_CATEGORIES.has(cat) && SPORTS_BAD_PATTERNS.some(p => p.test(q))) continue;

  if (!m.end_date || !m.first_seen) {
    noEndDate.total++;
    if (m.resolved) {
      noEndDate.resolved++;
      const won = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
      if (won) noEndDate.won++; else noEndDate.lost++;
    }
    continue;
  }

  const daysToEnd = (new Date(m.end_date) - new Date(m.first_seen)) / (1000 * 60 * 60 * 24);
  const bucket = getBucket(daysToEnd);

  if (!scannerBuckets[bucket]) continue;
  scannerBuckets[bucket].total++;

  if (m.resolved) {
    scannerBuckets[bucket].resolved++;
    const won = m.resolution === 'high_won' || m.resolution === true || m.high_outcome_won === true;
    if (won) scannerBuckets[bucket].won++; else scannerBuckets[bucket].lost++;
  }
}

console.log('\nBucket     | Total | Resolved | Won  | Lost | Win Rate');
console.log('-'.repeat(65));
for (const [label] of BUCKETS) {
  const b = scannerBuckets[label];
  const wr = b.resolved > 0 ? (b.won / b.resolved * 100).toFixed(1) + '%' : 'n/a';
  console.log(
    label.padEnd(10) + ' | ' +
    String(b.total).padStart(5) + ' | ' +
    String(b.resolved).padStart(8) + ' | ' +
    String(b.won).padStart(4) + ' | ' +
    String(b.lost).padStart(4) + ' | ' +
    wr.padStart(8)
  );
}
console.log('no_end     | ' +
  String(noEndDate.total).padStart(5) + ' | ' +
  String(noEndDate.resolved).padStart(8) + ' | ' +
  String(noEndDate.won).padStart(4) + ' | ' +
  String(noEndDate.lost).padStart(4) + ' | ' +
  (noEndDate.resolved > 0 ? (noEndDate.won / noEndDate.resolved * 100).toFixed(1) + '%' : 'n/a').padStart(8)
);

// ============= PART 2: Positions — cross-reference with scanner for days_to_end =============

console.log('\n' + '='.repeat(80));
console.log('  PART 2: Positions.json resolved — with days_to_end from scanner');
console.log('  Only positions that match scanner markets (by condition_id)');
console.log('='.repeat(80));

const posBuckets = {};
for (const label of BUCKETS.map(b => b[0])) {
  posBuckets[label] = { count: 0, won: 0, lost: 0, resolveTimesH: [], negRisk: 0, regular: 0 };
}
let posNoMatch = 0;
let posNoEndDate = 0;
let posMatched = 0;

for (const p of positions) {
  if (p.status !== 'won' && p.status !== 'lost') continue; // only resolved

  // Find matching scanner market
  const scannerMarket = p.condition_id ? conditionToMarket[p.condition_id] : null;

  if (!scannerMarket) {
    posNoMatch++;
    continue;
  }

  if (!scannerMarket.end_date || !scannerMarket.first_seen) {
    posNoEndDate++;
    continue;
  }

  posMatched++;
  const daysToEnd = (new Date(scannerMarket.end_date) - new Date(scannerMarket.first_seen)) / (1000 * 60 * 60 * 24);
  const bucket = getBucket(daysToEnd);

  if (!posBuckets[bucket]) continue;
  posBuckets[bucket].count++;

  if (p.status === 'won') posBuckets[bucket].won++;
  else posBuckets[bucket].lost++;

  if (p.neg_risk) posBuckets[bucket].negRisk++;
  else posBuckets[bucket].regular++;

  // Resolve time
  if (p.resolved_at && p.timestamp) {
    const resolveH = (new Date(p.resolved_at) - new Date(p.timestamp)) / 3600000;
    if (resolveH > 0 && resolveH < 10000) { // sanity check
      posBuckets[bucket].resolveTimesH.push(resolveH);
    }
  }
}

console.log('\nMatched: ' + posMatched + ' | No scanner match: ' + posNoMatch + ' | No end_date in scanner: ' + posNoEndDate);

console.log('\nBucket     | Count | Won  | Lost | WinRate  | Median h | Avg h    | P25 h    | P75 h    | Reg  | Neg');
console.log('-'.repeat(115));
for (const [label] of BUCKETS) {
  const b = posBuckets[label];
  const wr = b.count > 0 ? (b.won / b.count * 100).toFixed(1) + '%' : 'n/a';
  const med = median(b.resolveTimesH);
  const avg = average(b.resolveTimesH);
  const p25 = percentile(b.resolveTimesH, 0.25);
  const p75 = percentile(b.resolveTimesH, 0.75);

  console.log(
    label.padEnd(10) + ' | ' +
    String(b.count).padStart(5) + ' | ' +
    String(b.won).padStart(4) + ' | ' +
    String(b.lost).padStart(4) + ' | ' +
    wr.padStart(8) + ' | ' +
    (med !== null ? med.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    (avg !== null ? avg.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    (p25 !== null ? p25.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    (p75 !== null ? p75.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    String(b.regular).padStart(4) + ' | ' +
    String(b.negRisk).padStart(3)
  );
}

// ============= PART 3: ALL positions (not just filtered) by days_to_end =============

console.log('\n' + '='.repeat(80));
console.log('  PART 3: ALL resolved positions — bucketed by days_to_end');
console.log('  (No scanner filters applied — pure empirical data)');
console.log('='.repeat(80));

const allPosBuckets = {};
for (const label of BUCKETS.map(b => b[0])) {
  allPosBuckets[label] = { count: 0, won: 0, lost: 0, resolveTimesH: [], negRisk: 0, regular: 0 };
}
let allPosNoMatch = 0;
let allPosNoEndDate = 0;
let allPosTotal = 0;

for (const p of positions) {
  if (p.status !== 'won' && p.status !== 'lost') continue;
  allPosTotal++;

  const scannerMarket = p.condition_id ? conditionToMarket[p.condition_id] : null;
  if (!scannerMarket) { allPosNoMatch++; continue; }
  if (!scannerMarket.end_date || !scannerMarket.first_seen) { allPosNoEndDate++; continue; }

  const daysToEnd = (new Date(scannerMarket.end_date) - new Date(scannerMarket.first_seen)) / (1000 * 60 * 60 * 24);
  const bucket = getBucket(daysToEnd);

  if (!allPosBuckets[bucket]) continue;
  allPosBuckets[bucket].count++;
  if (p.status === 'won') allPosBuckets[bucket].won++;
  else allPosBuckets[bucket].lost++;
  if (p.neg_risk) allPosBuckets[bucket].negRisk++;
  else allPosBuckets[bucket].regular++;

  if (p.resolved_at && p.timestamp) {
    const resolveH = (new Date(p.resolved_at) - new Date(p.timestamp)) / 3600000;
    if (resolveH > 0 && resolveH < 10000) {
      allPosBuckets[bucket].resolveTimesH.push(resolveH);
    }
  }
}

console.log('\nTotal resolved: ' + allPosTotal + ' | Matched scanner: ' + (allPosTotal - allPosNoMatch) + ' | No end_date: ' + allPosNoEndDate);

console.log('\nBucket     | Count | Won  | Lost | WinRate  | Median h | Avg h    | P25 h    | P75 h    | Reg  | Neg');
console.log('-'.repeat(115));
for (const [label] of BUCKETS) {
  const b = allPosBuckets[label];
  const wr = b.count > 0 ? (b.won / b.count * 100).toFixed(1) + '%' : 'n/a';
  const med = median(b.resolveTimesH);
  const avg = average(b.resolveTimesH);
  const p25 = percentile(b.resolveTimesH, 0.25);
  const p75 = percentile(b.resolveTimesH, 0.75);

  console.log(
    label.padEnd(10) + ' | ' +
    String(b.count).padStart(5) + ' | ' +
    String(b.won).padStart(4) + ' | ' +
    String(b.lost).padStart(4) + ' | ' +
    wr.padStart(8) + ' | ' +
    (med !== null ? med.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    (avg !== null ? avg.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    (p25 !== null ? p25.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    (p75 !== null ? p75.toFixed(1) : 'n/a').padStart(8) + ' | ' +
    String(b.regular).padStart(4) + ' | ' +
    String(b.negRisk).padStart(3)
  );
}

// ============= PART 4: Split by neg_risk vs regular =============

console.log('\n' + '='.repeat(80));
console.log('  PART 4: Resolve times split by Regular vs Neg_risk');
console.log('='.repeat(80));

for (const typeLabel of ['Regular (non-neg_risk)', 'Neg_risk']) {
  const isNeg = typeLabel.startsWith('Neg');
  console.log('\n--- ' + typeLabel + ' ---\n');

  const typeBuckets = {};
  for (const label of BUCKETS.map(b => b[0])) {
    typeBuckets[label] = { count: 0, won: 0, lost: 0, resolveTimesH: [] };
  }

  for (const p of positions) {
    if (p.status !== 'won' && p.status !== 'lost') continue;
    if (isNeg && !p.neg_risk) continue;
    if (!isNeg && p.neg_risk) continue;

    const scannerMarket = p.condition_id ? conditionToMarket[p.condition_id] : null;
    if (!scannerMarket || !scannerMarket.end_date || !scannerMarket.first_seen) continue;

    const daysToEnd = (new Date(scannerMarket.end_date) - new Date(scannerMarket.first_seen)) / (1000 * 60 * 60 * 24);
    const bucket = getBucket(daysToEnd);
    if (!typeBuckets[bucket]) continue;

    typeBuckets[bucket].count++;
    if (p.status === 'won') typeBuckets[bucket].won++;
    else typeBuckets[bucket].lost++;

    if (p.resolved_at && p.timestamp) {
      const resolveH = (new Date(p.resolved_at) - new Date(p.timestamp)) / 3600000;
      if (resolveH > 0 && resolveH < 10000) {
        typeBuckets[bucket].resolveTimesH.push(resolveH);
      }
    }
  }

  console.log('Bucket     | Count | Won  | Lost | WinRate  | Median h | Avg h    | P75 h');
  console.log('-'.repeat(85));
  for (const [label] of BUCKETS) {
    const b = typeBuckets[label];
    const wr = b.count > 0 ? (b.won / b.count * 100).toFixed(1) + '%' : 'n/a';
    const med = median(b.resolveTimesH);
    const avg = average(b.resolveTimesH);
    const p75 = percentile(b.resolveTimesH, 0.75);

    console.log(
      label.padEnd(10) + ' | ' +
      String(b.count).padStart(5) + ' | ' +
      String(b.won).padStart(4) + ' | ' +
      String(b.lost).padStart(4) + ' | ' +
      wr.padStart(8) + ' | ' +
      (med !== null ? med.toFixed(1) : 'n/a').padStart(8) + ' | ' +
      (avg !== null ? avg.toFixed(1) : 'n/a').padStart(8) + ' | ' +
      (p75 !== null ? p75.toFixed(1) : 'n/a').padStart(8)
    );
  }
}

// ============= PART 5: Summary / Conclusion =============

console.log('\n' + '='.repeat(80));
console.log('  SUMMARY');
console.log('='.repeat(80));

// Compare 0-3d vs 3-7d resolve times from all positions
const shortResolve = [];
const longResolve = [];
for (const p of positions) {
  if (p.status !== 'won' && p.status !== 'lost') continue;
  const sm = p.condition_id ? conditionToMarket[p.condition_id] : null;
  if (!sm || !sm.end_date || !sm.first_seen) continue;
  const dte = (new Date(sm.end_date) - new Date(sm.first_seen)) / (1000 * 60 * 60 * 24);
  if (p.resolved_at && p.timestamp) {
    const rh = (new Date(p.resolved_at) - new Date(p.timestamp)) / 3600000;
    if (rh > 0 && rh < 10000) {
      if (dte < 3) shortResolve.push(rh);
      else if (dte >= 3 && dte < 7) longResolve.push(rh);
    }
  }
}

console.log('\nShort end_date (0-3 days): n=' + shortResolve.length +
  ' | median=' + (median(shortResolve) || 0).toFixed(1) + 'h' +
  ' | avg=' + (average(shortResolve) || 0).toFixed(1) + 'h' +
  ' | p75=' + (percentile(shortResolve, 0.75) || 0).toFixed(1) + 'h');

console.log('Long end_date (3-7 days):  n=' + longResolve.length +
  ' | median=' + (median(longResolve) || 0).toFixed(1) + 'h' +
  ' | avg=' + (average(longResolve) || 0).toFixed(1) + 'h' +
  ' | p75=' + (percentile(longResolve, 0.75) || 0).toFixed(1) + 'h');

if (median(shortResolve) && median(longResolve)) {
  const ratio = median(longResolve) / median(shortResolve);
  console.log('\nMedian resolve ratio (long/short): ' + ratio.toFixed(2) + 'x');
  if (ratio > 1.5) {
    console.log('=> YES, short end_date markets resolve significantly faster (' + ratio.toFixed(1) + 'x)');
  } else if (ratio > 1.1) {
    console.log('=> Moderate effect: short end_date markets resolve somewhat faster');
  } else {
    console.log('=> NO significant difference in resolve speed by end_date');
  }
}

console.log('\nDone.');
