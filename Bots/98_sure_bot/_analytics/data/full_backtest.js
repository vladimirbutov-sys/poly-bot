/**
 * Full historical backtest: Politics/Geopolitics/Tech at 90-97c entry prices
 *
 * Approach: Use outcomePrices from Gamma API directly (resolved markets show ~1.0 / ~0.0).
 * For pre-resolution prices, we look at markets where outcomes were priced 90-97c
 * BEFORE resolution. Since Gamma returns current (resolved) prices, we need to
 * reconstruct: if an outcome resolved to 1.0 and was in 90-97c range before,
 * we can't tell from outcomePrices alone.
 *
 * NEW STRATEGY: Fetch markets with various tags/keywords, and for each market
 * use CLOB /prices-history with batching to get pre-resolution prices.
 * Also: use the simpler approach of fetching ALL closed markets and using
 * outcomePrices for the ones that have NOT fully resolved yet (price != 0 or 1).
 *
 * HYBRID:
 * 1. Fetch ALL closed markets (up to API limits)
 * 2. For each market with clear resolution (one outcome >= 0.99), record that
 * 3. For pre-resolution price: use CLOB price history (batch with delays)
 * 4. If CLOB unavailable, skip that market for the "entry price" analysis
 *    but still use it for category win-rate baseline
 */

const fs = require("fs");
const path = require("path");

const GAMMA_API = "https://gamma-api.polymarket.com";
const CLOB_API = "https://clob.polymarket.com";
const PAGE_SIZE = 100;
const MAX_PAGES = 200; // up to 20,000 markets
const DELAY_MS = 100;
const CLOB_DELAY_MS = 250;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function categorize(q_) {
  const q = (q_ || "").toLowerCase();

  // Sports first
  const sports = ["vs.", "vs ", "o/u ", "spread:", "map ", "game handicap",
    "nba", "nhl", "mlb", "nfl", "mls", "ufc", "atp", "wta",
    "counter-strike", "cs2", "valorant", "dota", "lol:",
    "tennis", "boxing", "cricket", "t20", "ipl"];
  if (sports.some(k => q.includes(k))) return "sports";

  // Crypto
  if (["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "token"].some(k => q.includes(k)))
    return "crypto";

  // Politics (expanded keywords for better coverage)
  const pol = ["president", "election", "trump", "biden", "congress", "senate",
    "governor", "democrat", "republican", "vote", "minister", "parliament",
    "tariff", "executive order", "white house", "legislation", "veto",
    "impeach", "speaker", "nomination", "cabinet", "political", "party",
    "ballot", "primary", "poll", "midterm", "inaugural", "potus",
    "confirmation", "appointee", "secretary of", "attorney general",
    "supreme court", "scotus", "roe v wade", "filibuster"];
  if (pol.some(k => q.includes(k))) return "politics";

  // Geopolitics (expanded)
  const geo = ["war", "strike", "invasion", "military", "ceasefire", "nato",
    "ukraine", "russia", "iran", "israel", "sanction", "missile",
    "nuclear", "bomb", "attack", "conflict", "troops", "syria",
    "hamas", "hezbollah", "gaza", "yemen", "houthi", "china", "taiwan",
    "north korea", "annex", "occupation", "airstrike", "drone",
    "hostage", "prisoner", "peace deal", "arms deal", "embargo"];
  if (geo.some(k => q.includes(k))) return "geopolitics";

  // Finance
  if (["s&p", "nasdaq", "stock", "gold", "oil", "crude", "fed ",
    "interest rate", "gdp", "inflation"].some(k => q.includes(k)))
    return "finance";

  // Tech (expanded)
  const tech = ["ai ", "openai", "chatgpt", "google", "apple", "meta ", "amazon",
    "microsoft", "nvidia", "spacex", "tesla", "tiktok", "twitter",
    "starlink", "neuralink", "robot", "quantum", "semiconductor",
    "chip", "antitrust", "app store", "android", "iphone"];
  if (tech.some(k => q.includes(k))) return "tech";

  return "other";
}

function parseJSON(raw) {
  if (!raw) return [];
  try { return typeof raw === "string" ? JSON.parse(raw) : raw; }
  catch { return []; }
}

// Determine winner: which outcome has price >= 0.99 (resolved to Yes)
function findWinnerIndex(prices) {
  for (let i = 0; i < prices.length; i++) {
    if (prices[i] >= 0.99) return i;
  }
  return -1; // no clear winner (not fully resolved or multi-outcome)
}

function priceBucket(p) {
  if (p < 0.90) return "<90c";
  if (p < 0.92) return "90-92c";
  if (p < 0.94) return "92-94c";
  if (p < 0.96) return "94-96c";
  if (p < 0.97) return "96-97c";
  if (p < 0.98) return "97-98c";
  if (p < 0.99) return "98-99c";
  return "99c+";
}

async function fetchWithRetry(url, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const resp = await fetch(url);
      if (resp.ok) return await resp.json();
      if (resp.status === 429) {
        console.log(`  Rate limited, waiting ${(i+1)*2}s...`);
        await sleep((i + 1) * 2000);
        continue;
      }
      return null;
    } catch (e) {
      if (i === retries - 1) return null;
      await sleep(1000);
    }
  }
  return null;
}

