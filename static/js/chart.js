/**
 * ==========================================================================
 * VNSTOCK TERMINAL PRO - TRADINGVIEW LIGHTWEIGHT CHARTS & ORDER BOOK LADDER
 * ==========================================================================
 */

/**
 * Sanitizes and strictly sorts time-series arrays for LightweightCharts.
 * Eliminates duplicates, NaNs, and out-of-order timestamps.
 */
function sanitizeSeriesData(arr) {
  if (!arr || !Array.isArray(arr) || arr.length === 0) return [];
  
  const valid = [];
  const normalizeTime = (t) => {
    // Guarantee a uniform scalar time type per series: BusinessDay objects -> 'YYYY-MM-DD'
    if (t && typeof t === 'object' && t.year !== undefined) {
      return `${t.year}-${String(t.month).padStart(2, '0')}-${String(t.day).padStart(2, '0')}`;
    }
    return t;
  };
  for (let i = 0; i < arr.length; i++) {
    const item = arr[i];
    if (!item || item.time === undefined || item.time === null) continue;
    const normTime = normalizeTime(item.time);
    
    // Check OHLC candle
    if (item.close !== undefined) {
      const o = Number(item.open);
      const h = Number(item.high);
      const l = Number(item.low);
      const c = Number(item.close);
      if (isNaN(o) || isNaN(h) || isNaN(l) || isNaN(c)) continue;
      valid.push({
        time: normTime,
        open: o,
        high: Math.max(h, o, c),
        low: Math.min(l, o, c),
        close: c
      });
    }
    // Check single-value series (MA, RSI, MACD, Volume)
    else if (item.value !== undefined) {
      const v = Number(item.value);
      if (isNaN(v)) continue;
      const cleanItem = { time: normTime, value: v };
      if (item.color) cleanItem.color = item.color;
      valid.push(cleanItem);
    }
  }

  if (valid.length === 0) return [];

  // Sort chronologically
  valid.sort((a, b) => {
    if (typeof a.time === 'number' && typeof b.time === 'number') {
      return a.time - b.time;
    }
    return String(a.time).localeCompare(String(b.time));
  });

  // Deduplicate by time key (keep last occurrence)
  const uniqueMap = new Map();
  for (let i = 0; i < valid.length; i++) {
    uniqueMap.set(valid[i].time, valid[i]);
  }

  return Array.from(uniqueMap.values());
}

class StockChartManager {
  constructor(options = {}) {
    this.mainContainerId = options.mainContainerId || 'mainChartContainer';
    this.subContainerId = options.subContainerId || 'subChartContainer';
    this.hudPrefix = options.hudPrefix || 'hud'; // 'hud' or 'sectorHud'
    this.mainHeight = options.mainHeight || 360;
    this.subPaneHeight = options.subPaneHeight || 110;

    this.mainContainer = document.getElementById(this.mainContainerId);
    this.subContainer = document.getElementById(this.subContainerId);

    this.mainChart = null;
    this.rsiChart = null;
    this.macdChart = null;

    // Series references
    this.candleSeries = null;
    this.volumeSeries = null;
    this.ma20Series = null;
    this.ma50Series = null;
    this.bollUpperSeries = null;
    this.bollLowerSeries = null;

    this.rsiSeries = null;
    this.macdHistSeries = null;
    this.macdLineSeries = null;
    this.macdSignalSeries = null;

    // Indicators state
    this.indicators = {
      ma20: true,
      ma50: true,
      bollinger: false,
      volume: true,
      rsi: true,
      macd: true
    };

    this.isSyncingRange = false;
    this.isSyncingCrosshair = false;
    this.lastIsIntraday = null;
    this.currentData = null;
    this.logScale = false;
    this.lastRangeCode = null; // null => default (last ~250 bars); 'ALL' => opt-in full fit
    this.totalBars = 0;

    // Cached sanitized series for legend/HUD lookups by time
    this._candleData = [];
    this._rsiData = [];
    this._macdLineData = [];
    this._macdSignalData = [];
    this._macdHistData = [];
    this._volumeCache = [];

    this.initCharts(false);
    this.setupResizeObserver();
    this.setupLogScaleButton();
    this.setupSymbolSearchKeyboard();
  }

