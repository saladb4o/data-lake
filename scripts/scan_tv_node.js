const fs = require('fs');
const path = require('path');
const https = require('https');

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const COLUMNS = [
  "name", "description", "exchange", "close", "change", "volume", "market_cap_basic",
  "price_earnings_ttm", "price_book_fq", "price_sales_current", "return_on_equity_fq",
  "return_on_assets_fq", "gross_margin_fq", "operating_margin_fq", "net_margin_fq",
  "total_revenue_growth_yoy_fq", "net_income_growth_yoy_fq", "total_revenue_growth_3y_cagr",
  "total_revenue_growth_5y_cagr", "debt_to_equity_fq", "current_ratio_fq",
  "free_cash_flow_ttm", "free_cash_flow_fq", "cash_f_operating_activities_ttm",
  "net_income_ttm", "earnings_per_share_basic_ttm", "dividend_yield_recent"
];

async function scanTradingViewVietnam() {
  const payload = JSON.stringify({
    filter: [],
    options: { lang: "en" },
    symbols: { query: { types: [] } },
    columns: COLUMNS,
    sort: { sortBy: "market_cap_basic", sortOrder: "desc" },
    range: [0, 2500]
  });

  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: 'scanner.tradingview.com',
      path: '/vietnam/scan',
      method: 'POST',
      family: 4,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
      }
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(body);
          resolve(json);
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('timeout', () => {
      req.destroy(new Error('Request timed out'));
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

scanTradingViewVietnam()
  .then(res => {
    console.log('⚡ SUCCESS! Total Count:', res.totalCount, 'Rows:', res.data ? res.data.length : 0);
    if (res.data && res.data.length > 0) {
      console.log('Top 3 Stocks:');
      res.data.slice(0, 3).forEach(r => {
        console.log(`  • ${r.s} | Price: ${r.d[3]} | Mcap(Bil): ${Math.round(r.d[6]/1e9)} | P/E: ${r.d[7]} | P/B: ${r.d[8]} | ROE: ${r.d[10]}%`);
      });
    }
  })
  .catch(err => console.error('Scan error:', err));