// Fetch ALL closed markets from Gamma
async function fetchAllClosedMarkets() {
  const all = [];

  for (let page = 0; page < MAX_PAGES; page++) {
    const offset = page * PAGE_SIZE;
    const url = `${GAMMA_API}/markets?closed=true&limit=${PAGE_SIZE}&offset=${offset}`;
    const batch = await fetchWithRetry(url);

    if (!batch || batch.length === 0) break;
    all.push(...batch);
    process.stdout.write(`  Fetched ${all.length} closed markets...\r`);
    if (batch.length < PAGE_SIZE) break;
    await sleep(DELAY_MS);
  }

  console.log(`\nTotal closed markets fetched: ${all.length}`);
  return all;
}

// Fetch CLOB price history for a token
async function fetchPriceHistory(tokenId) {
  const url = `${CLOB_API}/prices-history?market=${tokenId}&interval=max&fidelity=60`;
  return await fetchWithRetry(url, 2);
}

// Get pre-resolution price from history
// "Last stable price" = last price between 0.02 and 0.98
function getLastStablePrice(history) {
  if (!history || !history.history || history.history.length === 0) return null;
  for (let i = history.history.length - 1; i >= 0; i--) {
    const p = parseFloat(history.history[i].p);
    if (p > 0.02 && p < 0.98) return p;
  }
  return null;
}

// Get average of last N stable prices (more robust)
function getAvgStablePrice(history, n = 5) {
  if (!history || !history.history || history.history.length === 0) return null;
  const prices = [];
  for (let i = history.history.length - 1; i >= 0 && prices.length < n; i--) {
    const p = parseFloat(history.history[i].p);
    if (p > 0.02 && p < 0.98) prices.push(p);
  }
  if (prices.length === 0) return null;
  return prices.reduce((a, b) => a + b, 0) / prices.length;
}

