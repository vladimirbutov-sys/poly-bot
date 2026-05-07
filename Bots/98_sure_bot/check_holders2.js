/**
 * Check unique traders on our CURRENT open positions
 * via different API approach - check order book depth
 * and CLOB trades endpoint.
 */
const https = require('https');
const fs = require('fs');

const positions = JSON.parse(fs.readFileSync(
    'C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json', 'utf8'
));

function fetch(url) {
    return new Promise((resolve) => {
        https.get(url, { timeout: 15000 }, (res) => {
            let body = '';
            res.on('data', d => body += d);
            res.on('end', () => {
                try { resolve(JSON.parse(body)); }
                catch(e) { resolve(null); }
            });
        }).on('error', () => resolve(null));
    });
}

async function main() {
    // Try Gamma API markets endpoint - check for 'userCount' or similar fields
    const openPositions = Object.values(positions.positions).filter(p => p.status === 'open');
    console.log('Checking', openPositions.length, 'open positions...\n');

    // Take a sample of 15
    const sample = openPositions.slice(0, 15);

    for (const pos of sample) {
        await new Promise(r => setTimeout(r, 300));

        // Try gamma API for market details
        const cid = pos.condition_id;
        if (!cid) { console.log('No CID:', pos.title.substring(0, 40)); continue; }

        const market = await fetch(`https://gamma-api.polymarket.com/markets?condition_id=${cid}`);

        let volume = 0, liquidity = 0, bestBid = 0, bestAsk = 0;
        if (market && market.length > 0) {
            const m = market[0];
            volume = parseFloat(m.volumeNum || 0);
            liquidity = parseFloat(m.liquidityNum || 0);
            bestBid = parseFloat(m.bestBid || 0);
            bestAsk = parseFloat(m.bestAsk || 0);

            console.log(
                `$${volume.toFixed(0).padStart(6)} vol | $${liquidity.toFixed(0).padStart(5)} liq | ` +
                `bid/ask: ${bestBid.toFixed(3)}/${bestAsk.toFixed(3)} | ${pos.title.substring(0, 45)}`
            );
        }

        // Try CLOB trades for this token
        const tokenId = pos.token_id;
        const trades = await fetch(`https://clob.polymarket.com/trades?token_id=${tokenId}&limit=100`);
        if (trades && Array.isArray(trades)) {
            const makers = new Set(trades.map(t => t.maker_address).filter(Boolean));
            const takers = new Set(trades.map(t => t.taker_address).filter(Boolean));
            const allUsers = new Set([...makers, ...takers]);
            console.log(`   -> ${trades.length} trades, ${allUsers.size} unique traders`);
        } else if (trades && trades.data && Array.isArray(trades.data)) {
            const allTrades = trades.data;
            const users = new Set();
            allTrades.forEach(t => {
                if (t.maker_address) users.add(t.maker_address);
                if (t.taker_address) users.add(t.taker_address);
                if (t.maker) users.add(t.maker);
                if (t.taker) users.add(t.taker);
            });
            console.log(`   -> ${allTrades.length} trades, ${users.size} unique traders`);
        } else {
            console.log(`   -> trades response:`, typeof trades, trades ? Object.keys(trades).join(',') : 'null');
        }
    }
}

main();
