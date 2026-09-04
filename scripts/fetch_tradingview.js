process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
const TradingView = require('@mathieuc/tradingview');

/**
 * Fetch real historical candles from TradingView WebSocket
 * @param {string} symbol e.g. "HOSE:FPT" or "HNX:SHS" or "UPCOM:BSR"
 * @param {number} range number of candles (default 1500 daily candles ~ 6 years)
 */
async function getTradingViewCandles(symbol = 'HOSE:FPT', range = 1500) {
  const client = new TradingView.Client();
  const chart = new client.Session.Chart();

  return new Promise((resolve, reject) => {
    let settled = false;
    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        client.end();
        reject(new Error(`TradingView timeout for ${symbol}`));
      }
    }, 12000);

    chart.setMarket(symbol, {
      timeframe: 'D',
      range: range,
    });

    chart.onUpdate(() => {
      if (!settled && chart.periods && chart.periods.length > 0) {
        settled = true;
        clearTimeout(timeout);
        const data = chart.periods.map(p => ({
          time: new Date(p.time * 1000).toISOString().split('T')[0],
          timestamp: p.time,
          open: p.open,
          high: p.max,
          low: p.min,
          close: p.close,
          volume: p.volume
        }));
        client.end();
        resolve(data);
      }
    });

    chart.onError((...err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        client.end();
        reject(err);
      }
    });
  });
}

// If executed directly from CLI
if (require.main === module) {
  const sym = process.argv[2] || 'HOSE:FPT';
  console.log(`[TradingView] Fetching ${sym}...`);
  getTradingViewCandles(sym, 1200)
    .then(candles => {
      console.log(`[TradingView] Received ${candles.length} candles for ${sym}`);
      console.log(`[TradingView] Earliest:`, candles[0]);
      console.log(`[TradingView] Latest:`, candles[candles.length - 1]);
      process.exit(0);
    })
    .catch(err => {
      console.error('[TradingView] Error:', err);
      process.exit(1);
    });
}

module.exports = { getTradingViewCandles };
