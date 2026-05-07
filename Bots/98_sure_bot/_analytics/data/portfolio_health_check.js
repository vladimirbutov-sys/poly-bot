const fs = require('fs');
const path = require('path');

const POSITIONS_PATH = path.join(__dirname, '..', '..', 'positions.json');
const OUTPUT_PATH = path.join(__dirname, 'portfolio_health_2026-03-21.json');

async function fetchCurrentPrices(tokenIds) {
  // Gamma API does not support batch queries — fetch one by one
  const results = {};
  const concurrency = 5; // parallel requests

  for (let i = 0; i < tokenIds.length; i += concurrency) {
    const chunk = tokenIds.slice(i, i + concurrency);
    const promises = chunk.map(async (tid) => {
      const url = `https://gamma-api.polymarket.com/markets?clob_token_ids=${tid}`;
      try {
        const resp = await fetch(url);
        if (!resp.ok) {
          console.error(`  API error ${resp.status} for token ${tid.substring(0, 20)}...`);
          return;
        }
        const markets = await resp.json();
        if (!markets.length) return;

        const market = markets[0];
        if (!market.clobTokenIds || !market.outcomePrices) return;

        let tokenIdsList, pricesList;
        try {
          tokenIdsList = JSON.parse(market.clobTokenIds);
          pricesList = JSON.parse(market.outcomePrices);
        } catch {
          tokenIdsList = String(market.clobTokenIds).split(',');
          pricesList = String(market.outcomePrices).split(',');
        }

        for (let j = 0; j < tokenIdsList.length; j++) {
          const id = String(tokenIdsList[j]).trim();
          const price = parseFloat(String(pricesList[j]).trim());
          if (id === tid) {
            results[tid] = {
              current_price: price,
              question: market.question || market.title || '',
              end_date: market.endDate || '',
              active: market.active,
              closed: market.closed
            };
          }
        }
      } catch (err) {
        console.error(`  Fetch error for ${tid.substring(0, 20)}...: ${err.message}`);
      }
    });

    await Promise.all(promises);
    process.stdout.write(`  Fetched ${Math.min(i + concurrency, tokenIds.length)}/${tokenIds.length}\r`);

    // Small delay between chunks to avoid rate limiting
    if (i + concurrency < tokenIds.length) {
      await new Promise(r => setTimeout(r, 200));
    }
  }

  console.log('');
  return results;
}

function getRiskLevel(pctChange) {
  if (pctChange >= -1) return 'OK';
  if (pctChange >= -3) return 'WATCH';
  if (pctChange >= -5) return 'DANGER';
  return 'CRITICAL';
}

function getRiskScore(pctChange, sharesSize) {
  // 0-10 scale based on price drop % and position size
  let score = 0;
  if (pctChange < 0) score += Math.min(Math.abs(pctChange) * 1.5, 7);
  if (sharesSize > 10) score += 1;
  if (sharesSize > 50) score += 1;
  if (pctChange < -5) score += 1;
  return Math.min(Math.round(score * 10) / 10, 10);
}

