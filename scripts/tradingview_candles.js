// Daily candles for many symbols in one process, written as JSON lines.
//
// TradingView has no REST endpoint for this: a chart session is opened
// over a WebSocket, the market is set, and candles arrive on an update
// callback. That is why this is Node rather than Python - the library
// that speaks the protocol is a Node one - and why it is a batch rather
// than a process per symbol: a spawn per ticker would cost more than
// the fetch.
//
// Usage: node scripts/tradingview_candles.js <requests.json> <out.jsonl>
//   requests.json: [{"symbol": "FPT", "exchange": "HOSE"}, ...]
//   out.jsonl:     one {"symbol", "ok", "candles"|"error"} per line
//
// Every symbol produces a line, including the ones that fail. A symbol
// that is simply absent from the output is indistinguishable from one
// the venue refused, and that ambiguity is what the price path has
// spent several runs removing.

const fs = require('fs');
const TradingView = require('@mathieuc/tradingview');

//: How long one symbol may hold a session open. TradingView answers in
//: about a second when it answers at all; a symbol it does not know
//: goes quiet rather than erroring, so the timeout is the only thing
//: that ends it.
const TIMEOUT_MS = 12000;

//: Sessions open at once. The library multiplexes over one socket, so
//: this bounds memory and politeness rather than connections.
const CONCURRENCY = 8;

//: Daily candles to request. 2,600 trading days is about ten years,
//: which covers the 2016 start the quarter milestones assume.
const RANGE = 2600;

function candlesFor(client, symbol, exchange) {
  return new Promise((resolve) => {
    const chart = new client.Session.Chart();
    let settled = false;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { chart.delete(); } catch (err) { /* already gone */ }
      resolve(value);
    };

    const timer = setTimeout(
      () => finish({ symbol, ok: false, error: `timeout after ${TIMEOUT_MS}ms` }),
      TIMEOUT_MS);

    chart.onError((...err) => finish({ symbol, ok: false, error: String(err) }));

    chart.onUpdate(() => {
      if (!chart.periods || chart.periods.length === 0) return;
      // TradingView delivers newest-first; the lake and every quarter
      // boundary downstream assume ascending time.
      const candles = chart.periods
        .map((p) => ({
          time: new Date(p.time * 1000).toISOString().split('T')[0],
          open: p.open,
          high: p.max,
          low: p.min,
          close: p.close,
          volume: p.volume,
        }))
        .sort((a, b) => (a.time < b.time ? -1 : 1));
      finish({ symbol, ok: true, candles });
    });

    try {
      chart.setMarket(`${exchange}:${symbol}`, { timeframe: 'D', range: RANGE });
    } catch (err) {
      finish({ symbol, ok: false, error: String(err) });
    }
  });
}

async function main() {
  const [requestsPath, outPath] = process.argv.slice(2);
  if (!requestsPath || !outPath) {
    console.error('usage: tradingview_candles.js <requests.json> <out.jsonl>');
    process.exit(2);
  }

  const requests = JSON.parse(fs.readFileSync(requestsPath, 'utf-8'));
  const out = fs.createWriteStream(outPath, { flags: 'w' });
  const client = new TradingView.Client();

  let answered = 0;
  let index = 0;

  async function worker() {
    while (index < requests.length) {
      const req = requests[index++];
      const row = await candlesFor(client, req.symbol, req.exchange || 'HOSE');
      if (row.ok) answered += 1;
      out.write(JSON.stringify(row) + '\n');
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(CONCURRENCY, requests.length) }, worker));

  await new Promise((resolve) => out.end(resolve));
  try { client.end(); } catch (err) { /* socket already closed */ }

  // stderr, so the Python caller can read it without parsing the JSONL.
  console.error(`[tradingview] answered for ${answered} of ${requests.length}`);
  process.exit(0);
}

main().catch((err) => {
  console.error('[tradingview] fatal:', err);
  process.exit(1);
});
