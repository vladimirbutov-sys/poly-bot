/**
 * Check number of unique traders on a sample of markets (volume $1k-$5k)
 * via Polymarket Data API activity endpoint.
 */
const https = require('https');
const fs = require('fs');
const path = require('path');

const data = JSON.parse(fs.readFileSync(
    path.join('C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json'), 'utf8'
));

const allMarkets = Object.entries(data.markets);
const v1k5k = allMarkets
    .filter(([_, m]) => m.resolved && m.volume >= 1000 && m.volume < 5000)
    .slice(0, 30);  // sample 30

function fetchActivity(conditionId) {
    return new Promise((resolve) => {
        const url = `https://data-api.polymarket.com/activity?market=${conditionId}&limit=500`;
        https.get(url, { timeout: 15000 }, (res) => {
            let body = '';
            res.on('data', d => body += d);
            res.on('end', () => {
                try {
                    const trades = JSON.parse(body);
                    if (Array.isArray(trades)) {
                        const uniqueUsers = new Set(trades.map(t => t.user || t.maker || t.taker || ''));
                        uniqueUsers.delete('');
                        resolve({ trades: trades.length, users: uniqueUsers.size });
                    } else {
                        resolve({ trades: 0, users: 0 });
                    }
                } catch(e) { resolve({ trades: 0, users: 0 }); }
            });
        }).on('error', () => resolve({ trades: 0, users: 0 }));
    });
}

async function main() {
    console.log('Checking unique traders for 30 markets (volume $1k-$5k)...\n');

    const results = [];

    for (const [cid, m] of v1k5k) {
        await new Promise(r => setTimeout(r, 300));
        const { trades, users } = await fetchActivity(cid);
        results.push({ question: m.question, volume: m.volume, trades, users });
        console.log(
            `${users.toString().padStart(3)} users | ${trades.toString().padStart(3)} trades | $${m.volume.toFixed(0).padStart(5)} vol | ${m.question.substring(0, 50)}`
        );
    }

    console.log('\n=== SUMMARY ===');
    const under5 = results.filter(r => r.users < 5);
    const under10 = results.filter(r => r.users < 10);
    const under20 = results.filter(r => r.users < 20);
    console.log(`< 5 users:  ${under5.length} / ${results.length}`);
    console.log(`< 10 users: ${under10.length} / ${results.length}`);
    console.log(`< 20 users: ${under20.length} / ${results.length}`);

    if (under20.length > 0) {
        console.log('\n--- Markets with < 20 users ---');
        under20.forEach(r => console.log(`  ${r.users} users | $${r.volume.toFixed(0)} | ${r.question.substring(0, 55)}`));
    }
}

main();
