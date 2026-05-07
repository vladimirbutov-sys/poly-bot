const fs = require('fs');
const path = require('path');

const scannerRaw = fs.readFileSync(path.join(__dirname, '..', '..', '..', '97_scanner', 'scanner_data.json'), 'utf8');
const scannerData = JSON.parse(scannerRaw);
const positionsRaw = fs.readFileSync(path.join(__dirname, '..', '..', 'positions.json'), 'utf8');
const positionsData = JSON.parse(positionsRaw);

const markets = Object.values(scannerData.markets);
const resolved = markets.filter(m => m.resolved === true);
const losses97 = resolved.filter(m => m.high_outcome_won === false && (m.first_price || m.max_price_seen || 0) >= 0.97);

console.log('=== ALL 7 LOSSES at 97%+ in scanner data ===\n');
for (const m of losses97) {
  console.log(`Question: ${m.question}`);
  console.log(`  Category: ${m.category}`);
  console.log(`  First price: ${m.first_price}`);
  console.log(`  Max price: ${m.max_price_seen}`);
  console.log(`  High outcome: ${m.high_outcome}`);
  console.log(`  End date: ${m.end_date}`);
  console.log('');
}

// ---- Bot's own losses ----
console.log('\n=== BOT LOSSES (status=lost) ===\n');
const botPositions = Object.values(positionsData.positions);
const botLosses = botPositions.filter(p => p.status === 'lost');
for (const p of botLosses) {
  console.log(`Title: ${p.title}`);
  console.log(`  Entry: ${p.entry_price}, Cost: $${p.cost_usd}, PnL: $${p.pnl}`);
  console.log(`  Category: ${p.category || 'unknown'}`);
  console.log('');
}

// ---- Bot's sold at loss ----
console.log('\n=== BOT SOLD AT LOSS ===\n');
const soldAtLoss = botPositions.filter(p => p.status === 'sold' && (p.pnl || 0) < 0);
for (const p of soldAtLoss) {
  console.log(`Title: ${(p.title || '').slice(0, 70)}`);
  console.log(`  Entry: ${p.entry_price}, Sell: ${p.sell_price}, PnL: $${p.pnl}`);
  console.log('');
}

// ---- Stats summary ----
console.log('\n=== BOT OVERALL STATS ===\n');
const statusCounts = {};
for (const p of botPositions) {
  statusCounts[p.status] = (statusCounts[p.status] || 0) + 1;
}
console.log('Status counts:', statusCounts);

const wonPositions = botPositions.filter(p => p.status === 'won');
const totalPnlWon = wonPositions.reduce((s, p) => s + (p.pnl || 0), 0);
const totalPnlLost = botLosses.reduce((s, p) => s + (p.pnl || 0), 0);
const totalPnlSold = botPositions.filter(p => p.status === 'sold').reduce((s, p) => s + (p.pnl || 0), 0);
console.log(`\nWon PnL total: $${totalPnlWon.toFixed(2)} (${wonPositions.length} positions)`);
console.log(`Lost PnL total: $${totalPnlLost.toFixed(2)} (${botLosses.length} positions)`);
console.log(`Sold PnL total: $${totalPnlSold.toFixed(2)} (${botPositions.filter(p=>p.status==='sold').length} positions)`);
console.log(`Net realized PnL: $${(totalPnlWon + totalPnlLost + totalPnlSold).toFixed(2)}`);

// ---- Count open positions by type ----
console.log('\n\n=== OPEN POSITIONS RISK BREAKDOWN ===\n');
const openPositions = botPositions.filter(p => p.status === 'open');
console.log(`Total open: ${openPositions.length}`);

// Classify
const classified = {
  earthquake_bracket: [],
  tweet_post_bracket: [],
  election_politics: [],
  shipping_strait: [],
  bitcoin_crypto: [],
  exact_score: [],
  sports_match: [],
  esports: [],
  draw_market: [],
  will_say_word: [],
  seat_bracket: [],
  album_sales: [],
  other: [],
};

