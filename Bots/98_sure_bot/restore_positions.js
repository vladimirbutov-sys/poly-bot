/**
 * Restore positions.json from bot_log.txt
 * Extracts order_id, token_id, title, shares, price, cost.
 * Then removes unfilled and WON positions.
 * condition_id not available in log — will be fetched via Gamma API lookup.
 */
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(__dirname, 'bot_log.txt');
const SIM_PASSED = path.join(__dirname, 'sim_passed.json');
const OUT_FILE = path.join(__dirname, 'positions_restored.json');

const log = fs.readFileSync(LOG_FILE, 'utf8');
const lines = log.split('\n');

// Load sim_passed.json for condition_id + token_id lookup by title
let simPassed = [];
try {
    simPassed = JSON.parse(fs.readFileSync(SIM_PASSED, 'utf8'));
} catch(e) {}

// Build lookup: partial title -> {condition_id, token_id, neg_risk}
const simLookup = new Map();
for (const s of simPassed) {
    const key = s.question.substring(0, 40);
    simLookup.set(key, {
        condition_id: s.condition_id || '',
        token_id: s.token_id || '',
        neg_risk: s.neg_risk || false,
    });
}

// Regexes
const orderPlacedRe = /Order placed: (0x[a-f0-9]+) \| ([\d.]+) shares @ ([\d.]+) = \$([\d.]+)/;
const recordedRe = /Recorded position: (.+?) \| ([\d.]+) shares @ ([\d.]+) = \$([\d.]+)/;
const removedRe = /Removed unfilled position (0x[a-f0-9]+)/;
const wonRe = /\[redeemer\].*WON: (.+?) \|/;
const lostRe = /\[redeemer\].*LOST: (.+?) \|/;
const tickSizeRe = /tick-size\?token_id=(\d+)/;
const negRiskRe = /neg-risk\?token_id=(\d+)/;

// Pass 1: collect removed IDs, won/lost titles
const removedIds = new Set();
const wonTitles = new Set();
const lostTitles = new Set();

for (const line of lines) {
    const rm = line.match(removedRe);
    if (rm) removedIds.add(rm[1]);
    const wm = line.match(wonRe);
    if (wm) wonTitles.add(wm[1].trim());
    const lm = line.match(lostRe);
    if (lm) lostTitles.add(lm[1].trim());
}

// Pass 2: pair Placing bet -> tick-size (token_id) -> neg-risk -> Order placed -> Recorded
const positions = [];
let currentTokenId = '';
let currentNegRisk = false;
let currentOrderId = '';
let currentOrderData = null;

for (const line of lines) {
    // Extract token_id from tick-size URL
    const ts = line.match(tickSizeRe);
    if (ts) {
        currentTokenId = ts[1];
        currentNegRisk = false; // reset, will set if neg-risk call follows
        continue;
    }

    // If neg-risk check follows for same token, mark as neg_risk
    const nr = line.match(negRiskRe);
    if (nr && nr[1] === currentTokenId) {
        currentNegRisk = true;
        continue;
    }

    // Order placed
    const op = line.match(orderPlacedRe);
    if (op) {
        currentOrderId = op[1];
        currentOrderData = {
            shares: parseFloat(op[2]),
            price: parseFloat(op[3]),
            cost: parseFloat(op[4]),
        };
        continue;
    }

    // Recorded position
    const rp = line.match(recordedRe);
    if (rp && currentOrderId) {
        const title = rp[1];
        const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
        const timestamp = tsMatch ? tsMatch[1].replace(' ', 'T') + '+00:00' : '';

        // Try to find condition_id from sim_passed
        const simKey = title.substring(0, 40);
        const simData = simLookup.get(simKey);

        positions.push({
            order_id: currentOrderId,
            token_id: currentTokenId,
            condition_id: simData ? simData.condition_id : '',
            neg_risk: simData ? simData.neg_risk : currentNegRisk,
            title: title,
            shares: currentOrderData.shares,
            price: currentOrderData.price,
            cost: currentOrderData.cost,
            timestamp: timestamp,
        });

        currentOrderId = '';
        currentOrderData = null;
    }
}

console.log(`Total recorded: ${positions.length}`);
console.log(`Removed (unfilled): ${removedIds.size}`);
console.log(`WON: ${wonTitles.size}, LOST: ${lostTitles.size}`);

// Remove unfilled
let remaining = positions.filter(p => !removedIds.has(p.order_id));
console.log(`After removing unfilled: ${remaining.length}`);

// Remove WON/LOST by title match
remaining = remaining.filter(p => {
    for (const wt of wonTitles) {
        if (p.title.startsWith(wt) || wt.startsWith(p.title.substring(0, 40))) {
            console.log(`  WON (skip): ${p.title.substring(0, 50)}`);
            return false;
        }
    }
    for (const lt of lostTitles) {
        if (p.title.startsWith(lt) || lt.startsWith(p.title.substring(0, 40))) {
            console.log(`  LOST (skip): ${p.title.substring(0, 50)}`);
            return false;
        }
    }
    return true;
});

// Deduplicate by title (keep last)
const byTitle = new Map();
for (const p of remaining) {
    byTitle.set(p.title, p);
}
const unique = [...byTitle.values()];

console.log(`\nUnique open positions: ${unique.length}`);

// Check how many have condition_id
const withCid = unique.filter(p => p.condition_id);
const withoutCid = unique.filter(p => !p.condition_id);
console.log(`With condition_id: ${withCid.length}`);
console.log(`Without condition_id (need API lookup): ${withoutCid.length}`);

// Build positions.json
const totalCost = unique.reduce((s, p) => s + p.cost, 0);
const BANKROLL = 500.0;
const winPnl = 0.05; // from the 1 WON position

const positionsObj = {};
for (const p of unique) {
    positionsObj[p.order_id] = {
        condition_id: p.condition_id,
        token_id: p.token_id,
        title: p.title,
        entry_price: p.price,
        size_shares: p.shares,
        cost_usd: p.cost,
        neg_risk: p.neg_risk,
        order_id: p.order_id,
        timestamp: p.timestamp,
        status: "open",
    };
}

const result = {
    positions: positionsObj,
    stats: {
        total_bets: unique.length + 1, // +1 for WON position
        wins: 1,
        losses: 0,
        total_pnl: winPnl,
        peak_balance: BANKROLL,
        current_balance: BANKROLL - totalCost + winPnl,
    }
};

console.log(`\n=== SUMMARY ===`);
console.log(`Open: ${unique.length}`);
console.log(`Invested: $${totalCost.toFixed(2)}`);
console.log(`Balance: $${result.stats.current_balance.toFixed(2)}`);
console.log(`Portfolio value: $${(result.stats.current_balance + totalCost).toFixed(2)}`);

if (withoutCid.length > 0) {
    console.log(`\n--- Missing condition_id (${withoutCid.length}) ---`);
    withoutCid.forEach((p, i) => {
        console.log(`  ${i+1}. ${p.title.substring(0, 55)} | token: ${p.token_id.substring(0, 20)}...`);
    });
}

fs.writeFileSync(OUT_FILE, JSON.stringify(result, null, 2), 'utf8');
console.log(`\nSaved to: ${OUT_FILE}`);
