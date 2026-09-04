const fs = require('fs');
const path = require('path');

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
const TradingView = require('@mathieuc/tradingview');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT_FILE = path.join(DATA_DIR, 'historical_prices.json');

// Quarters 2016 to 2026
const QUARTERS = [];
for (let y = 2016; y <= 2026; y++) {
  const maxQ = (y === 2026) ? 1 : 4;
  for (let q = 1; q <= maxQ; q++) {
    const qCode = `${y}-Q${q}`;
    let sMonth = (q - 1) * 3 + 1;
    let eMonth = q * 3;
    let startStr = `${y}-${String(sMonth).padStart(2, '0')}-01`;
    let lastDay = (q === 1 || q === 4) ? '31' : '30';
    let endStr = `${y}-${String(eMonth).padStart(2, '0')}-${lastDay}`;
    QUARTERS.push({ code: qCode, year: y, quarter: q, start: startStr, end: endStr });
  }
}

function loadAllStockTickers() {
  const SNAPSHOT_FILE = path.join(DATA_DIR, 'screener_snapshot.json');
  const ALL_SYMBOLS_FILE = path.join(DATA_DIR, 'all_symbols.json');
  
  const validStocks = [];
  const seen = new Set();

  if (fs.existsSync(SNAPSHOT_FILE)) {
    try {
      const snap = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, 'utf-8'));
      const stocks = snap.stocks || {};
      for (const [sym, s] of Object.entries(stocks)) {
        const cleanSym = sym.trim().toUpperCase();
        const ex = (s.exchange || 'HOSE').trim().toUpperCase();
        if (cleanSym.length === 3 && /^[A-Z]{3}$/.test(cleanSym) && !seen.has(cleanSym)) {
          seen.add(cleanSym);
          validStocks.push({ sym: cleanSym, ex });
        }
      }
    } catch (e) {}
  }

  if (fs.existsSync(ALL_SYMBOLS_FILE)) {
    try {
      const raw = JSON.parse(fs.readFileSync(ALL_SYMBOLS_FILE, 'utf-8'));
      for (const item of raw) {
        const sym = (item.symbol || '').trim().toUpperCase();
        const ex = (item.exchange || '').trim().toUpperCase();
        const type = (item.type || '').trim().toUpperCase();
        if (sym.length === 3 && /^[A-Z]{3}$/.test(sym) && ['HOSE', 'HNX', 'UPCOM'].includes(ex)) {
          if (!seen.has(sym) && (type === 'STOCK' || !type || type === 'CP' || type === 'CO_PHIEU')) {
            seen.add(sym);
            validStocks.push({ sym, ex });
          }
        }
      }
    } catch (e) {}
  }

  const order = { 'HOSE': 1, 'HNX': 2, 'UPCOM': 3 };
  validStocks.sort((a, b) => (order[a.ex] || 99) - (order[b.ex] || 99));
  return validStocks;
}

function processCandlesToQuarters(sym, ex, candles) {
  if (!candles || candles.length === 0) return null;

  const sorted = [...candles].sort((a, b) => a.timestamp - b.timestamp);
  const quartersMap = {};
  let prevClose = null;

  for (const q of QUARTERS) {
    const qCandles = sorted.filter(c => c.time >= q.start && c.time <= q.end);
    if (qCandles.length === 0) continue;

    const firstCandle = qCandles[0];
    const lastCandle = qCandles[qCandles.length - 1];

    const basePrice = (prevClose !== null) ? prevClose : firstCandle.open;
    const endPrice = lastCandle.close;

    const retPct = basePrice > 0 ? Number((((endPrice - basePrice) / basePrice) * 100).toFixed(2)) : 0;

    let qHigh = Math.max(...qCandles.map(c => c.high));
    let qLow = Math.min(...qCandles.map(c => c.low));
    let qVol = qCandles.reduce((sum, c) => sum + (c.volume || 0), 0);

    quartersMap[q.code] = {
      quarter: q.code,
      start_date: firstCandle.time,
      end_date: lastCandle.time,
      start_price: Number(basePrice.toFixed(2)),
      close_price: Number(endPrice.toFixed(2)),
      high: Number(qHigh.toFixed(2)),
      low: Number(qLow.toFixed(2)),
      volume: qVol,
      return_pct: retPct
    };

    prevClose = endPrice;
  }

  const qKeys = Object.keys(quartersMap);
  if (qKeys.length === 0) return null;

  return {
    symbol: sym,
    exchange: ex,
    total_quarters: qKeys.length,
    earliest_quarter: qKeys[0],
    latest_quarter: qKeys[qKeys.length - 1],
    quarters: quartersMap
  };
}

class TVWorker {
  constructor(id) {
    this.id = id;
    this.client = new TradingView.Client();
  }