for (const p of openPositions) {
  const t = (p.title || '').toLowerCase();
  if (/earthquake|seismic|magnitude/.test(t)) classified.earthquake_bracket.push(p);
  else if (/tweet|elon\s+musk\s+post|trump\s+post|khamenei\s+post|white\s+house\s+post/.test(t)) classified.tweet_post_bracket.push(p);
  else if (/election|mayor|prime\s+minister|gubernat/.test(t)) classified.election_politics.push(p);
  else if (/strait|ships?\s+transit|transit.*strait/.test(t)) classified.shipping_strait.push(p);
  else if (/bitcoin|ethereum|btc|eth\b|dip\s+to/.test(t)) classified.bitcoin_crypto.push(p);
  else if (/exact\s+score/.test(t)) classified.exact_score.push(p);
  else if (/win\s+on\s+\d{4}|vs\..*\(W\)|catamount|mocs|bison|cardinals/.test(t)) classified.sports_match.push(p);
  else if (/esport|first\s+stand|gaming|gen\.g|fearx/.test(t)) classified.esports.push(p);
  else if (/draw/.test(t)) classified.draw_market.push(p);
  else if (/will.*say/.test(t)) classified.will_say_word.push(p);
  else if (/\d+-\d+\s+seats/.test(t)) classified.seat_bracket.push(p);
  else if (/album\s+sales|debut\s+week/.test(t)) classified.album_sales.push(p);
  else classified.other.push(p);
}

for (const [cat, positions] of Object.entries(classified)) {
  if (positions.length > 0) {
    const totalCost = positions.reduce((s, p) => s + (p.cost_usd || 0), 0);
    console.log(`${cat}: ${positions.length} positions, $${totalCost.toFixed(2)} total cost`);
  }
}

// ---- Check which patterns are NOT in scanner resolved at all ----
console.log('\n\n=== PATTERNS MISSING FROM SCANNER RESOLVED DATA ===');
console.log('(patterns with <10 resolved markets in scanner — risky because we lack data)\n');

const patternResolved = {
  earthquake: resolved.filter(m => /earthquake/i.test(m.question || '')).length,
  tweet_bracket: resolved.filter(m => /\d+-\d+\s*(tweets?|posts?)|tweets?\s+from/i.test(m.question || '')).length,
  exact_score: resolved.filter(m => /exact\s+score/i.test(m.question || '')).length,
  draw: resolved.filter(m => /end\s+in\s+a\s+draw|draw\?/i.test(m.question || '')).length,
  dip_to: resolved.filter(m => /dip\s+to/i.test(m.question || '')).length,
  election: resolved.filter(m => /\belection\b|\bmayoral\b|\bprime\s+minister\b/i.test(m.question || '')).length,
  golf_win: resolved.filter(m => /championship.*win|win.*championship/i.test(m.question || '')).length,
  seats_bracket: resolved.filter(m => /\d+-\d+\s+seats/i.test(m.question || '')).length,
  will_say: resolved.filter(m => /will\s+\w+\s+say\b/i.test(m.question || '')).length,
  shipping: resolved.filter(m => /strait|ships?\s+transit/i.test(m.question || '')).length,
  album: resolved.filter(m => /album\s+sales|debut\s+week/i.test(m.question || '')).length,
  spread: resolved.filter(m => /\bspread\b/i.test(m.question || '')).length,
  temperature: resolved.filter(m => /temperature/i.test(m.question || '')).length,
};

for (const [pat, count] of Object.entries(patternResolved).sort((a,b) => a[1] - b[1])) {
  const flag = count < 10 ? ' ⚠ LOW DATA' : '';
  console.log(`  ${pat}: ${count} resolved${flag}`);
}

// ---- Count unresolted/unresolved markets still tracked ----
const unresolved = markets.filter(m => !m.resolved);
console.log(`\n\nUnresolved markets in scanner: ${unresolved.length}`);
console.log(`Total markets in scanner: ${markets.length}`);