  initCharts(isIntraday = false) {
    if (!window.LightweightCharts) {
      console.warn("LightweightCharts library not yet ready, deferring init...");
      setTimeout(() => this.initCharts(isIntraday), 100);
      return;
    }

    if (!this.mainContainer) this.mainContainer = document.getElementById(this.mainContainerId);
    if (!this.subContainer) this.subContainer = document.getElementById(this.subContainerId);

    if (!this.mainContainer || !this.subContainer) return;

    // Explicitly destroy and remove previous LightweightCharts instances
    if (this.mainChart && typeof this.mainChart.remove === 'function') {
      try { this.mainChart.remove(); } catch (e) { console.warn('mainChart.remove error:', e); }
      this.mainChart = null;
    }
    if (this.rsiChart && typeof this.rsiChart.remove === 'function') {
      try { this.rsiChart.remove(); } catch (e) { console.warn('rsiChart.remove error:', e); }
      this.rsiChart = null;
    }
    if (this.macdChart && typeof this.macdChart.remove === 'function') {
      try { this.macdChart.remove(); } catch (e) { console.warn('macdChart.remove error:', e); }
      this.macdChart = null;
    }

    // Clear any previous chart canvases
    this.mainContainer.innerHTML = '';
    this.subContainer.innerHTML = '';

    const width = this.mainContainer.clientWidth > 0 ? this.mainContainer.clientWidth : 750;

    const baseChartOptions = {
      layout: {
        background: { color: '#090e17' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'Inter', monospace"
      },
      grid: {
        vertLines: { color: '#141e33' },
        horzLines: { color: '#141e33' }
      },
      crosshair: {
        vertLine: {
          color: '#38bdf8',
          width: 1,
          style: LightweightCharts.LineStyle.Dashed,
          labelBackgroundColor: '#1e293b'
        },
        horzLine: {
          color: '#38bdf8',
          width: 1,
          style: LightweightCharts.LineStyle.Dashed,
          labelBackgroundColor: '#1e293b'
        }
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: isIntraday,
        secondsVisible: false,
        tickMarkFormatter: (time, weight, locale) => this._formatTickMark(time, weight, locale)
      }
    };

    // 1. Initialize Main Candlestick Chart
    this.mainChart = LightweightCharts.createChart(this.mainContainer, {
      ...baseChartOptions,
      height: this.mainHeight,
      width: width,
      rightPriceScale: {
        borderColor: '#1e293b',
        autoScale: true,
        mode: this.logScale ? LightweightCharts.PriceScaleMode.Logarithmic : LightweightCharts.PriceScaleMode.Normal,
        scaleMargins: {
          top: 0.08,
          bottom: 0.24 // Keep candles in the upper 76% of chart height
        }
      }
    });

    // Candlestick series (TV parity: last price marker + horizontal price line)
    this.candleSeries = this.mainChart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      lastValueVisible: true,
      priceLineVisible: true
    });

