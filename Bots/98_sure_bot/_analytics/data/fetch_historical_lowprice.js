/**
 * Fetch resolved politics/geopolitics markets from Polymarket Gamma API
 * and analyze win rates at different price levels.
 *
 * Key question: If we bet on outcomes priced 85-96c in politics/geopolitics,
 * what would the historical win rate be?
 */

const fs = require("fs");
const path = require("path");

const GAMMA_API = "https://gamma-api.polymarket.com";
const PAGE_SIZE = 100;
const MAX_PAGES = 80; // up to 8000 markets
const DELAY_MS = 400;

// --- helpers ---

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function categorize(question) {
  const q = (question || "").toLowerCase();

  // Sports first (to exclude from politics/geo)
  const sportsKw = [
    "vs.", "vs ", "o/u ", "spread:", "map ", "game handicap",
    "nba", "nhl", "mlb", "nfl", "mls", "ufc", "atp", "wta",
    "counter-strike", "cs2", "valorant", "dota", "lol:",
    "tennis", "boxing", "cricket", "t20", "ipl",
  ];
  if (sportsKw.some((k) => q.includes(k))) return "sports";

  if (["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "token"].some((k) => q.includes(k)))
    return "crypto";

  if (
    ["president", "election", "trump", "biden", "congress", "senate",
      "governor", "democrat", "republican", "vote", "minister", "parliament",
      "tariff", "executive order", "white house", "oval office", "legislation",
      "veto", "impeach", "speaker", "nomination", "cabinet", "political",
      "party", "ballot", "primary", "caucus", "poll", "midterm",
    ].some((k) => q.includes(k))
  )
    return "politics";

  if (
    ["war", "strike", "invasion", "military", "ceasefire", "nato",
      "ukraine", "russia", "iran", "israel", "sanction", "missile",
      "nuclear", "bomb", "attack", "conflict", "troops", "syria",
      "hamas", "hezbollah", "gaza", "yemen", "houthi", "china", "taiwan",
      "north korea", "kim jong", "annex", "occupation",
    ].some((k) => q.includes(k))
  )
    return "geopolitics";

  if (["s&p", "nasdaq", "stock", "gold", "oil", "crude", "fed ",
    "interest rate", "gdp", "inflation"].some((k) => q.includes(k)))
    return "finance";

  if (["ai ", "openai", "chatgpt", "google", "apple", "meta ", "amazon"].some((k) => q.includes(k)))
    return "tech";

  return "other";
}

function parsePrices(raw) {
  if (!raw) return [];
  try {
    const arr = typeof raw === "string" ? JSON.parse(raw) : raw;
    return arr.map(Number);
  } catch {
    return [];
  }
}

function parseList(raw) {
  if (!raw) return [];
  try {
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return [];
  }
}

function priceBucket(p) {
  if (p < 0.85) return "<85c";
  if (p < 0.90) return "85-90c";
  if (p < 0.92) return "90-92c";
  if (p < 0.94) return "92-94c";
  if (p < 0.96) return "94-96c";
  if (p < 0.98) return "96-98c";
  return "98c+";
}

// --- API ---

async function fetchPage(offset, params) {
  const url = new URL(`${GAMMA_API}/markets`);
  const allParams = { limit: PAGE_SIZE, offset, ...params };
  for (const [k, v] of Object.entries(allParams)) {
    url.searchParams.set(k, String(v));
  }

  const resp = await fetch(url.toString());
  if (!resp.ok) {
    console.error(`API error ${resp.status} at offset ${offset}`);
    return [];
  }
  return resp.json();
}

async function fetchClosedMarkets() {
  const allMarkets = [];

  // Strategy: fetch closed markets, then filter by category locally
  // The Gamma API doesn't have a reliable "tag" or "category" param,
  // so we fetch all closed markets and categorize by keywords.
  console.log("Fetching closed markets from Gamma API...");

  for (let page = 0; page < MAX_PAGES; page++) {
    const offset = page * PAGE_SIZE;
    const batch = await fetchPage(offset, {
      closed: "true",
      active: "false",
      order: "volume",
      ascending: "false",
    });

    if (!batch || batch.length === 0) {
      console.log(`  Stopped at offset ${offset} (empty response)`);
      break;
    }

    allMarkets.push(...batch);
    process.stdout.write(`  Fetched ${allMarkets.length} markets (offset ${offset})...\r`);

    if (batch.length < PAGE_SIZE) {
      console.log(`\n  Stopped at offset ${offset} (partial page: ${batch.length})`);
      break;
    }

    await sleep(DELAY_MS);
  }

  console.log(`\nTotal closed markets fetched: ${allMarkets.length}`);
  return allMarkets;
}

// --- analysis ---

function determineWinner(market) {
  // Method 1: check if final outcomePrices has a 1.0 / 0.0
  const prices = parsePrices(market.outcomePrices);
  const outcomes = parseList(market.outcomes);

  if (prices.length === outcomes.length && prices.length >= 2) {
    for (let i = 0; i < prices.length; i++) {
      if (prices[i] >= 0.99) {
        return { winnerIndex: i, winnerOutcome: outcomes[i], method: "final_price" };
      }
    }
  }

  // Method 2: check winner field
  if (market.winner) {
    const idx = outcomes.indexOf(market.winner);
    return { winnerIndex: idx, winnerOutcome: market.winner, method: "winner_field" };
  }

  return null;
}

function analyzeMarkets(markets) {
  const targetCategories = ["politics", "geopolitics"];
  const results = [];
  let skippedNoCategory = 0;
  let skippedNoResolution = 0;

  for (const m of markets) {
    const cat = categorize(m.question);
    if (!targetCategories.includes(cat)) {
      skippedNoCategory++;
      continue;
    }

    // We need to figure out if this market is truly resolved
    if (!m.closed) {
      continue;
    }

    const outcomes = parseList(m.outcomes);
    const prices = parsePrices(m.outcomePrices);

    if (outcomes.length < 2 || prices.length < 2) continue;

    const resolution = determineWinner(m);
    if (!resolution) {
      skippedNoResolution++;
      continue;
    }

    // For each outcome, we want to know what its price was BEFORE resolution.
    // The current outcomePrices on a closed market are the FINAL prices (1.0/0.0).
    // We need pre-resolution prices. Unfortunately, the Gamma API snapshot only
    // shows final prices for closed markets.
    //
    // HOWEVER: for markets that resolved to a clear winner, we can reconstruct:
    // - The winning outcome is now at ~1.0
    // - The losing outcome is now at ~0.0
    //
    // We CAN'T get historical pre-close prices from the list endpoint alone.
    // But we can look at clobRewards or other indicators.
    //
    // Alternative approach: look at markets where we KNOW the final state,
    // and use the volume-weighted or last-trade data if available.
    //
    // Since the API returns final (post-resolution) prices, we'll need another
    // approach. Let's check if there's useful pre-resolution price data.

    results.push({
      id: m.id,
      conditionId: m.conditionId,
      question: m.question,
      category: cat,
      outcomes,
      finalPrices: prices,
      resolution,
      volume: parseFloat(m.volumeNum || 0),
      liquidity: parseFloat(m.liquidityNum || 0),
      endDate: m.endDate,
      closedTime: m.closedTime,
      createdAt: m.createdAt,
      clobRewards: m.clobRewards,
      negRisk: m.negRisk,
      // Store raw for debugging
      _rawOutcomePrices: m.outcomePrices,
    });
  }

  console.log(`\nAnalysis summary:`);
  console.log(`  Skipped (wrong category): ${skippedNoCategory}`);
  console.log(`  Skipped (no resolution): ${skippedNoResolution}`);
  console.log(`  Politics/geopolitics resolved: ${results.length}`);

  return results;
}

// Since the Gamma API list endpoint returns FINAL prices (post-resolution),
// we need to fetch individual market details or use the events/timeseries endpoint
// to get pre-resolution prices. Let's try fetching individual markets to see if
// there's price history or snapshot data.

async function fetchMarketDetails(marketId) {
  try {
    const resp = await fetch(`${GAMMA_API}/markets/${marketId}`);
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

// Alternative: use the Polymarket CLOB API for price history
// But that requires token IDs and is complex.
//
// BETTER APPROACH: The Gamma API actually does return final prices for closed
// markets. For a binary market that resolved YES, the prices are [1.0, 0.0].
//
// But we want to simulate: "if we had bought at price X before resolution".
// We can't get exact pre-resolution prices from the batch endpoint.
//
// WORKAROUND: Use the 97_scanner's collected data! It has pre-resolution snapshots.
// Let's also check if there are timeseries endpoints.

// Actually, let me re-think. The user wants us to check the Gamma API.
// Let's try a different approach: query markets that are CURRENTLY open
// at various price levels and also query the closed ones. For closed ones,
// we look at clobRewards to see payoff structure.
//
// ACTUALLY the simplest reliable approach:
// For closed markets, the outcomePrices field shows the RESOLUTION state.
// If outcome "Yes" has price 1.0, it means Yes won.
// We can't determine what the PRE-resolution price was from this endpoint alone.
//
// BUT: we can use the `events` endpoint which groups markets, and possibly
// the individual market endpoint has more detail. Let me try.

async function enrichWithPriceHistory(resolvedMarkets) {
  // For each resolved market, try to get price history from the timeseries endpoint
  // or check if the individual market endpoint has pre-close price data.

  // Actually, let me check one market to see what fields are available
  if (resolvedMarkets.length > 0) {
    console.log("\nChecking individual market endpoint for price history...");
    const sample = await fetchMarketDetails(resolvedMarkets[0].id);
    if (sample) {
      const keys = Object.keys(sample);
      console.log(`  Available fields: ${keys.join(", ")}`);

      // Check for any price-history-related fields
      const priceFields = keys.filter(k =>
        k.toLowerCase().includes("price") ||
        k.toLowerCase().includes("history") ||
        k.toLowerCase().includes("snapshot") ||
        k.toLowerCase().includes("reward")
      );
      console.log(`  Price-related fields: ${priceFields.join(", ")}`);

      // Log clobRewards
      if (sample.clobRewards) {
        console.log(`  clobRewards: ${JSON.stringify(sample.clobRewards)}`);
      }
    }
  }
}

// --- REVISED APPROACH ---
// Since we can't get pre-resolution prices from the closed markets endpoint,
// let's use a HYBRID approach:
//
// 1. Fetch OPEN markets in politics/geopolitics with high prices (85-99c)
//    This tells us what's currently available.
//
// 2. Fetch CLOSED markets and use the 97_scanner data which HAS snapshots
//    with pre-resolution prices.
//
// 3. For the closed markets from Gamma API, we analyze the RESOLUTION PATTERN:
//    - How many politics/geo markets resolved YES vs NO
//    - Volume distribution
//    - This gives us the base rate

// Actually, I just realized: we CAN get useful data.
// For BINARY markets: outcomes = ["Yes", "No"], prices = ["0.95", "0.05"]
// On CLOSED markets: prices = ["1", "0"] means Yes won.
//
// The KEY INSIGHT: We don't need pre-resolution prices from the API.
// We need to know: OF ALL OUTCOMES THAT WERE EVER PRICED AT 85-96c,
// HOW MANY WON?
//
// We can approximate this by using the 97_scanner's historical data,
// which actually tracks prices over time.
//
// For the Gamma API approach: we can look at CURRENTLY OPEN markets,
// note their prices, and then check resolution later. But for HISTORICAL
// analysis of closed markets, we need price history.
//
// Let me try the Polymarket CLOB timeseries or check if there's a
// price history endpoint.

async function tryTimeseries(conditionId) {
  // Try to get price history
  try {
    const resp = await fetch(`${GAMMA_API}/markets/${conditionId}/timeseries`);
    if (resp.ok) {
      const data = await resp.json();
      console.log(`  Timeseries available! Keys: ${Object.keys(data).join(", ")}`);
      return data;
    }
    console.log(`  Timeseries: ${resp.status}`);
  } catch (e) {
    console.log(`  Timeseries error: ${e.message}`);
  }
  return null;
}

// --- FINAL APPROACH ---
// After exploring the API limitations, here's the plan:
//
// The Gamma API /markets endpoint for closed markets returns final (post-resolution)
// prices. We CANNOT get pre-resolution prices from batch queries.
//
// HOWEVER, the Gamma API has a `/prices/history` or similar endpoint.
// Let me try different endpoints.
//
// If that fails, we'll use a statistical approach:
// For each closed market, we know the outcome. For binary Yes/No markets,
// if the market resolved to one side, we can check what the implied
// probability was by looking at the relationship between volume and outcome.
//
// SIMPLEST VALID APPROACH:
// Use scanner_data.json from 97_scanner which has historical price snapshots!

async function loadScannerData() {
  const scannerPath = path.join(__dirname, "..", "..", "97_scanner", "scanner_data.json");
  try {
    const raw = fs.readFileSync(scannerPath, "utf-8");
    return JSON.parse(raw);
  } catch (e) {
    console.log(`Could not load scanner data: ${e.message}`);
    return null;
  }
}

// ============================================================
// MAIN: Combined approach
// 1. Fetch closed markets from Gamma API (for volume, category, resolution data)
// 2. Try to get pre-resolution prices from timeseries/prices endpoint
// 3. Fall back to scanner_data.json for historical price snapshots
// ============================================================

async function main() {
  console.log("=" .repeat(70));
  console.log("  POLYMARKET HISTORICAL ANALYSIS: Politics/Geopolitics Win Rates");
  console.log("  Price range focus: 85-96 cents");
  console.log("=" .repeat(70));

  // Step 1: Fetch all closed markets
  const closedMarkets = await fetchClosedMarkets();

  // Step 2: Filter & analyze
  const resolved = analyzeMarkets(closedMarkets);

  console.log(`\nPolitics markets: ${resolved.filter(r => r.category === "politics").length}`);
  console.log(`Geopolitics markets: ${resolved.filter(r => r.category === "geopolitics").length}`);

  // Step 3: Try to get price history for a sample market
  if (resolved.length > 0) {
    console.log("\n--- Exploring price history endpoints ---");
    const sample = resolved[0];
    console.log(`Sample market: ${sample.question}`);
    console.log(`  ID: ${sample.id}, conditionId: ${sample.conditionId}`);

    // Try timeseries
    await tryTimeseries(sample.id);

    // Try /prices endpoint
    try {
      const resp = await fetch(`${GAMMA_API}/prices?market=${sample.conditionId}`);
      console.log(`  /prices?market=: ${resp.status}`);
      if (resp.ok) {
        const d = await resp.json();
        console.log(`  Prices response: ${JSON.stringify(d).substring(0, 200)}`);
      }
    } catch (e) {
      console.log(`  /prices error: ${e.message}`);
    }

    // Try individual market detail for enriched data
    const detail = await fetchMarketDetails(sample.id);
    if (detail) {
      // Check for any spread/bestBid/bestAsk that might indicate last pre-close price
      console.log(`  bestBid: ${detail.bestBid}, bestAsk: ${detail.bestAsk}, spread: ${detail.spread}`);
    }
  }

  // Step 4: Load scanner data for historical price snapshots
  console.log("\n--- Loading 97_scanner historical data ---");
  const scannerData = await loadScannerData();

  // Step 5: Build the analysis from scanner data (has pre-resolution prices)
  const bucketStats = {};
  const BUCKETS = ["<85c", "85-90c", "90-92c", "92-94c", "94-96c", "96-98c", "98c+"];
  const CATEGORIES = ["politics", "geopolitics", "all_pol_geo"];

  for (const cat of CATEGORIES) {
    bucketStats[cat] = {};
    for (const b of BUCKETS) {
      bucketStats[cat][b] = { total: 0, wins: 0, losses: 0, unknown: 0, markets: [] };
    }
  }

  // From scanner data
  let scannerAnalyzed = 0;
  if (scannerData && scannerData.markets) {
    console.log(`Scanner has ${Object.keys(scannerData.markets).length} tracked markets`);

    for (const [cid, entry] of Object.entries(scannerData.markets)) {
      if (!entry.resolved || entry.resolution === null) continue;

      const cat = entry.category;
      if (cat !== "politics" && cat !== "geopolitics") continue;

      scannerAnalyzed++;

      // Use first_price (price when first seen at high level)
      const fp = entry.first_price;
      if (!fp) continue;

      const bucket = priceBucket(fp);
      const won = entry.high_outcome_won;

      const record = {
        question: entry.question,
        price: fp,
        won: won,
        category: cat,
        volume: entry.volume,
      };

      // Add to specific category
      bucketStats[cat][bucket].total++;
      if (won === true) bucketStats[cat][bucket].wins++;
      else if (won === false) bucketStats[cat][bucket].losses++;
      else bucketStats[cat][bucket].unknown++;
      bucketStats[cat][bucket].markets.push(record);

      // Add to combined
      bucketStats["all_pol_geo"][bucket].total++;
      if (won === true) bucketStats["all_pol_geo"][bucket].wins++;
      else if (won === false) bucketStats["all_pol_geo"][bucket].losses++;
      else bucketStats["all_pol_geo"][bucket].unknown++;
      bucketStats["all_pol_geo"][bucket].markets.push(record);
    }
  }

  console.log(`\nScanner data: ${scannerAnalyzed} resolved politics/geopolitics markets`);

  // Step 6: Also analyze from Gamma API resolved data (resolution patterns, not price-based)
  // We can show: of all resolved politics/geo markets, what % resolved YES?
  const resolutionPatterns = { politics: { yes: 0, no: 0, other: 0 }, geopolitics: { yes: 0, no: 0, other: 0 } };

  for (const r of resolved) {
    const cat = r.category;
    const winOutcome = r.resolution?.winnerOutcome;
    if (winOutcome === "Yes") resolutionPatterns[cat].yes++;
    else if (winOutcome === "No") resolutionPatterns[cat].no++;
    else resolutionPatterns[cat].other++;
  }

  // Step 7: For Gamma closed markets, try to use volume as a proxy signal
  // Higher volume markets that resolved YES were likely priced high before resolution.
  // This is approximate but gives scale.

  // Step 8: ADDITIONAL - query the Gamma API for price history using the
  // /timeseries endpoint with proper market slug
  console.log("\n--- Trying bulk price history via CLOB API ---");

  // Try fetching historical prices for a few markets
  const sampleMarkets = resolved.slice(0, 3);
  for (const sm of sampleMarkets) {
    try {
      // Try the events endpoint which might have more data
      const resp = await fetch(`${GAMMA_API}/events?slug=${encodeURIComponent((sm.question || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").substring(0, 50))}`);
      if (resp.ok) {
        const events = await resp.json();
        if (events.length > 0) {
          const ev = events[0];
          console.log(`  Event "${(ev.title || "").substring(0, 50)}": ${ev.markets?.length || 0} markets`);
        }
      }
    } catch (e) { /* skip */ }
    await sleep(300);
  }

  // ============================================================
  // STEP 9: NEW APPROACH — Fetch price history from Polymarket CLOB prices API
  // The endpoint: GET /prices?token_id=TOKEN&fidelity=60 gives hourly candles
  // Let's try to get pre-resolution prices for resolved politics/geo markets
  // ============================================================

  console.log("\n--- Fetching pre-resolution prices from CLOB ---");

  // For each resolved market from Gamma, get the token IDs and fetch price history
  const enrichedResults = [];
  const MAX_ENRICH = 200; // limit API calls
  let enrichCount = 0;

  for (const rm of resolved) {
    if (enrichCount >= MAX_ENRICH) break;

    // Get full market details to find clobTokenIds
    const detail = await fetchMarketDetails(rm.id);
    if (!detail) { await sleep(200); continue; }

    const tokenIds = parseList(detail.clobTokenIds);
    const outcomes = parseList(detail.outcomes);

    if (tokenIds.length < 2 || outcomes.length < 2) { await sleep(200); continue; }

    // For each outcome/token, try to get the last known pre-resolution price
    // from the CLOB API: https://clob.polymarket.com/prices-history
    for (let i = 0; i < tokenIds.length; i++) {
      try {
        const clobUrl = `https://clob.polymarket.com/prices-history?market=${tokenIds[i]}&interval=max&fidelity=60`;
        const clobResp = await fetch(clobUrl);
        if (clobResp.ok) {
          const history = await clobResp.json();
          if (history && history.history && history.history.length > 0) {
            // Get the last few prices before resolution
            const pricePoints = history.history;
            const lastPrices = pricePoints.slice(-10); // last 10 data points

            // Find the price just before it went to 1.0 or 0.0
            let preResolutionPrice = null;
            for (let j = pricePoints.length - 1; j >= 0; j--) {
              const p = parseFloat(pricePoints[j].p);
              if (p > 0.01 && p < 0.99) {
                preResolutionPrice = p;
                break;
              }
            }

            if (preResolutionPrice !== null) {
              const won = rm.resolution?.winnerIndex === i;
              const bucket = priceBucket(preResolutionPrice);
              const cat = rm.category;

              enrichedResults.push({
                question: rm.question,
                outcome: outcomes[i],
                preResolutionPrice,
                won,
                bucket,
                category: cat,
                volume: rm.volume,
                endDate: rm.endDate,
              });

              // Add to bucket stats
              bucketStats[cat][bucket].total++;
              if (won) bucketStats[cat][bucket].wins++;
              else bucketStats[cat][bucket].losses++;
              bucketStats[cat][bucket].markets.push({
                question: rm.question,
                outcome: outcomes[i],
                price: preResolutionPrice,
                won,
                category: cat,
                volume: rm.volume,
                source: "clob_history",
              });

              bucketStats["all_pol_geo"][bucket].total++;
              if (won) bucketStats["all_pol_geo"][bucket].wins++;
              else bucketStats["all_pol_geo"][bucket].losses++;
              bucketStats["all_pol_geo"][bucket].markets.push({
                question: rm.question,
                outcome: outcomes[i],
                price: preResolutionPrice,
                won,
                category: cat,
                volume: rm.volume,
                source: "clob_history",
              });
            }
          }
        }
      } catch (e) { /* skip */ }
    }

    enrichCount++;
    if (enrichCount % 20 === 0) {
      process.stdout.write(`  Enriched ${enrichCount}/${Math.min(resolved.length, MAX_ENRICH)} markets...\r`);
    }
    await sleep(300);
  }

  console.log(`\nEnriched ${enrichCount} markets with CLOB price history`);
  console.log(`Found ${enrichedResults.length} outcome price points`);

  // ============================================================
  // OUTPUT RESULTS
  // ============================================================

  console.log("\n" + "=".repeat(70));
  console.log("  RESULTS: Win Rates by Price Bucket & Category");
  console.log("=".repeat(70));

  for (const cat of CATEGORIES) {
    const label = cat === "all_pol_geo" ? "COMBINED (Politics + Geopolitics)" : cat.toUpperCase();
    console.log(`\n  --- ${label} ---`);
    console.log(`  ${"Bucket".padEnd(12)} | ${"Total".padEnd(6)} | ${"Wins".padEnd(6)} | ${"Losses".padEnd(6)} | ${"Win%".padEnd(8)} | ${"EV at cost".padEnd(10)}`);
    console.log(`  ${"-".repeat(12)} | ${"-".repeat(6)} | ${"-".repeat(6)} | ${"-".repeat(6)} | ${"-".repeat(8)} | ${"-".repeat(10)}`);

    for (const b of BUCKETS) {
      const s = bucketStats[cat][b];
      const decided = s.wins + s.losses;
      const winRate = decided > 0 ? (s.wins / decided * 100).toFixed(1) : "N/A";

      // EV calculation: if you buy at mid-bucket price, win pays $1, lose pays $0
      // EV = winRate * (1 - cost) - (1 - winRate) * cost
      let ev = "N/A";
      if (decided > 0) {
        const midPrices = {
          "<85c": 0.80, "85-90c": 0.875, "90-92c": 0.91, "92-94c": 0.93,
          "94-96c": 0.95, "96-98c": 0.97, "98c+": 0.99,
        };
        const cost = midPrices[b];
        const wr = s.wins / decided;
        const evVal = wr * (1 - cost) - (1 - wr) * cost;
        ev = (evVal >= 0 ? "+" : "") + (evVal * 100).toFixed(1) + "c";
      }

      console.log(`  ${b.padEnd(12)} | ${String(s.total).padEnd(6)} | ${String(s.wins).padEnd(6)} | ${String(s.losses).padEnd(6)} | ${String(winRate + "%").padEnd(8)} | ${ev.padEnd(10)}`);
    }
  }

  // Resolution pattern from Gamma data
  console.log("\n" + "=".repeat(70));
  console.log("  RESOLUTION PATTERNS (from Gamma API closed markets)");
  console.log("=".repeat(70));
  for (const [cat, data] of Object.entries(resolutionPatterns)) {
    const total = data.yes + data.no + data.other;
    console.log(`  ${cat}: ${total} resolved (Yes: ${data.yes}, No: ${data.no}, Other: ${data.other})`);
    if (total > 0) {
      console.log(`    Yes rate: ${(data.yes / total * 100).toFixed(1)}%`);
    }
  }

  // Key finding for 85-96c range
  console.log("\n" + "=".repeat(70));
  console.log("  KEY FINDING: 85-96c Range Performance");
  console.log("=".repeat(70));

  const targetBuckets = ["85-90c", "90-92c", "92-94c", "94-96c"];
  for (const cat of CATEGORIES) {
    const label = cat === "all_pol_geo" ? "COMBINED" : cat;
    let totalW = 0, totalL = 0;
    for (const b of targetBuckets) {
      totalW += bucketStats[cat][b].wins;
      totalL += bucketStats[cat][b].losses;
    }
    const total = totalW + totalL;
    if (total > 0) {
      const wr = (totalW / total * 100).toFixed(1);
      // Average cost ~0.91
      const evVal = (totalW / total) * (1 - 0.91) - (totalL / total) * 0.91;
      console.log(`  ${label}: ${totalW}W / ${totalL}L = ${wr}% win rate (n=${total})`);
      console.log(`    EV at avg 91c cost: ${evVal >= 0 ? "+" : ""}${(evVal * 100).toFixed(2)} cents per dollar bet`);
    } else {
      console.log(`  ${label}: No data in 85-96c range`);
    }
  }

  // Interesting losses
  console.log("\n" + "=".repeat(70));
  console.log("  NOTABLE LOSSES (outcomes priced 85-96c that LOST)");
  console.log("=".repeat(70));

  for (const b of targetBuckets) {
    const losses = bucketStats["all_pol_geo"][b].markets.filter(m => m.won === false);
    for (const l of losses.slice(0, 10)) {
      console.log(`  ${(l.price * 100).toFixed(1)}c | ${l.category} | ${(l.question || "").substring(0, 60)}`);
      if (l.outcome) console.log(`    Outcome: ${l.outcome}`);
    }
  }

  // Save all data
  const outputPath = path.join(__dirname, "polymarket_historical_lowprice_2026-03-21.json");
  const outputData = {
    generatedAt: new Date().toISOString(),
    summary: {
      totalClosedMarketsFetched: closedMarkets.length,
      politicsGeoResolved: resolved.length,
      enrichedWithClobHistory: enrichedResults.length,
      scannerDataUsed: scannerAnalyzed,
    },
    bucketStats: Object.fromEntries(
      Object.entries(bucketStats).map(([cat, buckets]) => [
        cat,
        Object.fromEntries(
          Object.entries(buckets).map(([b, s]) => [
            b,
            { total: s.total, wins: s.wins, losses: s.losses, unknown: s.unknown, winRate: s.wins + s.losses > 0 ? (s.wins / (s.wins + s.losses) * 100).toFixed(1) + "%" : "N/A" },
          ])
        ),
      ])
    ),
    resolutionPatterns,
    resolvedMarkets: resolved.map(r => ({
      id: r.id,
      question: r.question,
      category: r.category,
      resolution: r.resolution,
      volume: r.volume,
      endDate: r.endDate,
    })),
    enrichedPriceData: enrichedResults,
    rawMarketCount: closedMarkets.length,
  };

  fs.writeFileSync(outputPath, JSON.stringify(outputData, null, 2), "utf-8");
  console.log(`\nData saved to: ${outputPath}`);
  console.log(`File size: ${(fs.statSync(outputPath).size / 1024).toFixed(0)} KB`);
}

main().catch(console.error);
