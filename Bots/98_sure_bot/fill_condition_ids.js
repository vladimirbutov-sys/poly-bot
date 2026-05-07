/**
 * Fill missing condition_ids in positions_restored.json
 * by querying Gamma API with token_id.
 */
const fs = require('fs');
const path = require('path');
const https = require('https');

const RESTORED = path.join(__dirname, 'positions_restored.json');
const OUT_FILE = path.join(__dirname, 'positions_restored.json');

const data = JSON.parse(fs.readFileSync(RESTORED, 'utf8'));

function fetchMarketByToken(tokenId) {
    return new Promise((resolve, reject) => {
        const url = `https://gamma-api.polymarket.com/markets?clob_token_ids=${tokenId}&closed=false&limit=1`;
        // Also try with closed markets
        const url2 = `https://gamma-api.polymarket.com/markets?clob_token_ids=${tokenId}&limit=1`;

        function tryUrl(u, fallback) {
            https.get(u, { timeout: 10000 }, (res) => {
                let body = '';
                res.on('data', d => body += d);
                res.on('end', () => {
                    try {
                        const markets = JSON.parse(body);
                        if (markets && markets.length > 0) {
                            resolve(markets[0]);
                        } else if (fallback) {
                            tryUrl(fallback, null);
                        } else {
                            resolve(null);
                        }
                    } catch(e) { resolve(null); }
                });
            }).on('error', () => {
                if (fallback) tryUrl(fallback, null);
                else resolve(null);
            });
        }

        tryUrl(url, url2);
    });
}

async function main() {
    const positions = Object.values(data.positions);
    const missing = positions.filter(p => !p.condition_id);
    console.log(`Total positions: ${positions.length}`);
    console.log(`Missing condition_id: ${missing.length}`);
    console.log();

    let found = 0;
    let notFound = 0;

    for (const pos of missing) {
        // Small delay to not hammer API
        await new Promise(r => setTimeout(r, 200));

        const market = await fetchMarketByToken(pos.token_id);
        if (market) {
            const cid = market.condition_id || market.conditionId || '';
            const negRisk = market.neg_risk || market.negRisk || false;
            if (cid) {
                pos.condition_id = cid;
                pos.neg_risk = negRisk;
                found++;
                console.log(`OK: ${pos.title.substring(0, 50)} -> ${cid.substring(0, 16)}...`);
            } else {
                notFound++;
                console.log(`NO CID: ${pos.title.substring(0, 50)}`);
            }
        } else {
            notFound++;
            console.log(`NOT FOUND: ${pos.title.substring(0, 50)} | token: ${pos.token_id.substring(0, 20)}...`);
        }
    }

    console.log(`\nFound: ${found}, Not found: ${notFound}`);

    // Update the data object
    for (const pos of positions) {
        data.positions[pos.order_id] = pos;
    }

    fs.writeFileSync(OUT_FILE, JSON.stringify(data, null, 2), 'utf8');
    console.log(`Updated: ${OUT_FILE}`);
}

main().catch(console.error);