async function main() {
  const startTime = Date.now();

  console.log("=".repeat(70));
  console.log("  FULL HISTORICAL BACKTEST: Low-price entries (90-97c)");
  console.log("  Categories: Politics, Geopolitics, Tech");
  console.log("  Date: 2026-03-21");
  console.log("=".repeat(70));

  // ============================================================
  // STEP 1: Fetch all closed markets
  // ============================================================
  console.log("\n[Step 1] Fetching all closed markets from Gamma API...");
  const allClosed = await fetchAllClosedMarkets();

  // ============================================================
  // STEP 2: Categorize and find resolved markets
  // ============================================================
  console.log("\n[Step 2] Categorizing and finding resolved markets...");

  const TARGET_CATS = new Set(["politics", "geopolitics", "tech"]);
  const resolvedMarkets = []; // markets with clear winner

  for (const m of allClosed) {
    const cat = categorize(m.question || "");
    if (!TARGET_CATS.has(cat)) continue;

    const prices = parseJSON(m.outcomePrices).map(Number);
    const outcomes = parseJSON(m.outcomes);
    const tokenIds = parseJSON(m.clobTokenIds);

    if (prices.length < 2 || prices.length !== outcomes.length) continue;
    if (tokenIds.length !== outcomes.length) continue;

    const winnerIdx = findWinnerIndex(prices);
    if (winnerIdx === -1) continue; // no clear resolution

    resolvedMarkets.push({
      id: m.id,
      question: m.question,
      category: cat,
      outcomes,
      prices,
      tokenIds,
      winnerIdx,
      winnerOutcome: outcomes[winnerIdx],
      volume: parseFloat(m.volumeNum || 0),
      liquidity: parseFloat(m.liquidityNum || 0),
      endDate: m.endDate,
      negRisk: m.negRisk || false,
    });
  }

  const catCounts = {};
  for (const m of resolvedMarkets) {
    catCounts[m.category] = (catCounts[m.category] || 0) + 1;
  }

  console.log(`Resolved markets in target categories: ${resolvedMarkets.length}`);
  for (const [cat, cnt] of Object.entries(catCounts).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${cat}: ${cnt}`);
  }

  // ============================================================
  // STEP 3: Fetch CLOB price history for all outcomes
  // ============================================================
  console.log(`\n[Step 3] Fetching CLOB price history for ${resolvedMarkets.length} markets...`);
  console.log("  This may take a while (rate limiting at 250ms per request)...");

  const allDataPoints = []; // { question, outcome, preResPrice, won, category, volume, ... }
  let processed = 0;
  let withHistory = 0;
  let withStablePrice = 0;

  for (const m of resolvedMarkets) {
    for (let i = 0; i < m.tokenIds.length; i++) {
      const history = await fetchPriceHistory(m.tokenIds[i]);

      if (history && history.history && history.history.length > 0) {
        withHistory++;
        const lastStable = getLastStablePrice(history);
        const avgStable = getAvgStablePrice(history, 5);

        if (lastStable !== null) {
          withStablePrice++;
          const won = (i === m.winnerIdx);

          allDataPoints.push({
            question: m.question,
            outcome: m.outcomes[i],
            lastStablePrice: lastStable,
            avgStablePrice: avgStable,
            won,
            category: m.category,
            volume: m.volume,
            liquidity: m.liquidity,
            endDate: m.endDate,
            negRisk: m.negRisk,
            marketId: m.id,
            tokenId: m.tokenIds[i],
            historyLength: history.history.length,
          });
        }
      }

      await sleep(CLOB_DELAY_MS);
    }

    processed++;
    if (processed % 20 === 0) {
      const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
      process.stdout.write(`  ${processed}/${resolvedMarkets.length} markets, ${allDataPoints.length} data points (${elapsed}m elapsed)...\r`);
    }
  }

  console.log(`\n\n[Step 3 complete]`);
  console.log(`  Markets processed: ${processed}`);
  console.log(`  Outcomes with CLOB history: ${withHistory}`);
  console.log(`  Outcomes with stable pre-res price: ${withStablePrice}`);
  console.log(`  Total data points: ${allDataPoints.length}`);

  // ============================================================
  // STEP 4: Build bucket stats by category
  // ============================================================
  console.log("\n[Step 4] Building win rate tables...");

  const BUCKETS = ["<90c", "90-92c", "92-94c", "94-96c", "96-97c", "97-98c", "98-99c", "99c+"];
  const CATEGORIES = ["politics", "geopolitics", "tech", "all_combined"];

  const stats = {};
  for (const cat of CATEGORIES) {
    stats[cat] = {};
    for (const b of BUCKETS) {
      stats[cat][b] = { wins: 0, losses: 0, examples: [] };
    }
  }

  for (const dp of allDataPoints) {
    const b = priceBucket(dp.lastStablePrice);
    const cats = [dp.category, "all_combined"];

    for (const cat of cats) {
      if (dp.won) stats[cat][b].wins++;
      else stats[cat][b].losses++;

      if (stats[cat][b].examples.length < 3) {
        stats[cat][b].examples.push({
          q: dp.question.substring(0, 80),
          outcome: dp.outcome,
          price: dp.lastStablePrice,
          won: dp.won,
          volume: dp.volume,
        });
      }
    }
  }

  // Print results
  console.log("\n" + "=".repeat(90));
  console.log("  WIN RATES BY PRICE BUCKET AND CATEGORY");
  console.log("=".repeat(90));

  const midpoints = {
    "<90c": 0.80, "90-92c": 0.91, "92-94c": 0.93, "94-96c": 0.95,
    "96-97c": 0.965, "97-98c": 0.975, "98-99c": 0.985, "99c+": 0.995
  };

  for (const cat of CATEGORIES) {
    const label = cat === "all_combined" ? "ALL COMBINED" : cat.toUpperCase();
    console.log(`\n  --- ${label} ---`);
    console.log(`  ${"Bucket".padEnd(10)} | ${"W".padEnd(5)} | ${"L".padEnd(5)} | ${"Total".padEnd(5)} | ${"WinRate".padEnd(8)} | ${"EV/bet".padEnd(10)} | ${"Verdict".padEnd(12)}`);
    console.log(`  ${"-".repeat(10)} | ${"-".repeat(5)} | ${"-".repeat(5)} | ${"-".repeat(5)} | ${"-".repeat(8)} | ${"-".repeat(10)} | ${"-".repeat(12)}`);

    for (const b of BUCKETS) {
      const s = stats[cat][b];
      const total = s.wins + s.losses;
      const wr = total > 0 ? (s.wins / total * 100).toFixed(1) + "%" : "N/A";

      let ev = "N/A";
      let verdict = "";
      if (total > 0) {
        const cost = midpoints[b];
        const winRate = s.wins / total;
        const evVal = winRate * (1 - cost) - (1 - winRate) * cost;
        ev = (evVal >= 0 ? "+" : "") + (evVal * 100).toFixed(2) + "c";

        // Need WR > cost for profitability
        const breakEvenWR = cost * 100;
        if (winRate * 100 > breakEvenWR) verdict = "PROFITABLE";
        else if (total < 10) verdict = "LOW_N";
        else verdict = "NEGATIVE EV";
      }

      console.log(`  ${b.padEnd(10)} | ${String(s.wins).padEnd(5)} | ${String(s.losses).padEnd(5)} | ${String(total).padEnd(5)} | ${wr.padEnd(8)} | ${ev.padEnd(10)} | ${verdict}`);
    }
  }

  // ============================================================
  // STEP 5: Full Backtest Simulation
  // ============================================================
  console.log("\n" + "=".repeat(90));
  console.log("  BACKTEST SIMULATION");
  console.log("=".repeat(90));

  // Sort data points by endDate (chronological order)
  const sortedPoints = [...allDataPoints].sort((a, b) =>
    new Date(a.endDate || "2020-01-01").getTime() - new Date(b.endDate || "2020-01-01").getTime()
  );

  // Only use outcomes that were in the 90-99.5c range (our potential entries)
  const tradablePoints = sortedPoints.filter(dp => dp.lastStablePrice >= 0.90 && dp.lastStablePrice <= 0.995);

  console.log(`\nTradable data points (90-99.5c): ${tradablePoints.length}`);

  // Scenario A: Current settings (96-99.5c for politics, 97.5-99.5c for others)
  // Scenario B: Expanded 90-99.5c for politics/geopolitics only
  // Scenario C: Expanded 90-99.5c for politics/geopolitics/tech

  function simulateScenario(name, filterFn, betSize, startBalance) {
    let balance = startBalance;
    let maxBalance = startBalance;
    let minBalance = startBalance;
    let maxDrawdown = 0;
    let wins = 0;
    let losses = 0;
    let totalProfit = 0;
    let totalLoss = 0;
    const equityCurve = [{ bet: 0, balance, event: "start" }];
    const lossDetails = [];

    for (const dp of tradablePoints) {
      if (!filterFn(dp)) continue;

      const entryPrice = dp.lastStablePrice;

      if (dp.won) {
        const profit = betSize * (1 - entryPrice);
        balance += profit;
        totalProfit += profit;
        wins++;
      } else {
        const loss = betSize * entryPrice;
        balance -= loss;
        totalLoss += loss;
        losses++;
        lossDetails.push({
          question: dp.question.substring(0, 80),
          outcome: dp.outcome,
          price: entryPrice,
          category: dp.category,
          lossAmount: loss,
        });
      }

      if (balance > maxBalance) maxBalance = balance;
      const dd = (maxBalance - balance) / maxBalance;
      if (dd > maxDrawdown) maxDrawdown = dd;
      if (balance < minBalance) minBalance = balance;

      equityCurve.push({
        bet: wins + losses,
        balance: Math.round(balance * 100) / 100,
        event: dp.won ? "win" : "loss",
        price: entryPrice,
        category: dp.category,
      });
    }

    const totalBets = wins + losses;
    const winRate = totalBets > 0 ? (wins / totalBets * 100) : 0;
    const pnl = balance - startBalance;
    const roi = (pnl / startBalance * 100);

    // Sharpe-like: avg profit per bet / std dev of returns
    const returns = equityCurve.slice(1).map((e, i) =>
      e.balance - (i > 0 ? equityCurve[i].balance : startBalance)
    );
    const avgReturn = returns.length > 0 ? returns.reduce((a, b) => a + b, 0) / returns.length : 0;
    const stdDev = returns.length > 1 ?
      Math.sqrt(returns.reduce((sum, r) => sum + (r - avgReturn) ** 2, 0) / (returns.length - 1)) : 0;
    const sharpe = stdDev > 0 ? (avgReturn / stdDev) : 0;

    console.log(`\n  === Scenario: ${name} ===`);
    console.log(`  Bets: ${totalBets} (${wins}W / ${losses}L)`);
    console.log(`  Win rate: ${winRate.toFixed(1)}%`);
    console.log(`  P&L: ${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`);
    console.log(`  ROI: ${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%`);
    console.log(`  Max drawdown: ${(maxDrawdown * 100).toFixed(1)}%`);
    console.log(`  Min balance: $${minBalance.toFixed(2)}`);
    console.log(`  Max balance: $${maxBalance.toFixed(2)}`);
    console.log(`  Sharpe-like: ${sharpe.toFixed(3)}`);
    console.log(`  Avg profit per bet: $${(totalBets > 0 ? pnl / totalBets : 0).toFixed(3)}`);

    if (lossDetails.length > 0) {
      console.log(`  --- Losses ---`);
      for (const l of lossDetails.slice(0, 10)) {
        console.log(`    -$${l.lossAmount.toFixed(2)} at ${(l.price*100).toFixed(1)}c [${l.category}] ${l.question}`);
      }
    }

    return { name, totalBets, wins, losses, winRate, pnl, roi, maxDrawdown, sharpe, equityCurve, lossDetails, minBalance, maxBalance };
  }

  const BET = 7.50; // mid of $5-10 range
  const START = 600;

  // Scenario A: Current settings
  const scenA = simulateScenario(
    "A: Current (pol 96c+, other 97.5c+)",
    (dp) => {
      if (dp.category === "politics" || dp.category === "geopolitics") {
        return dp.lastStablePrice >= 0.96 && dp.lastStablePrice <= 0.995;
      }
      return dp.lastStablePrice >= 0.975 && dp.lastStablePrice <= 0.995;
    },
    BET, START
  );

  // Scenario B: Expanded for pol/geo only
  const scenB = simulateScenario(
    "B: Expanded pol/geo to 90c+",
    (dp) => {
      if (dp.category === "politics" || dp.category === "geopolitics") {
        return dp.lastStablePrice >= 0.90 && dp.lastStablePrice <= 0.995;
      }
      return dp.lastStablePrice >= 0.975 && dp.lastStablePrice <= 0.995;
    },
    BET, START
  );

  // Scenario C: Expanded for pol/geo/tech
  const scenC = simulateScenario(
    "C: Expanded pol/geo/tech to 90c+",
    (dp) => {
      if (dp.category === "politics" || dp.category === "geopolitics" || dp.category === "tech") {
        return dp.lastStablePrice >= 0.90 && dp.lastStablePrice <= 0.995;
      }
      return dp.lastStablePrice >= 0.975 && dp.lastStablePrice <= 0.995;
    },
    BET, START
  );

  // ============================================================
  // STEP 6: Recommendations
  // ============================================================
  console.log("\n" + "=".repeat(90));
  console.log("  RECOMMENDATIONS");
  console.log("=".repeat(90));

  // Find optimal threshold per category
  for (const cat of ["politics", "geopolitics", "tech"]) {
    console.log(`\n  --- ${cat.toUpperCase()} ---`);
    const catPoints = allDataPoints.filter(dp => dp.category === cat);

    for (const threshold of [0.90, 0.92, 0.94, 0.95, 0.96, 0.97]) {
      const inRange = catPoints.filter(dp => dp.lastStablePrice >= threshold && dp.lastStablePrice <= 0.995);
      const w = inRange.filter(dp => dp.won).length;
      const l = inRange.filter(dp => !dp.won).length;
      const total = w + l;
      const wr = total > 0 ? (w / total * 100).toFixed(1) : "N/A";
      const breakEven = (threshold * 100).toFixed(0);
      const profitable = total > 0 && (w / total * 100) > threshold * 100;
      console.log(`  Threshold ${(threshold*100).toFixed(0)}c: ${w}W/${l}L = ${wr}% (need >${breakEven}%) ${profitable ? "PROFITABLE" : total < 5 ? "LOW_N" : "NEGATIVE"} (n=${total})`);
    }
  }

  // ============================================================
  // STEP 7: Save results
  // ============================================================
  const outputData = {
    generatedAt: new Date().toISOString(),
    methodology: "Fetched ALL closed markets from Gamma API, filtered to politics/geopolitics/tech with clear resolution. For each outcome, fetched CLOB price history to get pre-resolution 'last stable price' (between 2c-98c). Bucketed by that price and checked if outcome won.",
    summary: {
      totalClosedFetched: allClosed.length,
      resolvedInTargetCategories: resolvedMarkets.length,
      categoryCounts: catCounts,
      outcomesWithHistory: withHistory,
      outcomesWithStablePrice: withStablePrice,
      totalDataPoints: allDataPoints.length,
      elapsedMinutes: ((Date.now() - startTime) / 60000).toFixed(1),
    },
    bucketStats: stats,
    scenarios: {
      A: { ...scenA, equityCurve: scenA.equityCurve.filter((_, i) => i % 5 === 0 || i === scenA.equityCurve.length - 1) },
      B: { ...scenB, equityCurve: scenB.equityCurve.filter((_, i) => i % 5 === 0 || i === scenB.equityCurve.length - 1) },
      C: { ...scenC, equityCurve: scenC.equityCurve.filter((_, i) => i % 5 === 0 || i === scenC.equityCurve.length - 1) },
    },
    allDataPoints: allDataPoints.map(dp => ({
      question: dp.question,
      outcome: dp.outcome,
      lastStablePrice: dp.lastStablePrice,
      avgStablePrice: dp.avgStablePrice,
      won: dp.won,
      category: dp.category,
      volume: dp.volume,
      negRisk: dp.negRisk,
    })),
  };

  const outputPath = path.join(
    "c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data",
    "historical_lowprice_backtest_2026-03-21.json"
  );

  fs.writeFileSync(outputPath, JSON.stringify(outputData, null, 2), "utf-8");
  console.log(`\n\nSaved data to: ${outputPath}`);
  console.log(`Size: ${(fs.statSync(outputPath).size / 1024).toFixed(0)} KB`);
  console.log(`Total elapsed: ${((Date.now() - startTime) / 60000).toFixed(1)} minutes`);
}

main().catch(e => { console.error("Fatal:", e); process.exit(1); });