async function main() {
  // 1. Read positions
  const raw = JSON.parse(fs.readFileSync(POSITIONS_PATH, 'utf-8'));
  const allPositions = raw.positions || raw;

  // 2. Filter open positions
  const openPositions = [];
  for (const [orderId, pos] of Object.entries(allPositions)) {
    if (pos.status === 'open') {
      openPositions.push({ ...pos, order_id: orderId });
    }
  }

  console.log(`\nFound ${openPositions.length} open positions\n`);

  // 3. Collect unique token IDs
  const tokenIds = [...new Set(openPositions.map(p => p.token_id))];
  console.log(`Fetching prices for ${tokenIds.length} unique tokens...\n`);

  // 4. Fetch current prices
  const priceData = await fetchCurrentPrices(tokenIds);

  // 5. Calculate metrics for each position
  const results = openPositions.map(pos => {
    const market = priceData[pos.token_id] || {};
    const currentPrice = market.current_price ?? null;
    const entryPrice = pos.entry_price;

    let priceChange = null;
    let priceChangePct = null;
    let unrealizedPnl = null;
    let riskLevel = 'UNKNOWN';
    let riskScore = 0;

    if (currentPrice !== null) {
      priceChange = +(currentPrice - entryPrice).toFixed(6);
      priceChangePct = +((currentPrice - entryPrice) / entryPrice * 100).toFixed(3);
      unrealizedPnl = +((currentPrice - entryPrice) * pos.size_shares).toFixed(4);
      riskLevel = getRiskLevel(priceChangePct);
      riskScore = getRiskScore(priceChangePct, pos.size_shares);
    }

    return {
      order_id: pos.order_id,
      title: pos.title,
      token_id: pos.token_id,
      entry_price: entryPrice,
      current_price: currentPrice,
      price_change: priceChange,
      price_change_pct: priceChangePct,
      unrealized_pnl: unrealizedPnl,
      size_shares: pos.size_shares,
      cost_usd: pos.cost_usd,
      risk_level: riskLevel,
      risk_score: riskScore,
      market_question: market.question || pos.title,
      end_date: market.end_date || '',
      market_active: market.active,
      market_closed: market.closed,
      neg_risk: pos.neg_risk,
      timestamp: pos.timestamp
    };
  });

  // 6. Sort by price change (worst first)
  results.sort((a, b) => (a.price_change_pct ?? -999) - (b.price_change_pct ?? -999));

  // 7. Print table
  console.log('='.repeat(120));
  console.log('PORTFOLIO HEALTH CHECK — 98_sure_bot — 2026-03-21');
  console.log('='.repeat(120));
  console.log('');

  const counts = { OK: 0, WATCH: 0, DANGER: 0, CRITICAL: 0, UNKNOWN: 0 };
  let totalUnrealizedPnl = 0;
  let totalCost = 0;

  for (const r of results) {
    counts[r.risk_level] = (counts[r.risk_level] || 0) + 1;
    if (r.unrealized_pnl !== null) totalUnrealizedPnl += r.unrealized_pnl;
    totalCost += r.cost_usd;

    const levelTag = `[${r.risk_level.padEnd(8)}]`;
    const titleShort = r.title.length > 55 ? r.title.slice(0, 52) + '...' : r.title.padEnd(55);
    const entry = r.entry_price?.toFixed(3) || '?';
    const current = r.current_price?.toFixed(3) || '?';
    const delta = r.price_change_pct !== null ? `${r.price_change_pct >= 0 ? '+' : ''}${r.price_change_pct.toFixed(1)}%` : '?';
    const pnl = r.unrealized_pnl !== null ? `$${r.unrealized_pnl >= 0 ? '+' : ''}${r.unrealized_pnl.toFixed(3)}` : '?';

    console.log(`${levelTag} ${titleShort} | ${entry} -> ${current} | ${delta.padStart(7)} | shares: ${r.size_shares} | ${pnl}`);
  }

  console.log('');
  console.log('='.repeat(120));
  console.log('SUMMARY');
  console.log('='.repeat(120));
  console.log(`  OK:       ${counts.OK}`);
  console.log(`  WATCH:    ${counts.WATCH}`);
  console.log(`  DANGER:   ${counts.DANGER}`);
  console.log(`  CRITICAL: ${counts.CRITICAL}`);
  console.log(`  UNKNOWN:  ${counts.UNKNOWN}`);
  console.log(`  -------------------------`);
  console.log(`  Total open positions: ${results.length}`);
  console.log(`  Total cost (invested): $${totalCost.toFixed(2)}`);
  console.log(`  Total unrealized P&L:  $${totalUnrealizedPnl >= 0 ? '+' : ''}${totalUnrealizedPnl.toFixed(4)}`);
  console.log('');

  // 8. Print detailed analysis for DANGER and CRITICAL
  const dangerPositions = results.filter(r => r.risk_level === 'DANGER' || r.risk_level === 'CRITICAL');
  if (dangerPositions.length > 0) {
    console.log('='.repeat(120));
    console.log('DANGER & CRITICAL POSITIONS — DETAILED');
    console.log('='.repeat(120));
    for (const r of dangerPositions) {
      console.log(`\n  [${r.risk_level}] ${r.title}`);
      console.log(`    Entry: ${r.entry_price} -> Current: ${r.current_price} | Change: ${r.price_change_pct?.toFixed(2)}%`);
      console.log(`    Shares: ${r.size_shares} | Unrealized P&L: $${r.unrealized_pnl?.toFixed(4)}`);
      console.log(`    Risk Score: ${r.risk_score}/10`);
      console.log(`    Market: ${r.market_question}`);
      console.log(`    End date: ${r.end_date || 'unknown'}`);
      console.log(`    Active: ${r.market_active}, Closed: ${r.market_closed}`);
    }
    console.log('');
  }

  // Also print WATCH positions
  const watchPositions = results.filter(r => r.risk_level === 'WATCH');
  if (watchPositions.length > 0) {
    console.log('='.repeat(120));
    console.log('WATCH POSITIONS — MONITORING NEEDED');
    console.log('='.repeat(120));
    for (const r of watchPositions) {
      console.log(`\n  [WATCH] ${r.title}`);
      console.log(`    Entry: ${r.entry_price} -> Current: ${r.current_price} | Change: ${r.price_change_pct?.toFixed(2)}%`);
      console.log(`    Shares: ${r.size_shares} | Unrealized P&L: $${r.unrealized_pnl?.toFixed(4)}`);
    }
    console.log('');
  }

  // 9. Save results
  const output = {
    generated_at: new Date().toISOString(),
    total_positions: results.length,
    summary: counts,
    total_cost_usd: +totalCost.toFixed(2),
    total_unrealized_pnl: +totalUnrealizedPnl.toFixed(4),
    positions: results
  };

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
  console.log(`Results saved to: ${OUTPUT_PATH}`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