  fetchStock(sym, ex, range = 2600) {
    return new Promise((resolve) => {
      let done = false;
      const fullSymbol = `${ex}:${sym}`;
      const chart = new this.client.Session.Chart();

      const cleanup = () => {
        try { chart.delete(); } catch(e) {}
      };

      const timeout = setTimeout(() => {
        if (!done) {
          done = true;
          cleanup();
          resolve(null);
        }
      }, 3500);

      chart.setMarket(fullSymbol, {
        timeframe: 'D',
        range: range
      });

      chart.onUpdate(() => {
        if (!done && chart.periods && chart.periods.length > 0) {
          done = true;
          clearTimeout(timeout);
          const candles = chart.periods.map(p => ({
            time: new Date(p.time * 1000).toISOString().split('T')[0],
            timestamp: p.time,
            open: p.open,
            high: p.max,
            low: p.min,
            close: p.close,
            volume: p.volume
          }));
          cleanup();
          resolve(candles);
        }
      });

      chart.onError(() => {
        if (!done) {
          done = true;
          clearTimeout(timeout);
          cleanup();
          resolve(null);
        }
      });
    });
  }

  async fetchWithFallback(sym, preferredEx) {
    let candles = await this.fetchStock(sym, preferredEx);
    if (candles && candles.length >= 4) return { candles, resolvedEx: preferredEx };

    const otherExchanges = ['HOSE', 'HNX', 'UPCOM'].filter(x => x !== preferredEx);
    for (const altEx of otherExchanges) {
      candles = await this.fetchStock(sym, altEx);
      if (candles && candles.length >= 4) {
        return { candles, resolvedEx: altEx };
      }
    }
    return { candles: null, resolvedEx: preferredEx };
  }

  close() {
    try { this.client.end(); } catch (e) {}
  }
}

async function syncAllTradingViewPrices() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  const allStocks = loadAllStockTickers();

  const forceRefresh = process.argv.includes('--force') || process.argv.includes('-f');
  let db = {};
  if (!forceRefresh && fs.existsSync(OUTPUT_FILE)) {
    try {
      db = JSON.parse(fs.readFileSync(OUTPUT_FILE, 'utf-8')).symbols || {};
    } catch (e) {}
  }

  console.log(`=============================================================`);
  console.log(` 🌐 TRADINGVIEW FULL MARKET REAL PRICE LAKE SYNCHRONIZER`);
  console.log(` Total Stocks on HOSE, HNX, UPCOM: ${allStocks.length}`);
  console.log(` Force Refresh Mode: ${forceRefresh ? 'YES (Full Clean Resync)' : 'NO'}`);
  console.log(` Already Cached: ${Object.keys(db).length}`);
  console.log(` Target File: ${OUTPUT_FILE}`);
  console.log(`=============================================================`);

  const targetStocks = forceRefresh ? allStocks : allStocks.filter(s => !db[s.sym] || Object.keys(db[s.sym].quarters || {}).length < 4);
  console.log(`🎯 Stocks to sync: ${targetStocks.length}`);

  const NUM_WORKERS = 5;
  const workers = Array.from({ length: NUM_WORKERS }, (_, i) => new TVWorker(i + 1));
  
  await new Promise(r => setTimeout(r, 600));

  const startTime = Date.now();
  let successCount = 0;
  let processedCount = 0;

  async function processQueue() {
    let idx = 0;

    async function workerLoop(worker) {
      while (idx < targetStocks.length) {
        const item = targetStocks[idx++];
        if (!item) break;

        const { candles, resolvedEx } = await worker.fetchWithFallback(item.sym, item.ex);
        processedCount++;

        if (candles && candles.length >= 4) {
          const qData = processCandlesToQuarters(item.sym, resolvedEx, candles);
          if (qData && qData.total_quarters >= 4) {
            db[item.sym] = qData;
            successCount++;
            if (successCount % 25 === 0 || successCount <= 10) {
              console.log(`  ✓ [${successCount}/${targetStocks.length}] ${resolvedEx}:${item.sym} -> ${qData.total_quarters}Q (${qData.earliest_quarter} -> ${qData.latest_quarter})`);
            }
          }
        }

        if (processedCount % 30 === 0 || processedCount >= targetStocks.length) {
          const payload = {
            version: '4.0-unified-full-market',
            last_updated: new Date().toISOString(),
            total_symbols: Object.keys(db).length,
            source: 'TradingView & Multi-Source Real Historical Feeds',
            symbols: db
          };
          fs.writeFileSync(OUTPUT_FILE, JSON.stringify(payload, null, 2), 'utf-8');
          console.log(`  💾 [Checkpoint] Data Lake holds ${Object.keys(db).length} stocks (Saved)`);
        }

        await new Promise(r => setTimeout(r, 30));
      }
    }

    await Promise.all(workers.map(w => workerLoop(w)));
  }

  await processQueue();

  workers.forEach(w => w.close());

  const payload = {
    version: '4.0-unified-full-market',
    last_updated: new Date().toISOString(),
    total_symbols: Object.keys(db).length,
    source: 'TradingView & Multi-Source Real Historical Feeds',
    symbols: db
  };

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(payload, null, 2), 'utf-8');
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\n✨ DONE: Successfully synced ${Object.keys(db).length} stocks in ${elapsed}s!`);
}

syncAllTradingViewPrices()
  .then(() => process.exit(0))
  .catch(err => {
    console.error('Sync error:', err);
    process.exit(1);
  });