    // Volume Series (isolated overlay scale confined strictly to bottom 18%)
    this.volumeSeries = this.mainChart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume_scale',
    });

    this.mainChart.priceScale('volume_scale').applyOptions({
      scaleMargins: {
        top: 0.82, // The highest volume bar will only reach 18% from chart bottom
        bottom: 0,
      },
    });

    // MA20 Line Series
    this.ma20Series = this.mainChart.addLineSeries({
      color: '#38bdf8',
      lineWidth: 2,
      title: 'MA20'
    });

    // MA50 Line Series
    this.ma50Series = this.mainChart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      title: 'MA50'
    });

    // Bollinger Bands Upper & Lower
    this.bollUpperSeries = this.mainChart.addLineSeries({
      color: 'rgba(192, 132, 252, 0.75)',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      title: 'BOLL Up'
    });
    this.bollLowerSeries = this.mainChart.addLineSeries({
      color: 'rgba(192, 132, 252, 0.75)',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      title: 'BOLL Down'
    });

    // 2. Split sub-pane: RSI pane + MACD pane, each with its own TV-style legend row
    this.subContainer.innerHTML = '';
    this.subContainer.style.height = 'auto';

    const buildPane = (legendId, titleHtml) => {
      const wrap = document.createElement('div');
      wrap.style.cssText = 'position:relative;border-top:1px solid var(--border-color,#1e293b);background:#090e17;';
      const legend = document.createElement('div');
      legend.id = legendId;
      legend.style.cssText = 'position:absolute;top:4px;left:10px;z-index:5;font-size:10px;font-family:\'JetBrains Mono\',monospace;color:#94a3b8;pointer-events:none;white-space:nowrap;';
      legend.innerHTML = titleHtml;
      const canvasDiv = document.createElement('div');
      canvasDiv.style.cssText = `height:${this.subPaneHeight}px;width:100%;`;
      wrap.appendChild(legend);
      wrap.appendChild(canvasDiv);
      this.subContainer.appendChild(wrap);
      return canvasDiv;
    };

    const rsiCanvas = buildPane(`${this.hudPrefix}RsiLegend`, '');
    const macdCanvas = buildPane(`${this.hudPrefix}MacdLegend`, '');

    const baseSubOptions = {
      ...baseChartOptions,
      height: this.subPaneHeight,
      width: width,
      rightPriceScale: {
        visible: true,
        borderColor: '#1e293b',
        autoScale: true
      },
      timeScale: {
        ...baseChartOptions.timeScale,
        visible: false
      }
    };

    // RSI Pane Chart
    this.rsiChart = LightweightCharts.createChart(rsiCanvas, { ...baseSubOptions });
    // MACD Pane Chart
    this.macdChart = LightweightCharts.createChart(macdCanvas, {
      ...baseSubOptions,
      height: this.subPaneHeight + 18, // bottom-most pane keeps its own time axis labels
      timeScale: { ...baseSubOptions.timeScale, visible: true }
    });

    // RSI Series
    this.rsiSeries = this.rsiChart.addLineSeries({
      priceScaleId: 'right',
      color: '#c084fc',
      lineWidth: 2,
      title: 'RSI(14)'
    });

    this.rsiSeries.createPriceLine({
      price: 70,
      color: '#ef4444',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: '70'
    });
    this.rsiSeries.createPriceLine({
      price: 30,
      color: '#10b981',
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: '30'
    });

    // MACD Histogram & Lines
    this.macdHistSeries = this.macdChart.addHistogramSeries({
      priceScaleId: 'right',
      title: 'MACD Hist'
    });
    this.macdLineSeries = this.macdChart.addLineSeries({
      priceScaleId: 'right',
      color: '#38bdf8',
      lineWidth: 2,
      title: 'MACD'
    });
    this.macdSignalSeries = this.macdChart.addLineSeries({
      priceScaleId: 'right',
      color: '#f97316',
      lineWidth: 1,
      title: 'Signal'
    });

    // Synchronize Time Scales across ALL panes without recursive event loop
    const syncTargets = [
      () => ({ chart: this.mainChart }),
      () => ({ chart: this.rsiChart }),
      () => ({ chart: this.macdChart })
    ];
    for (const getTarget of syncTargets) {
      const t = getTarget();
      if (!t.chart) continue;
      t.chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (this.isSyncingRange || !range) return;
        this.isSyncingRange = true;
        try {
          for (const getOther of syncTargets) {
            const o = getOther();
            if (!o.chart || o.chart === t.chart) continue;
            o.chart.timeScale().setVisibleLogicalRange(range);
          }
        } catch (e) {}
        this.isSyncingRange = false;
      });
    }

    // Crosshair projection across all panes (lightweight-charts v4 setCrosshairPosition)
    const crossSources = [
      () => ({ chart: this.mainChart, series: () => this.candleSeries }),
      () => ({ chart: this.rsiChart, series: () => this.rsiSeries }),
      () => ({ chart: this.macdChart, series: () => this.macdLineSeries })
    ];
    for (const getSource of crossSources) {
      const s = getSource();
      if (!s.chart) continue;
      s.chart.subscribeCrosshairMove(param => {
        if (this.isSyncingCrosshair) return;
        this.isSyncingCrosshair = true;
        try {
          for (const getOther of crossSources) {
            const o = getOther();
            if (!o.chart || !o.series() || o.chart === s.chart) continue;
            if (param && param.time && param.point !== undefined) {
              const v = this._seriesValueAt(o.series(), param.time);
              try { o.chart.setCrosshairPosition(v, param.time, o.series()); } catch (e) {}
            } else {
              try { o.chart.clearCrosshairPosition(); } catch (e) {}
            }
          }
        } catch (e) {}
        this.isSyncingCrosshair = false;
        this.updateHUD(param);
        this.updatePaneLegends(param);
      });
    }

    this.lastIsIntraday = isIntraday;
  }

  _timeKey(time) {
    if (time && typeof time === 'object' && time.year !== undefined) {
      return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
    }
    return String(time);
  }

  /**
   * Custom tick formatter: keeps the daily x-axis to clean month/year labels.
   * lightweight-charts inserts Day-weight filler ticks when a data gap (e.g.
   * Tet holidays) makes two month-start bars sit closer than its minimum tick
   * spacing, which surfaced as a stray day-number ("4") between Feb and Apr.
   * We suppress day-number ticks when zoomed out and re-label first-of-month
   * fillers with their month name so no bare digits appear on the daily axis.
   */
  _formatTickMark(time, weight, locale) {
    if (this.lastIsIntraday || weight <= 1) return null; // default year/month rendering
    const key = this._timeKey(time);
    if (this._monthStartTimes && this._monthStartTimes.has(key)) {
      try {
        const [y, m, d] = key.split('-').map(Number);
        return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(locale, { month: 'short' });
      } catch (e) {}
    }
    let barSpacing = 0;
    try { barSpacing = this.mainChart ? (this.mainChart.timeScale().options().barSpacing || 0) : 0; } catch (e) {}
    return barSpacing >= 10 ? null : '';
  }

  _seriesValueAt(series, time) {
    try {
      const rows = series.data ? series.data() : null;
      if (rows && rows.length) {
        for (let i = rows.length - 1; i >= 0; i--) {
          if (String(rows[i].time) === String(time)) {
            return rows[i].value !== undefined ? rows[i].value : (rows[i].close !== undefined ? rows[i].close : null);
          }
        }
        return rows[rows.length - 1].value !== undefined ? rows[rows.length - 1].value : rows[rows.length - 1].close;
      }
    } catch (e) {}
    return null;
  }

  updatePaneLegends(param) {
    const rsiEl = document.getElementById(`${this.hudPrefix}RsiLegend`);
    const macdEl = document.getElementById(`${this.hudPrefix}MacdLegend`);
    if (!rsiEl || !macdEl) return;

    const t = (param && param.time) ? param.time : null;
    const pickLast = (arr) => arr.length ? arr[arr.length - 1].value : null;
    const rsiVal = t ? this._valueIn(this._rsiData, t) : pickLast(this._rsiData);
    const macdV = t ? this._valueIn(this._macdLineData, t) : pickLast(this._macdLineData);
    const sigV = t ? this._valueIn(this._macdSignalData, t) : pickLast(this._macdSignalData);
    const histV = t ? this._valueIn(this._macdHistData, t) : pickLast(this._macdHistData);

    const fmt = (v) => (v === null || v === undefined) ? '--' : Number(v).toFixed(2);

    rsiEl.innerHTML =
      `<span style="color:#c084fc;font-weight:700;">RSI(14)</span> ` +
      `<span style="color:${rsiVal >= 70 ? '#ef4444' : (rsiVal <= 30 ? '#10b981' : '#e2e8f0')};font-weight:600;">${fmt(rsiVal)}</span>`;

    const histColor = histV === null ? '#94a3b8' : (histV >= 0 ? '#10b981' : '#ef4444');
    macdEl.innerHTML =
      `<span style="color:#38bdf8;font-weight:700;">MACD(12,26,9)</span> ` +
      `<span style="color:#38bdf8;">${fmt(macdV)}</span> ` +
      `<span style="color:#f97316;">${fmt(sigV)}</span> ` +
      `<span style="color:${histColor};">${fmt(histV)}</span>`;
  }

  _valueIn(arr, time) {
    for (let i = arr.length - 1; i >= 0; i--) {
      if (String(arr[i].time) === String(time)) return arr[i].value;
    }
    return null;
  }

  setupLogScaleButton() {
    const btn = document.getElementById('btnLogScale');
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', () => {
      // Defer class update so it wins over the generic .ind-btn handler in app.js
      const active = this.toggleLogScale();
      setTimeout(() => btn.classList.toggle('active', active), 0);
    });
  }

  toggleLogScale() {
    if (!this.mainChart || !window.LightweightCharts) return false;
    this.logScale = !this.logScale;
    const mode = this.logScale
      ? LightweightCharts.PriceScaleMode.Logarithmic
      : LightweightCharts.PriceScaleMode.Normal;
    try {
      this.mainChart.priceScale('right').applyOptions({ mode });
    } catch (e) {}
    const btn = document.getElementById('btnLogScale');
    if (btn) btn.classList.toggle('active', this.logScale);
    return this.logScale;
  }

  setupSymbolSearchKeyboard() {
    const wrap = this.hudPrefix === 'hud' ? this.mainContainer : null;
    if (!wrap) return;
    wrap.setAttribute('tabindex', '0');
    wrap.style.outline = 'none';
    let buf = '';
    let resetTimer = null;
    wrap.addEventListener('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'Enter') {
        const sym = buf.trim();
        buf = '';
        clearTimeout(resetTimer);
        if (sym.length >= 2 && window.app && typeof window.app.selectSearchedStock === 'function') {
          e.preventDefault();
          window.app.selectSearchedStock(sym.toUpperCase());
        }
        return;
      }
      if (/^[a-zA-Z]$/.test(e.key)) {
        e.preventDefault();
        buf += e.key.toUpperCase();
        clearTimeout(resetTimer);
        resetTimer = setTimeout(() => { buf = ''; }, 2000);
        // Reuse the global symbol-search overlay: focus it and replay the typed query
        const si = document.getElementById('searchInput');
        if (si) {
          si.focus();
          si.value = buf;
          si.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }
    });
  }

  destroy() {
    if (this.mainChart && typeof this.mainChart.remove === 'function') {
      try { this.mainChart.remove(); } catch (e) {}
      this.mainChart = null;
    }
    if (this.rsiChart && typeof this.rsiChart.remove === 'function') {
      try { this.rsiChart.remove(); } catch (e) {}
      this.rsiChart = null;
    }
    if (this.macdChart && typeof this.macdChart.remove === 'function') {
      try { this.macdChart.remove(); } catch (e) {}
      this.macdChart = null;
    }
    if (this.mainContainer) this.mainContainer.innerHTML = '';
    if (this.subContainer) this.subContainer.innerHTML = '';
  }

  setupResizeObserver() {
    if (window.ResizeObserver && this.mainContainer) {
      let roRaf = null;
      const ro = new ResizeObserver(entries => {
        for (let entry of entries) {
          const cr = entry.contentRect;
          if (cr.width > 0) {
            if (roRaf) cancelAnimationFrame(roRaf);
            roRaf = requestAnimationFrame(() => {
              this.resize(cr.width);
              roRaf = null;
            });
          }
        }
      });
      ro.observe(this.mainContainer);
    }

    // Also listen to window resize with RAF throttling
    let winRaf = null;
    window.addEventListener('resize', () => {
      if (winRaf) cancelAnimationFrame(winRaf);
      winRaf = requestAnimationFrame(() => {
        this.resize();
        winRaf = null;
      });
    });
  }

  resize(targetWidth) {
    if (!this.mainContainer) this.mainContainer = document.getElementById(this.mainContainerId);
    if (!this.subContainer) this.subContainer = document.getElementById(this.subContainerId);

    const w = targetWidth || (this.mainContainer ? this.mainContainer.clientWidth : 0);
    if (w > 0) {
      if (this.mainChart) {
        try { this.mainChart.applyOptions({ width: w, height: this.mainHeight }); } catch (e) {}
      }
      if (this.rsiChart) {
        try { this.rsiChart.applyOptions({ width: w, height: this.subPaneHeight }); } catch (e) {}
      }
      if (this.macdChart) {
        try { this.macdChart.applyOptions({ width: w, height: this.subPaneHeight + 18 }); } catch (e) {}
      }
    }
  }

  _defaultVisibleBars(isIntraday) {
    const total = this.totalBars;
    if (!isIntraday) {
      // Daily/Weekly/Monthly: TV-style default of last ~250 daily bars
      return Math.min(total, 250);
    }
    // Intraday: show an equivalent window (~1 trading month of sessions)
    const itv = this.currentData.interval || '15m';
    const perSession = { '1m': 260, '5m': 55, '15m': 19, '30m': 10, '1H': 5 };
    const sessions = itv === '1m' ? 8 : (itv === '5m' ? 12 : 22);
    return Math.min(total, (perSession[itv] || 19) * sessions);
  }

  applyDefaultZoom() {
    if (!this.mainChart || !this.totalBars) return;
    const to = this.totalBars - 1;
    const from = Math.max(0, this.totalBars - this._defaultVisibleBars(this.lastIsIntraday));
    try {
      this.mainChart.timeScale().setVisibleLogicalRange({ from: from - 2, to: to + 2 });
    } catch (e) {
      try { this.mainChart.timeScale().fitContent(); } catch (e2) {}
    }
  }

  setData(data) {
    this.currentData = data;
    if (!data || !data.candles || data.candles.length === 0) return;

    // Sanitize all time series to guarantee strictly ascending order and no duplicates
    const cleanCandles = sanitizeSeriesData(data.candles);
    if (cleanCandles.length === 0) return;

    // Track first session of each month so the tick formatter can render clean
    // month labels even when holiday gaps compress the spacing between months
    this._monthStartTimes = new Set();
    let prevMonth = null;
    for (const c of cleanCandles) {
      const key = this._timeKey(c.time);
      const m = key.length >= 7 ? key.slice(0, 7) : key;
      if (m !== prevMonth) { this._monthStartTimes.add(key); prevMonth = m; }
    }

    const isIntraday = (typeof cleanCandles[0].time === 'number');

    // If time format changed between intraday (number) and daily (string), or charts not yet created, reinit
    if (this.lastIsIntraday !== isIntraday || !this.mainChart || !this.candleSeries) {
      this.initCharts(isIntraday);
    }

    try {
      this.candleSeries.setData(cleanCandles);
      this._candleData = cleanCandles;

      // Volume (soft semi-transparent bars at bottom)
      if (this.indicators.volume && data.volumes && data.volumes.length > 0) {
        const rawVols = sanitizeSeriesData(data.volumes);
        this._volumeCache = rawVols;
        const cleanVols = rawVols.map(v => {
          let col = v.color;
          if (!col || !col.startsWith('rgba')) {
            col = (col === '#ef4444' || col === '#f43f5e') ? 'rgba(239, 68, 68, 0.35)' : 'rgba(16, 185, 129, 0.35)';
          }
          return { time: v.time, value: v.value, color: col };
        });
        this.volumeSeries.setData(cleanVols);
      } else {
    this._volumeCache = [];
    this._monthStartTimes = new Set(); // first session of each month, for clean axis labels
        this.volumeSeries.setData([]);
      }

      // MA20
      if (this.indicators.ma20 && data.ma20 && data.ma20.length > 0) {
        this.ma20Series.setData(sanitizeSeriesData(data.ma20));
      } else {
        this.ma20Series.setData([]);
      }

      // MA50
      if (this.indicators.ma50 && data.ma50 && data.ma50.length > 0) {
        this.ma50Series.setData(sanitizeSeriesData(data.ma50));
      } else {
        this.ma50Series.setData([]);
      }

      // Bollinger Bands
      if (this.indicators.bollinger && data.boll_upper && data.boll_lower && data.boll_upper.length > 0) {
        this.bollUpperSeries.setData(sanitizeSeriesData(data.boll_upper));
        this.bollLowerSeries.setData(sanitizeSeriesData(data.boll_lower));
      } else {
        this.bollUpperSeries.setData([]);
        this.bollLowerSeries.setData([]);
      }

      // RSI
      if (this.indicators.rsi && data.rsi && data.rsi.length > 0) {
        this._rsiData = sanitizeSeriesData(data.rsi);
        this.rsiSeries.setData(this._rsiData);
      } else {
        this._rsiData = [];
        this.rsiSeries.setData([]);
      }

      // MACD
      if (this.indicators.macd && data.macd && data.macd.length > 0) {
        this._macdLineData = sanitizeSeriesData(data.macd);
        this._macdSignalData = sanitizeSeriesData(data.macd_signal || []);
        this._macdHistData = sanitizeSeriesData(data.macd_hist || []);
        this.macdLineSeries.setData(this._macdLineData);
        this.macdSignalSeries.setData(this._macdSignalData);
        this.macdHistSeries.setData(this._macdHistData);
      } else {
        this._macdLineData = [];
        this._macdSignalData = [];
        this._macdHistData = [];
        this.macdLineSeries.setData([]);
        this.macdSignalSeries.setData([]);
        this.macdHistSeries.setData([]);
      }

      // TV-style default zoom: last ~250 daily bars (or intraday equivalent);
      // 'ALL' range pill remains opt-in. Explicit range selection is preserved.
      this.totalBars = cleanCandles.length;
      this.resize();
      setTimeout(() => {
        if (this.lastRangeCode === 'ALL') {
          if (this.mainChart) this.mainChart.timeScale().fitContent();
        } else {
          this.applyDefaultZoom();
        }
        this.updatePaneLegends(null);
      }, 30);

      const last = cleanCandles[cleanCandles.length - 1];
      const lastVol = data.volumes && data.volumes.length > 0 ? data.volumes[data.volumes.length - 1]?.value : 0;
      this.renderHUDValues(last.time, last.open, last.high, last.low, last.close, lastVol);

      // Render Order Book Depth Ladder if present
      if (data.ladder) {
        this.renderOrderLadder(data.ladder);
      }
    } catch (e) {
      console.error("Error setting chart series data, attempting fallback...", e);
      try {
        this.totalBars = cleanCandles.length;
        this.initCharts(isIntraday);
        this.candleSeries.setData(cleanCandles);
        if (data.volumes) this.volumeSeries.setData(sanitizeSeriesData(data.volumes));
        if (this.mainChart) this.applyDefaultZoom();
      } catch (err) {
        console.error("Critical fallback setData error:", err);
      }
    }
  }

  zoomToRange(rangeCode) {
    if (!this.currentData || !this.currentData.candles || this.currentData.candles.length === 0) return;
    if (!this.mainChart) return;

    this.lastRangeCode = rangeCode;

    if (rangeCode === 'ALL') {
      this.mainChart.timeScale().fitContent();
      if (this.rsiChart) this.rsiChart.timeScale().fitContent();
      if (this.macdChart) this.macdChart.timeScale().fitContent();
      return;
    }

    const total = this.currentData.candles.length;
    let bars = total;

    if (this.lastIsIntraday) {
      if (rangeCode === '1D') bars = 48;
      else if (rangeCode === '1W') bars = 240;
      else if (rangeCode === '1M') bars = 800;
      else if (rangeCode === '3M') bars = 2400;
      else bars = total;
    } else {
      const itv = this.currentData.interval || '1D';
      if (itv === '1D') {
        if (rangeCode === '1W') bars = 7;
        else if (rangeCode === '1M') bars = 22;
        else if (rangeCode === '3M') bars = 66;
        else if (rangeCode === '6M') bars = 132;
        else if (rangeCode === '1Y') bars = 252;
        else bars = total;
      } else if (itv === '1W') {
        if (rangeCode === '1M') bars = 4;
        else if (rangeCode === '3M') bars = 13;
        else if (rangeCode === '6M') bars = 26;
        else if (rangeCode === '1Y') bars = 52;
        else bars = total;
      } else {
        if (rangeCode === '1Y') bars = 12;
        else if (rangeCode === '3M') bars = 3;
        else if (rangeCode === '6M') bars = 6;
        else bars = total;
      }
    }

    const fromIdx = Math.max(0, total - bars);
    const toIdx = total - 1;

    try {
      this.mainChart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: toIdx });
      if (this.rsiChart) {
        this.rsiChart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: toIdx });
      }
      if (this.macdChart) {
        this.macdChart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: toIdx });
      }
    } catch (e) {
      console.warn("Could not set visible logical range:", e);
    }
  }

  renderOrderLadder(ladder) {
    const container = document.getElementById('orderBookLadder');
    if (!container || !ladder) return;

    if (ladder.status === 'unavailable') {
      container.innerHTML = `
        <div class="ladder-empty" style="display:flex; align-items:center; justify-content:center; min-height:120px; color:var(--text-muted); font-size:12px; text-align:center; padding:12px;">
          ${ladder.message || 'Sổ lệnh trực tiếp không có từ nguồn dữ liệu'}
        </div>
      `;
      return;
    }

    const maxVol = Math.max(
      ladder.kl3 || 0, ladder.kl2 || 0, ladder.kl1 || 0,
      ladder.b_kl1 || 0, ladder.b_kl2 || 0, ladder.b_kl3 || 0,
      1
    );

    container.innerHTML = `
      <div class="ladder-container">
        <!-- Bên Mua (Bids) -->
        <div class="ladder-side ladder-buy">
          <div class="ladder-header">BÊN MUA (BIDS)</div>
          <div class="ladder-row">
            <span class="ladder-vol mono">${(ladder.kl3 || 0).toLocaleString()}</span>
            <div class="ladder-bar-wrap">
              <div class="ladder-bar bar-buy" style="width: ${((ladder.kl3 || 0) / maxVol) * 100}%;"></div>
            </div>
            <span class="ladder-price mono ${ladder.c3}">${(ladder.g3 || 0).toFixed(2)}</span>
          </div>
          <div class="ladder-row">
            <span class="ladder-vol mono">${(ladder.kl2 || 0).toLocaleString()}</span>
            <div class="ladder-bar-wrap">
              <div class="ladder-bar bar-buy" style="width: ${((ladder.kl2 || 0) / maxVol) * 100}%;"></div>
            </div>
            <span class="ladder-price mono ${ladder.c2}">${(ladder.g2 || 0).toFixed(2)}</span>
          </div>
          <div class="ladder-row highlight-tier">
            <span class="ladder-vol mono">${(ladder.kl1 || 0).toLocaleString()}</span>
            <div class="ladder-bar-wrap">
              <div class="ladder-bar bar-buy" style="width: ${((ladder.kl1 || 0) / maxVol) * 100}%;"></div>
            </div>
            <span class="ladder-price mono ${ladder.c1}">${(ladder.g1 || 0).toFixed(2)}</span>
          </div>
        </div>

        <!-- Bên Bán (Asks) -->
        <div class="ladder-side ladder-ask">
          <div class="ladder-header">BÊN BÁN (ASKS)</div>
          <div class="ladder-row highlight-tier">
            <span class="ladder-price mono ${ladder.b_c1}">${(ladder.b_g1 || 0).toFixed(2)}</span>
            <div class="ladder-bar-wrap">
              <div class="ladder-bar bar-ask" style="width: ${((ladder.b_kl1 || 0) / maxVol) * 100}%;"></div>
            </div>
            <span class="ladder-vol mono">${(ladder.b_kl1 || 0).toLocaleString()}</span>
          </div>
          <div class="ladder-row">
            <span class="ladder-price mono ${ladder.b_c2}">${(ladder.b_g2 || 0).toFixed(2)}</span>
            <div class="ladder-bar-wrap">
              <div class="ladder-bar bar-ask" style="width: ${((ladder.b_kl2 || 0) / maxVol) * 100}%;"></div>
            </div>
            <span class="ladder-vol mono">${(ladder.b_kl2 || 0).toLocaleString()}</span>
          </div>
          <div class="ladder-row">
            <span class="ladder-price mono ${ladder.b_c3}">${(ladder.b_g3 || 0).toFixed(2)}</span>
            <div class="ladder-bar-wrap">
              <div class="ladder-bar bar-ask" style="width: ${((ladder.b_kl3 || 0) / maxVol) * 100}%;"></div>
            </div>
            <span class="ladder-vol mono">${(ladder.b_kl3 || 0).toLocaleString()}</span>
          </div>
        </div>
      </div>
    `;
  }

  toggleIndicator(name) {
    if (this.indicators[name] !== undefined) {
      this.indicators[name] = !this.indicators[name];
      if (this.currentData) {
        this.setData(this.currentData);
      }
      return this.indicators[name];
    }
    return false;
  }

  updateHUD(param) {
    if (!param || !param.time || !this.candleSeries) return;
    const priceData = param.seriesData.get(this.candleSeries);
    const volData = this.volumeSeries ? param.seriesData.get(this.volumeSeries) : null;

    if (priceData) {
      this.renderHUDValues(param.time, priceData.open, priceData.high, priceData.low, priceData.close, volData?.value);
    } else {
      // Hovering a sub-pane: project OHLCV from cached candle data at the same time
      const t = param.time;
      for (let i = this._candleData.length - 1; i >= 0; i--) {
        if (String(this._candleData[i].time) === String(t)) {
          const c = this._candleData[i];
          let vol = null;
          for (let j = this._volumeCache.length - 1; j >= 0; j--) {
            if (String(this._volumeCache[j].time) === String(t)) { vol = this._volumeCache[j].value; break; }
          }
          this.renderHUDValues(t, c.open, c.high, c.low, c.close, vol);
          break;
        }
      }
    }
  }

  /**
   * True when the given bar is today's still-forming session bar, so its
   * volume is a running total rather than the settled session figure.
   */
  _isLiveBar(time) {
    const last = this._candleData && this._candleData.length ? this._candleData[this._candleData.length - 1] : null;
    if (!last || String(last.time) !== String(time)) return false;
    const now = new Date();
    const dow = now.getDay();
    if (dow === 0 || dow === 6) return false;
    const mins = now.getHours() * 60 + now.getMinutes();
    if (mins < 9 * 60 || mins > 15 * 60 + 35) return false;
    if (!this.lastIsIntraday && typeof time === 'string' && /^\d{4}-\d{2}-\d{2}/.test(time)) {
      return time.slice(0, 10) === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    }
    return true;
  }

  renderHUDValues(time, o, h, l, c, v) {
    const isDefaultHud = (this.hudPrefix === 'hud');
    const elTime = document.getElementById(isDefaultHud ? 'hudDate' : `${this.hudPrefix}Date`);
    const elO = document.getElementById(isDefaultHud ? 'hudOpen' : `${this.hudPrefix}Open`);
    const elH = document.getElementById(isDefaultHud ? 'hudHigh' : `${this.hudPrefix}High`);
    const elL = document.getElementById(isDefaultHud ? 'hudLow' : `${this.hudPrefix}Low`);
    const elC = document.getElementById(isDefaultHud ? 'hudClose' : `${this.hudPrefix}Close`);
    const elV = document.getElementById(isDefaultHud ? 'hudVolume' : `${this.hudPrefix}Volume`);

    let displayTime = time || '--';
    if (typeof time === 'number') {
      // Intraday: unix timestamp
      const d = new Date(time * 1000);
      displayTime = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
    } else if (time && typeof time === 'object' && time.year) {
      // Daily: lightweight-charts BusinessDay object
      displayTime = `${String(time.day).padStart(2, '0')}/${String(time.month).padStart(2, '0')}/${time.year}`;
    } else if (typeof time === 'string' && /^\d{4}-\d{2}-\d{2}/.test(time)) {
      // Daily: ISO date string (e.g. 2024-05-02)
      const [y, m, d] = time.split('-');
      displayTime = `${d}/${m}/${y}`;
    }

    if (elTime) elTime.textContent = displayTime;
    if (elO) elO.textContent = o !== undefined ? Number(o).toFixed(2) : '--';
    if (elH) elH.textContent = h !== undefined ? Number(h).toFixed(2) : '--';
    if (elL) elL.textContent = l !== undefined ? Number(l).toFixed(2) : '--';
    if (elC) {
      elC.textContent = c !== undefined ? Number(c).toFixed(2) : '--';
      elC.style.color = (c >= o) ? 'var(--color-up, #10b981)' : 'var(--color-down, #ef4444)';
    }
    if (elV) {
      if (v !== undefined) {
        const volText = Number(v).toLocaleString();
        if (this._isLiveBar(time)) {
          elV.innerHTML = `${volText} <span style="opacity:0.55;font-size:0.85em;" title="Phiên chưa kết thúc - KL đang tích lũy">(tạm thời)</span>`;
        } else {
          elV.textContent = volText;
        }
      } else {
        elV.textContent = '--';
      }
    }
  }
}

window.StockChartManager = StockChartManager;
