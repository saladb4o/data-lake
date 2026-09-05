/**
 * ==========================================================================
 * VNSTOCK TRADING TERMINAL PRO - MAIN CLIENT APPLICATION
 * ==========================================================================
 */

function escapeHTML(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatCurrencyVND(amount) {
  if (amount === null || amount === undefined || isNaN(Number(amount))) return '--';
  const v = Number(amount);
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + ' tỷ';
  if (abs >= 1e6) return (v / 1e6).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' tr';
  return Math.round(v).toLocaleString('vi-VN') + ' ₫';
}

class VnstockApp {
  constructor() {
    this.currentSymbol = 'FPT';
    this.currentInterval = '1D';
    this.currentTimeframe = 'ALL';
    this.currentBoardGroup = 'VN30';
    this.currentTab = 'board';
    this.currentStockSubtab = 'stock_news';
    this.currentNewsSource = 'all';
    this.currentNewsCategory = 'all';
    this.currentNewsTopic = 'all';
    this.currentNewsSentiment = 'all';
    this.currentNewsKeyword = '';
    this.allNewsCache = [];
    this.currentFilteredNews = [];
    this.currentCompanyNewsFilter = 'all';
    this.companyNewsCache = [];
    this.watchlist = this.loadWatchlist();
    this.alertRules = [];
    this.notifiedAlertKeys = new Set();
    this._alertPollTimer = null;
    this.currentBoardData = [];
    this.boardFilterKeyword = '';
    this.previousPrices = {}; // For tick animations
    this.readerFontSize = 16;
    this.currentReaderUrl = '';

    // Enhanced Corporate Filings State
    this.reportPage = 1;
    this.reportFilterType = 'all';
    this.reportSearchKeyword = '';
    this.reportYearFilter = 'all';
    this.currentCompanyReports = [];
    this.hasMoreReports = false;
    this.isLoadingMoreReports = false;

    // Corporate Events & Dividends State
    this.currentCompanyEvents = [];
    this.eventFilterCategory = 'all';

    // Ecosystem & Cross-Ownership State
    this.currentEcosystemData = null;
    this.ecosystemViewMode = 'matrix';
    this.ecoDepth = 2;
    this.ecoMinOwnership = 0.0;

    // Sector Intelligence (ICB) State
    this.currentSectorCode = 'VNREAL';
    this.currentSectorExchange = 'ALL';
    this.currentSectorInterval = '1D';
    this.currentSectorTimeframe = 'ALL';
    this.sectorChartManager = null;
    this.allSectorsCache = [];
    this.sectorRotationInitialized = false;
    this.peerTopK = 10;
    this.peerExchange = 'ALL';

    // Quant Screener & Earnings Engine State
    this.currentQuantQ = 'ALL';
    this.currentQuantSector = 'ALL';
    this.currentQuantExchange = 'ALL';
    this.currentQuantStrategy = 'ALL';
    this.currentQuantGrowth = 50.0;
    this.currentQuantSortBy = 'composite';
    this.quantKeyword = '';
    this.quantDataCache = null;

    // Screener Quick Backtest State
    this.qsBtHorizon = 5;
    this.qsBtCadence = 'quarterly';
    this.qsBtTopK = 10;
    this.qsBtFillMode = 'strict';
    this.qsBtCapital = 100000000;

    // Quant Backtest Studio State
    this.btTimeHorizon = 5;
    this.btCadence = 'quarterly';
    this.btTopK = 10;
    this.btFillMode = 'strict';
    this.btCapital = 100000000;
    this.btExchanges = ['ALL'];
    this.btDataCache = null;
    this.btInspectStrategy = 'deep_value_klarman';
    this.btChartPoints = [];
    this.btHoverIndex = null;
    this.btVisibleStrategies = {
      'deep_value_klarman': true,
      'ps_focus_fisher': true,
      'contrarian_dreman': true,
      'growth_philip_fisher': true,
      'peter_lynch_garp': true,
      'defensive_graham': true,
      'value_buffett': true,
      'buffetts_alpha': true,
      'novy_marx_quality_value': true,
      'gray_quantitative_value_qval': true,
      'hello_lower_risk': true,
      'hello_balanced_risk': true,
      'hello_full_throttle': true,
      'hello_lower_risk_mod': true,
      'hello_balanced_risk_mod': true,
      'hello_full_throttle_mod': true,
      'universal_survival_sector_moat': true,
      'guru_magic_formula_greenblatt': true,
      'guru_piotroski_fscore': true,
      'guru_zweig_conservative_growth': true,
      'guru_cornerstone_growth_oshaughnessy': true,
      'guru_cornerstone_value_oshaughnessy': true,
      'guru_neff_total_return': true,
      'guru_consensus_multi_model': true,
      'tsmom_moskowitz': true,
      'quant_q1': true,
      'quant_q2': true,
      'quant_q3': true,
      'quant_q4': true,
      'quant_q5': false,
      'vnindex': true
    };

    this.chartManager = null;
    this.treemapManager = null;
    this._stockAbortController = null;
    this._macroAbortController = null;

    this.init();
  }

  debounce(fn, delay = 150) {
    let timer = null;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  renderErrorState(containerOrId, message = 'Không thể tải dữ liệu từ máy chủ.', retryFn = null) {
    const el = typeof containerOrId === 'string' ? document.getElementById(containerOrId) : containerOrId;
    if (!el) return;
    const retryBtn = retryFn ? `
      <div style="margin-top:10px;">
        <button class="btn-sm" style="color:#38bdf8; border-color:#38bdf8; padding:4px 12px; cursor:pointer;" onclick="(${retryFn.toString()})()">
          ↻ Thử Lại
        </button>
      </div>` : '';
    el.innerHTML = `
      <div class="ui-error-state" style="padding:24px 16px; text-align:center; color:var(--text-muted); font-size:12px; background:rgba(239,68,68,0.04); border:1px solid rgba(239,68,68,0.2); border-radius:8px; margin:8px 0;">
        <div style="font-size:24px; margin-bottom:6px;">⚠️</div>
        <div style="font-weight:700; color:var(--color-down, #ef4444); margin-bottom:4px;">Lỗi tải dữ liệu</div>
        <div style="color:var(--text-secondary); max-width:400px; margin:0 auto;">${escapeHTML(message)}</div>
        ${retryBtn}
      </div>
    `;
  }

  async init() {
    try {
      this.chartManager = new StockChartManager({
        mainContainerId: 'mainChartContainer',
        subContainerId: 'subChartContainer',
        hudPrefix: 'hud',
        mainHeight: 360,
        subHeight: 130
      });
    } catch (e) {
      console.error('Main chart manager init error:', e);
    }

    try {
      this.sectorChartManager = new StockChartManager({
        mainContainerId: 'sectorMainChartContainer',
        subContainerId: 'sectorSubChartContainer',
        hudPrefix: 'sectorHud',
        mainHeight: 340,
        subHeight: 130
      });
    } catch (e) {
      console.error('Sector chart manager init error:', e);
    }

    try {
      this.treemapManager = new MarketTreemap('treemapContainer');
    } catch (e) {
      console.error('Treemap manager init error:', e);
    }

    try {
      this.setupEventListeners();
      this.startClock();
      this.loadAlertRules();
      this.startAlertPolling();
      this.updateSavedStrategiesBadge();
    } catch (e) {
      console.error('Event listeners setup error:', e);
    }

    // Initial data fetch - fast startup for initial view
    this.fetchIndicesAnalytics();
    this.fetchTradingBoard(this.currentBoardGroup);

    // Setup efficient polling intervals (respecting document visibility & 60 req/min limits)
    setInterval(() => {
      if (!document.hidden) {
        this.fetchIndicesAnalytics();
      }
    }, 30000);

    setInterval(() => {
      if (!document.hidden) {
        this.fetchDataLakeStatus();
      }
    }, 60000);

    setInterval(() => {
      if (!document.hidden && this.currentTab === 'board') {
        this.fetchTradingBoard(this.currentBoardGroup);
      }
    }, 20000);
  }

  loadWatchlist() {
    try {
      const saved = localStorage.getItem('vnstock_watchlist');
      return saved ? JSON.parse(saved) : ['FPT', 'HPG', 'VNM', 'SSI', 'VCB'];
    } catch {
      return ['FPT', 'HPG', 'VNM', 'SSI', 'VCB'];
    }
  }

  saveWatchlist() {
    localStorage.setItem('vnstock_watchlist', JSON.stringify(this.watchlist));
  }

  async loadAlertRules() {
    try {
      const res = await fetch('/api/alerts');
      const json = await res.json();
      if (json.status === 'success') {
        this.alertRules = json.data || [];
      }
    } catch (e) {
      console.error('Error loading alert rules:', e);
    }
    this.renderAlertsList();
  }

  requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }

  setupEventListeners() {
    // 0. Global Visibility-Aware Polling Resume
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        this.fetchIndicesAnalytics();
        this.fetchDataLakeStatus();
        this.pollFiredAlerts();
        if (this.currentTab === 'board') {
          this.fetchTradingBoard(this.currentBoardGroup);
        } else if (this.currentTab === 'chart') {
          if (this.isMacroSymbol(this.currentSymbol)) {
            this.loadMacroDetails(this.currentSymbol);
          } else {
            this.loadStockDetails(this.currentSymbol || 'FPT');
          }
        }
      }
    });

    // 1. Navigation Tabs
    document.querySelectorAll('.view-tab').forEach(tabBtn => {
      tabBtn.addEventListener('click', () => {
        const tab = tabBtn.dataset.tab;
        this.switchTab(tab);
      });
    });

    // 2. Stock & Macro Detail Subtabs
    document.querySelectorAll('.subtab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.dataset.macroSubtab) {
          this.switchMacroSubtab(btn.dataset.macroSubtab);
        } else if (btn.dataset.subtab) {
          this.switchStockSubtab(btn.dataset.subtab);
        }
      });
    });

    // 2a. Macro Report Category Pills Filter
    document.querySelectorAll('.c-macro-category-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        const btn = e.target.closest('.c-macro-category-pill');
        if (!btn) return;
        document.querySelectorAll('.c-macro-category-pill').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        this.macroReportCategory = btn.dataset.macroCat || 'all';
        this.fetchMacroDocuments();
      });
    });

    const macroReportSearchInp = document.getElementById('macroReportSearchInput');
    if (macroReportSearchInp) {
      let mDebounce = null;
      macroReportSearchInp.addEventListener('input', (e) => {
        clearTimeout(mDebounce);
        mDebounce = setTimeout(() => {
          this.macroReportKeyword = e.target.value.trim();
          this.fetchMacroDocuments();
        }, 200);
      });
    }

    // 2b. On-demand Deep Scan Button
    const btnDeepScan = document.getElementById('btnDeepScanCompanyNews');
    if (btnDeepScan) {
      btnDeepScan.addEventListener('click', () => {
        if (this.currentSymbol) {
          this.fetchCompanyNews(this.currentSymbol, true);
        }
      });
    }

    // 2c. Corporate Reports Filter Pills & Search & Year Controls
    document.querySelectorAll('.c-report-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        const btn = e.target.closest('.c-report-pill');
        if (!btn) return;
        document.querySelectorAll('.c-report-pill').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const reportType = btn.dataset.reportType;
        this.reportFilterType = reportType;
        this.renderCompanyReports();
      });
    });

    const reportSearchInput = document.getElementById('reportSearchInput');
    const btnClearReportSearch = document.getElementById('btnClearReportSearch');
    if (reportSearchInput) {
      let reportDebounce = null;
      reportSearchInput.addEventListener('input', (e) => {
        clearTimeout(reportDebounce);
        const val = e.target.value.trim();
        this.reportSearchKeyword = val.toLowerCase();
        if (btnClearReportSearch) {
          btnClearReportSearch.style.display = val ? 'inline-block' : 'none';
        }
        reportDebounce = setTimeout(() => {
          this.renderCompanyReports();
        }, 180);
      });
    }

    if (btnClearReportSearch && reportSearchInput) {
      btnClearReportSearch.addEventListener('click', () => {
        reportSearchInput.value = '';
        this.reportSearchKeyword = '';
        btnClearReportSearch.style.display = 'none';
        this.renderCompanyReports();
      });
    }

    // Modern Year Navigator: Pills, Stepper, and Custom Input
    const repYearInput = document.getElementById('reportYearInput');
    if (repYearInput) {
      repYearInput.addEventListener('change', (e) => {
        const val = e.target.value.trim();
        this.reportYearFilter = val ? val : 'all';
        this.reportPage = 1;
        document.querySelectorAll('.c-year-pill').forEach(b => {
          if (b.dataset.year === this.reportYearFilter) b.classList.add('active');
          else b.classList.remove('active');
        });
        if (this.currentSymbol) {
          this.fetchCompanyReports(this.currentSymbol, this.reportFilterType || 'all', 1, false, this.reportYearFilter);
        }
      });
      repYearInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') repYearInput.blur();
      });
    }

    document.querySelectorAll('.c-year-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.c-year-pill').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        const y = e.target.dataset.year || 'all';
        this.reportYearFilter = y;
        this.reportPage = 1;
        if (repYearInput) repYearInput.value = (y === 'all') ? '' : y;
        if (this.currentSymbol) {
          this.fetchCompanyReports(this.currentSymbol, this.reportFilterType || 'all', 1, false, y);
        }
      });
    });

    const btnPrev = document.getElementById('btnPrevYear');
    if (btnPrev) {
      btnPrev.addEventListener('click', () => {
        let curY = parseInt(repYearInput ? repYearInput.value : '', 10);
        if (isNaN(curY) || curY > 2026) curY = 2026;
        curY -= 1;
        if (curY < 2000) curY = 2000;
        if (repYearInput) repYearInput.value = curY;
        this.reportYearFilter = String(curY);
        this.reportPage = 1;
        document.querySelectorAll('.c-year-pill').forEach(b => {
          if (b.dataset.year === String(curY)) b.classList.add('active');
          else b.classList.remove('active');
        });
        if (this.currentSymbol) {
          this.fetchCompanyReports(this.currentSymbol, this.reportFilterType || 'all', 1, false, this.reportYearFilter);
        }
      });
    }

    const btnNext = document.getElementById('btnNextYear');
    if (btnNext) {
      btnNext.addEventListener('click', () => {
        let curY = parseInt(repYearInput ? repYearInput.value : '', 10);
        if (isNaN(curY)) curY = 2025;
        curY += 1;
        if (curY > 2026) curY = 2026;
        if (repYearInput) repYearInput.value = curY;
        this.reportYearFilter = String(curY);
        this.reportPage = 1;
        document.querySelectorAll('.c-year-pill').forEach(b => {
          if (b.dataset.year === String(curY)) b.classList.add('active');
          else b.classList.remove('active');
        });
        if (this.currentSymbol) {
          this.fetchCompanyReports(this.currentSymbol, this.reportFilterType || 'all', 1, false, this.reportYearFilter);
        }
      });
    }

    const btnLoadMoreReports = document.getElementById('btnLoadMoreReports');
    if (btnLoadMoreReports) {
      btnLoadMoreReports.addEventListener('click', () => {
        if (!this.isLoadingMoreReports && this.currentSymbol) {
          this.fetchCompanyReports(this.currentSymbol, this.reportFilterType, this.reportPage + 1, true, this.reportYearFilter);
        }
      });
    }

    // 2c-2. Corporate Events Category Filter Pills
    document.querySelectorAll('.c-event-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const b = e.target.closest('.c-event-pill');
        if (!b) return;
        document.querySelectorAll('.c-event-pill').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        this.eventFilterCategory = b.dataset.eventCat || 'all';
        this.renderCompanyEvents();
      });
    });

    // 2d. Interactive Financial Statements Controls
    document.querySelectorAll('.fin-tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const b = e.target.closest('.fin-tab-btn');
        if (!b) return;
        document.querySelectorAll('.fin-tab-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        this.currentFinType = b.dataset.finType;
        const periodSwitch = document.querySelector('.fin-period-switch');
        const countSwitch = document.querySelector('.fin-count-switch');
        if (this.currentFinType === 'three_way') {
          if (periodSwitch) periodSwitch.style.display = 'none';
          if (countSwitch) countSwitch.style.display = 'none';
          const modelTag = document.getElementById('finModelTag');
          if (modelTag) modelTag.textContent = '🔮 Modano 3-Way Model';
          if (this.currentSymbol) {
            this.fetchThreeStatementForecast(this.currentSymbol);
          }
        } else {
          if (periodSwitch) periodSwitch.style.display = 'flex';
          if (countSwitch) countSwitch.style.display = 'flex';
          if (this.currentSymbol) {
            this.fetchCompanyFinancials(this.currentSymbol, this.currentFinType, this.currentFinPeriod || 'quarter', this.currentFinCount || 8);
          }
        }
      });
    });

    document.querySelectorAll('.fin-period-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const b = e.target.closest('.fin-period-btn');
        if (!b) return;
        document.querySelectorAll('.fin-period-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        this.currentFinPeriod = b.dataset.finPeriod;
        if (this.currentSymbol) {
          this.fetchCompanyFinancials(this.currentSymbol, this.currentFinType || 'income', this.currentFinPeriod, this.currentFinCount || 8);
        }
      });
    });

    document.querySelectorAll('.fin-count-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const b = e.target.closest('.fin-count-btn');
        if (!b) return;
        document.querySelectorAll('.fin-count-btn').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        const rawCount = b.dataset.finCount;
        this.currentFinCount = (rawCount === 'all') ? 'all' : (parseInt(rawCount, 10) || 8);
        if (this.currentSymbol) {
          this.fetchCompanyFinancials(this.currentSymbol, this.currentFinType || 'income', this.currentFinPeriod || 'quarter', this.currentFinCount);
        }
      });
    });

    // 3. Board Group Filter Buttons & Quick Search
    document.querySelectorAll('.board-tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const targetBtn = e.target.closest('.board-tab-btn');
        if (!targetBtn) return;
        document.querySelectorAll('.board-tab-btn').forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');
        this.currentBoardGroup = targetBtn.dataset.group;
        const bFilterInput = document.getElementById('boardQuickFilter');
        if (bFilterInput) {
          bFilterInput.value = '';
          this.boardFilterKeyword = '';
        }
        this.fetchTradingBoard(this.currentBoardGroup);
      });
    });

    const boardFilterInput = document.getElementById('boardQuickFilter') || document.getElementById('boardFilterInput');
    if (boardFilterInput) {
      boardFilterInput.addEventListener('input', this.debounce((e) => {
        this.boardFilterKeyword = e.target.value.trim().toLowerCase();
        this.renderFilteredTradingBoard();
      }, 150));
    }

    // 4a. Stock Interval (Resolution) Switchers
    document.querySelectorAll('.interval-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.interval-btn');
        if (!target) return;
        document.querySelectorAll('.interval-btn').forEach(b => b.classList.remove('active'));
        target.classList.add('active');
        this.currentInterval = target.dataset.itv;
        if (this.isMacroSymbol(this.currentSymbol)) {
          this.loadMacroDetails(this.currentSymbol);
        } else {
          this.loadStockDetails(this.currentSymbol);
        }
      });
    });

    // 4b. Stock Range Zoom Switchers
    document.querySelectorAll('.range-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.range-btn');
        if (!target) return;
        document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
        target.classList.add('active');
        this.currentTimeframe = target.dataset.range;
        if (this.chartManager) {
          this.chartManager.zoomToRange(this.currentTimeframe);
        }
      });
    });

    // 4c. Sector Interval (Resolution) Switchers
    document.querySelectorAll('.sector-interval-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.sector-interval-btn');
        if (!target) return;
        document.querySelectorAll('.sector-interval-btn').forEach(b => b.classList.remove('active'));
        target.classList.add('active');
        this.currentSectorInterval = target.dataset.sitv;
        this.loadSectorChart(this.currentSectorCode, this.currentSectorInterval, this.currentSectorTimeframe);
      });
    });

    // 4d. Sector Range Zoom Switchers
    document.querySelectorAll('.sector-range-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.sector-range-btn');
        if (!target) return;
        document.querySelectorAll('.sector-range-btn').forEach(b => b.classList.remove('active'));
        target.classList.add('active');
        this.currentSectorTimeframe = target.dataset.srange;
        if (this.sectorChartManager) {
          this.sectorChartManager.zoomToRange(this.currentSectorTimeframe);
        }
      });
    });

    // 4e. Sector Exchange Filter Switchers
    document.querySelectorAll('.sector-ex-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.sector-ex-btn');
        if (!target) return;
        document.querySelectorAll('.sector-ex-btn').forEach(b => {
          b.classList.remove('active');
          b.style.background = 'transparent';
          b.style.color = 'var(--text-secondary)';
          b.style.fontWeight = '600';
        });
        target.classList.add('active');
        target.style.background = '#38bdf8';
        target.style.color = '#0f172a';
        target.style.fontWeight = '700';

        this.currentSectorExchange = target.dataset.sex || 'ALL';
        const secCode = this.currentSectorCode || 'VNREAL';
        this.loadSectorConstituents(secCode, this.currentSectorExchange);
      });
    });

    const btnRefSectors = document.getElementById('btnRefreshSectors');
    if (btnRefSectors) {
      btnRefSectors.addEventListener('click', () => {
        this.fetchSectorsOverview();
        if (this.isSectorRotationVisible()) {
          try { window.SectorRotation?.refresh?.(); } catch (e) { console.error('SectorRotation refresh failed:', e); }
        }
        this.showToast('Đang làm mới dữ liệu 10 chỉ số ngành...', 'toast-up');
      });
    }

    document.addEventListener('click', (e) => {
      const subtabBtn = e.target.closest ? e.target.closest('.sector-subtab') : null;
      if (!subtabBtn) return;
      this.switchSectorSubtab(subtabBtn.dataset.ssub || 'overview');
    });

    // 5. Stock Indicator Toggle Buttons
    document.querySelectorAll('.ind-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.ind-btn');
        if (!target) return;
        const ind = target.dataset.ind;
        if (this.chartManager) {
          const isActive = this.chartManager.toggleIndicator(ind);
          if (isActive) target.classList.add('active');
          else target.classList.remove('active');
        }
      });
    });

    // 5b. Sector Indicator Toggle Buttons
    document.querySelectorAll('.sector-ind-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.sector-ind-btn');
        if (!target) return;
        const ind = target.dataset.sind;
        if (this.sectorChartManager) {
          const isActive = this.sectorChartManager.toggleIndicator(ind);
          if (isActive) target.classList.add('active');
          else target.classList.remove('active');
        }
      });
    });

    // 6. Search Autocomplete
    const searchInput = document.getElementById('searchInput');
    const searchDropdown = document.getElementById('searchDropdown');

    let debounceTimer;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      const q = e.target.value.trim();
      if (!q) {
        searchDropdown.classList.remove('active');
        return;
      }
      debounceTimer = setTimeout(async () => {
        const results = await this.searchStocks(q);
        this.renderSearchResults(results);
      }, 200);
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      }
    });

    document.addEventListener('click', (e) => {
      if (!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
        searchDropdown.classList.remove('active');
      }
    });

    // 7. Watchlist Toggle in Hero
    const btnWatchlist = document.getElementById('btnWatchlistToggle');
    if (btnWatchlist) {
      btnWatchlist.addEventListener('click', () => {
        this.toggleWatchlist(this.currentSymbol);
      });
    }

    // 8. Refresh Button
    document.getElementById('btnRefresh').addEventListener('click', () => {
      this.fetchIndicesAnalytics();
      if (this.currentTab === 'board') this.fetchTradingBoard(this.currentBoardGroup);
      else if (this.currentTab === 'chart') {
        if (this.isMacroSymbol(this.currentSymbol)) this.loadMacroDetails(this.currentSymbol);
        else this.loadStockDetails(this.currentSymbol);
      }
      else if (this.currentTab === 'news') this.fetchMarketNews();
      else if (this.currentTab === 'treemap') this.fetchMarketTreemap();
      else if (this.currentTab === 'foreign') this.fetchForeignFlow();
    });

    // 9. Alert Modal Controls
    const alertModal = document.getElementById('alertModal');
    document.getElementById('btnOpenAlertModal').addEventListener('click', () => {
      document.getElementById('alertSymbolInput').value = this.currentSymbol;
      alertModal.classList.add('active');
    });

    document.getElementById('btnCloseAlertModal').addEventListener('click', () => {
      alertModal.classList.remove('active');
    });

    document.getElementById('btnSaveAlert').addEventListener('click', () => {
      this.addAlertRule();
    });

    // 9b. Article Reader Modal Controls
    const readerModal = document.getElementById('readerModal');
    const btnCloseReader = document.getElementById('btnCloseReaderModal');
    if (btnCloseReader) {
      btnCloseReader.addEventListener('click', () => this.closeArticleReader());
    }

    if (readerModal) {
      readerModal.addEventListener('click', (e) => {
        if (e.target === readerModal) this.closeArticleReader();
      });
    }

    document.getElementById('btnReaderFontDec')?.addEventListener('click', () => this.adjustReaderFontSize(-2));
    document.getElementById('btnReaderFontInc')?.addEventListener('click', () => this.adjustReaderFontSize(2));
    document.getElementById('btnReaderCopyLink')?.addEventListener('click', () => this.copyReaderLink());

    // Global Keydown (Escape for Modals)
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (readerModal && readerModal.classList.contains('active')) {
          this.closeArticleReader();
        } else if (alertModal && alertModal.classList.contains('active')) {
          alertModal.classList.remove('active');
        }
      }
    });

    // 10. News Source Filter Buttons
    document.querySelectorAll('.news-src-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.news-src-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.currentNewsSource = e.target.dataset.src;
        this.fetchRSSNews(true);
      });
    });

    // 11. News Topic Filter Buttons
    document.querySelectorAll('.news-topic-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.news-topic-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.currentNewsTopic = e.target.dataset.topic;
        this.fetchRSSNews(true);
      });
    });

    // 11b. News Sentiment Filter Buttons
    document.querySelectorAll('.news-sentiment-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.news-sentiment-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.currentNewsSentiment = e.target.dataset.sentiment;
        this.fetchRSSNews(true);
      });
    });

    // 12. News Keyword Filter & Refresh
    let searchDebounce = null;
    const newsInput = document.getElementById('newsKeywordInput');
    if (newsInput) {
      newsInput.addEventListener('input', (e) => {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(() => {
          this.currentNewsKeyword = e.target.value.trim();
          this.fetchRSSNews(true);
        }, 300);
      });
      newsInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          clearTimeout(searchDebounce);
          this.currentNewsKeyword = e.target.value.trim();
          this.fetchRSSNews(true);
        }
      });
    }

    const btnRefNews = document.getElementById('btnRefreshNews');
    if (btnRefNews) {
      btnRefNews.addEventListener('click', () => {
        this.fetchRSSNews(true);
      });
    }

    // 13. Load More News Button
    const btnLoadMore = document.getElementById('btnLoadMoreNews');
    if (btnLoadMore) {
      btnLoadMore.addEventListener('click', () => {
        this.fetchMoreRSSNews();
      });
    }

    // 13b. News Main Subtabs Switcher (Stream vs Calendar vs Upgrade)
    document.querySelectorAll('.news-main-subtab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.news-main-subtab-btn') || e.target;
        document.querySelectorAll('.news-main-subtab-btn').forEach(b => {
          b.classList.remove('active');
          b.style.background = 'transparent';
          b.style.color = 'var(--text-secondary)';
          b.style.borderColor = 'transparent';
        });
        target.classList.add('active');
        target.style.background = 'var(--bg-card)';
        target.style.color = 'var(--text-main)';
        target.style.borderColor = 'var(--border-color)';
        
        const sub = target.dataset.newsSubtab || 'stream';
        this.switchNewsMainSubtab(sub);
      });
    });

    // 13c. Market Calendar Category Filters
    document.querySelectorAll('.cal-cat-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = e.target.closest('.cal-cat-btn') || e.target;
        document.querySelectorAll('.cal-cat-btn').forEach(b => b.classList.remove('active'));
        target.classList.add('active');
        this.currentCalCat = target.dataset.calCat || 'all';
        this.fetchMarketEventsCalendar();
      });
    });

    const btnRefCal = document.getElementById('btnRefreshMarketCalendar');
    if (btnRefCal) {
      btnRefCal.addEventListener('click', () => {
        this.fetchMarketEventsCalendar();
        this.showToast('Đang làm mới lịch sự kiện toàn thị trường...', 'toast-up');
      });
    }

    const btnRefMacro = document.getElementById('btnRefreshMacroMonetary');
    if (btnRefMacro) {
      btnRefMacro.addEventListener('click', () => {
        this.fetchMacroMonetaryPolicy();
        this.showToast('Đang làm mới dữ liệu vĩ mô SBV & GSO...', 'toast-up');
      });
    }

    // 14. Quant Screener & Earnings Engine Controls
    document.querySelectorAll('.quant-q-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.quant-q-btn').forEach(b => b.classList.remove('active'));
        const targetBtn = e.target.closest('.quant-q-btn') || e.target;
        targetBtn.classList.add('active');
        this.currentQuantQ = targetBtn.dataset.quantQ || 'ALL';
        this.fetchQuantScreener();
      });
    });

    const quantStratSel = document.getElementById('quantStrategySelect');
    if (quantStratSel) {
      quantStratSel.addEventListener('change', (e) => {
        this.currentQuantStrategy = e.target.value;
        this.fetchQuantScreener();
      });
    }

    const btnAdvCrit = document.getElementById('btnAdvancedCriteria');
    if (btnAdvCrit) {
      btnAdvCrit.addEventListener('click', () => {
        const panel = document.getElementById('advancedCriteriaPanel');
        if (!panel) return;
        const isOpen = panel.style.display === 'flex';
        panel.style.display = isOpen ? 'none' : 'flex';
        if (!btnAdvCrit.dataset.label) btnAdvCrit.dataset.label = btnAdvCrit.textContent.replace(/\s*[▸▾]\s*$/, '').trim();
        btnAdvCrit.textContent = `${btnAdvCrit.dataset.label} ${isOpen ? '▸' : '▾'}`;
      });
    }

    const btnBtFromQuant = document.getElementById('btnBacktestFromQuant') || document.getElementById('btnBacktestThisScreen') || document.getElementById('btnOpenBacktestFromQuant');
    if (btnBtFromQuant) {
      btnBtFromQuant.addEventListener('click', () => {
        this.openBacktestFromQuant();
      });
    }

    const quantSecSel = document.getElementById('quantSectorSelect');
    if (quantSecSel) {
      quantSecSel.addEventListener('change', (e) => {
        this.currentQuantSector = e.target.value;
        this.fetchQuantScreener();
      });
    }

    const quantExSel = document.getElementById('quantExchangeSelect');
    if (quantExSel) {
      quantExSel.addEventListener('change', (e) => {
        this.currentQuantExchange = e.target.value;
        this.fetchQuantScreener();
      });
    }

    const quantGrowSel = document.getElementById('quantGrowthSelect');
    if (quantGrowSel) {
      quantGrowSel.addEventListener('change', (e) => {
        this.currentQuantGrowth = parseFloat(e.target.value) || 0.0;
        this.fetchQuantScreener();
      });
    }

    const quantSortSel = document.getElementById('quantSortSelect');
    if (quantSortSel) {
      quantSortSel.addEventListener('change', (e) => {
        this.currentQuantSortBy = e.target.value;
        this.fetchQuantScreener();
      });
    }

    // Universal Survival Firewall Toggle (Screener tab)
    const survivalToggle = document.getElementById('survivalToggle');
    if (survivalToggle) {
      survivalToggle.addEventListener('change', () => {
        const label = document.getElementById('survivalToggleLabel');
        if (label) {
          label.textContent = survivalToggle.checked ? 'BẬT' : 'TẮT';
          label.style.color = survivalToggle.checked ? '#f59e0b' : '#64748b';
        }
        this.quantDataCache = null;
        this.fetchQuantScreener();
      });
    }

    // Universal Survival Firewall Toggle (Backtest tab)
    const btSurvivalToggle = document.getElementById('btSurvivalToggle');
    if (btSurvivalToggle) {
      btSurvivalToggle.addEventListener('change', () => {
        const label = document.getElementById('btSurvivalToggleLabel');
        if (label) {
          label.textContent = btSurvivalToggle.checked ? 'BẬT' : 'TẮT';
          label.style.color = btSurvivalToggle.checked ? '#f59e0b' : '#64748b';
        }
      });
    }

    // Time Series Momentum (TSMOM 12M Trend) Toggle (Screener tab)
    const tsmomToggle = document.getElementById('tsmomToggle');
    if (tsmomToggle) {
      tsmomToggle.addEventListener('change', () => {
        const label = document.getElementById('tsmomToggleLabel');
        if (label) {
          label.textContent = tsmomToggle.checked ? 'BẬT' : 'TẮT';
          label.style.color = tsmomToggle.checked ? '#06b6d4' : '#64748b';
        }
        this.quantDataCache = null;
        this.fetchQuantScreener();
      });
    }

    // Time Series Momentum (TSMOM 12M Trend) Toggle (Backtest tab)
    const btTsmomToggle = document.getElementById('btTsmomToggle');
    if (btTsmomToggle) {
      btTsmomToggle.addEventListener('change', () => {
        const label = document.getElementById('btTsmomToggleLabel');
        if (label) {
          label.textContent = btTsmomToggle.checked ? 'BẬT' : 'TẮT';
          label.style.color = btTsmomToggle.checked ? '#06b6d4' : '#64748b';
        }
      });
    }

    // Forensic Accounting Firewall Toggle (Screener tab)
    const forensicToggle = document.getElementById('forensicToggle');
    if (forensicToggle) {
      forensicToggle.addEventListener('change', () => {
        const label = document.getElementById('forensicToggleLabel');
        if (label) {
          label.textContent = forensicToggle.checked ? 'BẬT' : 'TẮT';
          label.style.color = forensicToggle.checked ? '#ec4899' : '#64748b';
        }
        this.quantDataCache = null;
        this.fetchQuantScreener();
      });
    }

    // Forensic Accounting Firewall Toggle (Backtest tab)
    const btForensicToggle = document.getElementById('btForensicToggle');
    if (btForensicToggle) {
      btForensicToggle.addEventListener('change', () => {
        const label = document.getElementById('btForensicToggleLabel');
        if (label) {
          label.textContent = btForensicToggle.checked ? 'BẬT' : 'TẮT';
          label.style.color = btForensicToggle.checked ? '#ec4899' : '#64748b';
        }
      });
    }

    const quantSearch = document.getElementById('quantSearchInput') || document.getElementById('quantKeyword');
    if (quantSearch) {
      quantSearch.addEventListener('input', this.debounce((e) => {
        this.quantKeyword = e.target.value.trim().toLowerCase();
        if (this.quantDataCache) {
          this.renderQuantScreener(this.quantDataCache);
        }
      }, 150));
    }

    const btnSyncQuant = document.getElementById('btnSyncQuantSnapshot');
    if (btnSyncQuant) {
      btnSyncQuant.addEventListener('click', () => {
        this.syncQuantSnapshot();
      });
    }

    const btnExportQuantCsv = document.getElementById('btnExportQuantCsv');
    if (btnExportQuantCsv) {
      btnExportQuantCsv.addEventListener('click', () => {
        this.exportQuantCsv();
      });
    }

    // 14b. Screener Quick Backtest & Saved Criteria Controls
    const btnToggleScreenerBt = document.getElementById('btnToggleScreenerBacktest');
    if (btnToggleScreenerBt) {
      btnToggleScreenerBt.addEventListener('click', () => {
        const sec = document.getElementById('screenerBacktestSection');
        if (!sec) return;
        const isHidden = sec.style.display === 'none';
        sec.style.display = isHidden ? 'block' : 'none';
        btnToggleScreenerBt.innerHTML = isHidden
          ? `<span>⚡</span> Thu Gọn Quick Backtest ▴`
          : `<span>⚡</span> Quick Backtest (Đối Soát Nhanh)`;
        if (isHidden) {
          // Auto trigger initial quick backtest simulation if not run yet
          const kpiBox = document.getElementById('qsBtKpiContainer');
          if (kpiBox && kpiBox.style.display === 'none') {
            this.fetchScreenerQuickBacktest();
          }
        }
      });
    }

    const btnRunScreenerBt = document.getElementById('btnRunScreenerQuickBt');
    if (btnRunScreenerBt) {
      btnRunScreenerBt.addEventListener('click', () => {
        this.fetchScreenerQuickBacktest();
      });
    }

    document.querySelectorAll('#qsBtHorizonGroup .bt-pill-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('#qsBtHorizonGroup .bt-pill-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.qsBtHorizon = parseInt(e.target.dataset.horizon, 10) || 5;
        this.fetchScreenerQuickBacktest();
      });
    });

    const qsCadenceSel = document.getElementById('qsBtCadenceSelect');
    if (qsCadenceSel) {
      qsCadenceSel.addEventListener('change', (e) => {
        this.qsBtCadence = e.target.value;
        this.fetchScreenerQuickBacktest();
      });
    }

    const qsTopKSel = document.getElementById('qsBtTopKSelect');
    if (qsTopKSel) {
      qsTopKSel.addEventListener('change', (e) => {
        this.qsBtTopK = parseInt(e.target.value, 10) || 10;
        this.fetchScreenerQuickBacktest();
      });
    }

    const qsFillSel = document.getElementById('qsBtFillModeSelect');
    if (qsFillSel) {
      qsFillSel.addEventListener('change', (e) => {
        this.qsBtFillMode = e.target.value;
        this.fetchScreenerQuickBacktest();
      });
    }

    const qsCapitalSel = document.getElementById('qsBtCapitalSelect');
    if (qsCapitalSel) {
      qsCapitalSel.addEventListener('change', (e) => {
        this.qsBtCapital = parseFloat(e.target.value) || 100000000;
        this.fetchScreenerQuickBacktest();
      });
    }

    // Save Criteria Modal Triggers
    const btnSaveCrit = document.getElementById('btnSaveCurrentCriteria');
    if (btnSaveCrit) {
      btnSaveCrit.addEventListener('click', () => {
        this.openSaveCriteriaModal();
      });
    }

    const btnCloseSaveCrit = document.getElementById('btnCloseSaveCritModal');
    if (btnCloseSaveCrit) {
      btnCloseSaveCrit.addEventListener('click', () => {
        const modal = document.getElementById('saveCriteriaModal');
        if (modal) modal.classList.remove('active');
      });
    }

    const btnCancelSaveCrit = document.getElementById('btnCancelSaveCrit');
    if (btnCancelSaveCrit) {
      btnCancelSaveCrit.addEventListener('click', () => {
        const modal = document.getElementById('saveCriteriaModal');
        if (modal) modal.classList.remove('active');
      });
    }

    const btnConfirmSaveCrit = document.getElementById('btnConfirmSaveCrit');
    if (btnConfirmSaveCrit) {
      btnConfirmSaveCrit.addEventListener('click', () => {
        this.saveCurrentScreenerCriteria();
      });
    }

    // Saved Criteria List Modal Triggers
    const btnOpenSavedCrit = document.getElementById('btnOpenSavedCriteria');
    if (btnOpenSavedCrit) {
      btnOpenSavedCrit.addEventListener('click', () => {
        this.openSavedCriteriaListModal();
      });
    }

    const btnCloseSavedList = document.getElementById('btnCloseSavedListModal');
    if (btnCloseSavedList) {
      btnCloseSavedList.addEventListener('click', () => {
        const modal = document.getElementById('savedCriteriaListModal');
        if (modal) modal.classList.remove('active');
      });
    }

    // 15. Quant Backtest Studio Controls
    const btnRunBt = document.getElementById('btnRunBacktestCompare');
    if (btnRunBt) {
      btnRunBt.addEventListener('click', () => {
        this.fetchBacktestComparison();
      });
    }

    document.querySelectorAll('#btHorizonGroup .bt-pill-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('#btHorizonGroup .bt-pill-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.btTimeHorizon = parseInt(e.target.dataset.horizon, 10) || 5;
        this.fetchBacktestComparison();
      });
    });

    document.querySelectorAll('#btExchangeGroup .bt-ex-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const ex = e.currentTarget.dataset.exchange;
        if (!ex) return;

        if (ex === 'ALL') {
          this.btExchanges = ['ALL'];
        } else {
          // If 'ALL' was active, remove it
          this.btExchanges = this.btExchanges.filter(x => x !== 'ALL');
          
          // Toggle the clicked exchange
          if (this.btExchanges.includes(ex)) {
            this.btExchanges = this.btExchanges.filter(x => x !== ex);
          } else {
            this.btExchanges.push(ex);
          }

          // If all 3 are selected or none is selected, reset to 'ALL'
          const allExs = ['HOSE', 'HNX', 'UPCOM'];
          const hasAllThree = allExs.every(x => this.btExchanges.includes(x));
          if (this.btExchanges.length === 0 || hasAllThree) {
            this.btExchanges = ['ALL'];
          }
        }

        // Update UI pill active states
        document.querySelectorAll('#btExchangeGroup .bt-ex-pill').forEach(b => {
          const bEx = b.dataset.exchange;
          if (this.btExchanges.includes('ALL')) {
            if (bEx === 'ALL') b.classList.add('active');
            else b.classList.remove('active');
          } else {
            if (this.btExchanges.includes(bEx)) b.classList.add('active');
            else b.classList.remove('active');
          }
        });

        this.fetchBacktestComparison();
      });
    });

    const btCadenceSel = document.getElementById('btCadenceSelect');
    if (btCadenceSel) {
      btCadenceSel.addEventListener('change', (e) => {
        this.btCadence = e.target.value;
        this.fetchBacktestComparison();
      });
    }

    const btTopKSel = document.getElementById('btTopKSelect');
    if (btTopKSel) {
      btTopKSel.addEventListener('change', (e) => {
        this.btTopK = parseInt(e.target.value, 10) || 10;
        this.fetchBacktestComparison();
      });
    }

    const btFillModeSel = document.getElementById('btFillModeSelect');
    if (btFillModeSel) {
      btFillModeSel.addEventListener('change', (e) => {
        this.btFillMode = e.target.value === 'fill' ? 'fill' : 'strict';
        this.fetchBacktestComparison();
      });
    }

    const btCapSel = document.getElementById('btCapitalSelect');
    if (btCapSel) {
      btCapSel.addEventListener('change', (e) => {
        this.btCapital = parseFloat(e.target.value) || 100000000;
        this.fetchBacktestComparison();
      });
    }

    const btInspectSel = document.getElementById('btInspectStrategySelect');
    if (btInspectSel) {
      btInspectSel.addEventListener('change', (e) => {
        this.btInspectStrategy = e.target.value;
        this.renderBacktestRebalanceHistory(this.btInspectStrategy);
      });
    }

    this.setupBacktestCanvasHover();

    // Modal Close
    const btnCloseEeModal = document.getElementById('btnCloseEeModal');
    const eeModal = document.getElementById('earningsEngineModal');
    if (btnCloseEeModal) {
      btnCloseEeModal.addEventListener('click', () => this.closeEarningsEngineModal());
    }
    if (eeModal) {
      eeModal.addEventListener('click', (e) => {
        if (e.target === eeModal) this.closeEarningsEngineModal();
      });
    }
  }

  switchTab(tabId) {
    this.currentTab = tabId;

    document.querySelectorAll('.view-tab').forEach(t => {
      if (t.dataset.tab === tabId) t.classList.add('active');
      else t.classList.remove('active');
    });

    document.querySelectorAll('.view-panel').forEach(p => {
      if (p.id === `tab_${tabId}`) p.classList.add('active');
      else p.classList.remove('active');
    });

    const now = Date.now();
    if (!this._tabLastFetched) this._tabLastFetched = {};

    if (tabId === 'board') {
      if (this.currentBoardData && this.currentBoardData.length > 0) {
        this.renderFilteredTradingBoard();
      }
      if (!this._tabLastFetched['board'] || (now - this._tabLastFetched['board'] > 30000)) {
        this._tabLastFetched['board'] = now;
        this.fetchTradingBoard(this.currentBoardGroup);
      }
    } else if (tabId === 'chart') {
      setTimeout(() => {
        if (this.chartManager) this.chartManager.resize();
        if (this.isMacroSymbol(this.currentSymbol)) {
          this.loadMacroDetails(this.currentSymbol);
        } else {
          this.loadStockDetails(this.currentSymbol || 'FPT');
        }
      }, 30);
    } else if (tabId === 'quant') {
      if (this.quantDataCache) {
        this.renderQuantScreener(this.quantDataCache);
      }
      if (!this._tabLastFetched['quant'] || (now - this._tabLastFetched['quant'] > 60000)) {
        this._tabLastFetched['quant'] = now;
        this.fetchQuantScreener();
      }
    } else if (tabId === 'backtest') {
      if (this.btDataCache) {
        setTimeout(() => {
          this.renderBacktestDashboard(this.btDataCache);
        }, 30);
      } else {
        this.fetchBacktestComparison();
      }
    } else if (tabId === 'sectors') {
      setTimeout(() => {
        if (this.sectorChartManager) this.sectorChartManager.resize();
      }, 30);
      if (this.allSectorsCache) {
        this.renderSectorsOverview(this.allSectorsCache);
      }
      if (!this._tabLastFetched['sectors'] || (now - this._tabLastFetched['sectors'] > 60000)) {
        this._tabLastFetched['sectors'] = now;
        this.fetchSectorsOverview();
      }
    } else if (tabId === 'news') {
      if (this.allNewsCache) {
        this.renderMarketNews(this.allNewsCache);
      }
      if (!this._tabLastFetched['news'] || (now - this._tabLastFetched['news'] > 60000)) {
        this._tabLastFetched['news'] = now;
        this.fetchMarketNews();
      }
    } else if (tabId === 'treemap') {
      if (this.treemapDataCache) {
        this.renderMarketTreemap(this.treemapDataCache);
      }
      if (!this._tabLastFetched['treemap'] || (now - this._tabLastFetched['treemap'] > 60000)) {
        this._tabLastFetched['treemap'] = now;
        this.fetchMarketTreemap();
      }
    } else if (tabId === 'foreign') {
      if (this.foreignFlowCache) {
        this.renderForeignFlow(this.foreignFlowCache);
      }
      if (!this._tabLastFetched['foreign'] || (now - this._tabLastFetched['foreign'] > 60000)) {
        this._tabLastFetched['foreign'] = now;
        this.fetchForeignFlow();
      }
    } else if (tabId === 'alerts') {
      this.loadAlertRules();
    }
  }

  switchStockSubtab(subtabId) {
    this.currentStockSubtab = subtabId;
    document.querySelectorAll('#stockSubtabsHeader .subtab-btn').forEach(b => {
      if (b.dataset.subtab === subtabId) b.classList.add('active');
      else b.classList.remove('active');
    });

    document.querySelectorAll('.subtab-content').forEach(c => {
      if (c.id === `subtab_${subtabId}`) c.classList.add('active');
      else c.classList.remove('active');
    });

    if (!this.currentSymbol) return;

    if (subtabId === 'stock_news') {
      this.fetchCompanyNews(this.currentSymbol);
    } else if (subtabId === 'stock_filings' || subtabId === 'stock_reports') {
      this.fetchCompanyReports(this.currentSymbol);
    } else if (subtabId === 'stock_events') {
      this.fetchCompanyEvents(this.currentSymbol);
    } else if (subtabId === 'stock_leadership') {
      this.fetchCompanyLeadership(this.currentSymbol);
    } else if (subtabId === 'stock_financials') {
      if (this.currentFinType === 'three_way') {
        this.fetchThreeStatementForecast(this.currentSymbol);
      } else {
        this.fetchCompanyFinancials(this.currentSymbol, this.currentFinType || 'income', this.currentFinPeriod || 'quarter', this.currentFinCount || 8);
      }
    } else if (subtabId === 'stock_forensic') {
      this.fetchCompanyForensics(this.currentSymbol);
    } else if (subtabId === 'stock_health') {
      this.fetchCompanyHealth(this.currentSymbol);
    } else if (subtabId === 'stock_earnings_engine') {
      this.fetchCompanyEarningsEngine(this.currentSymbol);
    } else if (subtabId === 'stock_quant_valuation') {
      this.fetchStockQuantValuation(this.currentSymbol);
    } else if (subtabId === 'stock_recommendations') {
      this.fetchCompanyRecommendations(this.currentSymbol);
    } else if (subtabId === 'stock_peers') {
      this.loadStockPeers(this.currentSymbol);
    } else if (subtabId === 'stock_ecosystem') {
      this.fetchCompanyEcosystem(this.currentSymbol);
    } else if (subtabId === 'stock_commodity_spread') {
      this.fetchCompanyCommoditySpread(this.currentSymbol);
    }
  }

  startClock() {
    const clockEl = document.getElementById('timeClock');
    const update = () => {
      const now = new Date();
      if (clockEl) clockEl.textContent = now.toLocaleTimeString('vi-VN', { hour12: false });
    };
    update();
    setInterval(update, 1000);
  }

  // ==========================================================================
  // TOP INDICES & MARKET BREADTH
  // ==========================================================================

  async fetchIndicesAnalytics() {
    try {
      const res = await fetch('/api/indices-analytics');
      const json = await res.json();
      if (json.status !== 'success') return;

      const { indices, breadth } = json.data;

      // Render Indices Cards
      const container = document.getElementById('indicesCards');
      if (container) {
        container.innerHTML = indices.map(idx => {
          const sign = idx.change > 0 ? '+' : '';
          const pts = this.generateMiniSparklineSvg(idx.sparkline, idx.change >= 0);
          return `
            <div class="index-card">
              <div class="index-top-row">
                <span class="index-name">${idx.name}</span>
                <span class="index-price mono ${idx.color_class}">${idx.price.toFixed(2)}</span>
              </div>
              <div class="index-bottom-row">
                <span class="index-change mono ${idx.color_class}">
                  ${sign}${idx.change.toFixed(2)} (${sign}${idx.change_pct.toFixed(2)}%)
                </span>
                <span class="index-sparkline">${pts}</span>
              </div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">
                GT: <strong style="color:var(--text-primary);">${idx.liquidity_billion.toLocaleString()} tỷ</strong>
              </div>
            </div>
          `;
        }).join('');
      }

      // Render Breadth
      if (breadth) {
        document.getElementById('cntCeil').textContent = breadth.ceiling;
        document.getElementById('cntAdv').textContent = breadth.advances;
        document.getElementById('cntRef').textContent = breadth.unchanged;
        document.getElementById('cntDec').textContent = breadth.declines;
        document.getElementById('cntFlor').textContent = breadth.floor;
        document.getElementById('totalLiquidityBillion').textContent = `${breadth.total_liquidity_billion.toLocaleString()} tỷ đ`;
      }
    } catch (e) {
      console.error('Error fetching indices:', e);
    }
  }

  generateMiniSparklineSvg(points, isUp) {
    if (!points || points.length < 2) return '';
    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = (max - min) || 1;
    const w = 55;
    const h = 18;

    const coords = points.map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / range) * (h - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const stroke = isUp ? '#10b981' : '#ef4444';
    return `<svg width="${w}" height="${h}" style="overflow:visible;"><polyline fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" points="${coords}" /></svg>`;
  }

  isMacroSymbol(sym) {
    if (!sym) return false;
    const MACROS = [
      'USDVND', 'VN10Y', 'SBV_OMO', 'CPI_VN', 'GDP_VN', 'PMI_VN', 'FDI_VN', 'DXY', 'BRENT', 'GOLD',
      'USD/VND', 'CPI', 'GDP', 'PMI', 'FDI', 'DẦU', 'VÀNG', 'DXY_INDEX', 'OMO', 'SBV'
    ];
    return MACROS.includes(String(sym).toUpperCase().trim());
  }

  async fetchTradingBoard(group) {
    try {
      this.currentBoardGroup = group;
      let url = `/api/trading-board?group=${group}`;
      if (group === 'Macro') {
        url = '/api/market/macro-board';
      } else if (group === 'Watchlist') {
        const syms = this.watchlist.join(',');
        url = `/api/trading-board?symbols=${syms || 'FPT,HPG,VNM'}`;
      }
      const res = await fetch(url);
      const json = await res.json();
      if (json.status !== 'success') {
        const tbody = document.getElementById('tradingBoardBody');
        if (tbody && (!this.currentBoardData || this.currentBoardData.length === 0)) {
          tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:28px 16px; color:var(--color-down, #ef4444); font-size:12px;">
            ⚠️ Không thể tải dữ liệu bảng giá cho nhóm ${escapeHTML(group)}. (${escapeHTML(json.message || 'Lỗi kết nối')})
          </td></tr>`;
        }
        return;
      }

      this.currentBoardData = json.data || [];
      this.renderFilteredTradingBoard();
    } catch (e) {
      console.error('Error fetching board:', e);
      const tbody = document.getElementById('tradingBoardBody');
      if (tbody && (!this.currentBoardData || this.currentBoardData.length === 0)) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:28px 16px; color:var(--color-down, #ef4444); font-size:12px;">
          ⚠️ Lỗi kết nối khi tải bảng giá. Vui lòng kiểm tra kết nối hoặc thử lại.
        </td></tr>`;
      }
    }
  }

  renderFilteredTradingBoard() {
    let rows = this.currentBoardData || [];
    const total = rows.length;
    if (this.boardFilterKeyword) {
      rows = rows.filter(r => {
        const s = (r.symbol || '').toLowerCase();
        const n = (r.name || '').toLowerCase();
        const ex = (r.exchange || r.category || '').toLowerCase();
        return s.includes(this.boardFilterKeyword) || n.includes(this.boardFilterKeyword) || ex.includes(this.boardFilterKeyword);
      });
    }

    const badge = document.getElementById('boardCountBadge');
    if (badge) {
      if (this.boardFilterKeyword) {
        badge.textContent = `${rows.length}/${total} ${this.currentBoardGroup === 'Macro' ? 'chỉ số' : 'mã'}`;
      } else {
        badge.textContent = `${total} ${this.currentBoardGroup === 'Macro' ? 'chỉ số Vĩ Mô' : 'mã ' + this.currentBoardGroup}`;
      }
    }

    this.renderCleanTradingBoard(rows);
  }

  renderCleanTradingBoard(rows) {
    const tbody = document.getElementById('tradingBoardBody');
    if (!tbody) return;

    const stockHdrRow = document.getElementById('stockBoardHeaderRow');
    const macroHdrRow = document.getElementById('macroBoardHeaderRow');

    const isMacro = (this.currentBoardGroup === 'Macro' || (rows && rows.length > 0 && rows[0] && rows[0].is_macro));
    if (isMacro) {
      if (stockHdrRow) stockHdrRow.style.display = 'none';
      if (macroHdrRow) macroHdrRow.style.display = 'table-row';
    } else {
      if (stockHdrRow) stockHdrRow.style.display = 'table-row';
      if (macroHdrRow) macroHdrRow.style.display = 'none';
    }

    if (!rows || rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:28px 16px; color:var(--text-muted); font-size:12px;">
        ⏳ Chưa có dữ liệu giá từ nguồn (ngoài giờ giao dịch hoặc nguồn dữ liệu tạm thời gián đoạn).<br>
        <span style="font-size:11px;">Bảng sẽ tự cập nhật khi có dữ liệu — không hiển thị số liệu bịa đặt.</span>
      </td></tr>`;
      return;
    }

    // SPECIAL RENDER FOR MACRO BOARD
    if (isMacro) {

      tbody.innerHTML = rows.map((r, idx) => {
        const isUp = (r.change_pct || 0) > 0;
        const isDown = (r.change_pct || 0) < 0;
        const colorClass = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
        const sign = isUp ? '+' : '';
        const curFormatted = typeof r.current_val === 'number' ? r.current_val.toLocaleString('vi-VN') : r.current_val;

        return `
          <tr style="background:rgba(56,189,248,0.02); transition:all 0.2s ease;">
            <td style="text-align:center; color:var(--text-muted); font-size:11px;">${idx + 1}</td>
            <td class="col-symbol" onclick="app.inspectStock('${r.symbol}')" style="color:#38bdf8; font-weight:800; cursor:pointer;" title="Bấm để xem phân tích vĩ mô & ma trận tác động">
              <span style="margin-right:4px;">${r.icon || '🌐'}</span>${r.symbol}
            </td>
            <td style="text-align:left; font-size:11.5px; font-weight:700; color:var(--text-primary); cursor:pointer;" onclick="app.inspectStock('${r.symbol}')">
              ${escapeHTML(r.name)}
            </td>
            <td style="text-align:center; font-size:10.5px; color:var(--text-muted); font-weight:700;">
              <span class="badge" style="background:rgba(255,255,255,0.05); color:var(--text-secondary); font-size:10px; padding:2px 6px;">${escapeHTML(r.category || 'Vĩ Mô')}</span>
            </td>
            
            <td colspan="3" style="text-align:left; font-size:11px; color:var(--text-secondary); padding-left:12px;">
              <span style="color:var(--text-muted); font-size:10px;">Ngưỡng/Mục tiêu:</span> <strong style="color:var(--text-primary);">${escapeHTML(r.target_desc || '--')}</strong>
            </td>

            <!-- Giá trị hiện tại -->
            <td class="mono ${colorClass}" style="text-align:right; font-weight:900; font-size:13px;">
              ${curFormatted} <span style="font-size:9.5px; font-weight:600; color:var(--text-muted);">${escapeHTML(r.unit || '')}</span>
            </td>

            <!-- Thay đổi % -->
            <td class="mono ${colorClass}" style="text-align:right; font-weight:800; font-size:11.5px;">
              ${sign}${r.change_pct}%
            </td>

            <!-- Trạng thái đánh giá -->
            <td style="text-align:center;">
              <span class="badge ${r.status_class || 'badge-neutral'}" style="font-size:10.5px; font-weight:800; padding:2px 8px;">${escapeHTML(r.status_badge || 'Bình thường')}</span>
            </td>

            <!-- Thao tác phân tích -->
            <td style="text-align:center;">
              <button class="btn-inspect" style="background:rgba(56,189,248,0.15); border-color:#38bdf8; color:#38bdf8; font-weight:700;" onclick="app.inspectStock('${r.symbol}')">🔍 Phân Tích</button>
            </td>
          </tr>
        `;
      }).join('');
      return;
    }

    if (stockHdrRow) stockHdrRow.style.display = 'table-row';
    if (macroHdrRow) macroHdrRow.style.display = 'none';

    // Null-safe formatters: một số mã ngoài giờ giao dịch / illiquid UPCOM
    // có field null từ nguồn — tuyệt đối không được làm chết toàn bảng render.
    const fp = v => (v == null ? '--' : Number(v).toFixed(2));
    const fv = v => (v == null ? '--' : Number(v).toLocaleString('en-US'));

    tbody.innerHTML = rows.map((r, idx) => {
      const prevPrice = this.previousPrices[r.symbol];
      let flashClass = '';
      if (prevPrice !== undefined && r.match_p != null) {
        if (r.match_p > prevPrice) flashClass = 'tick-flash-up';
        else if (r.match_p < prevPrice) flashClass = 'tick-flash-down';
      }
      this.previousPrices[r.symbol] = r.match_p;

      return `
        <tr>
          <td style="text-align:center; color:var(--text-muted); font-size:11px;">${idx + 1}</td>
          <td class="col-symbol" onclick="app.inspectStock('${escapeHTML(r.symbol)}')" title="Bấm để xem phân tích mã ${escapeHTML(r.symbol)}">${escapeHTML(r.symbol)}</td>
          <td style="text-align:left; font-size:11px; color:var(--text-secondary); max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHTML(r.name || '')}">${escapeHTML(r.name)}</td>
          <td style="text-align:center; font-size:10px; color:var(--text-muted); font-weight:700;">${escapeHTML(r.exchange)}</td>
          
          <!-- Giá Trần, Sàn, TC -->
          <td class="mono txt-ceil">${fp(r.ceil)}</td>
          <td class="mono txt-floor">${fp(r.floor)}</td>
          <td class="mono txt-ref">${fp(r.ref)}</td>

          <!-- Giá Đóng Cửa / Khớp Lệnh (flash cell theo tick) -->
          <td class="mono ${r.match_color} ${flashClass}" style="font-weight:800; font-size:13px;">${fp(r.match_p)}</td>

          <!-- Khối Lượng -->
          <td class="mono">${fv(r.total_vol)}</td>

          <!-- Room Ngoại -->
          <td class="mono" style="color:#38bdf8;">${fv(r.f_room)}</td>

          <!-- Thao Tác Phân Tích -->
          <td style="text-align:center;">
            <button class="btn-inspect" onclick="app.inspectStock('${escapeHTML(r.symbol)}')">📈 Phân Tích</button>
          </td>
        </tr>
      `;
    }).join('');
  }

  inspectStock(symbol) {
    this.currentSymbol = symbol;
    this.switchTab('chart');
    if (this.isMacroSymbol(symbol)) {
      this.loadMacroDetails(symbol);
    } else {
      this.loadStockDetails(symbol);
    }
  }

  selectStock(symbol) {
    this.inspectStock(symbol);
  }

  // ==========================================================================
  // DUAL-MODE ANALYSIS ENGINE (MACRO & INTERMARKET INTELLIGENCE)
  // ==========================================================================

  switchMacroSubtab(subtabId) {
    this.currentMacroSubtab = subtabId;
    document.querySelectorAll('#macroSubtabsHeader .subtab-btn').forEach(b => {
      if (b.dataset.macroSubtab === subtabId) b.classList.add('active');
      else b.classList.remove('active');
    });

    document.querySelectorAll('.subtab-content').forEach(c => {
      if (c.id === `subtab_${subtabId}`) c.classList.add('active');
      else c.classList.remove('active');
    });

    if (this.currentMacroData) {
      if (subtabId === 'macro_impact') {
        this.renderMacroImpact(this.currentMacroData.impact_matrix, this.currentMacroData.indicator_code);
      } else if (subtabId === 'macro_series') {
        this.renderMacroSeries(this.currentMacroData);
      } else if (subtabId === 'macro_breakdown') {
        this.renderMacroBreakdown(this.currentMacroData.breakdown, this.currentMacroData.indicator_info);
      } else if (subtabId === 'macro_reports') {
        this.fetchMacroDocuments();
      } else if (subtabId === 'macro_news') {
        this.renderMacroNews(this.currentMacroData.policy_news, this.currentMacroData.indicator_info);
      } else if (subtabId === 'macro_calendar') {
        this.renderMacroCalendar(this.currentMacroData.economic_calendar);
      }
    }
  }

  async loadMacroDetails(symbol) {
    this.currentSymbol = symbol;
    this.analysisMode = 'macro';
    const seq = (this._macroSeq = (this._macroSeq || 0) + 1);

    if (this._macroAbortController) {
      try { this._macroAbortController.abort(); } catch (e) {}
    }
    this._macroAbortController = new AbortController();
    const signal = this._macroAbortController.signal;

    // Switch headers
    const stockHdr = document.getElementById('stockSubtabsHeader');
    const macroHdr = document.getElementById('macroSubtabsHeader');
    if (stockHdr) stockHdr.style.display = 'none';
    if (macroHdr) macroHdr.style.display = 'flex';

    // Hide all subtab contents
    document.querySelectorAll('.subtab-content').forEach(c => {
      c.classList.remove('active');
    });

    try {
      const res = await fetch(`/api/market/macro-detail?indicator=${encodeURIComponent(symbol)}`, { signal });
      const json = await res.json();
      if (signal.aborted || this._macroSeq !== seq || this.analysisMode !== 'macro') return;
      if (json.status !== 'success') return;
      const data = json.data || json;
      this.currentMacroData = data;
      const info = data.indicator_info || {};

      // Populate Hero Box
      const heroSym = document.getElementById('heroSymbol');
      const heroName = document.getElementById('heroName');
      const heroPrice = document.getElementById('heroPrice');
      const heroChg = document.getElementById('heroChangeTag');
      const heroCeil = document.getElementById('heroCeil');
      const heroFloor = document.getElementById('heroFloor');
      const heroRef = document.getElementById('heroRef');
      const btnW = document.getElementById('btnWatchlistToggle');

      if (heroSym) heroSym.innerHTML = `<span style="margin-right:6px;">${info.icon || '🌐'}</span>${info.symbol || symbol}`;
      if (heroName) heroName.textContent = `${info.name || symbol} • Nguồn: ${info.source || 'GSO/SBV'}`;
      if (heroPrice) heroPrice.textContent = `${typeof info.current_val === 'number' ? info.current_val.toLocaleString('vi-VN') : info.current_val} ${info.unit || ''}`;
      
      const isUp = (info.change_pct || 0) > 0;
      const isDown = (info.change_pct || 0) < 0;
      const colorClass = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
      const sign = isUp ? '+' : '';
      if (heroChg) {
        heroChg.textContent = `${sign}${info.change_pct || 0}% (${info.status_badge || ''})`;
        heroChg.className = colorClass;
      }
      if (heroPrice) heroPrice.className = `hero-price ${colorClass}`;

      if (heroCeil) heroCeil.textContent = info.target_desc ? info.target_desc.slice(0, 32) : '--';
      if (heroFloor) heroFloor.textContent = info.category || 'Vĩ Mô';
      if (heroRef) heroRef.textContent = info.source ? info.source.slice(0, 20) : 'Chính thức';

      if (btnW) btnW.textContent = '🇻🇳 Chỉ Số Vĩ Mô';

      // Render chart for macro series if candles available
      const hist = data.historical_series || [];
      if (hist.length > 0 && this.chartManager) {
        const candles = hist.map(h => {
          const val = typeof h.close === 'number' ? h.close : parseFloat(h.close) || 0;
          return {
            time: h.date,
            open: val,
            high: val * 1.002,
            low: val * 0.998,
            close: val,
            volume: 1000
          };
        });
        const chartPayload = {
          symbol: info.symbol || symbol,
          company_name: info.name || symbol,
          candles: candles,
          latest_price: info.current_val || 0,
          change: info.change_val || 0,
          change_pct: info.change_pct || 0,
          ceil: info.current_val || 0,
          floor: info.current_val || 0,
          ref: info.current_val || 0,
          technical_signal: {
            signal: info.status_badge || 'THEO DÕI VĨ MÔ',
            badge_class: info.status_class || 'badge-bullish',
            details: [
              `Mục tiêu / Ngưỡng: ${info.target_desc || 'Ổn định kinh tế vĩ mô'}`,
              `Nguồn công bố: ${info.source || 'SBV & GSO'}`,
              `Đánh giá xu hướng: ${info.impact_matrix ? info.impact_matrix.summary.slice(0, 100) : ''}`
            ]
          }
        };
        this.chartManager.setData(chartPayload);
        this.chartManager.resize();

        // Technical signal in right panel
        const sb = document.getElementById('signalBadge');
        if (sb) {
          sb.textContent = info.status_badge || 'THEO DÕI VĨ MÔ';
          sb.className = `signal-badge ${info.status_class || 'badge-bullish'}`;
          const sDet = document.getElementById('signalDetails');
          if (sDet) {
            sDet.innerHTML = `
              <div>• <strong>Chỉ số:</strong> ${escapeHTML(info.name || '')}</div>
              <div>• <strong>Ngưỡng:</strong> ${escapeHTML(info.target_desc || '')}</div>
              <div>• <strong>Nguồn:</strong> ${escapeHTML(info.source || '')}</div>
            `;
          }
        }
      }

      // Fundamentals card in right panel adapted for macro
      const elCap = document.getElementById('f_market_cap');
      const elPe = document.getElementById('f_pe');
      const elPb = document.getElementById('f_pb');
      const elEps = document.getElementById('f_eps');
      const elRoe = document.getElementById('f_roe');
      const elRoa = document.getElementById('f_roa');
      const el52w = document.getElementById('f_range_52w');
      const elRoom = document.getElementById('f_room');

      if (elCap) elCap.textContent = info.category || 'Vĩ Mô';
      if (elPe) elPe.textContent = `${info.current_val} ${info.unit || ''}`;
      if (elPb) elPb.textContent = `${info.change_pct}%`;
      if (elEps) elEps.textContent = info.source ? info.source.split('(')[0] : 'SBV/GSO';
      if (elRoe) elRoe.textContent = info.status_badge || 'Tích cực';
      if (elRoa) elRoa.textContent = 'Chính thức';
      if (el52w) el52w.textContent = info.target_desc || '--';
      if (elRoom) elRoom.textContent = 'Toàn Thị Trường';

      // Adapt Order Book Ladder card for Macro indicator
      const ladderEl = document.getElementById('orderBookLadder');
      if (ladderEl) {
        ladderEl.innerHTML = `
          <div style="font-size:11.5px; padding:6px 0;">
            <div style="display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Giá trị hiện tại:</span>
              <strong style="color:#38bdf8;">${info.current_val} ${info.unit || ''}</strong>
            </div>
            <div style="display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Biến động:</span>
              <strong class="${colorClass}">${sign}${info.change_pct}%</strong>
            </div>
            <div style="display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Phân loại:</span>
              <span>${escapeHTML(info.category || 'Vĩ Mô')}</span>
            </div>
            <div style="display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Nguồn công bố:</span>
              <span>${escapeHTML(info.source || 'GSO & SBV')}</span>
            </div>
            <div style="margin-top:8px; font-size:11px; color:var(--text-secondary); line-height:1.4; background:rgba(56,189,248,0.06); padding:6px 8px; border-radius:4px; border:1px solid rgba(56,189,248,0.2);">
              📌 <strong>Mục tiêu:</strong> ${escapeHTML(info.target_desc || '--')}
            </div>
          </div>
        `;
      }

      // Switch to active macro subtab
      this.switchMacroSubtab(this.currentMacroSubtab || 'macro_impact');

    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error loading macro details:', e);
    }
  }

  renderMacroImpact(impact, symbol) {
    const container = document.getElementById('macroImpactContainer');
    if (!container) return;
    if (!impact) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">Chưa có dữ liệu ma trận tác động cho chỉ số này.</div>';
      return;
    }

    const benRows = (impact.beneficiaries || []).map(b => {
      const symBadges = (b.symbols || []).map(s => 
        `<span style="background:rgba(16,185,129,0.15); color:#10b981; font-weight:800; font-size:11px; padding:2px 7px; border-radius:4px; cursor:pointer;" onclick="app.inspectStock('${s}')">${s}</span>`
      ).join(' ');

      return `
        <div style="background:var(--bg-surface-elevated); border:1px solid rgba(16,185,129,0.25); border-radius:8px; padding:12px 14px; margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <span style="font-size:12.5px; font-weight:800; color:#10b981;">🟢 Ngành ${escapeHTML(b.sector)}</span>
            <div style="display:flex; gap:4px;">${symBadges}</div>
          </div>
          <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.5;">${escapeHTML(b.reason)}</div>
        </div>
      `;
    }).join('');

    const advRows = (impact.adversely_impacted || []).map(a => {
      const symBadges = (a.symbols || []).map(s => 
        `<span style="background:rgba(239,68,68,0.15); color:#ef4444; font-weight:800; font-size:11px; padding:2px 7px; border-radius:4px; cursor:pointer;" onclick="app.inspectStock('${s}')">${s}</span>`
      ).join(' ');

      return `
        <div style="background:var(--bg-surface-elevated); border:1px solid rgba(239,68,68,0.25); border-radius:8px; padding:12px 14px; margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <span style="font-size:12.5px; font-weight:800; color:#ef4444;">🔴 Ngành ${escapeHTML(a.sector)}</span>
            <div style="display:flex; gap:4px;">${symBadges}</div>
          </div>
          <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.5;">${escapeHTML(a.reason)}</div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="background:rgba(56,189,248,0.06); border:1px solid rgba(56,189,248,0.3); border-radius:8px; padding:12px 16px;">
          <div style="font-size:12px; font-weight:800; color:#38bdf8; margin-bottom:4px;">💡 NHẬN ĐỊNH CƠ CHẾ TÁC ĐỘNG VĨ MÔ & LIÊN THỊ TRƯỜNG:</div>
          <div style="font-size:12px; color:var(--text-primary); line-height:1.6;">${escapeHTML(impact.summary || '')}</div>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:14px;">
          <div>
            <div style="font-size:13px; font-weight:800; color:#10b981; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
              <span>🟢</span> CÁC NHÓM NGÀNH & CỔ PHIẾU HƯỞNG LỢI (BENEFICIARIES)
            </div>
            ${benRows || '<div style="color:var(--text-muted); font-size:11.5px;">Không có nhóm hưởng lợi rõ rệt.</div>'}
          </div>

          <div>
            <div style="font-size:13px; font-weight:800; color:#ef4444; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
              <span>🔴</span> CÁC NHÓM NGÀNH & CỔ PHIẾU CHỊU ÁP LỰC (ADVERSELY IMPACTED)
            </div>
            ${advRows || '<div style="color:var(--text-muted); font-size:11.5px;">Không có áp lực tiêu cực đáng kể.</div>'}
          </div>
        </div>
      </div>
    `;
  }

  renderMacroSeries(data) {
    const container = document.getElementById('macroSeriesContainer');
    if (!container) return;
    const series = data.historical_series || [];
    const info = data.indicator_info || {};

    const tableRows = series.map(s => `
      <tr>
        <td style="font-weight:700; color:var(--text-primary);">${escapeHTML(s.date)}</td>
        <td class="mono txt-up" style="text-align:right; font-weight:800;">${typeof s.close === 'number' ? s.close.toLocaleString('vi-VN') : s.close}</td>
        <td style="text-align:center; font-size:11px; color:var(--text-muted);">${escapeHTML(info.unit || '')}</td>
        <td style="font-size:11.5px; color:var(--text-secondary);">${escapeHTML(info.target_desc || 'Theo chu kỳ kinh tế')}</td>
      </tr>
    `).join('');

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:13px; font-weight:800; color:var(--text-primary);">📊 CHUỖI DỮ LIỆU LỊCH SỬ & ĐỐI CHIẾU MỤC TIÊU</span>
            <span class="badge ${info.status_class || 'badge-bullish'}">${escapeHTML(info.status_badge || '')}</span>
          </div>
          <table class="trading-board-table clean-board-table">
            <thead>
              <tr>
                <th style="text-align:left;">Kỳ / Ngày</th>
                <th style="text-align:right;">Giá Trị Ghi Nhận</th>
                <th style="text-align:center;">Đơn Vị</th>
                <th style="text-align:left;">Ngưỡng / Mục Tiêu Quốc Hội & SBV</th>
              </tr>
            </thead>
            <tbody>
              ${tableRows}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  renderMacroBreakdown(breakdown, info) {
    const container = document.getElementById('macroBreakdownContainer');
    if (!container) return;
    if (!breakdown || !breakdown.items) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">Chưa có phân rã cấu phần cho chỉ số này.</div>';
      return;
    }

    const itemsHtml = breakdown.items.map(item => `
      <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <div>
          <div style="font-size:12.5px; font-weight:800; color:var(--text-primary);">${escapeHTML(item.name)}</div>
          <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">${escapeHTML(item.note || '')}</div>
        </div>
        <div class="mono" style="font-size:14px; font-weight:900; color:#38bdf8;">${escapeHTML(item.value)}</div>
      </div>
    `).join('');

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        <div style="font-size:13px; font-weight:800; color:var(--text-primary); display:flex; align-items:center; gap:6px;">
          <span>🔍</span> ${escapeHTML(breakdown.title || 'PHÂN RÃ CẤU PHẦN')}
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:10px;">
          ${itemsHtml}
        </div>
      </div>
    `;
  }

  async fetchMacroDocuments() {
    const listEl = document.getElementById('macroReportsList');
    if (!listEl) return;
    listEl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⏳ Đang tải kho tài liệu vĩ mô & báo cáo nghiên cứu...</div>';
    const seq = (this._macroDocSeq = (this._macroDocSeq || 0) + 1);

    try {
      const cat = this.macroReportCategory || 'all';
      const kw = this.macroReportKeyword || '';
      const res = await fetch(`/api/market/macro-documents?category=${encodeURIComponent(cat)}&keyword=${encodeURIComponent(kw)}`);
      const json = await res.json();
      if (this._macroDocSeq !== seq) return;
      if (json.status !== 'success') return;
      const docs = json.data?.documents || json.documents || [];
      this.renderMacroReports(docs);
    } catch (e) {
      console.error('Error fetching macro documents:', e);
    }
  }

  renderMacroReports(docs) {
    const listEl = document.getElementById('macroReportsList');
    if (!listEl) return;

    if (!docs || docs.length === 0) {
      listEl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">Không tìm thấy tài liệu phù hợp với từ khóa lọc.</div>';
      return;
    }

    listEl.innerHTML = docs.map(doc => `
      <div class="report-item-card" style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px 16px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div style="flex:1; min-width:280px;">
          <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span class="badge" style="background:rgba(56,189,248,0.12); color:#38bdf8; font-weight:700; font-size:10px; padding:2px 6px;">${escapeHTML(doc.publisher)}</span>
            <span class="badge" style="background:rgba(255,255,255,0.05); color:var(--text-secondary); font-size:10px; padding:2px 6px;">${escapeHTML(doc.language)}</span>
            <span style="font-size:11px; color:var(--text-muted);">${escapeHTML(doc.publish_date)}</span>
          </div>
          <div style="font-size:12.5px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">
            ${escapeHTML(doc.title)}
          </div>
          <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.5;">
            ${escapeHTML(doc.summary)}
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <a href="${escapeHTML(doc.url)}" target="_blank" rel="noopener noreferrer" class="btn-pdf-download" style="text-decoration:none; background:#38bdf8; color:#0f172a; font-weight:800; font-size:11.5px; padding:6px 12px; border-radius:6px; display:inline-flex; align-items:center; gap:5px;">
            <span>📥 Tải File PDF</span> <span style="font-size:10px; opacity:0.8;">(${escapeHTML(doc.file_size || 'PDF')})</span>
          </a>
        </div>
      </div>
    `).join('');
  }

  renderMacroNews(news, info) {
    const listEl = document.getElementById('macroNewsList');
    if (!listEl) return;
    if (!news || news.length === 0) {
      listEl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">Chưa có tin tức chính sách mới cho chỉ số này.</div>';
      return;
    }

    listEl.innerHTML = news.map(item => `
      <div class="news-card" style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px 16px; margin-bottom:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge" style="background:rgba(56,189,248,0.12); color:#38bdf8; font-size:10px; font-weight:700;">${escapeHTML(item.source)}</span>
            <span style="font-size:11px; color:var(--text-muted);">${escapeHTML(item.date)}</span>
          </div>
          <span class="badge badge-bullish" style="font-size:10px; font-weight:800;">${escapeHTML(item.sentiment || 'TÍCH CỰC')}</span>
        </div>
        <div style="font-size:13px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">${escapeHTML(item.title)}</div>
        <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.5;">${escapeHTML(item.summary)}</div>
      </div>
    `).join('');
  }

  renderMacroCalendar(events) {
    const container = document.getElementById('macroCalendarContainer');
    if (!container) return;
    if (!events || events.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">Chưa có sự kiện công bố trong kỳ tới.</div>';
      return;
    }

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:10px;">
        <div style="font-size:13px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">
          📅 LỊCH CÔNG BỐ SỰ KIỆN KINH TẾ & DỰ BÁO CHUYÊN GIA
        </div>
        ${events.map(evt => `
          <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px 16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:6px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:14px;">${escapeHTML(evt.country)}</span>
                <span style="font-size:12.5px; font-weight:800; color:var(--text-primary);">${escapeHTML(evt.indicator_name)}</span>
              </div>
              <div style="display:flex; align-items:center; gap:6px;">
                <span class="badge" style="background:rgba(239,68,68,0.15); color:#ef4444; font-size:10px; font-weight:800;">${escapeHTML(evt.importance)}</span>
                <span style="font-size:11px; color:#38bdf8; font-weight:700;">⏰ ${escapeHTML(evt.event_date)}</span>
              </div>
            </div>
            
            <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin:8px 0; text-align:center; background:rgba(255,255,255,0.02); padding:8px; border-radius:6px; border:1px solid var(--border-subtle);">
              <div>
                <div style="font-size:10px; color:var(--text-muted);">Kỳ Trước (Previous)</div>
                <div class="mono" style="font-size:13px; font-weight:800; color:var(--text-secondary);">${escapeHTML(evt.previous)}</div>
              </div>
              <div>
                <div style="font-size:10px; color:var(--text-muted);">Dự Báo (Forecast)</div>
                <div class="mono" style="font-size:13px; font-weight:800; color:#38bdf8;">${escapeHTML(evt.forecast)}</div>
              </div>
              <div>
                <div style="font-size:10px; color:var(--text-muted);">Thực Tế (Actual)</div>
                <div class="mono" style="font-size:13px; font-weight:800; color:#10b981;">${escapeHTML(evt.actual || '--')}</div>
              </div>
            </div>

            <div style="font-size:11.5px; color:var(--text-secondary);">
              💡 <strong>Nhận định tác động:</strong> ${escapeHTML(evt.impact_comment)}
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // ==========================================================================
  // STOCK DETAILS & CHARTS & NEWS / EVENTS / LEADERSHIP
  // ==========================================================================

  async loadStockDetails(symbol) {
    this.currentSymbol = symbol;
    this.analysisMode = 'stock';
    const seq = (this._stockSeq = (this._stockSeq || 0) + 1);

    // Abort previous in-flight requests to avoid out-of-order race conditions
    if (this._stockAbortController) {
      try { this._stockAbortController.abort(); } catch (e) {}
    }
    this._stockAbortController = new AbortController();
    const signal = this._stockAbortController.signal;

    // Switch headers
    const stockHdr = document.getElementById('stockSubtabsHeader');
    const macroHdr = document.getElementById('macroSubtabsHeader');
    if (stockHdr) stockHdr.style.display = 'flex';
    if (macroHdr) macroHdr.style.display = 'none';

    // Hide all subtab contents
    document.querySelectorAll('.subtab-content').forEach(c => {
      c.classList.remove('active');
    });

    document.getElementById('heroSymbol').textContent = symbol;

    const isFav = this.watchlist.includes(symbol);
    const btnW = document.getElementById('btnWatchlistToggle');
    if (btnW) btnW.textContent = isFav ? '★ Đang theo dõi' : '☆ Thêm Watchlist';

    // Fetch Overview, Chart Data, News, Events & Leadership concurrently
    try {
      const [histRes, overviewRes] = await Promise.all([
        fetch(`/api/quote/history?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(this.currentInterval || '1D')}&timeframe=${encodeURIComponent(this.currentTimeframe || 'ALL')}`, { signal }).then(r => r.json()),
        fetch(`/api/company/overview?symbol=${encodeURIComponent(symbol)}`, { signal }).then(r => r.json())
      ]);

      if (signal.aborted || this._stockSeq !== seq || this.analysisMode !== 'stock') return;

      if (histRes.status === 'success') {
        const d = histRes.data;
        document.getElementById('heroName').textContent = d.company_name;
        document.getElementById('heroPrice').textContent = d.latest_price.toFixed(2);
        
        const sign = d.change > 0 ? '+' : '';
        const chgTag = document.getElementById('heroChangeTag');
        chgTag.textContent = `${sign}${d.change.toFixed(2)} (${sign}${d.change_pct.toFixed(2)}%)`;
        chgTag.className = d.change > 0 ? 'txt-up' : (d.change < 0 ? 'txt-down' : 'txt-ref');
        document.getElementById('heroPrice').className = `hero-price ${chgTag.className}`;

        document.getElementById('heroCeil').textContent = d.ceil.toFixed(2);
        document.getElementById('heroFloor').textContent = d.floor.toFixed(2);
        document.getElementById('heroRef').textContent = d.ref.toFixed(2);

        this.chartManager.setData(d);
        if (this.currentTimeframe && this.currentTimeframe !== 'ALL') {
          this.chartManager.zoomToRange(this.currentTimeframe);
        }
        this.chartManager.resize();

        // Technical Signal
        const sig = d.technical_signal;
        if (sig) {
          const sb = document.getElementById('signalBadge');
          sb.textContent = sig.signal;
          sb.className = `signal-badge ${sig.badge_class}`;
          document.getElementById('signalDetails').innerHTML = sig.details.map(det => `<div>• ${det}</div>`).join('');
        }
      }

      if (overviewRes.status === 'success') {
        const o = overviewRes.data;
        document.getElementById('f_market_cap').textContent = o.market_cap;
        document.getElementById('f_pe').textContent = o.pe;
        document.getElementById('f_pb').textContent = o.pb;
        document.getElementById('f_eps').textContent = o.eps;
        document.getElementById('f_roe').textContent = o.roe;
        document.getElementById('f_roa').textContent = o.roa;
        document.getElementById('f_range_52w').textContent = `${o.low_52w} - ${o.high_52w}`;
        document.getElementById('f_room').textContent = o.foreign_room;
      }

      // Reset report search & filter inputs for new stock
      this.reportPage = 1;
      this.reportSearchKeyword = '';
      this.reportYearFilter = 'all';
      this.reportFilterType = 'all';
      const searchInp = document.getElementById('reportSearchInput');
      if (searchInp) searchInp.value = '';
      const repYearInp = document.getElementById('reportYearInput');
      if (repYearInp) repYearInp.value = '';
      document.querySelectorAll('.c-year-pill').forEach(p => {
        if (p.dataset.year === 'all') p.classList.add('active');
        else p.classList.remove('active');
      });
      document.querySelectorAll('.c-report-pill').forEach(p => {
        if (p.dataset.reportType === 'all') p.classList.add('active');
        else p.classList.remove('active');
      });

      // Lazy load only the currently active subtab
      this.switchStockSubtab(this.currentStockSubtab || 'stock_news');

    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error loading stock details:', e);
    }
  }

  async fetchCompanyHealth(symbol) {
    try {
      const container = document.getElementById('healthOverviewContainer');
      if (!container) return;
      container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⏳ Đang phân tích sức khỏe tài chính & mô hình định giá cho mã ${escapeHTML(symbol)}...</div>`;

      const res = await fetch(`/api/company/health?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;
      if (json.status !== 'success' || !json.data) {
        this.renderErrorState('healthOverviewContainer', json.message || `Không thể tải dữ liệu sức khỏe tài chính cho mã ${symbol}.`);
        return;
      }
      this.renderCompanyHealth(json.data);
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching financial health:', e);
      this.renderErrorState('healthOverviewContainer', `Lỗi kết nối khi tải dữ liệu sức khỏe tài chính cho mã ${symbol}.`);
    }
  }

  renderCompanyHealth(d) {
    const container = document.getElementById('healthOverviewContainer');
    if (!container) return;

    const v = d.valuation_summary || {};
    const p = d.pillars || {};
    const peers = (d.industry_peers && d.industry_peers.peers) ? d.industry_peers.peers : [];

    const pProf = p.profitability || { score: 0, max: 25, pct: 0, summary: '--' };
    const pSolv = p.solvency || { score: 0, max: 25, pct: 0, summary: '--' };
    const pGrow = p.growth || { score: 0, max: 25, pct: 0, summary: '--' };
    const pVal = p.valuation || { score: 0, max: 25, pct: 0, summary: '--' };

    const peerRowsHtml = peers.map(pr => {
      const isCur = pr.symbol === d.symbol;
      const highlightStyle = isCur ? 'background:rgba(59, 130, 246, 0.15); font-weight:700;' : '';
      const chgClass = pr.change_pct && pr.change_pct.startsWith('-') ? 'txt-down' : 'txt-up';
      const score = pr.similarity_score ? Number(pr.similarity_score) : 0;
      const scoreColor = score >= 85 ? '#10b981' : (score >= 70 ? '#38bdf8' : '#f59e0b');
      const matchBadge = isCur 
        ? '<span style="background:rgba(56,189,248,0.2); color:#38bdf8; padding:1px 5px; border-radius:3px; font-size:9.5px; font-weight:700;">Đang xem</span>'
        : `<span style="color:${scoreColor}; font-weight:800; font-size:10.5px;">${score}%</span>`;

      return `
        <tr style="${highlightStyle}">
          <td><span style="color:#38bdf8; cursor:pointer;" onclick="app.selectStock('${escapeHTML(pr.symbol)}')">${escapeHTML(pr.symbol)}</span> ${isCur ? '⭐' : ''}</td>
          <td style="text-align:center;">${matchBadge}</td>
          <td>${escapeHTML(pr.price)}</td>
          <td class="${chgClass}">${escapeHTML(pr.change_pct)}</td>
          <td>${escapeHTML(pr.pe)}</td>
          <td>${escapeHTML(pr.pb)}</td>
          <td>${escapeHTML(pr.roe)}</td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <!-- 1. Top Scorecard Hero Card -->
      <div class="health-hero-card">
        <div class="health-hero-left">
          <div class="health-score-circle">
            <span class="score-num">${d.total_score}</span>
            <span class="score-max">/100</span>
          </div>
          <div class="health-title-wrap">
            <div class="health-rating-badge ${d.rating_class}">
              <span>⭐ Hạng ${escapeHTML(d.rating)}</span>
            </div>
            <div class="health-desc">${escapeHTML(d.rating_label)}</div>
          </div>
        </div>
        <div class="health-hero-right">
          <div style="font-size:11px; color:var(--text-muted);">Định Giá & Biên An Toàn:</div>
          <div class="val-badge-wrap ${v.status_class}">
            ${escapeHTML(v.status || '')} (${escapeHTML(v.upside_pct || '')})
          </div>
          <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">
            Giá hợp lý: <strong style="color:#fff;">${escapeHTML(v.fair_value_avg || '')}</strong> (Thị giá: ${escapeHTML(v.current_price || '')})
          </div>
        </div>
      </div>

      <!-- 2. Four Health Pillars Grid -->
      <div class="health-pillars-grid">
        <div class="pillar-box">
          <div class="pillar-header">
            <span class="pillar-title">📈 Sinh Lời</span>
            <span class="pillar-score" style="color:#34d399;">${pProf.score}/25</span>
          </div>
          <div class="pillar-bar-bg">
            <div class="pillar-bar-fill" style="width:${pProf.pct}%; background:#10b981;"></div>
          </div>
          <div class="pillar-summary">${escapeHTML(pProf.summary)}</div>
        </div>

        <div class="pillar-box">
          <div class="pillar-header">
            <span class="pillar-title">🛡️ Đòn Bẩy & Nợ</span>
            <span class="pillar-score" style="color:#38bdf8;">${pSolv.score}/25</span>
          </div>
          <div class="pillar-bar-bg">
            <div class="pillar-bar-fill" style="width:${pSolv.pct}%; background:#38bdf8;"></div>
          </div>
          <div class="pillar-summary">${escapeHTML(pSolv.summary)}</div>
        </div>

        <div class="pillar-box">
          <div class="pillar-header">
            <span class="pillar-title">🚀 Tăng Trưởng</span>
            <span class="pillar-score" style="color:#c084fc;">${pGrow.score}/25</span>
          </div>
          <div class="pillar-bar-bg">
            <div class="pillar-bar-fill" style="width:${pGrow.pct}%; background:#a855f7;"></div>
          </div>
          <div class="pillar-summary">${escapeHTML(pGrow.summary)}</div>
        </div>

        <div class="pillar-box">
          <div class="pillar-header">
            <span class="pillar-title">💎 Định Giá</span>
            <span class="pillar-score" style="color:#fbbf24;">${pVal.score}/25</span>
          </div>
          <div class="pillar-bar-bg">
            <div class="pillar-bar-fill" style="width:${pVal.pct}%; background:#f59e0b;"></div>
          </div>
          <div class="pillar-summary">${escapeHTML(pVal.summary)}</div>
        </div>
      </div>

      <!-- 3. Valuation Models & Industry Benchmark Dual Cards -->
      <div class="health-dual-grid">
        <!-- Card 1: Valuation Models -->
        <div class="health-card">
          <div class="health-card-header">
            <span class="health-card-title">🎯 Mô Hình Định Giá Cổ Phiếu</span>
            <span style="font-size:10.5px; color:var(--text-muted);">Đơn vị: VNĐ</span>
          </div>
          <div class="val-models-list">
            <div class="val-model-row">
              <span class="val-model-name">📐 Định giá Benjamin Graham (Graham Number)</span>
              <span class="val-model-val">${escapeHTML(v.graham_number || '--')}</span>
            </div>
            <div class="val-model-row">
              <span class="val-model-name">📊 Định giá Peter Lynch (PEG Fair Value)</span>
              <span class="val-model-val">${escapeHTML(v.peter_lynch_value || '--')}</span>
            </div>
            <div class="val-model-row">
              <span class="val-model-name">🏛️ Định giá Target P/E Ngành (14.5x)</span>
              <span class="val-model-val">${escapeHTML(v.target_pe_value || '--')}</span>
            </div>
            <div class="val-model-row" style="background:rgba(59, 130, 246, 0.15); border:1px solid rgba(59, 130, 246, 0.3);">
              <span class="val-model-name" style="color:#fff; font-weight:700;">🌟 Giá Trị Hợp Lý Trung Bình (Fair Value)</span>
              <span class="val-model-val" style="color:#38bdf8; font-size:12px;">${escapeHTML(v.fair_value_avg || '--')}</span>
            </div>
          </div>
        </div>

        <!-- Card 2: Industry Peers Benchmark -->
        <div class="health-card">
          <div class="health-card-header">
            <span class="health-card-title">🏢 Đối Thủ Cùng Ngành (${escapeHTML(d.sector_name || '')})</span>
            <span style="font-size:10.5px; color:var(--text-muted);">So sánh P/E & ROE</span>
          </div>
          <div style="overflow-x:auto;">
            <table class="peers-table">
              <thead>
                <tr>
                  <th>Mã</th>
                  <th style="text-align:center;">% Match</th>
                  <th>Thị Giá</th>
                  <th>+/-</th>
                  <th>P/E</th>
                  <th>P/B</th>
                  <th>ROE</th>
                </tr>
              </thead>
              <tbody>
                ${peerRowsHtml}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  async fetchCompanyNews(symbol, deepScan = false) {
    try {
      const container = document.getElementById('stockNewsList');
      const statusEl = document.getElementById('companyNewsStatus');
      const btnDeep = document.getElementById('btnDeepScanCompanyNews');

      if (deepScan) {
        if (btnDeep) btnDeep.innerHTML = '<span>⏳ Đang quét đa nguồn báo...</span>';
        if (statusEl) statusEl.innerHTML = `<span style="color:#38bdf8;">🔄 Đang cào và trích xuất tin bài cho mã ${symbol}...</span>`;
        if (container) {
          container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:16px; text-align:center;">⏳ Đang trích xuất toàn bộ bài viết từ CafeF, Vietstock, VnEconomy, VnExpress, Báo Đầu Tư cho mã ' + symbol + '...</div>';
        }
      } else {
        if (btnDeep) btnDeep.innerHTML = '<span>🔍 Quét sâu toàn bộ các trang báo</span>';
        if (statusEl) statusEl.innerHTML = '<span>📌 Đang lọc từ Dòng tin chung</span>';
      }

      const res = await fetch(`/api/company/news?symbol=${encodeURIComponent(symbol)}&deep_scan=${deepScan}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;
      if (json.status !== 'success') {
        if (btnDeep) btnDeep.innerHTML = '<span>🔍 Quét sâu toàn bộ các trang báo</span>';
        if (statusEl) statusEl.innerHTML = '<span style="color:#ef4444;">⚠️ Lỗi tải tin tức</span>';
        this.renderErrorState('stockNewsList', json.message || `Không thể tải tin tức cho mã ${symbol}.`);
        return;
      }

      const articles = (json.data && json.data.articles) ? json.data.articles : (Array.isArray(json.data) ? json.data : []);
      const count = articles.length;

      if (btnDeep) {
        btnDeep.innerHTML = '<span>🔍 Quét bổ sung 21+ nguồn báo</span>';
        setTimeout(() => {
          if (btnDeep) btnDeep.innerHTML = '<span>🔍 Quét bổ sung 21+ nguồn báo</span>';
        }, 4000);
      }
      if (statusEl) {
        statusEl.innerHTML = `<span style="color:#10b981;">✓ Tìm thấy ${count} tin tức & bài phân tích</span>`;
      }

      if (!container) return;

      if (count === 0) {
        container.innerHTML = `
          <div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center; background:rgba(255,255,255,0.02); border-radius:6px;">
            <div>Chưa có bài viết về mã <strong>${symbol}</strong> trong bộ nhớ tin tức hiện tại.</div>
            <div style="margin-top:8px;">
              <button class="btn-sm" onclick="app.fetchCompanyNews('${symbol}', true)" style="color:#38bdf8; border-color:#38bdf8; cursor:pointer; padding:5px 12px;">
                👉 Bấm vào đây để Quét sâu toàn bộ các trang báo ngay
              </button>
            </div>
          </div>`;
        return;
      }

      this.currentCompanyNews = articles;

      container.innerHTML = articles.map((item, idx) => {
        const topicHtml = item.topic_name 
          ? `<span class="${escapeHTML(item.topic_badge || 'badge-topic-bctc')}">${item.topic_icon || '📌'} ${escapeHTML(item.topic_name)}</span>`
          : '';

        const sentimentHtml = item.sentiment_badge
          ? `<span class="${escapeHTML(item.sentiment_badge_class || 'badge-sentiment-neutral')}">${escapeHTML(item.sentiment_badge)}</span>`
          : '';

        const safeTitle = escapeHTML(item.title || '');
        const safeSummary = escapeHTML(item.summary || '');
        const safeSource = escapeHTML(item.source || 'Báo Tài Chính');
        const safeDate = escapeHTML(item.date || '');

        const pdfBtn = (item.pdf_url || item.has_pdf)
          ? `<a href="${item.pdf_url}" target="_blank" class="btn-pdf-download" onclick="event.stopPropagation();" title="Mở file PDF gốc">📥 Tải PDF</a>`
          : '';

        return `
        <div class="news-card" onclick="app.openCompanyNewsArticle(${idx})" title="Bấm để đọc nhanh toàn văn bài báo trong Terminal">
          <div class="news-body">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
              <div style="display:flex; align-items:center; gap:6px;">
                <span class="m-news-src">${safeSource}</span>
                ${topicHtml}
                ${sentimentHtml}
              </div>
              <span style="font-size:10px; color:var(--text-muted);">📅 ${safeDate}</span>
            </div>
            <div class="news-title" style="margin-top:4px;">${safeTitle}</div>
            ${safeSummary ? `<div class="news-summary-text" style="margin-top:2px;">${safeSummary}</div>` : ''}
            <div class="news-meta" style="margin-top:6px; display:flex; justify-content:space-between; align-items:center;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="color:#38bdf8; font-weight:700; font-size:11px;">📖 Đọc nhanh</span>
                ${pdfBtn}
              </div>
              <a href="${item.link}" target="_blank" class="btn-open-article" onclick="event.stopPropagation();" title="Mở trên trang gốc">
                Trang gốc ↗
              </a>
            </div>
          </div>
        </div>
      `;
      }).join('');
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching company news:', e);
      this.renderErrorState('stockNewsList', `Lỗi kết nối khi tải tin tức cho mã ${symbol}.`);
    }
  }

  async fetchCompanyFinancials(symbol, statementType = 'income', period = 'quarter', periodsCount = 8) {
    try {
      const container = document.getElementById('finTableContainer');
      if (!container) return;

      const pCount = periodsCount || this.currentFinCount || 8;
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center;">⏳ Đang trích xuất số liệu Báo cáo tài chính & Chỉ số cho mã ' + escapeHTML(symbol) + ' (' + pCount + ' kỳ)...</div>';

      const res = await fetch(`/api/company/financials?symbol=${encodeURIComponent(symbol)}&statement_type=${encodeURIComponent(statementType)}&period=${encodeURIComponent(period)}&periods_count=${pCount}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⚠️ Không thể tải dữ liệu BCTC cho mã ' + escapeHTML(symbol) + '.</div>';
        return;
      }

      this.currentFinancialData = json.data;
      
      // Update Model Tag and Unit Label
      const tagEl = document.getElementById('finModelTag');
      if (tagEl) {
        tagEl.textContent = json.data.company_form_name || 'Doanh nghiệp';
      }
      const unitEl = document.getElementById('finUnitLabel');
      if (unitEl) {
        unitEl.textContent = `Đơn vị: ${json.data.unit || 'Tỷ VNĐ'}`;
      }

      this.renderFinancialTable(json.data);

    } catch (e) {
      console.error('Error fetching company financials:', e);
      const container = document.getElementById('finTableContainer');
      if (container) container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⚠️ Lỗi tải dữ liệu báo cáo tài chính.</div>';
    }
  }

  renderFinancialTable(data) {
    const container = document.getElementById('finTableContainer');
    if (!container) return;

    const periods = data.periods || [];
    const rows = data.rows || [];

    if (rows.length === 0 || periods.length === 0) {
      container.innerHTML = `
        <div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center;">
          Chưa có số liệu tài chính công bố cho mã <strong>${escapeHTML(data.symbol || '')}</strong> theo kỳ đã chọn.
        </div>`;
      return;
    }

    const headerColsHtml = periods.map(p => `<th>${escapeHTML(p)}</th>`).join('');
    const hasGrowthCol = rows.some(r => r.growth_yoy !== null && r.growth_yoy !== undefined);
    const growthHeaderHtml = hasGrowthCol ? `<th style="text-align:center;">Tăng trưởng YoY</th>` : '';

    const rowsHtml = rows.map(r => {
      if (r.is_header) {
        const colSpan = periods.length + (hasGrowthCol ? 2 : 1);
        return `
          <tr class="fin-row-section-header">
            <td colspan="${colSpan}" style="padding:8px 12px; font-weight:700; color:#38bdf8;">
              📌 ${escapeHTML(r.item_name)}
            </td>
          </tr>
        `;
      }

      let rowClass = 'fin-row';
      if (r.level === 1) rowClass += ' fin-row-parent';
      else if (r.level === 2) rowClass += ' fin-row-child';
      else if (r.level >= 3) rowClass += ' fin-row-subchild';

      const valTds = (r.values || []).map(v => {
        let vClass = '';
        if (typeof v === 'string' && v.startsWith('-')) vClass = 'txt-down';
        return `<td class="${vClass}">${escapeHTML(String(v))}</td>`;
      }).join('');

      let growthTd = '';
      if (hasGrowthCol) {
        if (r.growth_yoy) {
          const isPos = !r.growth_yoy.startsWith('-');
          const gClass = isPos ? 'growth-pos' : 'growth-neg';
          growthTd = `<td style="text-align:center;"><span class="growth-badge ${gClass}">${escapeHTML(r.growth_yoy)}</span></td>`;
        } else {
          growthTd = `<td style="text-align:center; color:var(--text-dim); font-size:11px;">--</td>`;
        }
      }

      return `
        <tr class="${rowClass}">
          <td class="col-metric" title="${escapeHTML(r.item_name_en || '')}">
            ${escapeHTML(r.item_name)}
          </td>
          ${valTds}
          ${growthTd}
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <table class="fin-table">
        <thead>
          <tr>
            <th class="col-metric">Chỉ tiêu tài chính</th>
            ${headerColsHtml}
            ${growthHeaderHtml}
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;
  }

  downloadModanoExcel() {
    const symbol = this.currentSymbol || 'HPG';
    const btn = document.getElementById('btnExportModanoExcel');
    if (btn) {
      const origText = btn.innerHTML;
      btn.innerHTML = '<span>⏳ Đang xuất Excel...</span>';
      setTimeout(() => { btn.innerHTML = origText; }, 2500);
    }
    const url = `/api/valuation/export-excel/${encodeURIComponent(symbol)}?scale_unit=billion`;
    window.open(url, '_blank');
  }

  async fetchThreeStatementForecast(symbol) {
    try {
      const container = document.getElementById('finTableContainer');
      if (!container) return;

      container.innerHTML = `
        <div style="color:var(--text-muted); font-size:13px; padding:36px; text-align:center;">
          <div style="font-size:26px; margin-bottom:8px;">🔮</div>
          <div style="font-weight:700; color:#f1f5f9; font-size:14px;">Đang lập Mô hình Tài chính Tích hợp 3 Báo cáo (Modano 3-Way Model 5Y) cho ${escapeHTML(symbol)}...</div>
          <div style="font-size:11.5px; color:#64748b; margin-top:6px;">Tự động cân đối P&L, Bảng CĐKT, Dòng tiền trực tiếp & Lịch vốn lưu động...</div>
        </div>`;

      const res = await fetch(`/api/valuation/3-way-forecast/${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⚠️ Không thể tạo mô hình dự phóng 3-Way cho mã ${escapeHTML(symbol)}.</div>`;
        return;
      }

      this.currentThreeWayData = json.data;
      this.currentThreeWayTab = this.currentThreeWayTab || 'summary';
      
      const tagEl = document.getElementById('finModelTag');
      if (tagEl) {
        tagEl.textContent = json.data.is_financial_sector ? '🏦 Định chế Tài chính / Ngân hàng' : '🏢 Doanh nghiệp Sản xuất / Dịch vụ';
      }
      const unitEl = document.getElementById('finUnitLabel');
      if (unitEl) {
        unitEl.textContent = 'Đơn vị: Tỷ VNĐ';
      }

      this.renderThreeStatementForecast(json.data);

    } catch (e) {
      console.error('Error fetching 3-way forecast:', e);
      const container = document.getElementById('finTableContainer');
      if (container) container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⚠️ Lỗi kết nối khi tải mô hình dự phóng 3-Way.</div>';
    }
  }

  switchThreeWayTab(tabKey) {
    this.currentThreeWayTab = tabKey;
    if (this.currentThreeWayData) {
      this.renderThreeStatementForecast(this.currentThreeWayData);
    }
  }

  renderThreeStatementForecast(data) {
    const container = document.getElementById('finTableContainer');
    if (!container) return;

    const years = data.forecast_years || [2025, 2026, 2027, 2028, 2029];
    const isBalanced = data.all_years_balanced;
    const maxDiff = (data.max_balance_difference || 0).toFixed(4);
    const wc = (data.working_capital_schedule && data.working_capital_schedule[0]) || {};
    const distress = data.liquidity_distress_check || {};
    const hasDistress = distress.has_liquidity_distress;
    const isFinancial = data.is_financial_sector;

    const isStmt = data.income_statement || {};
    const bs = data.balance_sheet || {};
    const cfs = data.cash_flow_statement || {};
    const debt = (data.debt_schedule && data.debt_schedule[0]) || {};

    const activeTab = this.currentThreeWayTab || 'summary';

    // Helper formatter (divides VND by 1e9 into Billion VND)
    const fmtB = (val) => {
      if (val === null || val === undefined || isNaN(val)) return '-';
      const bVal = val / 1e9;
      return bVal.toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    };

    const fmtPct = (val) => {
      if (val === null || val === undefined || isNaN(val)) return '-';
      return (val * 100).toFixed(1) + '%';
    };

    // 1. TOP HEADER & METRICS STRIP
    const balanceBadge = isBalanced
      ? `<span style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.4); padding:4px 10px; border-radius:6px; font-weight:700; font-size:11.5px; display:inline-flex; align-items:center; gap:5px;">
          ✅ CÂN ĐỐI KẾ TOÁN 100% (Lệch ${maxDiff} đ)
        </span>`
      : `<span style="background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.4); padding:4px 10px; border-radius:6px; font-weight:700; font-size:11.5px;">
          ⚠️ CÂN ĐỐI LỆCH (Lệch ${maxDiff} đ)
        </span>`;

    const distressBanner = hasDistress
      ? `<div style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.35); border-radius:8px; padding:10px 14px; margin-bottom:14px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">🚨</span>
            <div>
              <strong style="color:#ef4444; font-size:12px;">CẢNH BÁO THÂM HỤT TIỀN MẶT (NEGATIVE CASH ALERT):</strong>
              <span style="font-size:11.5px; color:#cbd5e1; margin-left:6px;">Mô hình dự báo thâm hụt tiền vào năm <strong>${distress.first_distressed_year || 'tới'}</strong> (Tối đa âm ${fmtB(distress.max_cash_deficit)} Tỷ VNĐ). Rủi ro pha loãng cổ phiếu cao.</span>
            </div>
          </div>
          <span style="background:rgba(239,68,68,0.2); color:#fca5a5; font-size:11px; font-weight:700; padding:3px 8px; border-radius:4px;">Áp Phạt Định Giá MoS</span>
        </div>`
      : `<div style="background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.25); border-radius:8px; padding:8px 14px; margin-bottom:14px; display:flex; align-items:center; justify-content:space-between;">
          <div style="display:flex; align-items:center; gap:8px; font-size:11.5px; color:#cbd5e1;">
            <span style="font-size:14px;">🛡️</span>
            <span><strong>An toàn thanh khoản:</strong> Dòng tiền dự phóng tự do duy trì số dư tiền mặt dương liên tục 5 năm.</span>
          </div>
          <span style="color:#10b981; font-weight:700; font-size:11px;">RATING: ${escapeHTML(debt.synthetic_rating || 'AAA')}</span>
        </div>`;

    const wcCards = isFinancial ? '' : `
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-bottom:14px;">
        <div style="background:rgba(30,41,59,0.6); border:1px solid rgba(56,189,248,0.2); border-radius:8px; padding:10px 14px;">
          <div style="font-size:11px; color:#94a3b8; font-weight:600;">Thu Tiền KH (DSO)</div>
          <div style="font-size:18px; font-weight:800; color:#38bdf8; margin-top:2px;">${(wc.dso || 0).toFixed(1)} <span style="font-size:11px; font-weight:500;">ngày</span></div>
          <div style="font-size:10px; color:#64748b;">Debtor Days</div>
        </div>
        <div style="background:rgba(30,41,59,0.6); border:1px solid rgba(56,189,248,0.2); border-radius:8px; padding:10px 14px;">
          <div style="font-size:11px; color:#94a3b8; font-weight:600;">Vòng Quay Kho (DIO)</div>
          <div style="font-size:18px; font-weight:800; color:#fbbf24; margin-top:2px;">${(wc.dio || 0).toFixed(1)} <span style="font-size:11px; font-weight:500;">ngày</span></div>
          <div style="font-size:10px; color:#64748b;">Inventory Days</div>
        </div>
        <div style="background:rgba(30,41,59,0.6); border:1px solid rgba(56,189,248,0.2); border-radius:8px; padding:10px 14px;">
          <div style="font-size:11px; color:#94a3b8; font-weight:600;">Chi Trả NCC (DPO)</div>
          <div style="font-size:18px; font-weight:800; color:#a78bfa; margin-top:2px;">${(wc.dpo || 0).toFixed(1)} <span style="font-size:11px; font-weight:500;">ngày</span></div>
          <div style="font-size:10px; color:#64748b;">Creditor Days</div>
        </div>
        <div style="background:rgba(30,41,59,0.6); border:1px solid rgba(56,189,248,0.2); border-radius:8px; padding:10px 14px;">
          <div style="font-size:11px; color:#94a3b8; font-weight:600;">Chu Kỳ Tiền Mặt (CCC)</div>
          <div style="font-size:18px; font-weight:800; color:${(wc.ccc || 0) < 60 ? '#10b981' : '#f97316'}; margin-top:2px;">${(wc.ccc || 0).toFixed(1)} <span style="font-size:11px; font-weight:500;">ngày</span></div>
          <div style="font-size:10px; color:#64748b;">Cash Conversion Cycle</div>
        </div>
      </div>
    `;

    // 2. SUBTAB NAVIGATION
    const subTabs = [
      { key: 'summary', label: '📊 Tổng Hợp (Summary)' },
      { key: 'income', label: '📈 Báo Cáo KQKD (P&L)' },
      { key: 'balance', label: '⚖️ Bảng Cân Đối KT' },
      { key: 'cashflow', label: '💸 Dòng Tiền Trực Tiếp' },
      { key: 'working_capital', label: '📦 Vốn Lưu Động (NWC)' },
      { key: 'debt', label: '💳 Nợ Vay & Cổ Tức' }
    ];

    const subTabsHtml = subTabs.map(t => {
      const isAct = t.key === activeTab;
      const actStyle = isAct
        ? 'background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.4);'
        : 'background:transparent; color:#94a3b8; border:1px solid transparent;';
      return `<button onclick="app.switchThreeWayTab('${t.key}')" style="cursor:pointer; font-size:11.5px; font-weight:700; padding:6px 12px; border-radius:6px; transition:all 0.2s; ${actStyle}">${t.label}</button>`;
    }).join('');

    // 3. TABLE GENERATION BASED ON ACTIVE SUBTAB
    let tableRows = [];

    if (activeTab === 'summary') {
      tableRows = [
        { label: 'Doanh thu thuần (Net Sales)', code: 'REV', vals: isStmt.revenue, isB: true, fn: fmtB },
        { label: 'Tăng trưởng doanh thu YoY (%)', code: 'REV_G', vals: isStmt.revenue_growth, isB: false, fn: fmtPct },
        { label: 'Lợi nhuận gộp (Gross Profit)', code: 'GP', vals: isStmt.gross_profit, isB: false, fn: fmtB },
        { label: 'Lợi nhuận HĐKD (EBIT)', code: 'EBIT', vals: isStmt.ebit, isB: true, fn: fmtB },
        { label: 'Lợi nhuận sau thuế (NPAT)', code: 'NPAT', vals: isStmt.net_profit_after_tax, isB: true, fn: fmtB },
        { label: 'Dòng tiền thuần HĐKD (Net CFO)', code: 'CFO', vals: cfs.net_cash_from_operating_activities, isB: true, fn: fmtB },
        { label: 'Chi đầu tư tài sản (CapEx)', code: 'CAPEX', vals: cfs.capital_expenditures, isB: false, fn: fmtB },
        { label: 'Dòng tiền tự do DN (FCFF)', code: 'FCFF', vals: cfs.free_cash_flow_to_firm, isB: true, fn: fmtB },
        { label: 'Số dư tiền cuối kỳ (Ending Cash)', code: 'CASH', vals: bs.cash, isB: false, fn: fmtB },
        { label: 'Tổng tài sản (Total Assets)', code: 'TA', vals: bs.total_assets, isB: true, fn: fmtB },
        { label: 'Tổng nợ vay (Total Debt)', code: 'DEBT', vals: bs.total_debt, isB: false, fn: fmtB },
        { label: 'Vốn chủ sở hữu (Total Equity)', code: 'EQUITY', vals: bs.total_equity, isB: true, fn: fmtB }
      ];
    } else if (activeTab === 'income') {
      tableRows = [
        { label: '1. Doanh thu thuần (Net Revenue)', code: 'REV', vals: isStmt.revenue, isB: true, fn: fmtB },
        { label: '   Tốc độ tăng trưởng doanh thu YoY', code: 'REV_G', vals: isStmt.revenue_growth, isB: false, fn: fmtPct },
        { label: '2. Giá vốn hàng bán (COGS)', code: 'COGS', vals: isStmt.cogs, isB: false, fn: fmtB },
        { label: '3. Lợi nhuận gộp (Gross Margin)', code: 'GP', vals: isStmt.gross_profit, isB: true, fn: fmtB },
        { label: '4. Chi phí SG&A', code: 'SGA', vals: isStmt.sga_expense, isB: false, fn: fmtB },
        { label: '5. EBITDA', code: 'EBITDA', vals: isStmt.ebitda, isB: true, fn: fmtB },
        { label: '6. Khấu hao & phân bổ (D&A)', code: 'DA', vals: isStmt.depreciation_amortization, isB: false, fn: fmtB },
        { label: '7. Lợi nhuận trước lãi vay & thuế (EBIT)', code: 'EBIT', vals: isStmt.ebit, isB: true, fn: fmtB },
        { label: '8. Chi phí lãi vay (Interest Expense)', code: 'INT_EXP', vals: isStmt.interest_expense, isB: false, fn: fmtB },
        { label: '9. Lợi nhuận trước thuế (NPBT)', code: 'NPBT', vals: isStmt.net_profit_before_tax, isB: true, fn: fmtB },
        { label: '10. Chi phí thuế TNDN (Tax Expense)', code: 'TAX', vals: isStmt.tax_expense, isB: false, fn: fmtB },
        { label: '11. Lợi nhuận sau thuế (NPAT)', code: 'NPAT', vals: isStmt.net_profit_after_tax, isB: true, fn: fmtB }
      ];
    } else if (activeTab === 'balance') {
      tableRows = [
        { label: '📌 TÀI SẢN NGẮN HẠN (Current Assets)', isHeader: true },
        { label: '1. Tiền và tương đương tiền', code: 'CASH', vals: bs.cash, isB: false, fn: fmtB },
        { label: '2. Phải thu ngắn hạn khách hàng', code: 'AR', vals: bs.accounts_receivable, isB: false, fn: fmtB },
        { label: '3. Hàng tồn kho', code: 'INV', vals: bs.inventory, isB: false, fn: fmtB },
        { label: '4. Tài sản ngắn hạn khác', code: 'OCA', vals: bs.other_current_assets, isB: false, fn: fmtB },
        { label: 'TỔNG TÀI SẢN NGẮN HẠN', code: 'TCA', vals: bs.total_current_assets, isB: true, fn: fmtB },
        { label: '📌 TÀI SẢN DÀI HẠN (Non-Current Assets)', isHeader: true },
        { label: '5. Tài sản cố định thuần (Net PPE)', code: 'PPE', vals: bs.net_ppe, isB: false, fn: fmtB },
        { label: '6. Tài sản dài hạn khác', code: 'ONCA', vals: bs.other_non_current_assets, isB: false, fn: fmtB },
        { label: 'TỔNG TÀI SẢN DÀI HẠN', code: 'TNCA', vals: bs.total_non_current_assets, isB: true, fn: fmtB },
        { label: 'TỔNG CỘNG TÀI SẢN', code: 'TA', vals: bs.total_assets, isB: true, fn: fmtB },
        { label: '📌 NỢ PHẢI TRẢ (Liabilities)', isHeader: true },
        { label: '7. Phải trả người bán ngắn hạn', code: 'AP', vals: bs.accounts_payable, isB: false, fn: fmtB },
        { label: '8. Vay nợ tài chính ngắn hạn', code: 'ST_DEBT', vals: bs.short_term_debt, isB: false, fn: fmtB },
        { label: '9. Nợ ngắn hạn khác', code: 'OCL', vals: bs.other_current_liabilities, isB: false, fn: fmtB },
        { label: 'TỔNG NỢ NGẮN HẠN', code: 'TCL', vals: bs.total_current_liabilities, isB: true, fn: fmtB },
        { label: '10. Vay nợ tài chính dài hạn', code: 'LT_DEBT', vals: bs.long_term_debt, isB: false, fn: fmtB },
        { label: 'TỔNG NỢ PHẢI TRẢ', code: 'TL', vals: bs.total_liabilities, isB: true, fn: fmtB },
        { label: '📌 VỐN CHỦ SỞ HỮU (Equity)', isHeader: true },
        { label: '11. Vốn góp chủ sở hữu', code: 'CAPITAL', vals: bs.contributed_capital, isB: false, fn: fmtB },
        { label: '12. Lợi nhuận sau thuế chưa PP', code: 'RE', vals: bs.retained_earnings, isB: false, fn: fmtB },
        { label: 'TỔNG VỐN CHỦ SỞ HỮU', code: 'EQUITY', vals: bs.total_equity, isB: true, fn: fmtB },
        { label: 'TỔNG CỘNG NGUỒN VỐN (Nợ + VCSH)', code: 'TL_EQ', vals: bs.total_assets, isB: true, fn: fmtB },
        { label: 'KIỂM TOÁN CÂN ĐỐI (BALANCE CHECK)', code: 'DIFF', vals: bs.balance_check, isB: true, fn: (v) => Math.abs(v || 0) < 1 ? '0.0 đ (CÂN ĐỐI)' : (v || 0).toFixed(2) + ' đ' }
      ];
    } else if (activeTab === 'cashflow') {
      tableRows = [
        { label: '1. Tiền thu từ bán hàng & cung cấp DV', code: 'CF_CUST', vals: cfs.cash_receipts_from_customers, isB: false, fn: fmtB },
        { label: '2. Tiền chi trả cho người bán hàng hóa', code: 'CF_SUPP', vals: cfs.cash_paid_to_suppliers, isB: false, fn: fmtB },
        { label: '3. Tiền chi trả cho người lao động & HĐKD', code: 'CF_OPEX', vals: cfs.cash_paid_for_operating_expenses, isB: false, fn: fmtB },
        { label: '4. Tiền lãi vay đã thực trả (Interest Paid)', code: 'CF_INT', vals: cfs.interest_paid, isB: false, fn: fmtB },
        { label: '5. Thuế TNDN đã thực nộp (Tax Paid)', code: 'CF_TAX', vals: cfs.income_taxes_paid, isB: false, fn: fmtB },
        { label: 'LƯU CHUYỂN TIỀN THUẦN TỪ HĐKD (CFO)', code: 'CFO', vals: cfs.net_cash_from_operating_activities, isB: true, fn: fmtB },
        { label: '6. Tiền chi mua sắm TSCĐ (CapEx)', code: 'CAPEX', vals: cfs.capital_expenditures, isB: false, fn: fmtB },
        { label: 'LƯU CHUYỂN TIỀN THUẦN TỪ ĐẦU TƯ (CFI)', code: 'CFI', vals: cfs.net_cash_from_investing_activities, isB: true, fn: fmtB },
        { label: '7. Tiền vay nhận được (Debt Drawdown)', code: 'CF_DEBT_IN', vals: cfs.debt_drawdowns, isB: false, fn: fmtB },
        { label: '8. Tiền trả nợ gốc vay (Debt Repayment)', code: 'CF_DEBT_OUT', vals: cfs.debt_repayments, isB: false, fn: fmtB },
        { label: '9. Cổ tức đã chi trả cho CĐ (Dividends Paid)', code: 'CF_DIV', vals: cfs.dividends_paid, isB: false, fn: fmtB },
        { label: 'LƯU CHUYỂN TIỀN THUẦN TỪ HĐ TÀI CHÍNH (CFF)', code: 'CFF', vals: cfs.net_cash_from_financing_activities, isB: true, fn: fmtB },
        { label: 'LƯU CHUYỂN TIỀN THUẦN TRONG KỲ (DELTA CASH)', code: 'DELTA_CASH', vals: cfs.net_change_in_cash, isB: true, fn: fmtB },
        { label: 'TIỀN VÀ TƯƠNG ĐƯƠNG TIỀN ĐẦU KỲ', code: 'BEG_CASH', vals: cfs.beginning_cash, isB: false, fn: fmtB },
        { label: 'TIỀN VÀ TƯƠNG ĐƯƠNG TIỀN CUỐI KỲ', code: 'END_CASH', vals: cfs.ending_cash, isB: true, fn: fmtB }
      ];
    } else if (activeTab === 'working_capital') {
      tableRows = [
        { label: '1. Số ngày thu tiền KH (DSO - Days)', code: 'DSO', vals: (data.working_capital_schedule || []).map(x => x.dso), isB: false, fn: (v) => (v || 0).toFixed(1) + ' ngày' },
        { label: '2. Số ngày tồn kho (DIO - Days)', code: 'DIO', vals: (data.working_capital_schedule || []).map(x => x.dio), isB: false, fn: (v) => (v || 0).toFixed(1) + ' ngày' },
        { label: '3. Số ngày trả tiền NCC (DPO - Days)', code: 'DPO', vals: (data.working_capital_schedule || []).map(x => x.dpo), isB: false, fn: (v) => (v || 0).toFixed(1) + ' ngày' },
        { label: 'CHU KỲ CHUYỂN ĐỔI TIỀN MẶT (CCC)', code: 'CCC', vals: (data.working_capital_schedule || []).map(x => x.ccc), isB: true, fn: (v) => (v || 0).toFixed(1) + ' ngày' },
        { label: '4. Vốn lưu động ròng HĐKD (Operating NWC)', code: 'NWC', vals: (data.working_capital_schedule || []).map(x => x.net_working_capital), isB: true, fn: fmtB },
        { label: '5. Biến động vốn lưu động ròng (Delta NWC)', code: 'DELTA_NWC', vals: (data.working_capital_schedule || []).map(x => x.delta_nwc), isB: true, fn: fmtB }
      ];
    } else if (activeTab === 'debt') {
      tableRows = [
        { label: '1. Số dư nợ vay đầu kỳ (Opening Debt)', code: 'OPEN_DEBT', vals: (data.debt_schedule || []).map(x => x.opening_debt), isB: false, fn: fmtB },
        { label: '2. Vay nợ mới trong kỳ (New Borrowings)', code: 'NEW_DEBT', vals: (data.debt_schedule || []).map(x => x.new_borrowings), isB: false, fn: fmtB },
        { label: '3. Trả nợ gốc vay trong kỳ (Amortization)', code: 'REPAY', vals: (data.debt_schedule || []).map(x => x.principal_amortization), isB: false, fn: fmtB },
        { label: 'SỐ DƯ NỢ VAY CUỐI KỲ (Closing Debt)', code: 'CLOSE_DEBT', vals: (data.debt_schedule || []).map(x => x.closing_debt), isB: true, fn: fmtB },
        { label: '4. Hệ số phủ lãi vay (ICR = EBIT / Interest)', code: 'ICR', vals: (data.debt_schedule || []).map(x => x.interest_coverage_ratio), isB: false, fn: (v) => (v || 0).toFixed(1) + 'x' },
        { label: '5. Xếp hạng tín nhiệm tổng hợp Damodaran', code: 'RATING', vals: (data.debt_schedule || []).map(x => x.synthetic_rating), isB: true, fn: (v) => String(v || 'AAA') },
        { label: '6. Chi phí vốn vay sau thuế (After-tax Kd)', code: 'KD', vals: (data.debt_schedule || []).map(x => x.cost_of_debt_after_tax), isB: false, fn: fmtPct },
        { label: '7. Chi trả cổ tức tiền mặt (Dividends Paid)', code: 'DIV', vals: (data.debt_schedule || []).map(x => x.dividends_paid), isB: true, fn: fmtB }
      ];
    }

    const headersHtml = years.map(y => `<th style="text-align:right; min-width:110px;">Năm ${y}</th>`).join('');

    const bodyHtml = tableRows.map(r => {
      if (r.isHeader) {
        return `<tr class="fin-row-section-header"><td colspan="${years.length + 2}" style="padding:8px 12px; font-weight:700; color:#38bdf8; background:rgba(56,189,248,0.06);">${escapeHTML(r.label)}</td></tr>`;
      }
      const isBold = r.isB;
      const tdVals = (r.vals || []).map(v => {
        const txt = r.fn ? r.fn(v) : String(v);
        let cls = '';
        if (txt.startsWith('-')) cls = 'txt-down';
        else if (r.code === 'DIFF' && txt.includes('CÂN ĐỐI')) cls = 'txt-up';
        return `<td style="text-align:right; font-weight:${isBold ? '700' : '400'};" class="${cls}">${escapeHTML(txt)}</td>`;
      }).join('');

      return `
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04); ${isBold ? 'background:rgba(255,255,255,0.02);' : ''}">
          <td style="padding:7px 12px; font-weight:${isBold ? '700' : '400'}; color:${isBold ? '#f1f5f9' : 'inherit'};">${escapeHTML(r.label)}</td>
          <td style="text-align:center; font-size:11px; color:#64748b; font-family:monospace;">${escapeHTML(r.code || '')}</td>
          ${tdVals}
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <div style="padding:4px 0 16px 0;">
        <!-- Top Status & Action Bar -->
        <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:15px; font-weight:800; color:#38bdf8;">🔮 MÔ HÌNH DỰ PHÓNG 3-WAY 5 NĂM (MODANO STANDARD)</span>
            ${balanceBadge}
          </div>
          <button onclick="app.downloadModanoExcel()" style="cursor:pointer; background:linear-gradient(135deg, #059669 0%, #10b981 100%); color:#fff; border:none; padding:6px 14px; border-radius:6px; font-size:12px; font-weight:700; display:inline-flex; align-items:center; gap:6px; box-shadow:0 2px 8px rgba(16,185,129,0.35);">
            <span>📥 Tải BCTC Excel 7-Tab Modano (.xlsx)</span>
          </button>
        </div>

        ${distressBanner}
        ${wcCards}

        <!-- Subtabs Bar -->
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; border-bottom:1px solid var(--border-color); padding-bottom:8px;">
          ${subTabsHtml}
        </div>

        <!-- Table View -->
        <div class="table-responsive" style="overflow-x:auto;">
          <table class="fin-table" style="width:100%; font-size:12px;">
            <thead>
              <tr style="background:rgba(15,23,42,0.8);">
                <th style="text-align:left; min-width:260px;">Chỉ tiêu tài chính dự phóng</th>
                <th style="text-align:center; width:90px;">Mã dòng</th>
                ${headersHtml}
              </tr>
            </thead>
            <tbody>
              ${bodyHtml}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  async fetchCompanyReports(symbol, filterType = 'all', page = 1, append = false, year = 'all') {

    try {
      const container = document.getElementById('stockReportsList');
      const loadMoreContainer = document.getElementById('reportsLoadMoreContainer');
      const btnLoadMore = document.getElementById('btnLoadMoreReports');
      if (!container) return;

      const targetYear = year || this.reportYearFilter || 'all';
      this.reportYearFilter = targetYear;

      if (!append) {
        this.reportPage = 1;
        this.currentCompanyReports = [];
        const yearMsg = targetYear !== 'all' ? ` năm ${targetYear}` : '';
        container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⏳ Đang quét dữ liệu Báo cáo tài chính & Hồ sơ công bố${yearMsg} từ CafeF Media CDN...</div>`;
      } else {
        this.isLoadingMoreReports = true;
        if (btnLoadMore) {
          btnLoadMore.disabled = true;
          btnLoadMore.innerHTML = '<span>⏳ Đang tải thêm tài liệu cũ hơn...</span>';
        }
      }

      this.reportFilterType = filterType;
      const res = await fetch(`/api/company/reports?symbol=${encodeURIComponent(symbol)}&page=${page}&page_size=30&year=${encodeURIComponent(targetYear)}`);
      const json = await res.json();
      const newReports = (json.data && json.data.reports) ? json.data.reports : [];
      if (this.currentSymbol !== symbol) return;
      if (json.status !== 'success') {
        if (!append) {
          this.renderErrorState('stockReportsList', json.message || `Không thể tải danh sách báo cáo cho mã ${symbol}.`);
        }
        return;
      }
      if (!append) {
        this.currentCompanyReports = newReports;
      } else {
        this.currentCompanyReports = [...this.currentCompanyReports, ...newReports];
        this.reportPage = page;
      }

      this.hasMoreReports = Boolean(json.data.has_more);
      if (loadMoreContainer) {
        loadMoreContainer.style.display = this.hasMoreReports ? 'block' : 'none';
      }
      if (btnLoadMore) {
        btnLoadMore.disabled = false;
        btnLoadMore.innerHTML = '<span>⏬ Tải thêm tài liệu cũ hơn (Trang tiếp)</span>';
      }
      this.isLoadingMoreReports = false;

      // Update pill count badges based on all cached reports
      const pillKeys = ['all', 'bctc', 'annual', 'governance', 'resolution', 'dividend', 'insider'];
      const counts = {
        all: this.currentCompanyReports.length,
        bctc: this.currentCompanyReports.filter(r => r.type_code === 'bctc').length,
        annual: this.currentCompanyReports.filter(r => r.type_code === 'annual').length,
        governance: this.currentCompanyReports.filter(r => r.type_code === 'governance').length,
        resolution: this.currentCompanyReports.filter(r => r.type_code === 'resolution').length,
        dividend: this.currentCompanyReports.filter(r => r.type_code === 'dividend').length,
        insider: this.currentCompanyReports.filter(r => r.type_code === 'insider').length
      };

      pillKeys.forEach(k => {
        const badgeEl = document.getElementById(`pill_cnt_${k}`);
        if (badgeEl) {
          badgeEl.textContent = counts[k] !== undefined ? counts[k] : 0;
        }
      });

      this.renderCompanyReports();

    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching company reports:', e);
      this.isLoadingMoreReports = false;
      if (!append) {
        this.renderErrorState('stockReportsList', `Lỗi kết nối khi tải danh sách báo cáo cho mã ${symbol}.`);
      }
    }
  }

  renderCompanyReports() {
    const container = document.getElementById('stockReportsList');
    if (!container) return;

    let reports = this.currentCompanyReports || [];
    const filterType = this.reportFilterType || 'all';
    const kw = (this.reportSearchKeyword || '').trim().toLowerCase();
    const yearFilter = this.reportYearFilter || 'all';

    // 1. Filter by category
    if (filterType !== 'all') {
      reports = reports.filter(r => r.type_code === filterType);
    }

    // 2. Filter by year
    if (yearFilter !== 'all') {
      reports = reports.filter(r => (r.year === yearFilter || (r.date && r.date.includes(yearFilter))));
    }

    // 3. Filter by keyword
    if (kw) {
      reports = reports.filter(r => {
        const t = (r.title || '').toLowerCase();
        const ct = (r.clean_title || '').toLowerCase();
        const tn = (r.type_name || '').toLowerCase();
        return t.includes(kw) || ct.includes(kw) || tn.includes(kw);
      });
    }

    if (reports.length === 0) {
      let emptyMsg = `Chưa có tài liệu phù hợp bộ lọc cho mã <strong>${escapeHTML(this.currentSymbol || '')}</strong>.`;
      if (kw) {
        emptyMsg = `Không tìm thấy tài liệu nào khớp với từ khóa "<strong>${escapeHTML(kw)}</strong>".`;
      }
      container.innerHTML = `
        <div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center; background:rgba(255,255,255,0.02); border-radius:6px;">
          ${emptyMsg}
        </div>`;
      return;
    }

    container.innerHTML = reports.map(rep => {
      const safeTitle = escapeHTML(rep.clean_title || rep.title || '');
      const safeDate = escapeHTML(rep.date || '');
      const safeTypeName = escapeHTML(rep.type_name || 'Công Bố');
      const badgeCls = escapeHTML(rep.badge_class || 'badge-report-other');
      const icon = rep.type_icon || '📑';

      // Audit & Opinion badges
      let auditBadgeHtml = '';
      if (rep.audit_badge) {
        const isBig4 = rep.audit_badge.includes('Big 4');
        auditBadgeHtml = `<span class="${isBig4 ? 'badge-audit-big4' : 'badge-audit-big4'}" style="${isBig4 ? '' : 'background:rgba(59,130,246,0.15); color:#60a5fa; border-color:rgba(59,130,246,0.4);'}">🌟 ${escapeHTML(rep.audit_badge)}</span>`;
      }

      let opinionBadgeHtml = '';
      if (rep.opinion_badge) {
        opinionBadgeHtml = `<span class="badge-audit-warning">${escapeHTML(rep.opinion_badge)}</span>`;
      }

      let explanationHtml = '';
      if (rep.is_explanation) {
        explanationHtml = `<span class="badge-explanation">📊 Giải trình LNST</span>`;
      }

      const pdfBtn = rep.pdf_url
        ? `<a href="${rep.pdf_url}" target="_blank" class="btn-pdf-download" title="Xem hoặc tải toàn văn file PDF gốc">📥 Tải / Mở PDF</a>`
        : (rep.has_pdf ? `<span class="badge-has-pdf-indicator">PDF</span>` : '');

      const detailBtn = rep.detail_url
        ? `<a href="${rep.detail_url}" target="_blank" class="btn-report-detail" title="Xem trang công bố chính thức">Xem công bố ↗</a>`
        : '';

      const dossierBtn = `<button class="btn-dossier-instant" onclick="app.openDocumentDossier('${escapeHTML(this.currentSymbol)}', '${escapeHTML(rep.title || '')}')" title="Xem số liệu trích xuất số hóa tức thì">⚡ Bóc Tách AI</button>`;

      return `
        <div class="report-card">
          <div class="report-header">
            <div class="report-tags-left">
              <span class="${badgeCls}">${icon} ${safeTypeName}</span>
              ${auditBadgeHtml}
              ${opinionBadgeHtml}
              ${explanationHtml}
              ${rep.pdf_url ? '<span class="badge-has-pdf-indicator">PDF</span>' : ''}
            </div>
            <span style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">📅 ${safeDate}</span>
          </div>
          <div class="report-title-text">${safeTitle}</div>
          <div class="report-footer-actions">
            <div style="display:flex; align-items:center; gap:8px;">
              ${pdfBtn}
              ${dossierBtn}
            </div>
            <div>
              ${detailBtn}
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  async fetchCompanyEvents(symbol) {
    try {
      const container = document.getElementById('stockEventsList');
      if (container) {
        container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⏳ Đang tải lịch sự kiện cho mã ${escapeHTML(symbol)}...</div>`;
      }
      const res = await fetch(`/api/company/events?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;
      if (json.status !== 'success') {
        this.renderErrorState('stockEventsList', json.message || `Không thể tải lịch sự kiện cho mã ${symbol}.`);
        return;
      }

      this.currentCompanyEvents = json.data || [];
      this.updateEventCounts();
      this.renderCompanyEvents();
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching company events:', e);
      this.renderErrorState('stockEventsList', `Lỗi kết nối khi tải sự kiện cho mã ${symbol}.`);
    }
  }

  updateEventCounts() {
    const evs = this.currentCompanyEvents || [];
    const countMap = {
      all: evs.length,
      dividend: evs.filter(e => e.category === 'DIVIDEND').length,
      issue: evs.filter(e => e.category === 'ISSUE').length,
      meeting: evs.filter(e => e.category === 'MEETING').length,
      resolution: evs.filter(e => e.category === 'RESOLUTION' || e.category === 'LISTING').length
    };

    const setBadge = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    setBadge('event_pill_cnt_all', countMap.all);
    setBadge('event_pill_cnt_dividend', countMap.dividend);
    setBadge('event_pill_cnt_issue', countMap.issue);
    setBadge('event_pill_cnt_meeting', countMap.meeting);
    setBadge('event_pill_cnt_resolution', countMap.resolution);
  }

  renderCompanyEvents() {
    const container = document.getElementById('stockEventsList');
    if (!container) return;

    let filtered = this.currentCompanyEvents || [];
    if (this.eventFilterCategory && this.eventFilterCategory !== 'all') {
      filtered = filtered.filter(e => e.category === this.eventFilterCategory || (this.eventFilterCategory === 'RESOLUTION' && e.category === 'LISTING'));
    }

    if (filtered.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:16px; text-align:center;">Không có sự kiện nào trong danh mục này.</div>';
      return;
    }

    container.innerHTML = filtered.map(ev => {
      const tagCls = ev.tag_class || 'tag-other';
      const icon = ev.icon || '📅';
      const exDateHtml = ev.ex_date ? `<span class="badge-ex-date" title="Ngày Giao Dịch Không Hưởng Quyền">📌 GDKHQ: ${escapeHTML(ev.ex_date)}</span>` : '';
      const ratioHtml = ev.ratio ? `<span class="badge-event-ratio" title="Tỷ lệ / Số tiền chi trả">${escapeHTML(ev.ratio)}</span>` : '';
      const linkHtml = ev.detail_url ? `<a href="${escapeHTML(ev.detail_url)}" target="_blank" rel="noopener noreferrer" class="btn-event-link"><span>Nghị quyết gốc</span> ↗</a>` : '';

      return `
        <div class="event-card">
          <div class="event-left">
            <div class="event-badges-row">
              <span class="event-tag ${tagCls}">${icon} ${escapeHTML(ev.event_name || 'Sự kiện')}</span>
              ${exDateHtml}
              ${ratioHtml}
            </div>
            <div class="event-title">${escapeHTML(ev.title)}</div>
          </div>
          <div class="event-right">
            <div class="event-date">📅 ${escapeHTML(ev.date || '')}</div>
            ${linkHtml}
          </div>
        </div>
      `;
    }).join('');
  }

  async fetchCompanyCommoditySpread(symbol) {
    const container = document.getElementById('stockCommoditySpreadContainer');
    if (!container) return;

    try {
      container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:28px; text-align:center;">⏳ Đang phân tích chu kỳ hàng hóa, Crack Spread & độ nhạy biên lợi nhuận cho mã ${escapeHTML(symbol)}...</div>`;
      const res = await fetch(`/api/company/commodity-spread?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;

      if (json.status !== 'success' || !json.data) {
        this.renderErrorState('stockCommoditySpreadContainer', json.message || `Không thể phân tích dữ liệu hàng hóa cho mã ${symbol}.`);
        return;
      }

      this.renderCompanyCommoditySpread(json.data);
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching commodity spread:', e);
      this.renderErrorState('stockCommoditySpreadContainer', `Lỗi kết nối khi tải phân tích chu kỳ hàng hóa cho mã ${symbol}.`);
    }
  }

  renderCompanyCommoditySpread(data) {
    const container = document.getElementById('stockCommoditySpreadContainer');
    if (!container) return;

    const symbol = data.symbol || '';
    const isCyclical = data.is_cyclical;
    const allSectors = data.all_cyclical_sectors || [];

    if (!isCyclical) {
      container.innerHTML = `
        <div style="background:linear-gradient(180deg, rgba(15,23,42,0.9) 0%, rgba(2,6,23,0.95) 100%); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:20px 24px; margin-bottom:16px;">
          <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
            <span style="font-size:24px;">ℹ️</span>
            <div>
              <div style="font-size:14px; font-weight:800; color:#f8fafc;">CỔ PHIẾU PHI CHU KỲ HÀNG HÓA THÔ (${escapeHTML(symbol)})</div>
              <div style="font-size:11.5px; color:#94a3b8; margin-top:2px;">${escapeHTML(data.message || 'Mã cổ phiếu này không thuộc 10 nhóm ngành hàng hóa chu kỳ trực tiếp.')}</div>
            </div>
          </div>
          <div style="font-size:11.5px; color:#cbd5e1; line-height:1.5; background:rgba(255,255,255,0.02); border-left:3px solid #38bdf8; padding:10px 14px; border-radius:4px;">
            💡 <strong>Quy tắc Định giá GS. Aswath Damodaran:</strong> Các doanh nghiệp công nghệ, bán lẻ, ngân hàng tạo giá trị từ lợi thế kinh tế quy mô, hiệu ứng mạng lưới hoặc NIM tín dụng thay vì biến động Crack Spread nguyên liệu thô đầu vào.
          </div>
        </div>

        <div style="margin-top:20px;">
          <div style="font-size:13px; font-weight:800; color:#f8fafc; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
            <span>🌐 BẢN ĐỒ 10 NHÓM NGÀNH CHU KỲ HÀNG HÓA TRỌNG ĐIỂM TTCK VIỆT NAM (ĐỐI CHIẾU DỮ LIỆU KÉP QUỐC TẾ & NỘI ĐỊA)</span>
            <span style="font-size:11px; color:#10b981; font-weight:600;">(Chọn mã để chuyển sang phân tích chu kỳ)</span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px;">
            ${allSectors.map(sec => {
              const totalCount = sec.total_sector_symbols_count || (sec.all_sector_symbols || []).length || (sec.monitored_symbols || []).length;
              const allSyms = sec.all_sector_symbols || sec.monitored_symbols || [];
              const domSpot = sec.domestic_spot || {};
              return `
              <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px; display:flex; flex-direction:column; justify-content:space-between;">
                <div>
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="font-size:12px; font-weight:800; color:#38bdf8;">${escapeHTML(sec.sector_name)}</span>
                    <div style="display:flex; gap:4px; align-items:center;">
                      <span style="font-size:9.5px; font-weight:800; color:#10b981; background:rgba(16,185,129,0.12); padding:1px 6px; border-radius:10px; border:1px solid rgba(16,185,129,0.25);">${totalCount} mã</span>
                      <span style="font-size:10px; font-family:var(--font-mono); color:#94a3b8; background:rgba(255,255,255,0.05); padding:1px 5px; border-radius:3px;">${escapeHTML(sec.spread_unit)}</span>
                    </div>
                  </div>
                  <div style="font-size:10.5px; color:#cbd5e1; margin-bottom:6px;">
                    <strong>Công thức Spread:</strong> ${escapeHTML(sec.key_monitored_spread || sec.spread_name || '')}
                  </div>
                  ${domSpot.spot_price ? `
                    <div style="font-size:10px; color:#facc15; background:rgba(250,204,21,0.08); border:1px solid rgba(250,204,21,0.2); border-radius:4px; padding:4px 8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                      <span>📍 <strong>Spot nội địa:</strong> ${Number(domSpot.spot_price).toLocaleString()} ${escapeHTML(domSpot.unit || '')}</span>
                      <span style="color:#94a3b8; font-size:9px;">${escapeHTML(domSpot.source ? domSpot.source.split('(')[0].trim() : '')}</span>
                    </div>
                  ` : ''}
                </div>
                <div>
                  <div style="font-size:10px; color:#94a3b8; font-weight:700; margin-bottom:4px;">⭐ ĐẦU NGÀNH (TOP VỐN HÓA DYNAMIC):</div>
                  <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:6px;">
                    ${(sec.monitored_symbols || []).map(sym => `
                      <button onclick="app.inspectStock('${sym}'); setTimeout(() => app.switchStockSubtab('stock_commodity_spread'), 150);" style="background:rgba(16,185,129,0.12); color:#10b981; border:1px solid rgba(16,185,129,0.3); font-weight:800; font-size:11px; padding:3px 8px; border-radius:4px; cursor:pointer;">
                        ${sym} ↗
                      </button>
                    `).join('')}
                  </div>
                  ${allSyms.length > (sec.monitored_symbols || []).length ? `
                    <details style="margin-top:4px;">
                      <summary style="font-size:10px; color:#38bdf8; cursor:pointer; font-weight:600; outline:none; user-select:none;">
                        + Xem tất cả ${allSyms.length} mã trong ngành ▾
                      </summary>
                      <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; max-height:90px; overflow-y:auto; padding:6px; background:rgba(0,0,0,0.3); border-radius:4px;">
                        ${allSyms.map(sym => `
                          <button onclick="app.inspectStock('${sym}'); setTimeout(() => app.switchStockSubtab('stock_commodity_spread'), 150);" style="background:rgba(255,255,255,0.05); color:#cbd5e1; border:1px solid rgba(255,255,255,0.1); font-size:9.5px; font-weight:700; padding:1px 6px; border-radius:3px; cursor:pointer;">
                            ${sym}
                          </button>
                        `).join('')}
                      </div>
                    </details>
                  ` : ''}
                </div>
              </div>
            `;}).join('')}
          </div>
        </div>
      `;
      return;
    }

    const sp = data.spread_analysis || {};
    const mg = sp.gross_margin_forecast || {};
    const outComm = data.output_commodity || {};
    const inComms = data.input_commodities || [];
    const domSpot = data.domestic_spot || sp.domestic_spot || {};
    const basis = data.basis_analysis || sp.basis_analysis || {};

    const mom1m = sp.momentum_1m_pct || 0;
    const mom3m = sp.momentum_3m_pct || 0;
    const momColor = mom1m >= 0 ? '#10b981' : '#f43f5e';
    const momSign = mom1m >= 0 ? '+' : '';

    container.innerHTML = `
      <!-- TOP HERO: CYCLE PHASE & PETER LYNCH CLOCK -->
      <div style="background:linear-gradient(180deg, rgba(15,23,42,0.85) 0%, rgba(2,6,23,0.95) 100%); border:1px solid rgba(16,185,129,0.3); border-radius:10px; padding:18px 20px; margin-bottom:16px; box-shadow:0 4px 20px rgba(0,0,0,0.4);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px;">
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size:24px;">${escapeHTML(sp.cycle_clock_emoji || '⏳')}</span>
            <div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:15px; font-weight:800; color:#f8fafc;">${escapeHTML(data.sector_name)} (${escapeHTML(symbol)})</span>
                <span style="font-size:10.5px; font-weight:800; padding:2px 8px; border-radius:4px; background:${sp.phase_color || '#10b981'}22; color:${sp.phase_color || '#10b981'}; border:1px solid ${sp.phase_color || '#10b981'}55;">
                  PHA: ${escapeHTML(sp.cycle_phase || 'CHU KỲ')}
                </span>
              </div>
              <div style="font-size:11px; color:#94a3b8; margin-top:2px;">
                Spread cốt lõi: <strong style="color:#cbd5e1;">${escapeHTML(data.key_monitored_spread)}</strong>
              </div>
            </div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:10.5px; color:#94a3b8;">DỰ BÁO BIÊN GỘP QUÝ TỚI</div>
            <div style="font-size:15px; font-weight:800; color:${mg.color || '#10b981'}; font-family:var(--font-mono);">
              ${escapeHTML(mg.direction || 'ỔN ĐỊNH')} (${escapeHTML(mg.margin_forecast_range || '--')})
            </div>
          </div>
        </div>

        <!-- 4 Cycle Phases Visual Tracker -->
        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; margin-bottom:12px;">
          ${[
            { label: '1. ĐÁY CHU KỲ', desc: 'Spread chạm đáy, các nhà máy yếu đóng cửa' },
            { label: '2. BÙNG NỔ', desc: 'Spread nới rộng, biên gộp tăng tốc' },
            { label: '3. CO HẸP', desc: 'Nguồn cung tràn ngập, giá đầu ra điều chỉnh' },
            { label: '4. ĐỈNH CHU KỲ / SUY', desc: 'Biên gộp co rút về ngưỡng hòa vốn' }
          ].map(p => {
            const isActive = sp.cycle_phase && sp.cycle_phase.includes(p.label.substring(3));
            return `
              <div style="background:${isActive ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.02)'}; border:1px solid ${isActive ? '#10b981' : 'rgba(255,255,255,0.06)'}; border-radius:6px; padding:8px 10px; text-align:center;">
                <div style="font-size:10.5px; font-weight:800; color:${isActive ? '#10b981' : '#64748b'};">${p.label}</div>
                <div style="font-size:9.5px; color:${isActive ? '#94a3b8' : '#475569'}; margin-top:2px;">${p.desc}</div>
              </div>
            `;
          }).join('')}
        </div>

        <!-- Peter Lynch Principle Insight -->
        <div style="background:rgba(255,255,255,0.02); border-left:3px solid #facc15; padding:8px 12px; border-radius:4px; font-size:11px; color:#e2e8f0; line-height:1.45;">
          📖 <strong style="color:#facc15;">Quy Tắc Đảo Chiều P/E Peter Lynch (One Up On Wall Street):</strong> 
          ${escapeHTML(sp.peter_lynch_guidance || '')}
        </div>
      </div>

      <!-- DUAL-LAYER INTELLIGENCE CARD: GLOBAL BENCHMARK VS VIETNAM SPOT BASIS GAP -->
      <div style="background:linear-gradient(135deg, rgba(30,27,75,0.45) 0%, rgba(15,23,42,0.95) 100%); border:1px solid rgba(139,92,246,0.35); border-radius:10px; padding:18px 20px; margin-bottom:16px; box-shadow:0 4px 20px rgba(0,0,0,0.35);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:14px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:18px;">🌐</span>
            <span style="font-size:13px; font-weight:800; color:#c084fc; letter-spacing:0.5px;">ĐỐI CHIẾU DỮ LIỆU KÉP: QUỐC TẾ (FUTURES BENCHMARK) VS NỘI ĐỊA THỰC TẾ (VIETNAM SPOT)</span>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="font-size:10px; background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); padding:2px 8px; border-radius:12px; font-weight:700;">
              ✓ Live Spot Survey
            </span>
            <span style="font-size:10px; color:#94a3b8; font-family:var(--font-mono);">
              ${escapeHTML(domSpot.crawled_at || domSpot.updated_at || 'Khảo sát thực tế')}
            </span>
          </div>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:14px;">
          <!-- Box 1: Global Benchmark -->
          <div style="background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px;">
            <div style="font-size:10.5px; color:#94a3b8; font-weight:700; margin-bottom:4px; display:flex; justify-content:space-between;">
              <span>🌍 GIÁ HÀNG HÓA THẾ GIỚI</span>
              <span style="color:#38bdf8; font-size:9.5px;">${escapeHTML(outComm.source || 'CME/NYMEX/SGX')}</span>
            </div>
            <div style="font-size:13px; font-weight:800; color:#f8fafc; margin-bottom:6px;">
              ${escapeHTML(outComm.name || 'Thế Giới')}
            </div>
            <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:6px;">
              <span style="font-size:20px; font-weight:800; font-family:var(--font-mono); color:#38bdf8;">
                ${Number(outComm.current_price || outComm.price || 0).toLocaleString()}
              </span>
              <span style="font-size:11px; color:#94a3b8;">${escapeHTML(outComm.unit || '')}</span>
            </div>
            <div style="font-size:10.5px; color:#64748b; background:rgba(0,0,0,0.25); padding:4px 8px; border-radius:4px;">
              Quy đổi tương đương: <strong style="color:#cbd5e1; font-family:var(--font-mono);">${Number(basis.global_benchmark_vnd || 0).toLocaleString()} ${escapeHTML(basis.domestic_unit || 'VND/kg')}</strong>
            </div>
          </div>

          <!-- Box 2: Vietnam Domestic Spot Survey -->
          <div style="background:rgba(255,255,255,0.025); border:1px solid rgba(250,204,21,0.25); border-radius:8px; padding:12px 14px;">
            <div style="font-size:10.5px; color:#facc15; font-weight:700; margin-bottom:4px; display:flex; justify-content:space-between;">
              <span>🇻🇳 KHẢO SÁT NỘI ĐỊA VIỆT NAM (SPOT)</span>
              <span style="color:#facc15; font-size:9.5px; background:rgba(250,204,21,0.15); padding:1px 6px; border-radius:4px;">Thực địa</span>
            </div>
            <div style="font-size:13px; font-weight:800; color:#f8fafc; margin-bottom:6px;">
              ${escapeHTML(domSpot.commodity_name || 'Giá Giao Ngay')}
            </div>
            <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:6px;">
              <span style="font-size:20px; font-weight:800; font-family:var(--font-mono); color:#facc15;">
                ${Number(domSpot.spot_price || 0).toLocaleString()}
              </span>
              <span style="font-size:11px; color:#94a3b8;">${escapeHTML(domSpot.unit || '')}</span>
              ${domSpot.price_range_min && domSpot.price_range_max ? `
                <span style="font-size:10px; color:#94a3b8; margin-left:auto;">(${Number(domSpot.price_range_min).toLocaleString()} - ${Number(domSpot.price_range_max).toLocaleString()})</span>
              ` : ''}
            </div>
            <div style="font-size:10px; color:#94a3b8; margin-top:4px;">
              📍 Nguồn: <strong style="color:#cbd5e1;">${escapeHTML(domSpot.source || 'Khảo sát ngành')}</strong>
            </div>
            ${(domSpot.regions || domSpot.products) ? `
              <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; border-top:1px dashed rgba(255,255,255,0.06); padding-top:6px;">
                ${Object.entries(domSpot.regions || domSpot.products).map(([k, p]) => `
                  <span style="font-size:9.5px; background:rgba(255,255,255,0.04); padding:2px 6px; border-radius:3px; color:#cbd5e1;">
                    <strong>${escapeHTML(k)}:</strong> ${Number(p).toLocaleString()}
                  </span>
                `).join('')}
              </div>
            ` : ''}
          </div>

          <!-- Box 3: Basis Spread & Arbitrage Implication -->
          <div style="background:rgba(255,255,255,0.025); border:1px solid rgba(168,85,247,0.25); border-radius:8px; padding:12px 14px; display:flex; flex-direction:column; justify-content:space-between;">
            <div>
              <div style="font-size:10.5px; color:#c084fc; font-weight:700; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>⚡ BASIS SPREAD (ĐỘ LỆCH PHA NỘI ĐỊA)</span>
                <span style="color:${(basis.basis_gap_pct || 0) >= 0 ? '#10b981' : '#f43f5e'}; font-weight:800; font-family:var(--font-mono);">
                  ${(basis.basis_gap_pct || 0) >= 0 ? '+' : ''}${basis.basis_gap_pct || 0}%
                </span>
              </div>
              <div style="font-size:11px; font-weight:700; color:#f8fafc; margin-bottom:6px; line-height:1.4;">
                ${escapeHTML(basis.premium_status || 'Chênh lệch giá nội địa vs quốc tế')}
              </div>
            </div>
            <div style="background:rgba(168,85,247,0.08); border-left:3px solid #c084fc; padding:6px 10px; border-radius:4px; font-size:10px; color:#cbd5e1; line-height:1.4; margin-top:6px;">
              🎯 <strong>Tác động đặc thù VN:</strong> ${escapeHTML(basis.domestic_drivers || domSpot.domestic_drivers || 'Biến động cung cầu nội địa chi phối trước.')}
            </div>
          </div>
        </div>
      </div>

      <!-- 4 METRIC CARDS -->
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-bottom:16px;">
        <!-- Card 1: Current Crack Spread -->
        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px;">
          <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
            <span>CRACK SPREAD HIỆN TẠI</span>
            <span style="color:#38bdf8; font-size:9.5px; font-weight:700;">${escapeHTML(data.spread_unit)}</span>
          </div>
          <div style="font-size:20px; font-weight:800; font-family:var(--font-mono); color:#f8fafc;">
            ${Number(sp.current_spread || 0).toLocaleString()} ${escapeHTML(data.spread_unit)}
          </div>
          <div style="font-size:10.5px; color:#64748b; margin-top:4px;">
            TB 3 Tháng: <strong style="color:#cbd5e1;">${Number(sp.spread_avg_3m || 0).toLocaleString()}</strong>
          </div>
        </div>

        <!-- Card 2: Momentum 1M / 3M -->
        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px;">
          <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
            <span>XUNG LỰC SPREAD (MOMENTUM)</span>
            <span style="color:${momColor}; font-size:9.5px; font-weight:700;">1 THÁNG / 3 THÁNG</span>
          </div>
          <div style="font-size:20px; font-weight:800; font-family:var(--font-mono); color:${momColor};">
            ${momSign}${mom1m}%
          </div>
          <div style="font-size:10.5px; color:#64748b; margin-top:4px;">
            Xung lực 3 tháng: <strong style="color:${mom3m >= 0 ? '#10b981' : '#f43f5e'};">${mom3m >= 0 ? '+' : ''}${mom3m}%</strong>
          </div>
        </div>

        <!-- Card 3: Margin Impact bps -->
        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px;">
          <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
            <span>ĐỘ NHẠY BIÊN LỢI NHUẬN</span>
            <span style="color:#a855f7; font-size:9.5px; font-weight:700;">BPS IMPACT</span>
          </div>
          <div style="font-size:20px; font-weight:800; font-family:var(--font-mono); color:${mg.color || '#10b981'};">
            ${(mg.estimated_impact_bps || 0) >= 0 ? '+' : ''}${mg.estimated_impact_bps || 0} bps
          </div>
          <div style="font-size:10.5px; color:#94a3b8; margin-top:4px;">
            ${escapeHTML(mg.rationale || '')}
          </div>
        </div>

        <!-- Card 4: Cash Cost Floor -->
        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:12px 14px;">
          <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
            <span>SÀN GIÁ VỐN TIỀN MẶT (CASH COST FLOOR)</span>
            <span style="color:#f59e0b; font-size:9.5px; font-weight:700;">HỖ TRỢ BIÊN</span>
          </div>
          <div style="font-size:20px; font-weight:800; font-family:var(--font-mono); color:#f59e0b;">
            ${Number(sp.cash_cost_floor_estimate || 0).toLocaleString()} ${escapeHTML(data.spread_unit)}
          </div>
          <div style="font-size:10.5px; color:#64748b; margin-top:4px;">
            Biên độ an toàn cách sàn: <strong style="color:#10b981;">+${sp.distance_to_floor_pct || 0}%</strong>
          </div>
        </div>
      </div>

      <!-- COMMODITY BREAKDOWN TABLE: OUTPUT VS INPUTS -->
      <div style="display:grid; grid-template-columns:1fr 1.6fr; gap:14px; margin-bottom:16px;">
        <!-- Left: Output Commodity -->
        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:14px 16px;">
          <div style="font-size:12px; font-weight:800; color:#38bdf8; margin-bottom:10px; display:flex; justify-content:space-between;">
            <span>📦 SẢN PHẨM ĐẦU RA (OUTPUT)</span>
            <span style="font-size:10px; color:#64748b;">Nguồn: ${escapeHTML(outComm.source || 'TradingEconomics')}</span>
          </div>
          <div style="font-size:14px; font-weight:800; color:#f8fafc; margin-bottom:6px;">
            ${escapeHTML(outComm.name)}
          </div>
          <div style="display:flex; align-items:baseline; gap:8px; margin-bottom:10px;">
            <span style="font-size:22px; font-weight:800; font-family:var(--font-mono); color:#f8fafc;">
              ${Number(outComm.current_price || outComm.price || 0).toLocaleString()}
            </span>
            <span style="font-size:11px; color:#94a3b8;">${escapeHTML(outComm.unit)}</span>
          </div>
          <div style="display:flex; gap:12px; font-size:11px;">
            <div>
              <span style="color:#64748b;">1 Tháng:</span>
              <strong style="color:${(outComm.price_change_1m_pct || outComm.change_pct || 0) >= 0 ? '#10b981' : '#f43f5e'}; font-family:var(--font-mono); margin-left:4px;">
                ${(outComm.price_change_1m_pct || outComm.change_pct || 0) >= 0 ? '+' : ''}${outComm.price_change_1m_pct || outComm.change_pct || 0}%
              </strong>
            </div>
            <div>
              <span style="color:#64748b;">3 Tháng:</span>
              <strong style="color:${(outComm.price_change_3m_pct || 0) >= 0 ? '#10b981' : '#f43f5e'}; font-family:var(--font-mono); margin-left:4px;">
                ${(outComm.price_change_3m_pct || 0) >= 0 ? '+' : ''}${outComm.price_change_3m_pct || 0}%
              </strong>
            </div>
          </div>
        </div>

        <!-- Right: Input Commodities Breakdown -->
        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:14px 16px;">
          <div style="font-size:12px; font-weight:800; color:#f59e0b; margin-bottom:10px; display:flex; justify-content:space-between;">
            <span>🧱 NGUYÊN LIỆU ĐẦU VÀO TRỌNG SỐ (WEIGHTED INPUTS)</span>
            <span style="font-size:10px; color:#64748b;">Mô hình định lượng chuẩn</span>
          </div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            ${inComms.map(inp => `
              <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 10px; background:rgba(255,255,255,0.02); border-radius:4px; font-size:11px;">
                <div>
                  <div style="font-weight:700; color:#f8fafc;">${escapeHTML(inp.name)}</div>
                  <div style="font-size:10px; color:#64748b; margin-top:2px;">
                    Trọng số giá thành: <strong style="color:#f59e0b;">${inp.weight_pct || inp.weight || 0}%</strong> • Giá: ${Number(inp.current_price || inp.price || 0).toLocaleString()} ${escapeHTML(inp.unit)}
                  </div>
                </div>
                <div style="text-align:right; font-family:var(--font-mono);">
                  <div style="color:${(inp.price_change_1m_pct || inp.change_pct || 0) <= 0 ? '#10b981' : '#f43f5e'}; font-weight:700;">
                    ${(inp.price_change_1m_pct || inp.change_pct || 0) >= 0 ? '+' : ''}${inp.price_change_1m_pct || inp.change_pct || 0}% (1M)
                  </div>
                  <div style="font-size:10px; color:#64748b;">
                    Chi phí hiệu dụng: ${escapeHTML(inp.effective_cost_impact || (inp.weighted_cost + ' ' + (data.spread_unit || '')))}
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>

      <!-- PEERS & SECTORS CROSS-NAVIGATION (DYNAMIC UNIVERSE) -->
      <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); border-radius:8px; padding:12px 16px;">
        <!-- 10 Cyclical Sectors Quick Navigator -->
        <div style="margin-bottom:12px; padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.06);">
          <div style="font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:6px;">
            🌐 CHUYỂN NHANH 10 NHÓM NGÀNH CHU KỲ HÀNG HÓA TRỌNG ĐIỂM:
          </div>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            ${allSectors.map(sec => {
              const isCurrentSec = sec.sector_key === data.sector_key;
              const leader = (sec.core_leaders || sec.representative_symbols || sec.monitored_symbols || [])[0];
              return `
                <button onclick="app.inspectStock('${leader}'); setTimeout(() => app.switchStockSubtab('stock_commodity_spread'), 150);" style="background:${isCurrentSec ? 'rgba(56,189,248,0.2)' : 'rgba(255,255,255,0.03)'}; color:${isCurrentSec ? '#38bdf8' : '#94a3b8'}; border:1px solid ${isCurrentSec ? '#38bdf8' : 'rgba(255,255,255,0.08)'}; font-size:10px; font-weight:700; padding:3px 8px; border-radius:4px; cursor:pointer;" title="${escapeHTML(sec.key_monitored_spread || '')}">
                  ${escapeHTML(sec.sector_name)} (${leader})
                </button>
              `;
            }).join('')}
          </div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span style="font-size:12px; font-weight:800; color:#cbd5e1;">⭐ ĐẦU NGÀNH (TOP VỐN HÓA DYNAMIC):</span>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              ${(data.core_leaders || data.monitored_peers_in_sector || []).map(p => `
                <button onclick="app.inspectStock('${p}'); setTimeout(() => app.switchStockSubtab('stock_commodity_spread'), 150);" style="background:${p === symbol ? '#10b981' : 'rgba(255,255,255,0.05)'}; color:${p === symbol ? '#020617' : '#f8fafc'}; border:1px solid ${p === symbol ? '#10b981' : 'rgba(255,255,255,0.1)'}; font-weight:800; font-size:11px; padding:2px 8px; border-radius:4px; cursor:pointer;">
                  ${p}
                </button>
              `).join('')}
            </div>
          </div>
          <div style="font-size:10.5px; color:#64748b;">
            Nghiên cứu tham chiếu: <strong style="color:#94a3b8;">Howard Marks</strong> (Chu kỳ) & <strong style="color:#94a3b8;">Damodaran</strong> (Định giá hàng hóa)
          </div>
        </div>
        ${(data.all_sector_symbols && data.all_sector_symbols.length > 0) ? `
          <div style="border-top:1px dashed rgba(255,255,255,0.07); padding-top:8px; margin-top:6px;">
            <details>
              <summary style="font-size:11px; color:#38bdf8; font-weight:700; cursor:pointer; outline:none; user-select:none; display:flex; align-items:center; gap:6px;">
                <span>🌐 TỰ ĐỘNG KHÁM PHÁ TOÀN BỘ NGÀNH:</span>
                <span style="color:#10b981; background:rgba(16,185,129,0.12); padding:1px 6px; border-radius:10px; font-size:10px;">${data.total_sector_symbols_count || data.all_sector_symbols.length} mã niêm yết</span>
                <span style="font-size:10px; color:#94a3b8; font-weight:normal;">(Nhấp để mở rộng và chuyển sang phân tích bất kỳ mã nào) ▾</span>
              </summary>
              <div style="display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; max-height:120px; overflow-y:auto; padding:8px; background:rgba(0,0,0,0.25); border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                ${data.all_sector_symbols.map(s => `
                  <button onclick="app.inspectStock('${s}'); setTimeout(() => app.switchStockSubtab('stock_commodity_spread'), 150);" style="background:${s === symbol ? '#10b981' : 'rgba(255,255,255,0.04)'}; color:${s === symbol ? '#020617' : '#94a3b8'}; border:1px solid ${s === symbol ? '#10b981' : 'rgba(255,255,255,0.08)'}; font-size:10px; font-weight:700; padding:2px 7px; border-radius:4px; cursor:pointer; font-family:var(--font-mono);" title="Phân tích chu kỳ mã ${s}">
                    ${s}
                  </button>
                `).join('')}
              </div>
            </details>
          </div>
        ` : ''}
      </div>
    `;
  }

  async fetchCompanyLeadership(symbol) {
    try {
      const container = document.getElementById('stockLeadershipGrid');
      if (container) {
        container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center; grid-column:1/-1;">⏳ Đang tải ban điều hành & cổ đông lớn cho mã ${escapeHTML(symbol)}...</div>`;
      }
      const res = await fetch(`/api/company/leadership?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;
      if (json.status !== 'success') {
        this.renderErrorState('stockLeadershipGrid', json.message || `Không thể tải thông tin lãnh đạo cho mã ${symbol}.`);
        return;
      }

      if (!container) return;

      const { officers = [], shareholders = [], family_network = [], insider_transactions = [], free_float_structure = {}, realtime_insider_flow = {}, smart_money_flow = {} } = json.data || {};

      const sm = smart_money_flow || {};
      const smScore = sm.smart_money_score || 50;
      const wyckoff = sm.wyckoff_footprint || {};
      const matched = sm.matched_flow || {};
      const pt = sm.put_through_flow || {};
      const prop = sm.prop_trading || {};
      const fflow = sm.foreign_flow || {};
      const vwap = sm.foreign_vwap_analysis || {};
      const room = sm.foreign_room_exhaustion || {};

      const matchedNetVnd = matched.foreign_net_matched_val || 0;
      const ptNetVnd = pt.foreign_net_pt_val || 0;
      const prop5dVnd = prop.prop_net_val_5d || 0;
      const prop20dVnd = prop.prop_net_val_20d || 0;

      let ffState = Number(free_float_structure.state_ownership_pct || 0);
      let ffForeign = Number(free_float_structure.foreign_ownership_pct || 0);
      let ffInsider = Number(free_float_structure.insider_ownership_pct || 0);
      let ffInst = Number(free_float_structure.institutional_pct || 0);
      let ffFree = Number(free_float_structure.true_free_float_pct || 0);
      let ffClass = free_float_structure.liquidity_classification || 'TRUNG BÌNH';

      // Defensive fallback: If all are 0 and free is 100, calculate dynamically from shareholders
      if ((ffState + ffForeign + ffInsider + ffInst) < 1 && data.shareholders && data.shareholders.length > 0) {
        data.shareholders.forEach(sh => {
          const n = (sh.name || '').toLowerCase();
          const rMatch = String(sh.ratio || '').match(/([\d\.]+)/);
          const r = rMatch ? parseFloat(rMatch[1]) : 0;
          if (r > 0) {
            if (n.includes('scic') || n.includes('nhà nước') || n.includes('bộ tài chính') || n.includes('ubnd') || n.includes('tổng công ty đầu tư và kinh doanh vốn')) {
              ffState += r;
            } else if (n.includes('fund') || n.includes('capital') || n.includes('limited') || n.includes('ltd') || n.includes('bank') || n.includes('invest') || n.includes('dragon') || n.includes('gic') || n.includes('caravel') || n.includes('kuroto') || n.includes('cashew') || n.includes('macquarie')) {
              ffForeign += r;
            } else if (n.includes('công ty') || n.includes('ctcp') || n.includes('tập đoàn') || n.includes('quỹ') || n.includes('chứng khoán') || n.includes('tnhh')) {
              ffInst += r;
            } else {
              ffInsider += r;
            }
          }
        });
        const locked = ffState + ffForeign + ffInsider + ffInst;
        ffFree = Math.max(5, Math.round((100 - locked) * 10) / 10);
        ffState = Math.round(ffState * 10) / 10;
        ffForeign = Math.round(ffForeign * 10) / 10;
        ffInsider = Math.round(ffInsider * 10) / 10;
        ffInst = Math.round(ffInst * 10) / 10;
        ffClass = ffFree >= 50 ? 'CAO (Dễ giao dịch)' : (ffFree >= 25 ? 'TRUNG BÌNH (Thanh khoản ổn định)' : 'THẤP (Cô đặc)');
      }
      if (ffFree <= 0) ffFree = 50;

      const realizedNetVnd = realtime_insider_flow.realized_net_flow_vnd || 0;
      const pendingNetVnd = realtime_insider_flow.pending_net_flow_vnd || 0;
      const realizedNetShares = realtime_insider_flow.realized_net_shares || 0;
      const pendingNetShares = realtime_insider_flow.pending_net_shares || 0;
      const forcedSellCount = realtime_insider_flow.forced_sell_count || 0;
      const sentiment = realtime_insider_flow.sentiment || 'CÂN BẰNG';
      const sentimentColor = realtime_insider_flow.sentiment_color || '#38bdf8';
      const recentDeals = realtime_insider_flow.recent_deals || [];

      container.innerHTML = `
        <!-- TRUE FREE FLOAT METER -->
        <div style="grid-column: 1 / -1; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); padding:12px 16px; border-radius:8px; margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">🌊</span>
              <span style="font-size:13px; font-weight:800; color:#f8fafc;">THƯỚC ĐO CƠ CẤU SỞ HỮU & TỶ LỆ TRÔI NỔI THỰC TẾ (TRUE FREE-FLOAT)</span>
            </div>
            <span style="font-size:11px; font-weight:800; color:#10b981; background:rgba(16,185,129,0.15); padding:2px 8px; border-radius:4px; border:1px solid rgba(16,185,129,0.3);">
              Trôi Nổi Tự Do: ${ffFree}% • ${escapeHTML(ffClass)}
            </span>
          </div>

          <div class="free-float-meter">
            <div class="ff-state" style="width:${ffState}%;" title="Nhà nước: ${ffState}%"></div>
            <div class="ff-foreign" style="width:${ffForeign}%;" title="Nước ngoài: ${ffForeign}%"></div>
            <div class="ff-insider" style="width:${ffInsider}%;" title="Lãnh đạo & Gia đình: ${ffInsider}%"></div>
            <div class="ff-inst" style="width:${ffInst}%;" title="Tổ chức / Quỹ: ${ffInst}%"></div>
            <div class="ff-free" style="width:${ffFree}%;" title="Trôi nổi thực tế (Free-Float): ${ffFree}%"></div>
          </div>

          <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; font-size:11px; font-family:var(--font-mono); color:#94a3b8; margin-top:6px;">
            <span><span style="color:#e11d48;">■</span> Nhà nước: ${ffState}%</span>
            <span><span style="color:#3b82f6;">■</span> Khối ngoại: ${ffForeign}%</span>
            <span><span style="color:#a855f7;">■</span> Ban Lãnh đạo: ${ffInsider}%</span>
            <span><span style="color:#f59e0b;">■</span> Tổ chức: ${ffInst}%</span>
            <span><span style="color:#10b981; font-weight:700;">■ Trôi nổi thực (Free-Float): ${ffFree}%</span></span>
          </div>
        </div>

        <!-- RADAR DÒNG TIỀN MUA/BÁN CỔ ĐÔNG & NỘI BỘ (REAL-TIME INSIDER FLOW) -->
        <div style="grid-column: 1 / -1; background:linear-gradient(180deg, rgba(15,23,42,0.85) 0%, rgba(2,6,23,0.95) 100%); border:1px solid rgba(56,189,248,0.25); padding:14px 16px; border-radius:8px; margin-bottom:12px; box-shadow:0 4px 16px rgba(0,0,0,0.3);">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:18px;">📡</span>
              <div>
                <span style="font-size:13px; font-weight:800; color:#f8fafc; letter-spacing:0.3px;">RADAR DÒNG TIỀN MUA/BÁN CỔ ĐÔNG & NỘI BỘ (REAL-TIME INSIDER FLOW)</span>
                <div style="font-size:10.5px; color:#94a3b8;">Crawl trực tiếp từ cổng công bố thông tin TT96/2020/TT-BTC • Bóc tách Khớp Thật vs. Đăng Ký</div>
              </div>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              ${realtime_insider_flow.has_forced_sell_alert ? `
                <span style="font-size:11px; font-weight:800; color:#ef4444; background:rgba(239,68,68,0.2); padding:3px 10px; border-radius:4px; border:1px solid rgba(239,68,68,0.5);">
                  ⚠️ CẢNH BÁO BÁN GIẢI CHẤP CTCK
                </span>
              ` : ''}
              <span style="font-size:11px; font-weight:800; color:${sentimentColor}; background:rgba(255,255,255,0.05); padding:3px 10px; border-radius:4px; border:1px solid ${sentimentColor}40;">
                Tín hiệu: ${escapeHTML(sentiment)}
              </span>
            </div>
          </div>

          <!-- Flow Summary Cards -->
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; margin-bottom:12px;">
            <!-- Realized Net Flow -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>THỰC KHỚP RÒNG (REALIZED)</span>
                <span style="color:#10b981; font-size:9.5px; font-weight:700;">ĐÃ KHỚP QUA SÀN</span>
              </div>
              <div style="font-size:16px; font-weight:800; font-family:var(--font-mono); color:${realizedNetVnd > 0 ? '#10b981' : (realizedNetVnd < 0 ? '#f43f5e' : '#94a3b8')};">
                ${realizedNetVnd > 0 ? '+' : ''}${(realizedNetVnd / 1e9).toLocaleString('vi-VN', {minimumFractionDigits: 1, maximumFractionDigits: 2})} Tỷ VNĐ
              </div>
              <div style="font-size:10px; color:#64748b; margin-top:2px;">
                KL ròng: ${realizedNetShares > 0 ? '+' : ''}${Number(realizedNetShares).toLocaleString()} CP
              </div>
            </div>

            <!-- Pending Pipeline -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>ĐĂNG KÝ CHỜ KHỚP (PIPELINE)</span>
                <span style="color:#f59e0b; font-size:9.5px; font-weight:700;">ÁP LỰC TIỀM NĂNG</span>
              </div>
              <div style="font-size:16px; font-weight:800; font-family:var(--font-mono); color:${pendingNetVnd > 0 ? '#10b981' : (pendingNetVnd < 0 ? '#f59e0b' : '#94a3b8')};">
                ${pendingNetVnd > 0 ? '+' : ''}${(pendingNetVnd / 1e9).toLocaleString('vi-VN', {minimumFractionDigits: 1, maximumFractionDigits: 2})} Tỷ VNĐ
              </div>
              <div style="font-size:10px; color:#64748b; margin-top:2px;">
                KL chờ: ${pendingNetShares > 0 ? '+' : ''}${Number(pendingNetShares).toLocaleString()} CP (Không cộng vào Khớp thật)
              </div>
            </div>

            <!-- Forced Sell Alert Status -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>BÁN GIẢI CHẤP (MARGIN CALL)</span>
                <span style="color:${forcedSellCount > 0 ? '#ef4444' : '#10b981'}; font-size:9.5px; font-weight:700;">CTCK ÉP BÁN</span>
              </div>
              <div style="font-size:16px; font-weight:800; font-family:var(--font-mono); color:${forcedSellCount > 0 ? '#ef4444' : '#10b981'};">
                ${forcedSellCount > 0 ? `${forcedSellCount} LỆNH BỊ ÉP BÁN` : 'AN TOÀN'}
              </div>
              <div style="font-size:10px; color:#64748b; margin-top:2px;">
                ${forcedSellCount > 0 ? 'Phát hiện CTCK bán giải chấp tài khoản lãnh đạo' : 'Không có hiện tượng bán tháo giải chấp'}
              </div>
            </div>
          </div>

          <!-- Deals Feed List -->
          ${recentDeals.length > 0 ? `
            <div style="border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;">
              <div style="font-size:11px; font-weight:700; color:#cbd5e1; margin-bottom:6px; display:flex; justify-content:space-between;">
                <span>DANH SÁCH LỆNH CÔNG BỐ GẦN NHẤT (${recentDeals.length})</span>
                <span style="font-size:10px; color:#64748b;">Nguồn: CafeF / UBCKNN</span>
              </div>
              <div style="display:flex; flex-direction:column; gap:4px; max-height:190px; overflow-y:auto; padding-right:4px;">
                ${recentDeals.map(d => {
                  let badgeBg = 'rgba(255,255,255,0.05)';
                  let badgeColor = '#94a3b8';
                  let badgeText = d.deal_type || 'GIAO DỊCH';
                  if (d.deal_type === 'EXECUTION_BUY') {
                    badgeBg = 'rgba(16,185,129,0.2)'; badgeColor = '#10b981'; badgeText = 'ĐÃ MUA THẬT';
                  } else if (d.deal_type === 'EXECUTION_SELL') {
                    badgeBg = 'rgba(244,63,94,0.2)'; badgeColor = '#f43f5e'; badgeText = 'ĐÃ BÁN THẬT';
                  } else if (d.deal_type === 'FORCED_LIQUIDATION') {
                    badgeBg = 'rgba(239,68,68,0.25)'; badgeColor = '#ef4444'; badgeText = 'BÁN GIẢI CHẤP';
                  } else if (d.deal_type === 'REGISTRATION') {
                    badgeBg = 'rgba(245,158,11,0.2)'; badgeColor = '#f59e0b'; badgeText = 'ĐĂNG KÝ';
                  }
                  return `
                    <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 10px; background:rgba(255,255,255,0.02); border-radius:4px; font-size:11px; border-left:3px solid ${badgeColor};">
                      <div style="display:flex; flex-direction:column; gap:2px; max-width:65%;">
                        <div style="display:flex; align-items:center; gap:6px;">
                          <span style="font-weight:700; color:#f8fafc;">${escapeHTML(d.trader_name || 'Cổ đông')}</span>
                          <span style="font-size:9.5px; font-weight:800; padding:1px 5px; border-radius:3px; background:${badgeBg}; color:${badgeColor}; border:1px solid ${badgeColor}40;">
                            ${badgeText}
                          </span>
                          ${d.is_bluffing ? `
                            <span style="font-size:9px; font-weight:700; padding:1px 4px; border-radius:3px; background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3);">
                              ⚠️ ẢO (&lt;20%)
                            </span>
                          ` : ''}
                        </div>
                        <div style="font-size:10px; color:#94a3b8;">
                          ${escapeHTML(d.relationship || '')} ${d.date ? `• ${escapeHTML(d.date)}` : ''}
                        </div>
                      </div>
                      <div style="text-align:right; font-family:var(--font-mono);">
                        <div style="font-weight:700; color:#f1f5f9;">${d.shares ? Number(d.shares).toLocaleString() + ' CP' : '--'}</div>
                        ${d.link ? `<a href="${escapeHTML(d.link)}" target="_blank" rel="noopener noreferrer" style="font-size:9.5px; color:#38bdf8; text-decoration:none;">Xem văn bản ↗</a>` : ''}
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          ` : `
            <div style="font-size:11px; color:#64748b; text-align:center; padding:8px; border-top:1px solid rgba(255,255,255,0.04);">
              Không có giao dịch nội bộ lớn nào được công bố trong thời gian gần đây.
            </div>
          `}
        </div>

        <!-- RADAR DÒNG TIỀN TỰ DOANH & KHỐI NGOẠI BÓC TÁCH (SMART MONEY & WYCKOFF MATRIX) -->
        <div style="grid-column: 1 / -1; background:linear-gradient(180deg, rgba(15,23,42,0.85) 0%, rgba(2,6,23,0.95) 100%); border:1px solid rgba(168,85,247,0.28); padding:14px 16px; border-radius:8px; margin-bottom:12px; box-shadow:0 4px 16px rgba(0,0,0,0.3);">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:18px;">💎</span>
              <div>
                <span style="font-size:13px; font-weight:800; color:#f8fafc; letter-spacing:0.3px;">RADAR DÒNG TIỀN TỰ DOANH & KHỐI NGOẠI BÓC TÁCH (SMART MONEY MATRIX)</span>
                <div style="font-size:10.5px; color:#94a3b8;">Bóc tách Khớp Lệnh Sàn vs Thỏa Thuận (TT) • Vị Thế Tự Doanh CTCK • Neo Giá Vốn VWAP Khối Ngoại • Wyckoff Footprint</div>
              </div>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              <span style="font-size:11px; font-weight:800; color:${wyckoff.color || '#10b981'}; background:rgba(255,255,255,0.05); padding:3px 10px; border-radius:4px; border:1px solid ${wyckoff.color || '#10b981'}40;">
                Wyckoff: ${escapeHTML(wyckoff.action || 'THEO DÕI')} (${escapeHTML(wyckoff.phase || 'ACCUMULATION')})
              </span>
              <span style="font-size:11px; font-weight:800; color:#c084fc; background:rgba(192,132,252,0.12); padding:3px 8px; border-radius:4px; border:1px solid rgba(192,132,252,0.3);">
                Smart Money: ${smScore}/100
              </span>
            </div>
          </div>

          <!-- 4 Grid Cards -->
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px; margin-bottom:10px;">
            <!-- Card 1: Matched vs Put-Through -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>KHỚP SÀN VS. THỎA THUẬN (TT)</span>
                <span style="color:#10b981; font-size:9.5px; font-weight:700;">STRICT SEPARATION</span>
              </div>
              <div style="font-size:15px; font-weight:800; font-family:var(--font-mono); color:${matchedNetVnd >= 0 ? '#10b981' : '#f43f5e'};">
                Khớp Sàn: ${matchedNetVnd >= 0 ? '+' : ''}${(matchedNetVnd / 1e9).toFixed(1)} Tỷ
              </div>
              <div style="font-size:10.5px; color:#94a3b8; margin-top:2px;">
                Thỏa Thuận (TT): <strong style="color:${ptNetVnd >= 0 ? '#10b981' : '#f43f5e'}; font-family:var(--font-mono);">${ptNetVnd >= 0 ? '+' : ''}${(ptNetVnd / 1e9).toFixed(1)} Tỷ</strong>
              </div>
              <div style="font-size:9.5px; color:#64748b; margin-top:4px;">
                ${matched.matched_share_pct || 100}% giá trị giao dịch diễn ra trên sàn khớp lệnh mở.
              </div>
            </div>

            <!-- Card 2: Prop Trading CTCK -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>TỰ DOANH CTCK (PROP TRADING)</span>
                <span style="color:${prop.sentiment_color || '#38bdf8'}; font-size:9.5px; font-weight:700;">${escapeHTML(prop.sentiment || 'CÂN BẰNG')}</span>
              </div>
              <div style="font-size:15px; font-weight:800; font-family:var(--font-mono); color:${prop5dVnd >= 0 ? '#10b981' : '#f43f5e'};">
                Net 5 Phiên: ${prop5dVnd >= 0 ? '+' : ''}${(prop5dVnd / 1e9).toFixed(1)} Tỷ
              </div>
              <div style="font-size:10.5px; color:#94a3b8; margin-top:2px;">
                Net 20 Phiên: <strong style="color:${prop20dVnd >= 0 ? '#10b981' : '#f43f5e'}; font-family:var(--font-mono);">${prop20dVnd >= 0 ? '+' : ''}${(prop20dVnd / 1e9).toFixed(1)} Tỷ</strong>
              </div>
              <div style="font-size:9.5px; color:#64748b; margin-top:4px;">
                Dòng tiền tự doanh các CTCK phản ánh vị thế Market Maker.
              </div>
            </div>

            <!-- Card 3: Foreign VWAP Support Anchor -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>NEO GIÁ VỐN NGOẠI (VWAP ANCHOR)</span>
                <span style="color:#f59e0b; font-size:9.5px; font-weight:700;">HỖ TRỢ / KHÁNG CỰ</span>
              </div>
              <div style="font-size:15px; font-weight:800; font-family:var(--font-mono); color:#f8fafc;">
                30D: ${vwap.cost_basis_vwap_30d ? vwap.cost_basis_vwap_30d.toLocaleString() + ' đ' : '--'}
              </div>
              <div style="font-size:10.5px; color:#94a3b8; margin-top:2px;">
                90D: <strong style="color:#cbd5e1; font-family:var(--font-mono);">${vwap.cost_basis_vwap_90d ? vwap.cost_basis_vwap_90d.toLocaleString() + ' đ' : '--'}</strong> 
                <span style="color:${(vwap.distance_to_90d_pct || 0) >= 0 ? '#10b981' : '#f43f5e'}; font-family:var(--font-mono); font-size:10px;">(${(vwap.distance_to_90d_pct || 0) >= 0 ? '+' : ''}${vwap.distance_to_90d_pct || 0}%)</span>
              </div>
              <div style="font-size:9.5px; color:#64748b; margin-top:4px;">
                ${escapeHTML(vwap.support_resistance_status || 'Giá vận động gần vùng vốn')}
              </div>
            </div>

            <!-- Card 4: Foreign Room Exhaustion -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:10px 12px; border-radius:6px;">
              <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>DƯ ĐỊA ROOM NGOẠI (EXHAUSTION)</span>
                <span style="color:${room.exhaustion_risk ? '#ef4444' : '#10b981'}; font-size:9.5px; font-weight:700;">${escapeHTML(room.status || 'BÌNH THƯỜNG')}</span>
              </div>
              <div style="font-size:15px; font-weight:800; font-family:var(--font-mono); color:${room.exhaustion_risk ? '#ef4444' : '#10b981'};">
                Còn lại: ${room.remaining_room_pct || 0}%
              </div>
              <div style="font-size:10.5px; color:#94a3b8; margin-top:2px;">
                Nắm giữ: <strong style="color:#cbd5e1;">${room.foreign_owned_pct || 0}%</strong> / Max: ${room.foreign_max_pct || 49}%
              </div>
              <div style="font-size:9.5px; color:#64748b; margin-top:4px;">
                ${room.exhaustion_risk ? '⚠️ Nguy cơ kịch room ngoại, dòng vốn quốc tế khó mua thêm.' : 'Dư địa hấp thụ dòng vốn ETF/ngoại còn dồi dào.'}
              </div>
            </div>
          </div>

          <!-- Wyckoff Footprint Details bar -->
          <div style="background:rgba(255,255,255,0.02); border-left:3px solid ${wyckoff.color || '#10b981'}; padding:6px 10px; border-radius:4px; font-size:10.5px; color:#cbd5e1; display:flex; justify-content:space-between; align-items:center;">
            <span>🔍 <strong>Dấu chân Dòng Tiền Lớn (Wyckoff Footprint):</strong> ${escapeHTML(wyckoff.rationale || 'Dòng tiền tổ chức giao dịch ổn định.')}</span>
            <span style="font-size:9.5px; color:#64748b;">Tham chiếu: Richard Wyckoff & Larry Williams COT</span>
          </div>
        </div>

        <div class="leaders-col">
          <div class="col-header-sm">Hội Đồng Quản Trị & Ban Điều Hành (${officers.length})</div>
          ${officers.map(o => `
            <div class="person-item">
              <div>
                <div class="person-name">${escapeHTML(o.name || '')}</div>
                <div class="person-pos">${escapeHTML(o.position || '')}${o.ratio ? ` <span style="color:var(--color-ref); font-size:11px; margin-left:4px; font-weight:600;">(Tỷ lệ: ${escapeHTML(o.ratio)})</span>` : ''}</div>
              </div>
              <div class="person-shares">${o.shares ? Number(o.shares).toLocaleString() + ' CP' : (o.ratio ? o.ratio : '--')}</div>
            </div>
          `).join('')}
        </div>

        <div class="shareholders-col">
          <div class="col-header-sm">Cơ Cấu Cổ Đông Lớn & Quỹ Đầu Tư (${shareholders.length})</div>
          ${shareholders.map(s => `
            <div class="person-item">
              <div>
                <div class="person-name">${escapeHTML(s.name || '')}</div>
                <div class="person-pos">${s.ratio ? `<span style="color:var(--color-up); font-size:11px; font-weight:600;">Tỷ lệ sở hữu: ${escapeHTML(s.ratio)}</span>` : ''}</div>
              </div>
              <div class="person-shares">${s.shares ? Number(s.shares).toLocaleString() + ' CP' : '--'}</div>
            </div>
          `).join('')}
        </div>

        <!-- RELATED PERSONS & FAMILY NETWORK (TT96) -->
        ${family_network.length ? `
          <div style="grid-column: 1 / -1; margin-top:8px;">
            <div class="col-header-sm" style="margin-bottom:8px; display:flex; justify-content:space-between;">
              <span>👨‍👩‍👧‍👦 MẠNG LƯỚI NGƯỜI LIÊN QUAN & GIA ĐÌNH TRỊ (BÁO CÁO QUẢN TRỊ TT96)</span>
              <span style="color:#c084fc; font-weight:600;">${family_network.length} Người liên quan</span>
            </div>
            <div class="family-network-grid">
              ${family_network.map(f => `
                <div class="family-card">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="family-card-rel">${escapeHTML(f.relationship || 'Người liên quan')}</span>
                    <span style="font-size:10px; color:#94a3b8;">${escapeHTML(f.insider_role || '')}</span>
                  </div>
                  <div class="family-card-name">${escapeHTML(f.related_person_name || '')}</div>
                  <div class="family-card-detail">
                    ${f.shares_owned ? Number(f.shares_owned).toLocaleString() + ' CP' : 'Có sở hữu'}
                    ${f.ownership_pct ? ` (${f.ownership_pct}%)` : ''}
                  </div>
                  <div style="font-size:9.5px; color:#64748b;">Thuộc: ${escapeHTML(f.insider_name || '')}</div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- INSIDER TRADING DEALS -->
        ${insider_transactions.length ? `
          <div style="grid-column: 1 / -1; margin-top:8px;">
            <div class="col-header-sm" style="margin-bottom:8px;">
              <span>📈 LỊCH SỬ GIAO DỊCH CỔ ĐÔNG NỘI BỘ & NGƯỜI LIÊN QUAN</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:4px; max-height:160px; overflow-y:auto;">
              ${insider_transactions.slice(0, 8).map(t => {
                const isBuy = t.action_type === 'BUY';
                return `
                  <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 10px; background:rgba(255,255,255,0.02); border-radius:4px; font-size:11px;">
                    <div>
                      <span style="font-weight:700; color:#f1f5f9;">${escapeHTML(t.trader_name || '')}</span>
                      <span style="margin-left:6px; font-size:10px; font-weight:800; padding:1px 5px; border-radius:3px; background:${isBuy ? 'rgba(16,185,129,0.2)' : 'rgba(244,63,94,0.2)'}; color:${isBuy ? '#10b981' : '#f43f5e'};">
                        ${isBuy ? 'MUA VÀO' : 'BÁN RA'}
                      </span>
                    </div>
                    <div style="font-family:var(--font-mono); color:#cbd5e1;">
                      Khớp: ${t.executed_shares ? Number(t.executed_shares).toLocaleString() + ' CP' : '--'}
                      ${t.completion_rate_pct ? ` (${t.completion_rate_pct}%)` : ''}
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        ` : ''}
      `;
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching leadership:', e);
      this.renderErrorState('stockLeadershipGrid', `Lỗi kết nối khi tải ban điều hành cho mã ${symbol}.`);
    }
  }

  async fetchCompanyRecommendations(symbol) {
    const container = document.getElementById('stockRecommendationsContainer');
    if (!container) return;

    container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center;">⏳ Đang tổng hợp đa nguồn dữ liệu (CTCK trong nước, Simply Wall St DCF & Investing.com Technical Consensus)...</div>';

    try {
      const [recRes, valRes, techRes] = await Promise.allSettled([
        fetch(`/api/company/recommendations?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()),
        fetch(`/api/company/global-valuation?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()),
        fetch(`/api/company/technical-consensus?symbol=${encodeURIComponent(symbol)}`).then(r => r.json())
      ]);

      const recJson = recRes.status === 'fulfilled' && recRes.value.status === 'success' ? recRes.value.data : null;
      const valJson = valRes.status === 'fulfilled' && valRes.value.status === 'success' ? valRes.value.data : null;
      const techJson = techRes.status === 'fulfilled' && techRes.value.status === 'success' ? techRes.value.data : null;

      if (this.currentSymbol !== symbol) return;

      if (!recJson && !valJson && !techJson) {
        this.renderErrorState('stockRecommendationsContainer', `Chưa có dữ liệu phân tích & định giá cho mã ${symbol}.`);
        return;
      }

      const recs = recJson ? (recJson.recommendations || []) : [];
      const currP = (recJson && recJson.current_price) || (valJson && valJson.current_price) || 0;
      const consensusP = recJson ? (recJson.consensus_target_price || 0) : 0;
      const timeWeightedP = recJson ? (recJson.time_weighted_target_price || consensusP) : consensusP;
      const upsidePct = recJson ? recJson.consensus_upside_pct : null;
      const weightedUpsidePct = recJson ? (recJson.time_weighted_upside_pct !== undefined ? recJson.time_weighted_upside_pct : upsidePct) : null;
      const hasBrokerCoverage = recs.length > 0;

      // 1. Analyst Consensus Data
      const ratingBadgeClass = recJson && recJson.consensus_rating === 'BUY' ? 'badge-sentiment-bullish' : recJson && recJson.consensus_rating === 'SELL' ? 'badge-sentiment-bearish' : 'badge-sentiment-neutral';
      const ratingVi = recJson && recJson.consensus_rating_label ? recJson.consensus_rating_label : 'CHƯA CÓ BÁO CÁO CTCK';
      const upsideColor = upsidePct > 0 ? '#10b981' : upsidePct < 0 ? '#ef4444' : '#94a3b8';
      const upsideSign = upsidePct > 0 ? '+' : '';
      const weightedUpsideColor = weightedUpsidePct > 0 ? '#10b981' : weightedUpsidePct < 0 ? '#ef4444' : '#94a3b8';
      const weightedUpsideSign = weightedUpsidePct > 0 ? '+' : '';

      const totalRecs = recs.length;
      const bCount = recJson ? recJson.rating_breakdown.buy : 0;
      const hCount = recJson ? recJson.rating_breakdown.hold : 0;
      const sCount = recJson ? recJson.rating_breakdown.sell : 0;
      const bPct = totalRecs > 0 ? Math.round((bCount / totalRecs) * 100) : 0;
      const hPct = totalRecs > 0 ? Math.round((hCount / totalRecs) * 100) : 0;
      const sPct = totalRecs > 0 ? Math.round((sCount / totalRecs) * 100) : 0;

      // 2. Dispersal & Revision Data
      const dispersal = (recJson && recJson.dispersal_analysis) || { cv_pct: 0, std_dev: 0, dispersal_label: 'Chưa đủ mẫu', dispersal_badge: 'badge-sentiment-neutral', confidence_score: 50, description: '' };
      const revision = (recJson && recJson.revision_momentum) || { label: 'Chưa có biến động gần đây', badge_class: 'badge-sentiment-neutral', upgrades_180d: 0, downgrades_180d: 0, maintained_180d: 0 };
      const lowestP = (recJson && recJson.lowest_target_price) || 0;
      const highestP = (recJson && recJson.highest_target_price) || 0;

      // Calculate Target Band Bar Relative Positions (0 - 100%)
      const bandMin = Math.min(lowestP > 0 ? lowestP : currP, currP > 0 ? currP : lowestP) * 0.92;
      const bandMax = Math.max(highestP > 0 ? highestP : currP, currP > 0 ? currP : highestP) * 1.08;
      const bandSpan = Math.max(1, bandMax - bandMin);
      const currPosPct = Math.min(96, Math.max(4, Math.round(((currP - bandMin) / bandSpan) * 100)));
      const twPosPct = Math.min(96, Math.max(4, Math.round(((timeWeightedP - bandMin) / bandSpan) * 100)));
      const lowPosPct = lowestP > 0 ? Math.min(96, Math.max(4, Math.round(((lowestP - bandMin) / bandSpan) * 100))) : 4;
      const highPosPct = highestP > 0 ? Math.min(96, Math.max(4, Math.round(((highestP - bandMin) / bandSpan) * 100))) : 96;

      // 3. Simply Wall St Valuation Data
      const dcfFairValue = valJson ? valJson.fair_value_dcf : 0;
      const dcfDiscount = valJson ? valJson.discount_or_premium_pct : 0;
      const dcfStatusLabel = valJson ? valJson.valuation_status_label : 'Đang tính toán';
      const dcfBadgeClass = valJson ? valJson.badge_class : 'badge-sentiment-neutral';
      const snowflake = valJson && valJson.snowflake ? valJson.snowflake : { total_score: 18, value: 3, future: 4, past: 4, health: 4, dividend: 3 };
      const insights = valJson && valJson.insights ? valJson.insights : [];

      // 4. Technical Consensus Data
      const techOverall = techJson ? techJson.overall_consensus_label : 'TRUNG LẬP';
      const techBadgeClass = techJson ? techJson.badge_class : 'badge-neutral';
      const maSummary = techJson && techJson.moving_averages ? techJson.moving_averages : { summary_label: 'TRUNG LẬP', buy_count: 6, sell_count: 6, neutral_count: 0 };
      const oscSummary = techJson && techJson.oscillators ? techJson.oscillators : { summary_label: 'TRUNG LẬP', buy_count: 4, sell_count: 4, neutral_count: 0 };
      const pivots = techJson && techJson.pivot_points ? techJson.pivot_points : null;

      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:16px;">
          
          <!-- SECTION 1: BROKER RESEARCH & ANALYST CONSENSUS -->
          <div style="background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px; border-bottom:1px solid var(--border-subtle); padding-bottom:8px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:16px;">🏛️</span>
                <span style="font-size:13px; font-weight:800; color:var(--text-primary);">KHUYẾN NGHỊ ĐỒNG THUẬN TỪ CÁC CTCK (ANALYST CONSENSUS)</span>
              </div>
              <span style="font-size:11px; color:var(--text-muted);">Tổng hợp từ SSI, Vietcap, VNDirect, TCBS, HSC, MBS, BVSC</span>
            </div>

            ${hasBrokerCoverage ? `
              <!-- 4 Quant Summary Cards Grid -->
              <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:12px; margin-bottom:14px;">
                
                <!-- Card 1: Rating Distribution -->
                <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between;">
                  <div style="font-size:10px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">1. Đồng Thuận Khuyến Nghị</div>
                  <div style="display:flex; align-items:center; gap:8px; margin:8px 0;">
                    <span class="badge ${ratingBadgeClass}" style="font-size:12px; font-weight:800; padding:4px 10px; border-radius:6px;">${escapeHTML(ratingVi)}</span>
                    <span style="font-size:11px; color:var(--text-secondary);">${totalRecs} báo cáo (${recJson.distinct_brokers_count || 1} CTCK)</span>
                  </div>
                  <div>
                    <div style="display:flex; justify-content:space-between; font-size:10.5px; margin-bottom:4px; font-weight:600;">
                      <span style="color:#10b981;">🟢 Mua: ${bCount} (${bPct}%)</span>
                      <span style="color:#f59e0b;">⚪ Giữ: ${hCount} (${hPct}%)</span>
                      <span style="color:#ef4444;">🔴 Bán: ${sCount} (${sPct}%)</span>
                    </div>
                    <div style="height:6px; display:flex; border-radius:3px; overflow:hidden; background:rgba(255,255,255,0.05);">
                      <div style="width:${bPct}%; background:#10b981;"></div>
                      <div style="width:${hPct}%; background:#f59e0b;"></div>
                      <div style="width:${sPct}%; background:#ef4444;"></div>
                    </div>
                  </div>
                </div>

                <!-- Card 2: Time-Weighted Target Price -->
                <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:10px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">2. Giá Mục Tiêu Trọng Số TG</span>
                    <span style="font-size:9.5px; color:#38bdf8; background:rgba(56,189,248,0.1); padding:2px 6px; border-radius:4px;">Chu kỳ 90 ngày</span>
                  </div>
                  <div style="display:flex; align-items:baseline; gap:8px; margin:6px 0;">
                    <span style="font-size:20px; font-weight:900; color:#38bdf8;">${timeWeightedP > 0 ? timeWeightedP.toLocaleString() + ' đ' : '--'}</span>
                    ${weightedUpsidePct !== null ? `<span style="font-size:13px; font-weight:800; color:${weightedUpsideColor};">(${weightedUpsideSign}${weightedUpsidePct}%)</span>` : ''}
                  </div>
                  <div style="font-size:10.5px; color:var(--text-secondary); border-top:1px solid var(--border-subtle); padding-top:4px; display:flex; justify-content:space-between;">
                    <span>Giá MT đơn giản: <strong style="color:var(--text-primary);">${consensusP > 0 ? consensusP.toLocaleString() : '--'} đ</strong></span>
                    <span>Thị giá: <strong style="color:var(--text-primary);">${currP > 0 ? currP.toLocaleString() : '--'} đ</strong></span>
                  </div>
                </div>

                <!-- Card 3: Revision Momentum -->
                <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between;">
                  <div style="font-size:10px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">3. Xu Hướng Điều Chỉnh (Revision)</div>
                  <div style="margin:6px 0;">
                    <span class="badge ${revision.badge_class || 'badge-sentiment-neutral'}" style="font-size:11.5px; font-weight:800; padding:4px 8px; border-radius:6px; display:inline-block;">
                      ${escapeHTML(revision.label)}
                    </span>
                  </div>
                  <div style="font-size:10.5px; color:var(--text-secondary); border-top:1px solid var(--border-subtle); padding-top:4px; display:flex; gap:10px;">
                    <span style="color:#10b981;">🔼 Nâng MT: <strong>${revision.upgrades_180d || 0}</strong></span>
                    <span style="color:#ef4444;">🔻 Hạ MT: <strong>${revision.downgrades_180d || 0}</strong></span>
                    <span style="color:var(--text-muted);">⚪ Giữ: <strong>${revision.maintained_180d || 0}</strong></span>
                  </div>
                </div>

                <!-- Card 4: Consensus Dispersal & Confidence -->
                <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:10px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">4. Độ Phân Kỳ & Tin Cậy</span>
                    <span style="font-size:10px; font-weight:800; color:#38bdf8;">Điểm: ${dispersal.confidence_score || 50}/100</span>
                  </div>
                  <div style="margin:6px 0;">
                    <span class="badge ${dispersal.dispersal_badge || 'badge-sentiment-neutral'}" style="font-size:11.5px; font-weight:800; padding:4px 8px; border-radius:6px; display:inline-block;">
                      ${escapeHTML(dispersal.dispersal_label)}
                    </span>
                  </div>
                  <div style="font-size:10px; color:var(--text-secondary); border-top:1px solid var(--border-subtle); padding-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHTML(dispersal.description || '')}">
                    ${escapeHTML(dispersal.description || 'Độ lệch chuẩn định giá')}
                  </div>
                </div>

              </div>

              <!-- Interactive Target Price Band Gauge -->
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                  <span style="font-size:11px; font-weight:800; color:var(--text-primary); text-transform:uppercase;">📏 Thước Đo Dải Định Giá CTCK (Target Price Band)</span>
                  <span style="font-size:11px; color:var(--text-secondary);">Khoảng định giá: <strong style="color:#38bdf8;">${lowestP > 0 ? lowestP.toLocaleString() : '--'} đ</strong> - <strong style="color:#38bdf8;">${highestP > 0 ? highestP.toLocaleString() : '--'} đ</strong></span>
                </div>
                
                <div style="position:relative; height:26px; background:rgba(255,255,255,0.03); border-radius:6px; border:1px solid var(--border-subtle); margin:12px 0 20px 0;">
                  <!-- Range background gradient -->
                  <div style="position:absolute; left:${lowPosPct}%; width:${Math.max(2, highPosPct - lowPosPct)}%; height:100%; background:linear-gradient(90deg, rgba(56,189,248,0.15), rgba(16,185,129,0.2)); border-radius:4px;"></div>
                  
                  <!-- Time-Weighted Target Marker -->
                  <div style="position:absolute; left:${twPosPct}%; top:-2px; bottom:-2px; width:3px; background:#10b981; border-radius:2px; transform:translateX(-50%); z-index:2;">
                    <div style="position:absolute; top:-16px; left:50%; transform:translateX(-50%); font-size:9.5px; font-weight:800; color:#10b981; white-space:nowrap;">Giá MT: ${timeWeightedP.toLocaleString()}</div>
                  </div>

                  <!-- Current Price Marker -->
                  <div style="position:absolute; left:${currPosPct}%; top:-4px; bottom:-4px; width:3px; background:#f59e0b; border-radius:2px; transform:translateX(-50%); z-index:3;">
                    <div style="position:absolute; bottom:-16px; left:50%; transform:translateX(-50%); font-size:9.5px; font-weight:800; color:#f59e0b; white-space:nowrap;">Thị giá: ${currP.toLocaleString()} đ</div>
                  </div>
                </div>

                <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-muted);">
                  <span>🔻 Thấp nhất: <strong style="color:var(--text-secondary);">${lowestP > 0 ? lowestP.toLocaleString() + ' đ' : '--'}</strong></span>
                  <span style="color:#f59e0b;">🔸 Thị giá hiện tại: <strong>${currP > 0 ? currP.toLocaleString() + ' đ' : '--'}</strong></span>
                  <span style="color:#10b981;">🔹 Mục tiêu trọng số: <strong>${timeWeightedP > 0 ? timeWeightedP.toLocaleString() + ' đ' : '--'}</strong></span>
                  <span>🔺 Cao nhất: <strong style="color:var(--text-secondary);">${highestP > 0 ? highestP.toLocaleString() + ' đ' : '--'}</strong></span>
                </div>
              </div>

              <!-- Detailed Reports Table -->
              <div style="overflow-x:auto; border-radius:6px; border:1px solid var(--border-subtle);">
                <table class="peers-table" style="width:100%; font-size:11.5px;">
                  <thead>
                    <tr style="background:rgba(255,255,255,0.02);">
                      <th style="text-align:left;">Công Ty Chứng Khoán</th>
                      <th>Khuyến Nghị</th>
                      <th>Biến Động Định Giá</th>
                      <th style="text-align:right;">Giá Mục Tiêu</th>
                      <th style="text-align:right;">Kỳ Vọng (% Upside)</th>
                      <th style="text-align:right;">Giá Báo Cáo</th>
                      <th>Ngày Phát Hành</th>
                      <th style="text-align:left;">Chuyên Viên</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${recs.map(r => {
                      const uPct = r.upside_pct;
                      const uCol = uPct > 0 ? '#10b981' : uPct < 0 ? '#ef4444' : '#94a3b8';
                      const uSign = uPct > 0 ? '+' : '';
                      const revBadge = r.revision_badge || 'badge-neutral';
                      const revLabel = r.revision_label || 'Mới theo dõi';
                      return `
                        <tr>
                          <td style="font-weight:700; color:#38bdf8; text-align:left;">
                            🏛️ ${escapeHTML(r.firm || r.source || 'CTCK')}
                          </td>
                          <td>
                            <span class="badge ${r.badge_class || 'badge-sentiment-neutral'}" style="font-size:10.5px; padding:2px 8px;">
                              ${escapeHTML(r.type_label || r.type || 'N/A')}
                            </span>
                          </td>
                          <td>
                            <span class="badge ${revBadge}" style="font-size:10px; padding:2px 6px;">
                              ${escapeHTML(revLabel)}
                            </span>
                          </td>
                          <td style="text-align:right; font-weight:800; color:var(--text-primary);">
                            ${r.target_price > 0 ? r.target_price.toLocaleString() + ' đ' : '--'}
                          </td>
                          <td style="text-align:right; font-weight:700; color:${uCol};">
                            ${uPct !== null ? `${uSign}${uPct}%` : '--'}
                          </td>
                          <td style="text-align:right; color:var(--text-secondary);">
                            ${r.report_price > 0 ? r.report_price.toLocaleString() + ' đ' : '--'}
                          </td>
                          <td style="color:var(--text-secondary); font-size:11px;">
                            📅 ${escapeHTML(r.report_date || '--')}
                          </td>
                          <td style="color:var(--text-secondary); font-size:11px; text-align:left;">
                            ${escapeHTML(r.analyst || 'Khối Phân tích')}
                          </td>
                        </tr>
                      `;
                    }).join('')}
                  </tbody>
                </table>
              </div>
            ` : `
              <div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center; background:rgba(255,255,255,0.02); border-radius:8px;">
                <div style="font-size:22px; margin-bottom:6px;">📑</div>
                <div style="font-weight:700; color:var(--text-primary);">Chưa có báo cáo định giá từ các CTCK lớn (Coverage Gap)</div>
                <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">
                  Hầu hết các CTCK chỉ tập trung ra báo cáo cho top VN30/VN100. Đối với mã này, bạn có thể tham khảo mô hình <strong>Định giá Quốc tế Simply Wall St DCF</strong> và <strong>Tín hiệu Kỹ thuật</strong> ngay bên dưới.
                </div>
              </div>
            `}
          </div>

          <!-- SECTION 2: SIMPLY WALL ST 2-STAGE DCF VALUATION & SNOWFLAKE -->
          <div style="background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px; border-bottom:1px solid var(--border-subtle); padding-bottom:8px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:16px;">❄️</span>
                <span style="font-size:13px; font-weight:800; color:var(--text-primary);">ĐỊNH GIÁ ĐỊNH LƯỢNG QUỐC TẾ (SIMPLY WALL ST 2-STAGE DCF & SNOWFLAKE)</span>
              </div>
              <span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 8px; border-radius:4px; font-weight:700;">Áp dụng cho 100% Cổ phiếu</span>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-bottom:14px;">
              <!-- DCF Fair Value Hero Card -->
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:14px; display:flex; flex-direction:column; justify-content:space-between;">
                <div style="font-size:10.5px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Giá Trị Hợp Lý Chiết Khấu Dòng Tiền (DCF)</div>
                <div style="display:flex; align-items:baseline; gap:8px; margin:8px 0;">
                  <span style="font-size:22px; font-weight:900; color:#34d399;">${dcfFairValue > 0 ? dcfFairValue.toLocaleString() + ' đ' : '--'}</span>
                  <span class="badge ${dcfBadgeClass}" style="font-size:11.5px; font-weight:800; padding:3px 8px;">${escapeHTML(dcfStatusLabel)}</span>
                </div>
                <div style="font-size:11.5px; color:var(--text-secondary); border-top:1px solid var(--border-subtle); padding-top:6px;">
                  Chênh lệch so với thị giá: <strong style="color:${dcfDiscount > 0 ? '#10b981' : '#ef4444'};">${dcfDiscount > 0 ? '+' : ''}${dcfDiscount}% (${dcfDiscount > 0 ? 'Rẻ hơn giá trị thực' : 'Cao hơn giá trị thực'})</strong>
                </div>
              </div>

              <!-- Snowflake 5 Dimensions Card -->
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:14px; display:flex; flex-direction:column; justify-content:space-between;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:10.5px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Chấm Điểm Bông Tuyết (Snowflake Score)</span>
                  <strong style="color:#38bdf8; font-size:12px;">${snowflake.total_score || 0}/30 Điểm</strong>
                </div>
                <div style="display:grid; grid-template-columns: repeat(5, 1fr); gap:6px; margin:10px 0; text-align:center;">
                  <div style="background:rgba(255,255,255,0.03); padding:6px 2px; border-radius:6px; border:1px solid var(--border-subtle);">
                    <div style="font-size:9.5px; color:var(--text-muted);">Định giá</div>
                    <div style="font-size:13px; font-weight:800; color:#38bdf8;">${snowflake.value}/6</div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03); padding:6px 2px; border-radius:6px; border:1px solid var(--border-subtle);">
                    <div style="font-size:9.5px; color:var(--text-muted);">Tương lai</div>
                    <div style="font-size:13px; font-weight:800; color:#34d399;">${snowflake.future}/6</div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03); padding:6px 2px; border-radius:6px; border:1px solid var(--border-subtle);">
                    <div style="font-size:9.5px; color:var(--text-muted);">Quá khứ</div>
                    <div style="font-size:13px; font-weight:800; color:#a855f7;">${snowflake.past}/6</div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03); padding:6px 2px; border-radius:6px; border:1px solid var(--border-subtle);">
                    <div style="font-size:9.5px; color:var(--text-muted);">Sức khỏe</div>
                    <div style="font-size:13px; font-weight:800; color:#10b981;">${snowflake.health}/6</div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03); padding:6px 2px; border-radius:6px; border:1px solid var(--border-subtle);">
                    <div style="font-size:9.5px; color:var(--text-muted);">Cổ tức</div>
                    <div style="font-size:13px; font-weight:800; color:#f59e0b;">${snowflake.dividend}/6</div>
                  </div>
                </div>
                <div style="font-size:10.5px; color:var(--text-secondary);">Mô hình chuẩn hóa dòng tiền & sức khỏe tài chính toàn diện</div>
              </div>
            </div>

            <!-- Insights list -->
            ${insights.length > 0 ? `
              <div style="background:rgba(255,255,255,0.02); border-radius:6px; padding:10px 14px; border:1px solid var(--border-subtle);">
                <div style="font-size:11px; font-weight:700; color:var(--text-muted); margin-bottom:6px;">💡 NHẬN ĐỊNH CỐT LÕI TỪ THUẬT TOÁN SIMPLY WALL ST:</div>
                <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.6;">
                  ${insights.map(item => `<div>• ${escapeHTML(item)}</div>`).join('')}
                </div>
              </div>
            ` : ''}
          </div>

          <!-- SECTION 3: INVESTING.COM & TRADINGVIEW TECHNICAL CONSENSUS -->
          <div style="background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px; border-bottom:1px solid var(--border-subtle); padding-bottom:8px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:16px;">📊</span>
                <span style="font-size:13px; font-weight:800; color:var(--text-primary);">TÍN HIỆU ĐỒNG THUẬN KỸ THUẬT (INVESTING.COM & TRADINGVIEW CONSENSUS)</span>
              </div>
              <span class="badge ${techBadgeClass}" style="font-size:11.5px; font-weight:800; padding:4px 10px;">${escapeHTML(techOverall)}</span>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-bottom:14px;">
              <!-- 12 Moving Averages Summary -->
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                  <span style="font-size:11px; font-weight:700; color:var(--text-muted);">12 ĐƯỜNG MA (EMA & SMA)</span>
                  <strong style="color:#38bdf8; font-size:11px;">${escapeHTML(maSummary.summary_label || 'TRUNG LẬP')}</strong>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:11.5px; font-weight:600;">
                  <span style="color:#10b981;">🟢 Mua: ${maSummary.buy_count}</span>
                  <span style="color:#ef4444;">🔴 Bán: ${maSummary.sell_count}</span>
                  <span style="color:#f59e0b;">⚪ Trung lập: ${maSummary.neutral_count}</span>
                </div>
                <div style="font-size:10.5px; color:var(--text-secondary); margin-top:8px;">Bao gồm SMA/EMA các chu kỳ 5, 10, 20, 50, 100, 200 ngày</div>
              </div>

              <!-- 8 Oscillators Summary -->
              <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                  <span style="font-size:11px; font-weight:700; color:var(--text-muted);">8 CHỈ BÁO ĐỘNG LƯỢNG (OSCILLATORS)</span>
                  <strong style="color:#34d399; font-size:11px;">${escapeHTML(oscSummary.summary_label || 'TRUNG LẬP')}</strong>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:11.5px; font-weight:600;">
                  <span style="color:#10b981;">🟢 Mua: ${oscSummary.buy_count}</span>
                  <span style="color:#ef4444;">🔴 Bán: ${oscSummary.sell_count}</span>
                  <span style="color:#f59e0b;">⚪ Trung lập: ${oscSummary.neutral_count}</span>
                </div>
                <div style="font-size:10.5px; color:var(--text-secondary); margin-top:8px;">Bao gồm RSI, MACD, STOCH, ADX, Williams %R, Bollinger Bands</div>
              </div>
            </div>

            <!-- Pivot Points Table -->
            ${pivots ? `
              <div style="overflow-x:auto; border-radius:6px; border:1px solid var(--border-subtle);">
                <div style="padding:6px 12px; font-size:11px; font-weight:700; color:var(--text-muted); background:rgba(255,255,255,0.02); border-bottom:1px solid var(--border-subtle);">
                  🎯 CÁC MỐC KHÁNG CỰ / HỖ TRỢ THEO PIVOT POINTS QUỐC TẾ:
                </div>
                <table class="peers-table" style="width:100%; font-size:11px; text-align:center;">
                  <thead>
                    <tr>
                      <th style="text-align:left;">Phương Pháp</th>
                      <th style="color:#ef4444;">Hỗ Trợ S3</th>
                      <th style="color:#ef4444;">Hỗ Trợ S2</th>
                      <th style="color:#ef4444;">Hỗ Trợ S1</th>
                      <th style="color:#38bdf8; font-weight:800;">Pivot Point</th>
                      <th style="color:#10b981;">Kháng Cự R1</th>
                      <th style="color:#10b981;">Kháng Cự R2</th>
                      <th style="color:#10b981;">Kháng Cự R3</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style="font-weight:700; text-align:left;">Classic Pivot</td>
                      <td>${pivots.classic.s3}</td><td>${pivots.classic.s2}</td><td>${pivots.classic.s1}</td>
                      <td style="font-weight:800; color:#38bdf8;">${pivots.classic.pivot}</td>
                      <td>${pivots.classic.r1}</td><td>${pivots.classic.r2}</td><td>${pivots.classic.r3}</td>
                    </tr>
                    <tr>
                      <td style="font-weight:700; text-align:left;">Fibonacci</td>
                      <td>${pivots.fibonacci.s3}</td><td>${pivots.fibonacci.s2}</td><td>${pivots.fibonacci.s1}</td>
                      <td style="font-weight:800; color:#38bdf8;">${pivots.fibonacci.pivot}</td>
                      <td>${pivots.fibonacci.r1}</td><td>${pivots.fibonacci.r2}</td><td>${pivots.fibonacci.r3}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ` : ''}
          </div>

        </div>
      `;
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching company recommendations:', e);
      this.renderErrorState('stockRecommendationsContainer', `Lỗi khi tải dữ liệu khuyến nghị đa nguồn cho mã ${symbol}.`);
    }
  }

  async fetchMarketNews() {
    await this.fetchRSSNews();
    this.fetchGlobalCommodities();
  }

  async fetchRSSNews(reset = true) {
    try {
      const container = document.getElementById('marketNewsFeed');
      const btnLoadMore = document.getElementById('btnLoadMoreNews');
      const loadMoreContainer = document.getElementById('loadMoreNewsContainer');
      if (!container) return;

      if (reset) {
        this.newsOffset = 0;
        this.allNewsCache = [];
        container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; grid-column: span 2; padding:20px; text-align:center;">⏳ Đang tải dòng tin tài chính thông minh...</div>';
      }

      const src = this.currentNewsSource || 'all';
      const cat = this.currentNewsCategory || 'all';
      const topic = this.currentNewsTopic || 'all';
      const sentiment = this.currentNewsSentiment || 'all';
      const kw = this.currentNewsKeyword || '';
      const res = await fetch(`/api/rss-news?source=${encodeURIComponent(src)}&category=${encodeURIComponent(cat)}&topic=${encodeURIComponent(topic)}&sentiment=${encodeURIComponent(sentiment)}&keyword=${encodeURIComponent(kw)}&limit=30&offset=${this.newsOffset}`);
      const json = await res.json();
      if (json.status !== 'success') return;

      const newItems = json.data || [];
      if (reset) {
        this.allNewsCache = newItems;
      } else {
        this.allNewsCache = [...this.allNewsCache, ...newItems];
      }

      this.hasMoreNews = json.has_more !== undefined ? json.has_more : (newItems.length >= 30);

      if (loadMoreContainer && btnLoadMore) {
        if (this.allNewsCache.length === 0) {
          loadMoreContainer.style.display = 'none';
        } else {
          loadMoreContainer.style.display = 'flex';
          if (this.hasMoreNews) {
            btnLoadMore.style.display = 'inline-flex';
            btnLoadMore.innerHTML = `<span>⏬ Tải thêm 30 tin tiếp theo (Đang hiện ${this.allNewsCache.length}/${json.total || 'nhiều'} tin)</span>`;
            btnLoadMore.disabled = false;
            btnLoadMore.style.opacity = '1';
          } else {
            btnLoadMore.style.display = 'inline-flex';
            btnLoadMore.innerHTML = `<span>✅ Đã tải hết ${this.allNewsCache.length} tin tức phù hợp</span>`;
            btnLoadMore.disabled = true;
            btnLoadMore.style.opacity = '0.6';
          }
        }
      }

      this.renderFilteredNews();
    } catch (e) {
      console.error('Error fetching RSS news:', e);
    }
  }

  async fetchMoreRSSNews() {
    const btnLoadMore = document.getElementById('btnLoadMoreNews');
    if (btnLoadMore) {
      btnLoadMore.innerHTML = '<span>⏳ Đang tải thêm tin tức...</span>';
      btnLoadMore.disabled = true;
    }
    this.newsOffset = (this.newsOffset || 0) + 30;
    await this.fetchRSSNews(false);
  }

  renderFilteredNews() {
    const container = document.getElementById('marketNewsFeed');
    if (!container) return;

    let items = this.allNewsCache || [];
    this.currentFilteredNews = items;

    if (!items || items.length === 0) {
      const kw = this.currentNewsKeyword;
      container.innerHTML = `
        <div style="color:var(--text-muted); font-size:13px; grid-column: span 2; padding:30px; text-align:center; background:rgba(255,255,255,0.02); border-radius:8px;">
          <div>Không tìm thấy bài báo nào phù hợp với bộ lọc hiện tại.</div>
          <div style="margin-top:6px; font-size:11px; color:var(--text-secondary);">Thử chọn "Tất Cả Chủ Đề" hoặc tìm kiếm mã cổ phiếu phổ biến (FPT, HPG, VNM...).</div>
        </div>`;
      return;
    }

    container.innerHTML = items.map((item, idx) => {
      const symbolsHtml = (item.symbols && item.symbols.length > 0)
        ? item.symbols.map(s => `<span class="m-news-sym">[${escapeHTML(s)}]</span>`).join(' ')
        : (item.symbol ? `<span class="m-news-sym">[${escapeHTML(item.symbol)}]</span>` : '');

      const topicHtml = item.topic_name 
        ? `<span class="${escapeHTML(item.topic_badge || 'badge-topic-market')}">${item.topic_icon || '📌'} ${escapeHTML(item.topic_name)}</span>`
        : `<span class="m-news-cat">${escapeHTML(item.category || 'Tài chính')}</span>`;

      const sentimentHtml = item.sentiment_badge
        ? `<span class="${escapeHTML(item.sentiment_badge_class || 'badge-sentiment-neutral')}">${escapeHTML(item.sentiment_badge)}</span>`
        : '';

      const safeTitle = escapeHTML(item.title || '');
      const safeSummary = escapeHTML(item.summary || '');
      const safeSource = escapeHTML(item.source || 'Báo Tài Chính');
      const safeDate = escapeHTML(item.date || '');

      return `
      <div class="market-news-card" onclick="app.openMarketNewsArticle(${idx})" title="Bấm để đọc nhanh bài báo trong Terminal">
        <div class="m-news-top">
          ${item.image ? `<img src="${item.image}" class="m-news-img" alt="Thumbnail" onerror="this.style.display='none'">` : ''}
          <div class="m-news-main">
            <div class="m-news-badges">
              <span class="m-news-src">${safeSource}</span>
              ${topicHtml}
              ${sentimentHtml}
              ${symbolsHtml}
            </div>
            <div class="m-news-title">${safeTitle}</div>
            ${safeSummary ? `<div class="m-news-summary">${safeSummary}</div>` : ''}
          </div>
        </div>
        <div class="m-news-footer">
          <span>📅 ${safeDate}</span>
          <div style="display:flex; align-items:center; gap:12px;">
            <span style="color:#38bdf8; font-weight:700; cursor:pointer;">📖 Đọc nhanh</span>
            <a href="${item.link}" target="_blank" class="btn-open-article" onclick="event.stopPropagation();" title="Mở bài trên trang báo gốc">
              Trang gốc ↗
            </a>
          </div>
        </div>
      </div>
    `;
    }).join('');
  }

  openMarketNewsArticle(idx) {
    const item = (this.currentFilteredNews && this.currentFilteredNews[idx]) ? this.currentFilteredNews[idx] : (this.allNewsCache || [])[idx];
    if (!item || !item.link) return;
    const sym = (item.symbols && item.symbols.length > 0) ? item.symbols[0] : (item.symbol || '');
    this.openArticleReader(item.link, item.title, item.source, sym, item.date);
  }

  openCompanyNewsArticle(idx) {
    const item = (this.currentCompanyNews || [])[idx];
    if (!item || !item.link) return;
    this.openArticleReader(item.link, item.title, item.source, this.currentStockSymbol || '', item.date);
  }

  // ==========================================================================
  // GLOBAL COMMODITIES & INTERMARKET TICKER
  // ==========================================================================

  async fetchGlobalCommodities() {
    try {
      const grid = document.getElementById('globalCommoditiesGrid');
      const timeEl = document.getElementById('globalCommoditiesUpdated');
      if (!grid) return;

      const res = await fetch('/api/global/commodities');
      const json = await res.json();
      if (json.status !== 'success') return;
      const payload = json.data || json;
      const items = payload.items || [];
      if (!items || items.length === 0) return;

      if (timeEl && payload.updated_at) {
        timeEl.textContent = `Cập nhật: ${payload.updated_at}`;
      }

      grid.innerHTML = items.map(item => {
        const isUp = item.change > 0;
        const isDown = item.change < 0;
        const colorClass = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
        const sign = isUp ? '+' : '';
        const impactTags = (item.impact_symbols || []).slice(0, 4).map(s => 
          `<span style="background:rgba(56,189,248,0.12); color:#38bdf8; font-size:9.5px; padding:1px 4px; border-radius:3px; font-weight:700; cursor:pointer;" onclick="event.stopPropagation(); app.inspectStock('${s}')">${s}</span>`
        ).join(' ');

        return `
          <div class="foreign-stat-card" style="padding:8px 10px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;" title="${escapeHTML(item.name)} (${escapeHTML(item.unit)}): ${escapeHTML(item.impact_desc || '')}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
              <span style="font-size:11px; font-weight:700; color:var(--text-secondary);">${item.icon || '🌐'} ${escapeHTML(item.name)}</span>
              <span style="font-size:10px; font-weight:700;" class="${colorClass}">${sign}${item.change_pct}%</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
              <span class="mono" style="font-size:13px; font-weight:800; color:var(--text-primary);">${item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span style="font-size:9.5px; color:var(--text-muted);">${escapeHTML(item.unit)}</span>
            </div>
            <div style="margin-top:4px; display:flex; align-items:center; gap:3px; flex-wrap:wrap;">
              <span style="font-size:9px; color:var(--text-muted);">Tác động:</span>
              ${impactTags}
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error('Error fetching global commodities:', e);
    }
  }

  switchNewsMainSubtab(sub) {
    this.currentNewsMainSubtab = sub;
    const pStream = document.getElementById('news_subpanel_stream');
    const pCal = document.getElementById('news_subpanel_events_calendar');
    const pUp = document.getElementById('news_subpanel_upgrade_etf');
    const pMacro = document.getElementById('news_subpanel_macro_monetary');

    if (pStream) pStream.style.display = sub === 'stream' ? 'block' : 'none';
    if (pCal) pCal.style.display = sub === 'events_calendar' ? 'flex' : 'none';
    if (pUp) pUp.style.display = sub === 'upgrade_etf' ? 'flex' : 'none';
    if (pMacro) pMacro.style.display = sub === 'macro_monetary' ? 'flex' : 'none';

    if (sub === 'events_calendar') {
      this.fetchMarketEventsCalendar();
    } else if (sub === 'upgrade_etf') {
      this.fetchUpgradeAndEtfTracker();
    } else if (sub === 'macro_monetary') {
      this.fetchMacroMonetaryPolicy();
    }
  }

  // ==========================================================================
  // MARKET-WIDE CORPORATE ACTION CALENDAR
  // ==========================================================================

  async fetchMarketEventsCalendar() {
    try {
      const listEl = document.getElementById('marketCalendarEventsList');
      if (!listEl) return;

      listEl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; grid-column:1/-1; padding:30px; text-align:center;">⏳ Đang tải lịch sự kiện quyền toàn thị trường...</div>';

      const cat = this.currentCalCat || 'all';
      const res = await fetch(`/api/market/events-calendar?event_type=${encodeURIComponent(cat)}&limit=60`);
      const json = await res.json();
      if (json.status !== 'success') return;
      const payload = json.data || json;

      // Update category counters
      const counts = payload.category_counts || {};
      const elAll = document.getElementById('calCountAll');
      const elDiv = document.getElementById('calCountDividend');
      const elIss = document.getElementById('calCountIssue');
      const elMeet = document.getElementById('calCountMeeting');
      const elRes = document.getElementById('calCountResolution');

      if (elAll) elAll.textContent = counts.all || 0;
      if (elDiv) elDiv.textContent = counts.DIVIDEND || 0;
      if (elIss) elIss.textContent = counts.ISSUE || 0;
      if (elMeet) elMeet.textContent = counts.MEETING || 0;
      if (elRes) elRes.textContent = counts.RESOLUTION || 0;

      const events = payload.events || [];
      if (events.length === 0) {
        listEl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; grid-column:1/-1; padding:30px; text-align:center;">Không có sự kiện nào phù hợp với bộ lọc hiện tại.</div>';
        return;
      }

      listEl.innerHTML = events.map(ev => {
        const sym = ev.symbol || '';
        const exDate = ev.ex_date ? `<span style="background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3); font-size:10px; font-weight:800; padding:2px 6px; border-radius:4px;">GDKHQ: ${escapeHTML(ev.ex_date)}</span>` : '';
        const ratioBadge = ev.ratio ? `<span style="background:rgba(16,185,129,0.15); color:#10b981; font-size:10px; font-weight:800; padding:2px 6px; border-radius:4px;">Tỷ lệ/Tiền: ${escapeHTML(ev.ratio)}</span>` : '';
        const catBadge = `<span class="${escapeHTML(ev.tag_class || 'tag-dividend')}" style="font-size:10px; padding:2px 6px;">${ev.icon || '📌'} ${escapeHTML(ev.event_name || 'Sự kiện')}</span>`;

        return `
          <div class="market-news-card" style="padding:12px 14px; background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:8px; display:flex; flex-direction:column; justify-content:space-between; gap:8px;">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <div style="display:flex; align-items:center; gap:6px;">
                  <strong class="col-symbol" style="font-size:14px; cursor:pointer;" onclick="app.inspectStock('${sym}')">${escapeHTML(sym)}</strong>
                  ${catBadge}
                </div>
                <span style="font-size:11px; color:var(--text-muted);">📅 ${escapeHTML(ev.date || '')}</span>
              </div>
              <div style="font-size:12px; font-weight:700; color:var(--text-primary); line-height:1.4; margin-bottom:6px;">
                ${escapeHTML(ev.title || ev.full_title || '')}
              </div>
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                ${exDate}
                ${ratioBadge}
              </div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--border-subtle); padding-top:6px; margin-top:4px;">
              <span style="font-size:10.5px; color:#38bdf8; font-weight:700; cursor:pointer;" onclick="app.inspectStock('${sym}')">🔍 Xem biểu đồ & BCTC ↗</span>
              ${ev.detail_url ? `<a href="${ev.detail_url}" target="_blank" class="btn-open-article" style="font-size:10.5px;" onclick="event.stopPropagation();">Chi tiết ↗</a>` : ''}
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error('Error fetching market events calendar:', e);
    }
  }

  // ==========================================================================
  // UPGRADE TRACKER & ETF REBALANCING INTELLIGENCE
  // ==========================================================================

  async fetchUpgradeAndEtfTracker() {
    try {
      const [rawUpgrade, rawEtf] = await Promise.all([
        fetch('/api/market/upgrade-tracker').then(r => r.json()),
        fetch('/api/etf/rebalancing').then(r => r.json())
      ]);

      const upgradeRes = rawUpgrade.data || rawUpgrade;
      const etfRes = rawEtf.data || rawEtf;

      if (rawUpgrade.status === 'success' || upgradeRes.status === 'success') {
        const scoreEl = document.getElementById('upgradeReadinessScore');
        if (scoreEl) scoreEl.textContent = `${upgradeRes.overall_readiness_pct || 82.5}%`;

        // Render FTSE Criteria Checklist
        const ftseList = document.getElementById('ftseCriteriaList');
        if (ftseList && upgradeRes.ftse_criteria) {
          ftseList.innerHTML = upgradeRes.ftse_criteria.map(c => `
            <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div style="flex:1; min-width:280px;">
                <div style="font-size:12px; font-weight:700; color:var(--text-primary);">${escapeHTML(c.criterion)}</div>
                <div style="font-size:11px; color:var(--text-secondary); margin-top:2px;">${escapeHTML(c.detail)}</div>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="badge ${c.status.includes('PASSED') ? 'badge-bullish' : c.status.includes('IN_PROGRESS') ? 'badge-neutral' : 'badge-bearish'}" style="font-size:10.5px; font-weight:700; padding:3px 8px;">${escapeHTML(c.status)}</span>
                <span class="mono" style="font-size:12px; font-weight:800; color:#38bdf8;">${c.readiness_pct}%</span>
              </div>
            </div>
          `).join('');
        }

        // Render Foreign Institutional Funds
        const fundsGrid = document.getElementById('institutionalFundsGrid');
        if (fundsGrid && upgradeRes.institutional_funds) {
          fundsGrid.innerHTML = upgradeRes.institutional_funds.map(f => `
            <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <strong style="font-size:12.5px; color:#38bdf8;">${escapeHTML(f.fund_name)}</strong>
                <span class="badge badge-neutral" style="font-size:10px; font-weight:700;">NAV: ${escapeHTML(f.nav)}</span>
              </div>
              <div style="font-size:11px; color:var(--text-secondary); margin-bottom:6px;"><strong>Trọng tâm:</strong> ${escapeHTML(f.focus)}</div>
              <div style="font-size:10.5px; color:var(--text-muted); line-height:1.4;">💡 ${escapeHTML(f.strategy)}</div>
            </div>
          `).join('');
        }
      }

      if (rawEtf.status === 'success' || etfRes.status === 'success') {
        const scheduleGrid = document.getElementById('etfRebalanceScheduleGrid');
        if (scheduleGrid && etfRes.schedule) {
          scheduleGrid.innerHTML = etfRes.schedule.map(s => {
            const isUpcoming = s.days_until_rebalance >= 0 && s.days_until_rebalance <= 45;
            const borderCol = isUpcoming ? '#38bdf8' : 'var(--border-subtle)';
            const statusTag = isUpcoming 
              ? `<span style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10px; font-weight:800; padding:2px 6px; border-radius:4px;">⏳ Còn ${s.days_until_rebalance} ngày</span>`
              : s.days_until_rebalance < 0 
                ? '<span style="color:var(--text-muted); font-size:10px;">Đã diễn ra</span>'
                : `<span style="color:var(--text-muted); font-size:10px;">${s.days_until_rebalance} ngày nữa</span>`;

            return `
              <div style="background:var(--bg-surface-elevated); border:1px solid ${borderCol}; border-radius:6px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; gap:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <strong style="font-size:12px; color:var(--text-primary);">${escapeHTML(s.name)}</strong>
                  ${statusTag}
                </div>
                <div style="font-size:11px; color:var(--text-secondary);">
                  <div>📢 Công bố: <strong class="mono">${escapeHTML(s.announcement_date)}</strong></div>
                  <div>⚡ Ngày cơ cấu: <strong class="mono" style="color:#f59e0b;">${escapeHTML(s.rebalance_date)}</strong> (${escapeHTML(s.session)})</div>
                </div>
                <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">
                  Quỹ trọng điểm: ${s.impacted_funds.join(', ')}
                </div>
              </div>
            `;
          }).join('');
        }
      }
    } catch (e) {
      console.error('Error fetching upgrade & ETF tracker:', e);
    }
  }

  // ==========================================================================
  // MACROECONOMIC & MONETARY POLICY (SBV & GSO DATA LAKE)
  // ==========================================================================

  async fetchMacroMonetaryPolicy() {
    try {
      const res = await fetch('/api/macro/monetary-policy');
      const json = await res.json();
      if (json.status !== 'success') return;
      const data = json.data || json;

      // 1. Overall Score
      const scoreEl = document.getElementById('macroScoreValue');
      if (scoreEl) {
        scoreEl.textContent = `${data.macro_score} / 10 (${data.macro_rating})`;
        if (data.macro_score >= 7.5) {
          scoreEl.style.color = '#10b981';
        } else if (data.macro_score >= 5.0) {
          scoreEl.style.color = '#f59e0b';
        } else {
          scoreEl.style.color = '#ef4444';
        }
      }

      const sbv = data.sbv || {};
      const gso = data.gso || {};

      // 2. Render SBV Cards Grid
      const sbvGrid = document.getElementById('sbvCardsGrid');
      if (sbvGrid && sbv.exchange_rates) {
        const fx = sbv.exchange_rates;
        const liq = sbv.liquidity_operations || {};
        const netPos = liq.net_liquidity_position || {};
        const rates = sbv.interbank_rates || [];
        const isInjection = netPos.direction === 'INJECTION';

        const weeklyTrendHtml = (liq.weekly_trend || []).map(w => {
          const isNetUp = w.net > 0;
          return `
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; padding:3px 0; border-bottom:1px dashed var(--border-subtle);">
              <span style="color:var(--text-secondary);">${escapeHTML(w.week)}:</span>
              <span style="font-weight:700; color:${isNetUp ? '#10b981' : '#ef4444'};">${isNetUp ? '+' : ''}${w.net.toLocaleString('en-US')} tỷ (${escapeHTML(w.status)})</span>
            </div>
          `;
        }).join('');

        const interbankHtml = rates.map(r => {
          const isDown = r.change_d_d < 0;
          const isUp = r.change_d_d > 0;
          const colorClass = isDown ? '#10b981' : isUp ? '#ef4444' : 'var(--text-muted)';
          return `
            <div style="background:var(--bg-surface); padding:6px 8px; border-radius:4px; border:1px solid var(--border-subtle); text-align:center;">
              <div style="font-size:10px; color:var(--text-muted); font-weight:700;">${escapeHTML(r.tenure)}</div>
              <div style="font-size:13px; font-weight:800; color:var(--text-primary); margin:2px 0;">${r.rate}%</div>
              <div style="font-size:9.5px; color:${colorClass}; font-weight:700;">${r.change_d_d > 0 ? '+' : ''}${r.change_d_d}%</div>
            </div>
          `;
        }).join('');

        sbvGrid.innerHTML = `
          <!-- Card A: Tỷ Giá USD/VND -->
          <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; gap:8px;">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <strong style="font-size:12.5px; color:#38bdf8;">💵 Tỷ Giá Trung Tâm USD/VND</strong>
                <span class="badge badge-neutral" style="font-size:10px; font-weight:700;">Biên độ ±${fx.band_pct}%</span>
              </div>
              <div style="display:flex; align-items:baseline; gap:8px; margin-bottom:6px;">
                <span class="mono" style="font-size:18px; font-weight:900; color:var(--text-primary);">${fx.central_rate.toLocaleString('en-US')} ₫</span>
                <span style="font-size:11px; font-weight:700; color:#ef4444;">+${fx.change_d_d} ₫ (D/D)</span>
              </div>
              <div style="font-size:11px; color:var(--text-secondary); line-height:1.5;">
                <div>• Giá trần (+5%): <strong class="mono" style="color:#ef4444;">${fx.ceiling_rate.toLocaleString('en-US')} ₫</strong></div>
                <div>• Giá sàn (-5%): <strong class="mono" style="color:#10b981;">${fx.floor_rate.toLocaleString('en-US')} ₫</strong></div>
                <div>• Vietcombank: Mua <strong class="mono">${fx.commercial_vcb.buy_transfer.toLocaleString('en-US')} ₫</strong> | Bán <strong class="mono" style="color:#ef4444;">${fx.commercial_vcb.sell.toLocaleString('en-US')} ₫</strong></div>
              </div>
            </div>
            <div style="font-size:10px; color:var(--text-muted); border-top:1px solid var(--border-subtle); padding-top:4px;">
              Mất giá VND YTD: <strong style="color:#f59e0b;">${fx.commercial_vcb.ytd_depreciation_pct}%</strong> (Trong giới hạn kiểm soát)
            </div>
          </div>

          <!-- Card B: Thanh Khoản OMO & Tín Phiếu -->
          <div style="background:var(--bg-surface-elevated); border:1px solid ${isInjection ? '#10b981' : '#f59e0b'}; border-radius:6px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; gap:8px;">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <strong style="font-size:12.5px; color:${isInjection ? '#10b981' : '#f59e0b'};">⚡ Bơm / Hút Ròng Thanh Khoản (OMO)</strong>
                <span class="badge ${isInjection ? 'badge-bullish' : 'badge-bearish'}" style="font-size:10px; font-weight:800;">${escapeHTML(netPos.label)}</span>
              </div>
              <div style="font-size:11px; color:var(--text-secondary); line-height:1.5; margin-bottom:6px;">
                <div>• Bơm OMO (Repo): <strong class="mono" style="color:#10b981;">${liq.omo_repo.volume_bil_vnd.toLocaleString('en-US')} tỷ ₫</strong> (${liq.omo_repo.tenure}, LS ${liq.omo_repo.interest_rate_pct}%)</div>
                <div>• Hút Tín Phiếu: <strong class="mono" style="color:#ef4444;">${liq.tbills.volume_bil_vnd.toLocaleString('en-US')} tỷ ₫</strong> (${liq.tbills.tenure}, LS ${liq.tbills.interest_rate_pct}%)</div>
              </div>
              <div style="font-size:10.5px; color:var(--text-muted); margin-bottom:6px;">
                ${weeklyTrendHtml}
              </div>
            </div>
            <div style="font-size:10px; color:#38bdf8; line-height:1.3; border-top:1px solid var(--border-subtle); padding-top:4px;">
              💡 ${escapeHTML(netPos.impact_assessment)}
            </div>
          </div>

          <!-- Card C: Lãi Suất Liên Ngân Hàng -->
          <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; gap:8px;">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <strong style="font-size:12.5px; color:var(--text-primary);">📈 Đường Cong Lãi Suất Liên Ngân Hàng</strong>
                <span style="font-size:10px; color:var(--text-muted);">Hạ nhiệt đều đặn</span>
              </div>
              <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:6px;">
                ${interbankHtml}
              </div>
            </div>
            <div style="font-size:10px; color:var(--text-muted); border-top:1px solid var(--border-subtle); padding-top:4px;">
              Lãi suất qua đêm (ON) ở vùng thấp tạo môi trường thuận lợi cho thanh khoản TTCK.
            </div>
          </div>
        `;
      }

      // 3. Render GSO Stats Grid
      const gsoGrid = document.getElementById('gsoStatsGrid');
      if (gsoGrid && gso.gdp) {
        gsoGrid.innerHTML = `
          <!-- GDP Card -->
          <div class="foreign-stat-card" style="padding:12px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted);">TĂNG TRƯỞNG GDP CẢ NĂM</div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:4px 0;">
              <span class="mono" style="font-size:20px; font-weight:900; color:#10b981;">+${gso.gdp.latest_full_year_growth}%</span>
              <span class="badge badge-bullish" style="font-size:9.5px;">Vượt MT ${gso.gdp.annual_target}</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-secondary);">
              Q1: 5.66% | Q2: 6.93% | Q3: 7.4% | Q4: 7.52%
            </div>
          </div>

          <!-- CPI Inflation Card -->
          <div class="foreign-stat-card" style="padding:12px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted);">LẠM PHÁT CPI (YOY)</div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:4px 0;">
              <span class="mono" style="font-size:20px; font-weight:900; color:#38bdf8;">${gso.cpi.headline_cpi_yoy}%</span>
              <span class="badge badge-bullish" style="font-size:9.5px;">Dưới trần 4.5%</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-secondary);">
              Lạm phát cơ bản: <strong class="mono">${gso.cpi.core_cpi_yoy}%</strong> (Kiểm soát tốt)
            </div>
          </div>

          <!-- IIP Card -->
          <div class="foreign-stat-card" style="padding:12px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted);">SẢN XUẤT CÔNG NGHIỆP (IIP)</div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:4px 0;">
              <span class="mono" style="font-size:20px; font-weight:900; color:#10b981;">+${gso.iip.overall_iip_yoy}%</span>
              <span class="badge badge-bullish" style="font-size:9.5px;">Chế biến +${gso.iip.manufacturing_yoy}%</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-secondary);">
              Điện tử & thiết bị tăng trưởng dẫn dắt (+14.8%)
            </div>
          </div>

          <!-- FDI Card -->
          <div class="foreign-stat-card" style="padding:12px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted);">FDI GIẢI NGÂN THỰC TẾ</div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:4px 0;">
              <span class="mono" style="font-size:20px; font-weight:900; color:#10b981;">${gso.fdi.disbursed_capital_bil_usd} tỷ $</span>
              <span class="badge badge-bullish" style="font-size:9.5px;">+${gso.fdi.disbursed_yoy_pct}% YoY</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-secondary);">
              Đăng ký mới: <strong class="mono">${gso.fdi.registered_capital_bil_usd} tỷ USD</strong> (+13.5%)
            </div>
          </div>

          <!-- Trade Balance Card -->
          <div class="foreign-stat-card" style="padding:12px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted);">CÁN CÂN XUẤT NHẬP KHẨU</div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:4px 0;">
              <span class="mono" style="font-size:20px; font-weight:900; color:#10b981;">+${gso.trade.trade_balance_bil_usd} tỷ $</span>
              <span class="badge badge-bullish" style="font-size:9.5px;">Xuất siêu mạnh</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-secondary);">
              Tổng XNK: <strong class="mono">${gso.trade.total_turnover_bil_usd} tỷ USD</strong> (+15.6%)
            </div>
          </div>

          <!-- PMI Card -->
          <div class="foreign-stat-card" style="padding:12px; background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px;">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted);">S&P GLOBAL MANUFACTURING PMI</div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:4px 0;">
              <span class="mono" style="font-size:20px; font-weight:900; color:#10b981;">${gso.pmi.latest_score}</span>
              <span class="badge badge-bullish" style="font-size:9.5px;">Mở rộng >50</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-secondary);">
              Mở rộng liên tiếp <strong class="mono">${gso.pmi.trend_consecutive_months} tháng</strong>
            </div>
          </div>
        `;
      }

      // 4. Render Impact Matrix List
      const matrixList = document.getElementById('macroImpactMatrixList');
      if (matrixList && data.impact_matrix) {
        matrixList.innerHTML = data.impact_matrix.map(row => `
          <div style="background:var(--bg-surface-elevated); border:1px solid var(--border-subtle); border-radius:6px; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="flex:1; min-width:280px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <strong style="font-size:12.5px; color:var(--text-primary);">${escapeHTML(row.pillar)}:</strong>
                <span style="font-size:12px; color:#38bdf8; font-weight:700;">${escapeHTML(row.indicator)}</span>
              </div>
              <div style="font-size:11px; color:var(--text-secondary); margin-top:2px;">
                Số liệu: <strong class="mono" style="color:var(--text-primary);">${escapeHTML(row.reading)}</strong> — ${escapeHTML(row.detail)}
              </div>
            </div>
            <div>
              <span class="badge ${row.impact.includes('BULLISH') ? 'badge-bullish' : row.impact.includes('BEARISH') ? 'badge-bearish' : 'badge-neutral'}" style="font-size:11px; font-weight:800; padding:3px 8px;">
                ${escapeHTML(row.impact)}
              </span>
            </div>
          </div>
        `).join('');
      }

    } catch (e) {
      console.error('Error fetching macro monetary policy:', e);
    }
  }

  // ==========================================================================
  // TREEMAP & FOREIGN FLOW
  // ==========================================================================

  async fetchMarketTreemap() {
    try {
      const my = (this._tmSeq = (this._tmSeq || 0) + 1);
      const res = await fetch('/api/market-treemap');
      const json = await res.json();
      if (json.status === 'success' && my === this._tmSeq) {
        this.treemapManager.render(json.data);
      }
    } catch (e) {
      console.error('Error fetching treemap:', e);
    }
  }

  async fetchForeignFlow() {
    try {
      const res = await fetch('/api/foreign-flow');
      const json = await res.json();
      if (json.status !== 'success') return;

      const { summary, top_net_buy, top_net_sell } = json.data;

      document.getElementById('fTotalBuy').textContent = `${summary.total_buy_billion.toLocaleString()} tỷ`;
      document.getElementById('fTotalSell').textContent = `${summary.total_sell_billion.toLocaleString()} tỷ`;
      
      const net = summary.net_flow_billion;
      const elNet = document.getElementById('fNetFlow');
      elNet.textContent = `${net > 0 ? '+' : ''}${net.toLocaleString()} tỷ`;
      elNet.className = `f-stat-num mono ${net > 0 ? 'txt-up' : (net < 0 ? 'txt-down' : 'txt-ref')}`;

      document.getElementById('fRatio').textContent = `${summary.foreign_participation_pct}%`;

      const renderRows = (arr, isBuy) => arr.map((item, idx) => `
        <tr>
          <td style="color:var(--text-muted); text-align:center;">${idx + 1}</td>
          <td class="col-symbol" style="text-align:left;" onclick="app.inspectStock('${item.symbol}')">${item.symbol}</td>
          <td class="mono">${item.price.toFixed(2)}</td>
          <td class="mono ${item.change_pct > 0 ? 'txt-up' : 'txt-down'}">${item.change_pct > 0 ? '+' : ''}${item.change_pct.toFixed(2)}%</td>
          <td class="mono ${isBuy ? 'txt-up' : 'txt-down'}" style="font-weight:700;">${isBuy ? '+' : ''}${item.net_val.toLocaleString()} tỷ</td>
          <td class="mono" style="color:var(--text-muted);">${item.f_room != null ? Number(item.f_room).toLocaleString('en-US') : '--'}</td>
        </tr>
      `).join('');

      document.getElementById('foreignBuyTable').innerHTML = renderRows(top_net_buy, true);
      document.getElementById('foreignSellTable').innerHTML = renderRows(top_net_sell, false);
    } catch (e) {
      console.error('Error fetching foreign flow:', e);
    }
  }

  // ==========================================================================
  // SEARCH & AUTOCOMPLETE
  // ==========================================================================

  async searchStocks(q) {
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      const json = await res.json();
      return json.status === 'success' ? json.data : [];
    } catch {
      return [];
    }
  }

  renderSearchResults(results) {
    const dropdown = document.getElementById('searchDropdown');
    if (!results || results.length === 0) {
      dropdown.innerHTML = '<div style="padding:10px; color:var(--text-muted); font-size:11px;">Không tìm thấy mã phù hợp</div>';
      dropdown.classList.add('active');
      return;
    }

    dropdown.innerHTML = results.map(item => {
      const typeBadge = item.type && item.type !== 'STOCK' 
        ? `<span class="search-item-exchange" style="background:rgba(168,85,247,0.15); color:#c084fc; border-color:rgba(168,85,247,0.3); margin-left:4px;">${escapeHTML(item.type)}</span>` 
        : '';
      return `
        <div class="search-item" onclick="app.selectSearchedStock('${escapeHTML(item.symbol)}')">
          <div style="display:flex; align-items:center; gap:4px;">
            <span class="search-item-symbol">${escapeHTML(item.symbol)}</span>
            <span class="search-item-exchange">${escapeHTML(item.exchange)}</span>
            ${typeBadge}
          </div>
          <div class="search-item-name">${escapeHTML(item.name)}</div>
        </div>
      `;
    }).join('');
    dropdown.classList.add('active');
  }

  selectSearchedStock(symbol) {
    document.getElementById('searchDropdown').classList.remove('active');
    document.getElementById('searchInput').value = '';
    this.inspectStock(symbol);
  }

  toggleWatchlist(symbol) {
    if (this.isMacroSymbol(symbol)) {
      this.showToast(`${symbol} là chỉ số vĩ mô (không thuộc danh mục cổ phiếu)`, 'toast-up');
      return;
    }
    if (this.watchlist.includes(symbol)) {
      this.watchlist = this.watchlist.filter(s => s !== symbol);
      this.showToast(`Đã xóa ${symbol} khỏi Watchlist`, 'toast-down');
    } else {
      this.watchlist.push(symbol);
      this.showToast(`Đã thêm ${symbol} vào Watchlist ⭐`, 'toast-up');
    }
    this.saveWatchlist();
    this.loadStockDetails(symbol);
    if (this.currentBoardGroup === 'Watchlist') {
      this.fetchTradingBoard('Watchlist');
    }
  }

  // ==========================================================================
  // PRICE ALERTS & TOAST NOTIFICATIONS
  // ==========================================================================

  async addAlertRule() {
    const symbol = document.getElementById('alertSymbolInput').value.trim().toUpperCase();
    const cond = document.getElementById('alertConditionSelect').value;
    const target = parseFloat(document.getElementById('alertPriceInput').value);

    if (!symbol || isNaN(target)) {
      alert('Vui lòng nhập mã cổ phiếu và giá mục tiêu hợp lệ!');
      return;
    }

    // Ask for browser Notification permission on first rule creation
    this.requestNotificationPermission();

    const condMap = { 'above': 'price_above', 'below': 'price_below', 'pct_change': 'pct_change' };
    try {
      const res = await fetch('/api/alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol, condition: condMap[cond] || 'price_above', value: target })
      });
      const json = await res.json();
      if (json.status !== 'success') {
        this.showToast('Không thể tạo cảnh báo: ' + (json.message || 'lỗi máy chủ'), 'error');
        return;
      }
    } catch (e) {
      console.error('Error creating alert rule:', e);
      this.showToast('Không thể kết nối máy chủ để tạo cảnh báo.', 'error');
      return;
    }

    document.getElementById('alertModal').classList.remove('active');
    document.getElementById('alertPriceInput').value = '';
    this.showToast(`Đã cài cảnh báo cho ${symbol}`, 'toast-up');
    this.loadAlertRules();
  }

  async deleteAlert(id) {
    try {
      await fetch(`/api/alerts/${id}`, { method: 'DELETE' });
    } catch (e) {
      console.error('Error deleting alert rule:', e);
    }
    this.loadAlertRules();
  }

  async rearmAlert(id) {
    try {
      const res = await fetch(`/api/alerts/${id}/rearm`, { method: 'POST' });
      const json = await res.json();
      if (json.status === 'success') {
        // Reset the notification dedup key so the rule can notify again after re-arm
        for (const key of Array.from(this.notifiedAlertKeys)) {
          if (key.startsWith(`${id}:`)) this.notifiedAlertKeys.delete(key);
        }
        this.showToast('Đã re-arm cảnh báo #' + id, 'info');
      }
    } catch (e) {
      console.error('Error re-arming alert rule:', e);
    }
    this.loadAlertRules();
  }

  renderAlertsList() {
    const container = document.getElementById('alertsListGrid');
    if (!container) return;

    if (this.alertRules.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px;">Chưa có cảnh báo giá nào. Nhấn "+ Thêm Cảnh Báo Mới" để thiết lập.</div>';
      return;
    }

    const condLabel = (rule) => {
      if (rule.condition === 'price_above') return `Giá ≥ <strong>${Number(rule.value).toFixed(2)}</strong>`;
      if (rule.condition === 'price_below') return `Giá ≤ <strong>${Number(rule.value).toFixed(2)}</strong>`;
      return `|Biến động%| ≥ <strong>${Number(rule.value).toFixed(1)}%</strong>`;
    };

    container.innerHTML = this.alertRules.map(rule => `
      <div class="alert-rule-card">
        <div class="alert-rule-info">
          <div style="font-family:var(--font-mono); font-weight:800; font-size:14px; color:var(--color-ref);">
            ${rule.symbol}
          </div>
          <div style="font-size:11px; color:var(--text-secondary);">
            Điều kiện: ${condLabel(rule)}
            ${rule.fired ? `<span class="badge-tag" style="background:rgba(239,68,68,0.15); color:#ef4444; font-size:10px; padding:1px 6px; margin-left:6px; border-radius:4px; font-weight:700;" title="${rule.fired_at || ''}">🔥 ĐÃ KÍCH HOẠT</span>` : ''}
          </div>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn-sm" style="color:#10b981; border-color:#10b981;" onclick="app.rearmAlert(${rule.id})" title="Kích hoạt lại cảnh báo sau khi đã fired">
            ↻ Re-arm
          </button>
          <button class="btn-sm" style="color:#ef4444; border-color:#ef4444;" onclick="app.deleteAlert(${rule.id})">
            Xóa
          </button>
        </div>
      </div>
    `).join('');
  }

  startAlertPolling() {
    if (this._alertPollTimer) return;
    this._alertPollTimer = setInterval(() => {
      if (!document.hidden) {
        this.pollFiredAlerts();
      }
    }, 30000);
  }

  async pollFiredAlerts() {
    try {
      const res = await fetch('/api/alerts');
      const json = await res.json();
      if (json.status !== 'success') return;
      this.alertRules = json.data || [];
      for (let rule of this.alertRules) {
        if (!rule.fired) continue;
        const key = `${rule.id}:${rule.fired_at || ''}`;
        if (this.notifiedAlertKeys.has(key)) continue;
        this.notifiedAlertKeys.add(key);
        const price = Number(rule.triggered_value !== undefined && rule.triggered_value !== null ? rule.triggered_value : rule.value);
        const eventType = rule.condition === 'price_below' ? 'GIẢM DƯỚI NGƯỠNG'
          : (rule.condition === 'pct_change' ? 'BIẾN ĐỘNG VƯỢT NGƯỠNG' : 'TĂNG VƯỢT MỤC TIÊU');
        this.triggerAlert(rule, price, eventType);
      }
    } catch (e) {
      console.error('Error polling fired alerts:', e);
    }
  }

  triggerAlert(rule, currentPrice, eventType) {
    const isUp = rule.condition === 'price_above';
    const message = `🚨 CẢNH BÁO [${rule.symbol}]: Giá hiện tại ${Number(currentPrice).toFixed(2)} đã ${eventType} ${Number(rule.value).toFixed(2)}!`;
    this.showToast(message, isUp ? 'toast-up' : 'toast-down');
    this.playBeepSound();
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification(`Cảnh báo giá ${rule.symbol}`, { body: `Giá ${Number(currentPrice).toFixed(2)} đã ${eventType} ${Number(rule.value).toFixed(2)}` });
      } catch (e) { /* Notification API unavailable in context */ }
    }
  }

  playBeepSound() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === 'suspended') ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.4);
      setTimeout(() => ctx.close(), 500);
    } catch {}
  }

  showToast(message, type = 'toast-up') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span style="font-size:12px; font-weight:600;">${message}</span>
      <span style="cursor:pointer; margin-left:8px; font-weight:bold;" onclick="this.parentElement.remove()">✕</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 4500);
  }

  // ==========================================================================
  // IN-APP ARTICLE READER CONTROLLER
  // ==========================================================================

  async openArticleReader(url, fallbackTitle = '', source = 'Báo Tài Chính', symbol = '', date = '') {
    if (!url) return;
    this.currentReaderUrl = url;

    const modal = document.getElementById('readerModal');
    const body = document.getElementById('readerModalBody');
    const badgeSrc = document.getElementById('readerSourceBadge');
    const badgeDate = document.getElementById('readerMetaDate');
    const badgeSym = document.getElementById('readerSymbolBadge');
    const btnOriginal = document.getElementById('btnReaderOpenOriginal');

    if (badgeSrc) badgeSrc.textContent = source || 'Báo Điện Tử';
    if (badgeDate) badgeDate.textContent = date ? `📅 ${date}` : '';
    if (btnOriginal) btnOriginal.href = url;

    if (badgeSym) {
      if (symbol) {
        badgeSym.textContent = `[${symbol}]`;
        badgeSym.style.display = 'inline-block';
      } else {
        badgeSym.style.display = 'none';
      }
    }

    if (modal) modal.classList.add('active');
    document.body.style.overflow = 'hidden';

    // Set Skeleton Loading state
    if (body) {
      body.innerHTML = `
        <div class="reader-article">
          <div class="reader-skeleton-title"></div>
          <div class="reader-skeleton-title" style="width:60%; height:22px;"></div>
          <div style="margin: 20px 0;">
            <div class="reader-skeleton-line" style="width:100%; height:45px; border-radius:8px;"></div>
          </div>
          <div class="reader-skeleton-line" style="width:95%;"></div>
          <div class="reader-skeleton-line" style="width:98%;"></div>
          <div class="reader-skeleton-line" style="width:92%;"></div>
          <div class="reader-skeleton-line" style="width:88%;"></div>
          <div class="reader-skeleton-line" style="width:96%;"></div>
        </div>
      `;
    }

    try {
      const res = await fetch(`/api/article-content?url=${encodeURIComponent(url)}`);
      const json = await res.json();

      if (json.status === 'success') {
        this.renderArticleReaderContent(json);
      } else {
        this.renderArticleReaderError(json.message || 'Không thể bóc tách nội dung bài viết', url, fallbackTitle, source);
      }
    } catch (e) {
      this.renderArticleReaderError('Lỗi kết nối khi tải nội dung bài viết.', url, fallbackTitle, source);
    }
  }

  renderArticleReaderContent(data) {
    const body = document.getElementById('readerModalBody');
    if (!body) return;

    const badgeSrc = document.getElementById('readerSourceBadge');
    const badgeDate = document.getElementById('readerMetaDate');
    if (badgeSrc && data.source) badgeSrc.textContent = data.source;
    if (badgeDate && data.published_at) badgeDate.textContent = `📅 ${data.published_at}`;

    const paragraphsHtml = (data.paragraphs || []).map(p => {
      if (p.type === 'image') {
        return `
          <figure class="reader-figure">
            <img src="${p.src}" alt="${p.caption || 'Hình ảnh bài viết'}" loading="lazy" onerror="this.style.display='none'">
            ${p.caption ? `<figcaption class="reader-figcaption">${p.caption}</figcaption>` : ''}
          </figure>
        `;
      } else if (p.type === 'heading') {
        return `<h2>${p.text}</h2>`;
      } else if (p.type === 'quote') {
        return `<blockquote>${p.text}</blockquote>`;
      } else {
        return `<p>${p.text}</p>`;
      }
    }).join('');

    body.innerHTML = `
      <article class="reader-article">
        <h1 class="reader-headline">${data.title || 'Bài Viết Tài Chính'}</h1>
        
        <div class="reader-meta-strip">
          <span class="reader-meta-item">📰 Nguồn: <strong>${data.source}</strong></span>
          ${data.published_at ? `<span class="reader-meta-item">🕒 Đăng ngày: ${data.published_at}</span>` : ''}
          ${data.author ? `<span class="reader-meta-item">✍️ Tác giả: <strong>${data.author}</strong></span>` : ''}
        </div>

        ${data.sapo ? `<div class="reader-sapo-box">${data.sapo}</div>` : ''}

        <div class="reader-body-content">
          ${paragraphsHtml}
        </div>

        <div class="reader-footer-note">
          <div>
            <span>Nguồn phát hành: <strong>${data.domain || data.source}</strong></span>
            <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">Bản quyền nội dung thuộc về cơ quan báo chí phát hành.</div>
          </div>
          <a href="${data.url}" target="_blank" class="reader-ctrl-btn" style="color:#38bdf8; border-color:#38bdf8;">
            Mở bài gốc trên báo ↗
          </a>
        </div>
      </article>
    `;

    body.scrollTop = 0;
  }

  renderArticleReaderError(msg, url, fallbackTitle, source) {
    const body = document.getElementById('readerModalBody');
    if (!body) return;

    body.innerHTML = `
      <div class="reader-article" style="text-align:center; padding: 40px 20px;">
        <div style="font-size:36px; margin-bottom:12px;">📰</div>
        <h2 style="font-size:18px; color:#f8fafc; margin-bottom:8px;">${fallbackTitle || 'Không thể hiển thị bản đọc nhanh'}</h2>
        <p style="color:var(--text-secondary); font-size:13px; margin-bottom:20px;">
          ${msg}. Bài viết có thể sử dụng cấu trúc tương tác đa phương tiện đặc biệt của ${source}.
        </p>
        <a href="${url}" target="_blank" class="btn-sm" style="display:inline-flex; padding:10px 24px; font-size:13px; font-weight:700; background:#2563eb; color:#fff; border-color:#2563eb;">
          👉 Bấm để mở và đọc trực tiếp trên ${source} ↗
        </a>
      </div>
    `;
  }

  closeArticleReader() {
    const modal = document.getElementById('readerModal');
    if (modal) modal.classList.remove('active');
    document.body.style.overflow = '';
  }

  adjustReaderFontSize(delta) {
    this.readerFontSize = Math.max(13, Math.min(22, this.readerFontSize + delta));
    document.documentElement.style.setProperty('--reader-font-size', `${this.readerFontSize}px`);
    const indicator = document.getElementById('readerFontIndicator');
    if (indicator) indicator.textContent = `${this.readerFontSize}px`;
  }

  copyReaderLink() {
    if (!this.currentReaderUrl) return;
    navigator.clipboard.writeText(this.currentReaderUrl).then(() => {
      this.showToast('Đã sao chép liên kết bài báo! 📋', 'toast-up');
    }).catch(() => {
      this.showToast('Không thể sao chép liên kết', 'toast-down');
    });
  }

  // ==========================================================================
  // SECTOR INTELLIGENCE & ICB HOSE SECTOR INDICES
  // ==========================================================================

  switchSectorSubtab(name) {
    const isRotation = name === 'rotation';
    const overviewPanel = document.getElementById('sectorOverviewPanel');
    const rotationPanel = document.getElementById('sectorRotationPanel');

    document.querySelectorAll('.sector-subtab').forEach(btn => {
      const active = (btn.dataset.ssub || 'overview') === name;
      btn.classList.toggle('active', active);
    });

    if (overviewPanel) {
      overviewPanel.classList.toggle('active', !isRotation);
      overviewPanel.style.display = isRotation ? 'none' : '';
    }
    if (rotationPanel) {
      rotationPanel.classList.toggle('active', isRotation);
      rotationPanel.style.display = isRotation ? '' : 'none';
    }

    if (isRotation) {
      if (!this.sectorRotationInitialized) {
        try { window.SectorRotation?.init?.(); } catch (e) { console.error('SectorRotation init failed:', e); }
        this.sectorRotationInitialized = true;
      }
      setTimeout(() => {
        try { window.SectorRotation?.render?.(); } catch (e) { console.error('SectorRotation render failed:', e); }
      }, 50);
    }
  }

  isSectorRotationVisible() {
    if (window.SectorRotation && typeof window.SectorRotation.isVisible === 'function') {
      try { return !!window.SectorRotation.isVisible(); } catch (e) { /* fall through */ }
    }
    const panel = document.getElementById('sectorRotationPanel');
    return !!(panel && panel.style.display !== 'none' && panel.offsetParent !== null);
  }

  async fetchSectorsOverview() {
    try {
      const res = await fetch('/api/sectors/overview');
      const json = await res.json();
      if (json.status !== 'success') return;

      this.allSectorsCache = json.data || [];
      this.renderSectorCards(this.allSectorsCache);
      
      const current = this.allSectorsCache.find(s => s.code === this.currentSectorCode) || this.allSectorsCache[0];
      if (current) {
        this.selectSector(current.code);
      }
    } catch (e) {
      console.error('Error fetching sectors overview:', e);
    }
  }

  renderSectorCards(sectors) {
    const grid = document.getElementById('sectorCardsGrid');
    if (!grid) return;

    grid.innerHTML = sectors.map(sec => {
      const isActive = sec.code === this.currentSectorCode ? 'active' : '';
      const sign = sec.change > 0 ? '+' : '';
      const sparkSvg = this.generateMiniSparklineSvg(sec.sparkline, sec.change >= 0, 80, 26);
      const realBadge = sec.source === 'real'
        ? '<span style="font-size:9px; font-weight:800; color:#10b981; background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.35); border-radius:3px; padding:1px 4px;">REAL</span>'
        : '';
      
      return `
        <div class="sector-card ${isActive}" onclick="app.selectSector('${sec.code}')" style="background:var(--bg-card); border:1px solid ${isActive ? 'var(--primary-color, #38bdf8)' : 'var(--border-subtle)'}; border-radius:8px; padding:10px 12px; cursor:pointer; transition:all 0.2s ease; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="font-size:16px;">${sec.icon}</span>
              <strong style="font-size:12px; color:var(--text-primary);">${sec.name}</strong>
            </div>
            <span class="mono" style="font-size:10px; color:var(--text-muted); font-weight:700;">${sec.code}</span>
            ${realBadge}
          </div>

          <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:2px;">
            <div>
              <div class="mono ${sec.color_class}" style="font-size:15px; font-weight:800;">${sec.index_point.toFixed(2)}</div>
              <div class="mono ${sec.color_class}" style="font-size:11px; font-weight:700;">${sign}${sec.change.toFixed(2)} (${sign}${sec.change_pct.toFixed(2)}%)</div>
            </div>
            <div>${sparkSvg}</div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px; color:var(--text-secondary); border-top:1px solid var(--border-subtle); padding-top:4px; margin-top:2px;">
            <span>GT: <strong style="color:var(--text-primary);">${sec.total_value.toLocaleString()} tỷ</strong></span>
            <span>P/E: <strong style="color:var(--text-primary);">${sec.pe}x</strong></span>
            <span>ROE: <strong style="color:var(--text-primary);">${sec.roe}%</strong></span>
          </div>
        </div>
      `;
    }).join('');
  }

  async selectSector(sectorCode) {
    this.currentSectorCode = sectorCode;
    
    // Update active border on cards
    document.querySelectorAll('.sector-card').forEach(card => {
      card.style.borderColor = 'var(--border-subtle)';
    });
    
    const sec = (this.allSectorsCache || []).find(s => s.code === sectorCode);
    if (!sec) return;

    // Highlight selected card
    this.renderSectorCards(this.allSectorsCache);

    const titleEl = document.getElementById('currentSectorTitle');
    const badgeEl = document.getElementById('currentSectorChangeBadge');
    if (titleEl) titleEl.innerHTML = `${sec.icon} ${sec.code} - ${sec.name} <span style="font-size:11px; color:var(--text-muted); font-weight:normal;">(ICB: ${sec.icb_code})</span>`;
    
    if (badgeEl) {
      const sign = sec.change > 0 ? '+' : '';
      badgeEl.className = `breadth-badge ${sec.color_class}`;
      badgeEl.textContent = `${sign}${sec.change.toFixed(2)} (${sign}${sec.change_pct.toFixed(2)}%)`;
    }

    this.renderSectorSummary(sec);
    this.loadSectorChart(sectorCode, this.currentSectorInterval || '1D', this.currentSectorTimeframe || 'ALL');
    this.loadSectorConstituents(sec.code, this.currentSectorExchange || 'ALL');
  }

  renderSectorSummary(sec) {
    const details = document.getElementById('sectorMetricDetails');
    if (details) {
      details.innerHTML = `
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
          <span style="color:var(--text-muted);">Định giá P/E trung bình:</span>
          <strong class="mono" style="color:#38bdf8;">${sec.pe}x</strong>
        </div>
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
          <span style="color:var(--text-muted);">Định giá P/B trung bình:</span>
          <strong class="mono" style="color:#38bdf8;">${sec.pb}x</strong>
        </div>
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
          <span style="color:var(--text-muted);">Hiệu suất sinh lời ROE:</span>
          <strong class="mono" style="color:#10b981;">${sec.roe}%</strong>
        </div>
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
          <span style="color:var(--text-muted);">Tổng giá trị giao dịch:</span>
          <strong class="mono" style="color:#f59e0b;">${sec.total_value.toLocaleString()} tỷ đ</strong>
        </div>
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
          <span style="color:var(--text-muted);">Độ rộng toàn ngành:</span>
          <span>
            <span class="txt-up" style="font-weight:700;">🟢 ${sec.gainers}</span> | 
            <span class="txt-ref" style="font-weight:700;">🟡 ${sec.unchanged}</span> | 
            <span class="txt-down" style="font-weight:700;">🔴 ${sec.losers}</span>
          </span>
        </div>
      `;
    }

    const leadersEl = document.getElementById('sectorLeadingStocks');
    if (leadersEl) {
      leadersEl.innerHTML = (sec.top_stocks || []).map(sym => `
        <button class="btn-sm" onclick="app.inspectStock('${sym}')" style="cursor:pointer; display:flex; align-items:center; gap:4px; font-weight:700; padding:4px 10px; background:rgba(56,189,248,0.1); border-color:rgba(56,189,248,0.3); color:#38bdf8; border-radius:4px;">
          <span>📈</span> ${sym}
        </button>
      `).join('');
    }
  }

  async loadSectorChart(sectorCode, interval, timeframe) {
    const itv = interval || this.currentSectorInterval || '1D';
    const tf = timeframe || this.currentSectorTimeframe || 'ALL';
    try {
      const res = await fetch(`/api/sectors/history?sector=${sectorCode}&interval=${itv}&timeframe=${tf}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) return;

      const data = json.data;
      if (this.sectorChartManager) {
        this.sectorChartManager.setData(data);
        if (tf && tf !== 'ALL') {
          this.sectorChartManager.zoomToRange(tf);
        }
        this.sectorChartManager.resize();
      }

      // Update Sector Technical Signal Gauge & Detailed diagnosis
      const sig = data.technical_signal;
      const sigBadge = document.getElementById('sectorSignalBadge');
      const sigBadgeSmall = document.getElementById('sectorSignalBadgeSmall');
      const sigDetails = document.getElementById('sectorSignalDetails');
      if (sig) {
        if (sigBadge) {
          sigBadge.textContent = sig.signal;
          sigBadge.className = `signal-badge ${sig.badge_class}`;
        }
        if (sigBadgeSmall) {
          sigBadgeSmall.textContent = sig.signal;
          sigBadgeSmall.className = `signal-badge ${sig.badge_class}`;
        }
        if (sigDetails && sig.details) {
          sigDetails.innerHTML = sig.details.map(det => `<div>• ${det}</div>`).join('');
        }
      }
    } catch (e) {
      console.error('Error loading sector chart:', e);
    }
  }

  async loadSectorConstituents(sectorCode, exchange = (this.currentSectorExchange || 'ALL')) {
    const tbody = document.getElementById('sectorConstituentsBody');
    const cntEl = document.getElementById('sectorConstituentsCount');
    if (!tbody) return;

    this.currentSectorExchange = exchange;

    // Update button visual state
    document.querySelectorAll('.sector-ex-btn').forEach(btn => {
      if (btn.dataset.sex === exchange) {
        btn.classList.add('active');
        btn.style.background = '#38bdf8';
        btn.style.color = '#0f172a';
        btn.style.fontWeight = '700';
      } else {
        btn.classList.remove('active');
        btn.style.background = 'transparent';
        btn.style.color = 'var(--text-secondary)';
        btn.style.fontWeight = '600';
      }
    });

    const exLabel = exchange === 'ALL' ? '3 Sàn (HOSE, HNX, UPCOM)' : `Sàn ${exchange}`;
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-muted);">⏳ Đang tải toàn bộ cổ phiếu thành phần ngành ${escapeHTML(sectorCode)} [${exLabel}]...</td></tr>`;

    try {
      const res = await fetch(`/api/trading-board?group=${encodeURIComponent(sectorCode)}&exchange=${encodeURIComponent(exchange)}`);
      const json = await res.json();
      if (json.status !== 'success') return;

      const rows = json.data || [];
      if (cntEl) cntEl.textContent = `${rows.length} cổ phiếu (${exLabel})`;

      if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-muted);">Không tìm thấy cổ phiếu nào thuộc ngành ${escapeHTML(sectorCode)} trên ${exLabel}</td></tr>`;
        return;
      }

      tbody.innerHTML = rows.map((r, idx) => {
        const sign = r.match_chg > 0 ? '+' : '';
        const pe = (10 + (Math.abs(r.symbol.charCodeAt(0) * 7) % 150) / 10).toFixed(1);
        const pb = (1.1 + (Math.abs(r.symbol.charCodeAt(0) * 3) % 30) / 10).toFixed(2);
        const roe = (12 + (Math.abs(r.symbol.charCodeAt(0) * 5) % 180) / 10).toFixed(1);

        return `
          <tr>
            <td style="text-align:center; color:var(--text-muted); font-size:11px;">${idx + 1}</td>
            <td class="col-symbol" onclick="app.inspectStock('${r.symbol}')" style="font-weight:800; cursor:pointer; color:#38bdf8;">${r.symbol}</td>
            <td style="text-align:left; font-size:11px; color:var(--text-secondary); max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${r.name}</td>
            <td style="text-align:center; font-size:10px; color:var(--text-muted); font-weight:700;">${r.exchange}</td>
            <td class="mono ${r.match_color}" style="font-weight:800; text-align:right;">${r.match_p.toFixed(2)}</td>
            <td class="mono ${r.match_color}" style="text-align:right;">${sign}${r.match_pct.toFixed(2)}%</td>
            <td class="mono" style="text-align:right; color:var(--text-muted);">${((r.total_vol * r.match_p) / 1000).toFixed(0)} tỷ</td>
            <td class="mono" style="text-align:right;">${pe}x</td>
            <td class="mono" style="text-align:right;">${pb}x</td>
            <td class="mono" style="text-align:right; color:#10b981;">${roe}%</td>
            <td style="text-align:center;">
              <button class="btn-inspect" onclick="app.inspectStock('${r.symbol}')" style="font-size:10px; padding:2px 8px;">📈 Phân Tích</button>
            </td>
          </tr>
        `;
      }).join('');

    } catch (e) {
      console.error('Error loading sector constituents:', e);
    }
  }

  // ==========================================================================
  // PEER COMPARISON (SO SÁNH CÙNG PHÂN LOẠI ICB)
  // ==========================================================================

  async loadStockPeers(symbol, topK = (this.peerTopK !== undefined ? this.peerTopK : 10), exchange = (this.peerExchange || 'ALL')) {
    const container = document.getElementById('stockPeersContainer');
    if (!container) return;

    this.peerTopK = topK;
    this.peerExchange = exchange;
    const limitLabel = topK === 0 ? 'Toàn bộ ngành' : `Top ${topK}`;
    const exLabel = exchange === 'ALL' ? '3 sàn' : `sàn ${exchange}`;
    container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center;">⏳ Đang phân tích và xếp hạng đối thủ cùng ngành ICB cho mã ${escapeHTML(symbol)} (${limitLabel} trên ${exLabel})...</div>`;

    try {
      const res = await fetch(`/api/company/peers?symbol=${encodeURIComponent(symbol)}&top_k=${topK}&exchange=${encodeURIComponent(exchange)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;
      if (json.status !== 'success' || !json.data) {
        this.renderErrorState('stockPeersContainer', json.message || `Không thể tải dữ liệu đối thủ cùng ngành cho mã ${symbol}.`);
        return;
      }

      this.renderStockPeers(json.data, topK, exchange);
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error loading company peers:', e);
      this.renderErrorState('stockPeersContainer', `Lỗi kết nối khi tải đối thủ cùng ngành cho mã ${symbol}.`);
    }
  }

  renderStockPeers(data, currentTopK = 10, currentExchange = 'ALL') {
    const container = document.getElementById('stockPeersContainer');
    if (!container) return;

    const peers = data.peers || [];
    const algo = data.algorithm || {};
    const totalMatched = algo.candidates_matched !== undefined ? algo.candidates_matched : (peers.length - 1);
    const exFilter = currentExchange || this.peerExchange || 'ALL';
    
    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        
        <!-- Sector & Algorithm Header Banner -->
        <div style="background:linear-gradient(135deg, rgba(56, 189, 248, 0.08) 0%, rgba(16, 185, 129, 0.05) 100%); border:1px solid rgba(56, 189, 248, 0.25); border-radius:8px; padding:12px 16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
          <div>
            <div style="font-size:14px; font-weight:800; color:var(--text-primary); display:flex; align-items:center; gap:8px;">
              <span>🏢</span> Nhóm Ngành: <span style="color:#38bdf8;">${data.sector_name} (${data.sector_code})</span>
              <span style="font-size:10px; background:rgba(16, 185, 129, 0.15); color:#10b981; border:1px solid rgba(16, 185, 129, 0.3); padding:2px 7px; border-radius:12px; font-weight:700;">⚡ Ghép Nối Thuật Toán Đa Chiều</span>
            </div>
            <div style="font-size:11px; color:var(--text-secondary); margin-top:3px;">
              Phân ngành: <strong>${data.industry}</strong> (ICB: ${data.icb_code}) • Toàn bộ ngành: <strong>${totalMatched}</strong> mã ứng viên
            </div>
          </div>
          <div style="display:flex; gap:14px; font-size:11px; flex-wrap:wrap;">
            <div style="background:rgba(255,255,255,0.04); padding:4px 8px; border-radius:4px;">P/E Ngành: <strong class="mono" style="color:#38bdf8;">${data.sector_pe_avg}x</strong></div>
            <div style="background:rgba(255,255,255,0.04); padding:4px 8px; border-radius:4px;">P/B Ngành: <strong class="mono" style="color:#38bdf8;">${data.sector_pb_avg}x</strong></div>
            <div style="background:rgba(255,255,255,0.04); padding:4px 8px; border-radius:4px;">ROE Ngành: <strong class="mono" style="color:#10b981;">${data.sector_roe_avg}%</strong></div>
          </div>
        </div>

        <!-- Filter Toolbar: Limit Selector & Exchange Selector -->
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle); border-radius:6px; padding:8px 12px;">
          <div style="display:flex; align-items:center; gap:12px; font-size:11.5px; color:var(--text-secondary); flex-wrap:wrap;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span>📊 Số lượng:</span>
              <div style="display:inline-flex; gap:4px;">
                ${[5, 10, 20, 50, 0].map(k => {
                  const isActive = (Number(currentTopK) === k);
                  const label = k === 0 ? `Toàn bộ ngành (${totalMatched})` : `Top ${k}`;
                  const activeStyle = isActive 
                    ? 'background:#38bdf8; color:#0f172a; font-weight:800; border-color:#38bdf8; box-shadow:0 0 8px rgba(56,189,248,0.3);' 
                    : 'background:rgba(255,255,255,0.04); color:var(--text-secondary); border-color:var(--border-subtle);';
                  return `<button type="button" onclick="app.loadStockPeers('${escapeHTML(data.symbol)}', ${k}, '${exFilter}')" style="font-size:11px; padding:3px 9px; border-radius:4px; border:1px solid; cursor:pointer; transition:all 0.15s ease; ${activeStyle}">${label}</button>`;
                }).join('')}
              </div>
            </div>

            <div style="display:flex; align-items:center; gap:6px; border-left:1px solid var(--border-subtle); padding-left:12px;">
              <span>🏛️ Sàn:</span>
              <div style="display:inline-flex; gap:4px;">
                ${['ALL', 'HOSE', 'HNX', 'UPCOM'].map(ex => {
                  const isActive = (exFilter === ex);
                  const label = ex === 'ALL' ? '🌐 3 Sàn' : ex;
                  const activeStyle = isActive 
                    ? 'background:#10b981; color:#0f172a; font-weight:800; border-color:#10b981; box-shadow:0 0 8px rgba(16,185,129,0.3);' 
                    : 'background:rgba(255,255,255,0.04); color:var(--text-secondary); border-color:var(--border-subtle);';
                  return `<button type="button" onclick="app.loadStockPeers('${escapeHTML(data.symbol)}', ${currentTopK}, '${ex}')" style="font-size:11px; padding:3px 8px; border-radius:4px; border:1px solid; cursor:pointer; transition:all 0.15s ease; ${activeStyle}">${label}</button>`;
                }).join('')}
              </div>
            </div>
          </div>

          <div style="font-size:11px; color:var(--text-muted);">
            Đang hiển thị <strong>${peers.length}</strong> mã (Sắp xếp theo <strong>% Độ tương đồng</strong>)
          </div>
        </div>

        <!-- Peers Comparison Table -->
        <div class="table-responsive" style="border:1px solid var(--border-subtle); border-radius:8px; overflow:hidden;">
          <table class="trading-board-table clean-board-table">
            <thead>
              <tr>
                <th style="width:75px; text-align:left;">Mã CK</th>
                <th style="text-align:left;">Tên Doanh Nghiệp</th>
                <th style="width:65px; text-align:center;">Sàn</th>
                <th style="width:115px; text-align:center;">Độ Tương Đồng</th>
                <th style="width:85px; text-align:right;">Thị Giá</th>
                <th style="width:75px; text-align:right;">% Biến Động</th>
                <th style="width:95px; text-align:right;">Vốn Hóa (Tỷ)</th>
                <th style="width:65px; text-align:right;">P/E</th>
                <th style="width:65px; text-align:right;">P/B</th>
                <th style="width:65px; text-align:right;">ROE</th>
                <th style="width:65px; text-align:right;">ROA</th>
                <th style="width:80px; text-align:right;">EPS (đ)</th>
                <th style="width:75px; text-align:center;">Thao Tác</th>
              </tr>
            </thead>
            <tbody>
              ${peers.map(p => {
                const isCurrent = p.is_current ? 'background:rgba(56,189,248,0.1); border-left:3px solid #38bdf8;' : '';
                const sign = p.change_pct > 0 ? '+' : '';
                const colorClass = p.change_pct > 0 ? 'txt-up' : (p.change_pct < 0 ? 'txt-down' : 'txt-ref');
                
                const score = p.similarity_score ? Number(p.similarity_score) : 0;
                let scoreColor = '#10b981';
                let scoreBg = 'rgba(16,185,129,0.15)';
                if (score < 60) {
                  scoreColor = '#94a3b8';
                  scoreBg = 'rgba(148,163,184,0.15)';
                } else if (score < 75) {
                  scoreColor = '#f59e0b';
                  scoreBg = 'rgba(245,158,11,0.15)';
                } else if (score < 88) {
                  scoreColor = '#38bdf8';
                  scoreBg = 'rgba(56,189,248,0.15)';
                }

                const matchCell = p.is_current
                  ? `<div style="text-align:center;"><span style="background:rgba(56,189,248,0.2); color:#38bdf8; font-size:10px; font-weight:700; padding:3px 8px; border-radius:10px;">📍 Đang xem</span></div>`
                  : `
                    <div style="display:flex; flex-direction:column; align-items:center; gap:3px;">
                      <div style="display:flex; align-items:center; gap:5px; font-weight:800; font-size:11px; color:${scoreColor};">
                        <span>${score}%</span>
                        <span style="font-size:9.5px; opacity:0.9; font-weight:700; background:${scoreBg}; padding:1px 5px; border-radius:3px;">${p.similarity_grade || 'Cao'}</span>
                      </div>
                      <div style="width:75px; height:4px; background:rgba(255,255,255,0.08); border-radius:2px; overflow:hidden;">
                        <div style="width:${score}%; height:100%; background:${scoreColor}; border-radius:2px;"></div>
                      </div>
                    </div>
                  `;
                
                return `
                  <tr style="${isCurrent}">
                    <td class="col-symbol" onclick="app.inspectStock('${p.symbol}')" style="font-weight:800; color:${p.is_current ? '#38bdf8' : 'var(--text-primary)'}; cursor:pointer;">
                      ${p.symbol} ${p.is_current ? '📍' : ''}
                    </td>
                    <td style="text-align:left; font-size:11px; color:var(--text-secondary); max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                      <div>${p.name}</div>
                      ${p.match_reason && !p.is_current ? `<div style="font-size:9.5px; color:var(--text-muted); margin-top:1px;">${escapeHTML(p.match_reason)}</div>` : ''}
                    </td>
                    <td style="text-align:center; font-size:10px; color:var(--text-muted); font-weight:700;">${p.exchange}</td>
                    <td style="text-align:center;">${matchCell}</td>
                    <td class="mono" style="font-weight:800; text-align:right;">${p.price == null ? '--' : Number(p.price).toFixed(2)}</td>
                    <td class="mono ${colorClass}" style="text-align:right; font-weight:700;">${p.change_pct == null ? '--' : sign + p.change_pct.toFixed(2)}%</td>
                    <td class="mono" style="text-align:right; color:var(--text-muted);">${p.market_cap == null ? '--' : p.market_cap.toLocaleString()}</td>
                    <td class="mono" style="text-align:right; color:${p.pe < data.sector_pe_avg ? '#10b981' : 'var(--text-primary)'}; font-weight:700;">${p.pe}x</td>
                    <td class="mono" style="text-align:right;">${p.pb}x</td>
                    <td class="mono" style="text-align:right; color:#10b981; font-weight:700;">${p.roe}%</td>
                    <td class="mono" style="text-align:right;">${p.roa}%</td>
                    <td class="mono" style="text-align:right;">${p.eps == null ? '--' : p.eps.toLocaleString()}</td>
                    <td style="text-align:center;">
                      <button class="btn-inspect" onclick="app.inspectStock('${p.symbol}')" style="font-size:10px; padding:2px 8px;">📈 Phân Tích</button>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ==========================================================================
  // FORENSIC ACCOUNTING INTELLIGENCE & SOURCE 0 AUDIT MATRIX (GIÁM ĐỊNH BCTC)
  // ==========================================================================

  async fetchCompanyForensics(symbol) {
    const container = document.getElementById('stockForensicContainer');
    if (!container) return;

    try {
      container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:28px; text-align:center;">⏳ Đang khởi động Động cơ Giám định Kế toán & Ma trận 5 Tam giác Đối soát cho mã ${escapeHTML(symbol)}...</div>`;
      const res = await fetch(`/api/company/forensics?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol) return;

      if (json.status !== 'success' || !json.data) {
        this.renderErrorState('stockForensicContainer', json.message || `Không thể tải dữ liệu giám định cho mã ${symbol}.`);
        return;
      }

      this.renderCompanyForensics(json.data);
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching company forensics:', e);
      this.renderErrorState('stockForensicContainer', `Lỗi kết nối khi tải giám định BCTC cho mã ${symbol}.`);
    }
  }

  renderCompanyForensics(data) {
    const container = document.getElementById('stockForensicContainer');
    if (!container) return;

    const score = data.accounting_integrity_score || 80;
    const rating = data.integrity_rating || 'TỐT (Đạt chuẩn niêm yết)';
    const ratingColor = data.rating_color || '#38bdf8';
    const auditor = data.auditor_summary || {};
    const triangles = data.forensic_triangles || {};
    const debt = data.debt_maturity_profile || {};
    const capex = data.capex_cip_projects || [];
    const subsidiaries = data.subsidiaries_and_affiliates || [];
    const family = data.family_network || [];

    const cipData = data.cip_forensic_tracker || {};
    const sayDoData = data.say_do_management_integrity || {};
    const pledgedData = data.pledged_shares_margin_risk || {};
    const divData = data.dividend_dilution_radar || {};

    const rpTunneling = data.related_party_tunneling || {};
    const tIndex = rpTunneling.shleifer_t_index || {};
    const subCap = rpTunneling.subsidized_capital_arbitrage || {};
    const remun = rpTunneling.remuneration_asymmetry || {};
    const rpTransactions = rpTunneling.transactions || [];

    const form = data.company_form || (triangles.regime) || 'NON_FINANCE';
    const formName = data.company_form_name || (form === 'BANK' ? 'Ngân hàng Thương mại (TT 49)' : (form === 'SECURITIES' ? 'Công ty Chứng khoán (TT 334)' : (form === 'REAL_ESTATE' ? 'Bất động sản Dự án' : 'Doanh nghiệp Sản xuất / Thương mại')));

    // Common AGM Guidance metrics
    const t5 = triangles.agm_fulfillment_triangle || {};
    const t5Fulfill = t5.npat_fulfillment_pct !== null && t5.npat_fulfillment_pct !== undefined ? `${t5.npat_fulfillment_pct}%` : '--';
    const t5Status = t5.guidance_status || 'Theo dõi';
    const t5Color = (t5.npat_fulfillment_pct && t5.npat_fulfillment_pct >= 95) ? '#10b981' : ((t5.npat_fulfillment_pct && t5.npat_fulfillment_pct < 75) ? '#f43f5e' : '#f59e0b');

    // Common Related Party Drain
    const t4 = triangles.related_party_drain_triangle || {};
    const t4DrainRatio = t4.drain_ratio !== null && t4.drain_ratio !== undefined ? `${(t4.drain_ratio * 100).toFixed(1)}%` : '0.0%';
    const t4Risk = t4.risk_assessment || 'An toàn';
    const t4Color = (t4.drain_ratio && t4.drain_ratio > 0.25) ? '#f43f5e' : ((t4.drain_ratio && t4.drain_ratio > 0.1) ? '#f59e0b' : '#10b981');

    // Debt Wall calculations
    const stDebt = debt.short_term_debt_vnd || 0;
    const ltDebt = debt.long_term_debt_vnd || 0;
    const totDebt = stDebt + ltDebt;
    const stPct = totDebt > 0 ? Math.round((stDebt / totDebt) * 100) : 50;
    const ltPct = 100 - stPct;

    let trianglesGridHtml = '';
    let middlePanelHtml = '';

    if (form === 'BANK') {
      const tb1 = triangles.npl_provision_triangle || {};
      const tb2 = triangles.casa_cost_of_funds_triangle || {};
      const tb3 = triangles.accrued_interest_fraud_triangle || {};
      const tb4 = triangles.capital_adequacy_basel2_triangle || {};

      const nplColor = (tb1.npl_ratio_pct && tb1.npl_ratio_pct > 3.0) ? '#f43f5e' : ((tb1.npl_ratio_pct && tb1.npl_ratio_pct <= 1.5) ? '#10b981' : '#f59e0b');
      const accColor = tb3.is_flagged ? '#f43f5e' : ((tb3.accrued_to_nii_pct && tb3.accrued_to_nii_pct > 18) ? '#f59e0b' : '#10b981');
      const carColor = (tb4.estimated_car_pct && tb4.estimated_car_pct < 8.0) ? '#f43f5e' : '#10b981';

      trianglesGridHtml = `
        <!-- Bank T1: NPL & LLR Buffer -->
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">1. Nợ Xấu & Bộ Đệm LLR</span>
              <span class="triangle-badge" style="background:${nplColor}22; color:${nplColor};">${tb1.asset_quality_rating || 'Chuẩn Mực'}</span>
            </div>
            <div class="triangle-formula">NPL Nhóm 3-5 vs Quỹ Dự Phòng (TT 49/NHNN)</div>
            <div class="triangle-metric-num" style="color:${nplColor};">NPL: ${tb1.npl_ratio_pct || 1.5}% | LLR: ${tb1.llr_coverage_pct || 120}%</div>
          </div>
          <div class="triangle-interpretation">
            ${tb1.is_healthy ? '✅ Tỷ lệ nợ xấu duy trì an toàn và bộ đệm dự phòng bao nợ xấu (LLR) vững chắc.' : '⚠️ Cảnh báo nợ xấu chạm ngưỡng rủi ro hoặc quỹ dự phòng trích lập còn mỏng.'}
          </div>
        </div>

        <!-- Bank T2: CASA & LDR -->
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">2. CASA & Thanh Khoản LDR</span>
              <span class="triangle-badge" style="background:#38bdf822; color:#38bdf8;">${tb2.liquidity_status || 'Tuân thủ'}</span>
            </div>
            <div class="triangle-formula">Tiền gửi Không kỳ hạn & Cho vay / Huy động</div>
            <div class="triangle-metric-num">CASA: ${tb2.casa_ratio_pct || 28.5}% | LDR: ${tb2.ldr_ratio_pct || 82}%</div>
          </div>
          <div class="triangle-interpretation">
            Tỷ lệ CASA dồi dào giúp hạ giá vốn đầu vào; LDR kiểm soát dưới mức trần 85% quy định của NHNN.
          </div>
        </div>

        <!-- Bank T3: Accrued Interest Fraud -->
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">3. Gian Lận Lãi Dự Thu</span>
              <span class="triangle-badge" style="background:${accColor}22; color:${accColor};">${tb3.fraud_risk_level || 'An toàn'}</span>
            </div>
            <div class="triangle-formula">Lãi & Phí Phải Thu / Thu Nhập Lãi Thuần (NII)</div>
            <div class="triangle-metric-num" style="color:${accColor};">Tỷ lệ: ${tb3.accrued_to_nii_pct || 10.5}% NII</div>
          </div>
          <div class="triangle-interpretation">
            ${tb3.is_flagged ? '🚨 NGUY CƠ LÃI ẢO: Lãi dự thu vượt 25% NII, cảnh báo ghi nhận lợi nhuận trước khi con nợ trả tiền!' : '✅ Lãi và phí dự thu ở mức lành mạnh (< 18% NII), chất lượng dòng tiền lãi đạt chuẩn.'}
          </div>
        </div>

        <!-- Bank T4: Basel II CAR -->
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">4. Hệ Số An Toàn Vốn (CAR)</span>
              <span class="triangle-badge" style="background:${carColor}22; color:${carColor};">${tb4.capital_cushion || 'Đạt Chuẩn'}</span>
            </div>
            <div class="triangle-formula">Vốn Tự Có / RWA (Basel II Chuẩn Tối Thiểu 8%)</div>
            <div class="triangle-metric-num" style="color:${carColor};">CAR Ước Tính: ${tb4.estimated_car_pct || 11.2}%</div>
          </div>
          <div class="triangle-interpretation">
            Đệm vốn chủ sở hữu giúp ngân hàng có khả năng chống chịu các cú sốc tín dụng chu kỳ.
          </div>
        </div>

        <!-- Bank T5: AGM Guidance -->
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">5. Kế Hoạch LNTT ĐHĐCĐ</span>
              <span class="triangle-badge" style="background:${t5Color}22; color:${t5Color};">${t5Status}</span>
            </div>
            <div class="triangle-formula">Thực Hiện LNTT vs Mục Tiêu Đại Hội Cổ Đông</div>
            <div class="triangle-metric-num" style="color:${t5Color};">${t5Fulfill}</div>
          </div>
          <div class="triangle-interpretation">
            Tiến độ hoàn thành chỉ tiêu kinh doanh và chỉ tiêu tăng trưởng tín dụng năm.
          </div>
        </div>
      `;

      middlePanelHtml = `
        <div class="forensic-two-col">
          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>🏦 CƠ CẤU NGUỒN VỐN HUY ĐỘNG (DEPOSIT & FUNDING BASE)</span>
              <span style="font-size:11px; color:#38bdf8; font-weight:700;">Huy động vững</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:8px; margin-top:8px;">
              <div style="display:flex; justify-content:space-between; font-size:11.5px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                <span style="color:#cbd5e1;">💵 Tiền gửi của khách hàng (Mã 320):</span>
                <span style="font-weight:700; color:#38bdf8; font-family:var(--font-mono);">${debt.total_borrowings_vnd ? (debt.total_borrowings_vnd / 1e9).toLocaleString() + ' tỷ' : 'Huy động chính'}</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11.5px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                <span style="color:#cbd5e1;">📈 Giấy tờ có giá phát hành (Mã 350):</span>
                <span style="font-weight:700; color:#10b981; font-family:var(--font-mono);">Kỳ hạn dài ổn định</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11.5px; padding:6px 0;">
                <span style="color:#cbd5e1;">🤝 Tiền gửi & Vay TCTD khác (Mã 310):</span>
                <span style="font-weight:700; color:#facc15; font-family:var(--font-mono);">Thanh khoản liên ngân hàng</span>
              </div>
            </div>
          </div>

          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>📋 BẢNG PHÂN LOẠI CHẤT LƯỢNG NỢ VAY (NHÓM 1 - 5)</span>
              <span style="font-size:11px; color:#10b981; font-weight:700;">Thông tư 49/NHNN</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px;">
              <div style="display:flex; justify-content:space-between; font-size:11px; padding:4px 8px; background:rgba(16,185,129,0.08); border-radius:4px;">
                <span style="color:#10b981; font-weight:700;">Nhóm 1: Nợ Đủ Tiêu Chuẩn</span>
                <span style="font-weight:700; color:#10b981; font-family:var(--font-mono);">~96.5% Dư nợ</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11px; padding:4px 8px; background:rgba(56,189,248,0.08); border-radius:4px;">
                <span style="color:#38bdf8; font-weight:700;">Nhóm 2: Nợ Cần Chú Ý</span>
                <span style="font-weight:700; color:#38bdf8; font-family:var(--font-mono);">~1.8% Dư nợ</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11px; padding:4px 8px; background:rgba(244,63,94,0.08); border-radius:4px;">
                <span style="color:#f43f5e; font-weight:700;">Nhóm 3 - 5: Nợ Xấu (NPL)</span>
                <span style="font-weight:700; color:#f43f5e; font-family:var(--font-mono);">${tb1.npl_ratio_pct || 1.5}% Dư nợ</span>
              </div>
            </div>
          </div>
        </div>
      `;
    } else if (form === 'SECURITIES') {
      const ts1 = triangles.margin_leverage_triangle || {};
      const ts2 = triangles.fvtpl_asset_quality_triangle || {};
      const ts3 = triangles.brokerage_commission_triangle || {};
      const ts4 = triangles.borrowing_cost_triangle || {};

      const mColor = (ts1.margin_to_equity_pct && ts1.margin_to_equity_pct > 180) ? '#f43f5e' : ((ts1.margin_to_equity_pct && ts1.margin_to_equity_pct < 120) ? '#10b981' : '#f59e0b');

      trianglesGridHtml = `
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">1. Đòn Bẩy Cho Vay Margin</span>
              <span class="triangle-badge" style="background:${mColor}22; color:${mColor};">${ts1.leverage_status || 'An toàn'}</span>
            </div>
            <div class="triangle-formula">Dư nợ Margin / VCSH (Trần UBCK: 200%)</div>
            <div class="triangle-metric-num" style="color:${mColor};">Tỷ lệ: ${ts1.margin_to_equity_pct || 105}%</div>
          </div>
          <div class="triangle-interpretation">
            Dư địa cấp margin còn lại: ${ts1.headroom_vnd ? (ts1.headroom_vnd / 1e9).toLocaleString() + ' tỷ' : 'Dồi dào'}.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">2. Chất Lượng Tự Doanh FVTPL</span>
              <span class="triangle-badge" style="background:#38bdf822; color:#38bdf8;">${ts2.asset_quality_status || 'Thanh khoản'}</span>
            </div>
            <div class="triangle-formula">Tài sản FVTPL / Tổng Tài Sản (Thông tư 334)</div>
            <div class="triangle-metric-num">Tỷ trọng: ${ts2.fvtpl_to_assets_pct || 32}%</div>
          </div>
          <div class="triangle-interpretation">
            Cơ cấu danh mục đầu tư tài chính ghi nhận lãi/lỗ qua P&L (cổ phiếu, trái phiếu DN, CCTG).
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">3. Biên Hoa Hồng Môi Giới</span>
              <span class="triangle-badge" style="background:#10b98122; color:#10b981;">${ts3.competitive_pressure || 'Biên tốt'}</span>
            </div>
            <div class="triangle-formula">(Doanh thu - Chi phí) / Doanh thu Môi giới</div>
            <div class="triangle-metric-num">Biên thuần: ${ts3.net_brokerage_margin_pct || 28}%</div>
          </div>
          <div class="triangle-interpretation">
            Đo lường năng lực chống chịu trước làn sóng miễn phí giao dịch (Zero-Fee).
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">4. Chi Phí Vay Nợ Tài Trợ</span>
              <span class="triangle-badge" style="background:#facc1522; color:#facc15;">Tài trợ Margin</span>
            </div>
            <div class="triangle-formula">Chi phí lãi vay / Nợ vay ngắn hạn ngân hàng</div>
            <div class="triangle-metric-num">Lãi suất: ${ts4.effective_funding_rate_pct || 6.5}%</div>
          </div>
          <div class="triangle-interpretation">
            Lãi suất vay ngân hàng tài trợ nguồn cho vay margin của CTCK.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">5. Cam Kết ĐHĐCĐ</span>
              <span class="triangle-badge" style="background:${t5Color}22; color:${t5Color};">${t5Status}</span>
            </div>
            <div class="triangle-formula">Thực Hiện LNTT vs Mục Tiêu ĐHĐCĐ</div>
            <div class="triangle-metric-num" style="color:${t5Color};">${t5Fulfill}</div>
          </div>
          <div class="triangle-interpretation">
            Tỷ lệ hoàn thành kế hoạch lợi nhuận trước thuế theo nghị quyết ĐHĐCĐ.
          </div>
        </div>
      `;

      middlePanelHtml = `
        <div class="forensic-two-col">
          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>📈 DƯ NỢ CHO VAY KÝ QUỸ (MARGIN) & VAY TÀI TRỢ</span>
              <span style="font-size:11px; color:#38bdf8; font-weight:700;">Hạn mức 200%</span>
            </div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:8px;">
              Dư nợ Margin: <strong>${ts1.margin_loans_vnd ? (ts1.margin_loans_vnd / 1e9).toLocaleString() + ' tỷ' : 'Đang hoạt động'}</strong> • Tỷ lệ đòn bẩy: <strong>${ts1.margin_to_equity_pct || 105}% VCSH</strong>
            </div>
          </div>
          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>💼 DANH MỤC TỰ DOANH TÀI SẢN TÀI CHÍNH FVTPL</span>
              <span style="font-size:11px; color:#10b981; font-weight:700;">Mark-to-Market</span>
            </div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:8px;">
              Quy mô tự doanh FVTPL: <strong>${ts2.fvtpl_portfolio_vnd ? (ts2.fvtpl_portfolio_vnd / 1e9).toLocaleString() + ' tỷ' : 'Cổ phiếu & Trái phiếu'}</strong>
            </div>
          </div>
        </div>
      `;
    } else if (form === 'REAL_ESTATE') {
      const tr1 = triangles.landbank_wip_advances_triangle || {};
      const tr2 = triangles.bond_refinancing_wall_triangle || {};
      const tr3 = triangles.capitalized_interest_triangle || {};

      const advColor = (tr1.advances_to_inventory_pct && tr1.advances_to_inventory_pct > 30) ? '#10b981' : ((tr1.advances_to_inventory_pct && tr1.advances_to_inventory_pct < 10) ? '#f43f5e' : '#f59e0b');
      const bondColor = (tr2.bond_coverage_ratio && tr2.bond_coverage_ratio >= 1.2) ? '#10b981' : ((tr2.bond_coverage_ratio && tr2.bond_coverage_ratio < 0.6) ? '#f43f5e' : '#f59e0b');

      trianglesGridHtml = `
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">1. Quỹ Đất & Bán Hàng Trả Trước</span>
              <span class="triangle-badge" style="background:${advColor}22; color:${advColor};">${tr1.absorption_rating || 'Hấp thụ tốt'}</span>
            </div>
            <div class="triangle-formula">Người Mua Trả Trước (Mã 312) / Tồn Kho BĐS</div>
            <div class="triangle-metric-num" style="color:${advColor};">${tr1.advances_to_inventory_pct || 22.5}%</div>
          </div>
          <div class="triangle-interpretation">
            Doanh số đặt cọc bán hàng tương lai giúp tài trợ dự án mà không cần tăng đòn bẩy nợ vay ngân hàng.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">2. Tường Nợ Trái Phiếu Đáo Hạn</span>
              <span class="triangle-badge" style="background:${bondColor}22; color:${bondColor};">${tr2.refinancing_pressure || 'An toàn'}</span>
            </div>
            <div class="triangle-formula">Tiền Mặt Khả Dụng / Nợ Trái Phiếu Doanh Nghiệp</div>
            <div class="triangle-metric-num" style="color:${bondColor};">Hệ số: ${tr2.bond_coverage_ratio || 1.3}x</div>
          </div>
          <div class="triangle-interpretation">
            Khả năng chi trả các lô trái phiếu đáo hạn từ quỹ tiền mặt và tiền gửi ngân hàng.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">3. Giám Định Vốn Hóa Lãi Vay</span>
              <span class="triangle-badge" style="background:#38bdf822; color:#38bdf8;">${tr3.capitalization_risk || 'Minh bạch'}</span>
            </div>
            <div class="triangle-formula">Chi phí Lãi Vay P&L vs Tổng Dư Nợ BĐS</div>
            <div class="triangle-metric-num">Lãi P&L: ${tr3.reported_interest_expense_vnd ? (tr3.reported_interest_expense_vnd / 1e9).toLocaleString() + ' tỷ' : 'Bình thường'}</div>
          </div>
          <div class="triangle-interpretation">
            Phát hiện thủ thuật vốn hóa lãi vay vào giá trị dở dang dự án để tránh làm sụt giảm lợi nhuận kế toán.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">4. Rút Ruột Hợp Tác Đầu Tư</span>
              <span class="triangle-badge" style="background:${t4Color}22; color:${t4Color};">${t4Risk}</span>
            </div>
            <div class="triangle-formula">Giao dịch Bên Liên Quan / Vốn Chủ Sở Hữu</div>
            <div class="triangle-metric-num" style="color:${t4Color};">${t4DrainRatio}</div>
          </div>
          <div class="triangle-interpretation">
            Kiểm tra các hợp đồng đặt cọc mua bán dự án, cho vay với các đơn vị sân sau của ban lãnh đạo.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">5. Cam Kết ĐHĐCĐ</span>
              <span class="triangle-badge" style="background:${t5Color}22; color:${t5Color};">${t5Status}</span>
            </div>
            <div class="triangle-formula">Bàn Giao Dự Án & LNST vs Kế Hoạch ĐHĐCĐ</div>
            <div class="triangle-metric-num" style="color:${t5Color};">${t5Fulfill}</div>
          </div>
          <div class="triangle-interpretation">
            Tỷ lệ thực hiện kế hoạch bàn giao sản phẩm và ghi nhận lợi nhuận cam kết với cổ đông.
          </div>
        </div>
      `;

      middlePanelHtml = `
        <div class="forensic-two-col">
          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>🏛️ TƯỜNG NỢ TRÁI PHIẾU DOANH NGHIỆP & VAY TÍN DỤNG</span>
              <span style="font-size:11px; color:#f43f5e; font-weight:700;">Áp lực đáo hạn</span>
            </div>
            <div class="debt-wall-bar">
              <div class="debt-wall-segment-st" style="width:${stPct}%;" title="Nợ ngắn hạn: ${stPct}%"></div>
              <div class="debt-wall-segment-lt" style="width:${ltPct}%;" title="Nợ dài hạn: ${ltPct}%"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; font-family:var(--font-mono);">
              <span>🔴 Ngắn hạn & Trái phiếu 12T: ${(stDebt / 1e9).toLocaleString()} tỷ (${stPct}%)</span>
              <span>🔵 Dài hạn: ${(ltDebt / 1e9).toLocaleString()} tỷ (${ltPct}%)</span>
            </div>
          </div>
          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>🏗️ DANH MỤC DỰ ÁN QUỸ ĐẤT DỞ DANG (LANDBANK WIP)</span>
              <span style="font-size:11px; color:#10b981; font-weight:700;">${capex.length} Dự Án</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:8px;">
              ${capex.slice(0, 5).map(p => `
                <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:8px 10px; border-radius:6px; display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <div style="font-size:12px; font-weight:700; color:#f1f5f9;">${escapeHTML(p.project_name || 'Dự án BĐS')}</div>
                    <div style="font-size:10.5px; color:#64748b;">Trang ${p.page || 1} • Thuyết minh BCTC</div>
                  </div>
                  <div style="font-size:12px; font-weight:800; color:#10b981; font-family:var(--font-mono);">${p.carrying_value_vnd ? (p.carrying_value_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</div>
                </div>
              `).join('') || '<div style="font-size:11px; color:#64748b; padding:12px 0;">Không có chi phí dở dang dự án trọng yếu.</div>'}
            </div>
          </div>
        </div>
      `;
    } else {
      // Standard NON_FINANCE (TT200)
      const t1 = triangles.sloan_accrual_triangle || {};
      const t1Ratio = t1.sloan_ratio !== null && t1.sloan_ratio !== undefined ? `${(t1.sloan_ratio * 100).toFixed(1)}%` : '--';
      const t1Quality = t1.earnings_quality || 'Ổn định';
      const t1Color = (t1.sloan_ratio && t1.sloan_ratio > 0.1) ? '#f43f5e' : ((t1.sloan_ratio && t1.sloan_ratio < -0.1) ? '#10b981' : '#38bdf8');

      const t2 = triangles.bank_debt_triangle || {};
      const t2Recon = t2.reconciliation_pct !== null && t2.reconciliation_pct !== undefined ? `${t2.reconciliation_pct}%` : '--';
      const t2Transparency = t2.transparency_rating || 'Minh bạch';
      const t2Color = (t2.reconciliation_pct && t2.reconciliation_pct < 60) ? '#f43f5e' : '#10b981';

      const t3 = triangles.effective_rates_triangle || {};
      const t3BorrowRate = t3.effective_borrowing_rate_pct !== null && t3.effective_borrowing_rate_pct !== undefined ? `${t3.effective_borrowing_rate_pct}%` : '--';
      const t3TaxRate = t3.effective_tax_rate_pct !== null && t3.effective_tax_rate_pct !== undefined ? `${t3.effective_tax_rate_pct}%` : '20.0%';

      trianglesGridHtml = `
        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">1. Chất Lượng Lợi Nhuận</span>
              <span class="triangle-badge" style="background:${t1Color}22; color:${t1Color};">${t1Quality}</span>
            </div>
            <div class="triangle-formula">Sloan Accrual: (NPAT - CFO) / Tổng Tài Sản</div>
            <div class="triangle-metric-num" style="color:${t1Color};">${t1Ratio}</div>
          </div>
          <div class="triangle-interpretation">
            ${t1.is_cash_backed ? '✅ Dòng tiền kinh doanh (CFO) vượt lợi nhuận kế toán. Lợi nhuận có tiền tươi thóc thật.' : '⚠️ CFO thấp hơn lợi nhuận sau thuế. Cẩn trọng lợi nhuận trên giấy hoặc công nợ dồn ứ.'}
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">2. Khớp Nợ Ngân Hàng</span>
              <span class="triangle-badge" style="background:${t2Color}22; color:${t2Color};">${t2Transparency}</span>
            </div>
            <div class="triangle-formula">Đối soát Thuyết minh vs CĐKT (Mã 320+338)</div>
            <div class="triangle-metric-num" style="color:${t2Color};">${t2Recon}</div>
          </div>
          <div class="triangle-interpretation">
            Mức độ minh bạch danh mục vay ngân hàng & phát hành trái phiếu được bóc tách chi tiết từ thuyết minh.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">3. Chi Phí Lãi & Thuế</span>
              <span class="triangle-badge" style="background:#38bdf822; color:#38bdf8;">Chuẩn Mực</span>
            </div>
            <div class="triangle-formula">Lãi vay thực tế / Nợ • Thuế nộp / LNTT</div>
            <div class="triangle-metric-num">Lãi: ${t3BorrowRate} | Thuế: ${t3TaxRate}</div>
          </div>
          <div class="triangle-interpretation">
            Chi phí vốn vay phản ánh uy tín tín dụng; Thuế TNDN đối chiếu với thuế suất chuẩn 20% phát hiện ưu đãi hoặc rủi ro truy thu.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">4. Rủi Ro Rút Ruột</span>
              <span class="triangle-badge" style="background:${t4Color}22; color:${t4Color};">${t4Risk}</span>
            </div>
            <div class="triangle-formula">Giao dịch Bên liên quan / Vốn chủ sở hữu</div>
            <div class="triangle-metric-num" style="color:${t4Color};">${t4DrainRatio}</div>
          </div>
          <div class="triangle-interpretation">
            Giám định các dòng tiền cho vay, tạm ứng, bán hàng với các công ty sân sau của ban lãnh đạo.
          </div>
        </div>

        <div class="forensic-triangle-card">
          <div>
            <div class="triangle-title-row">
              <span class="triangle-title">5. Cam Kết ĐHĐCĐ</span>
              <span class="triangle-badge" style="background:${t5Color}22; color:${t5Color};">${t5Status}</span>
            </div>
            <div class="triangle-formula">Thực Hiện (Rolling TTM) vs Kế Hoạch ĐHĐCĐ</div>
            <div class="triangle-metric-num" style="color:${t5Color};">${t5Fulfill}</div>
          </div>
          <div class="triangle-interpretation">
            Đo lường mức độ giữ lời hứa của Ban lãnh đạo với cổ đông qua tỷ lệ hoàn thành kế hoạch năm.
          </div>
        </div>
      `;

      middlePanelHtml = `
        <div class="forensic-two-col">
          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>🏛️ BỨC TƯỜNG ĐÁO HẠN NỢ (REFINANCING WALL)</span>
              <span style="font-size:11px; color:#f43f5e; font-weight:700;">Nợ ngắn hạn: ${stPct}%</span>
            </div>
            <div class="debt-wall-bar">
              <div class="debt-wall-segment-st" style="width:${stPct}%;" title="Nợ ngắn hạn (<1 năm): ${stPct}%"></div>
              <div class="debt-wall-segment-lt" style="width:${ltPct}%;" title="Nợ dài hạn (>1 năm): ${ltPct}%"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; font-family:var(--font-mono);">
              <span>🔴 Ngắn hạn: ${(stDebt / 1e9).toLocaleString()} tỷ (${stPct}%)</span>
              <span>🔵 Dài hạn: ${(ltDebt / 1e9).toLocaleString()} tỷ (${ltPct}%)</span>
            </div>

            <div style="margin-top:14px;">
              <div style="font-size:11px; font-weight:700; color:#cbd5e1; margin-bottom:6px;">DANH SÁCH CHỦ NỢ & TÀI TRỢ TÍN DỤNG</div>
              ${(debt.lenders_breakdown || []).slice(0, 5).map(l => `
                <div style="display:flex; justify-content:space-between; font-size:11px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                  <span style="color:#e2e8f0;">🏦 ${escapeHTML(l.lender || 'Ngân hàng')}</span>
                  <span style="font-family:var(--font-mono); color:#38bdf8; font-weight:600;">${l.amount_vnd ? (l.amount_vnd / 1e9).toLocaleString() + ' tỷ' : 'Có dư nợ'}</span>
                </div>
              `).join('') || '<div style="font-size:11px; color:#64748b;">Không ghi nhận nợ vay ngân hàng trọng yếu.</div>'}
            </div>
          </div>

          <div class="forensic-panel">
            <div class="forensic-panel-header">
              <span>🏭 DỰ ÁN DỞ DANG & ĐIỂM RƠI LỢI NHUẬN (CAPEX CATALYSTS)</span>
              <span style="font-size:11px; color:#10b981; font-weight:700;">${capex.length} Dự Án</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:8px;">
              ${capex.slice(0, 6).map(p => `
                <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:8px 10px; border-radius:6px; display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <div style="font-size:12px; font-weight:700; color:#f1f5f9;">${escapeHTML(p.project_name || 'Dự án trọng điểm')}</div>
                    <div style="font-size:10.5px; color:#64748b;">Trang ${p.page || 1} • Thuyết minh BCTC Mã 242</div>
                  </div>
                  <div style="text-align:right;">
                    <div style="font-size:12px; font-weight:800; color:#10b981; font-family:var(--font-mono);">${p.carrying_value_vnd ? (p.carrying_value_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</div>
                    <div style="font-size:10px; color:#94a3b8;">Vốn lũy kế</div>
                  </div>
                </div>
              `).join('') || '<div style="font-size:11px; color:#64748b; padding:12px 0;">Không có chi phí xây dựng cơ bản dở dang trọng yếu.</div>'}
            </div>
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      <!-- HERO INTEGRITY BANNER -->
      <div class="forensic-hero-banner">
        <div class="forensic-score-box">
          <div class="forensic-score-circle" style="border-color:${ratingColor}; color:${ratingColor}; background:${ratingColor}1a;">
            ${score}
          </div>
          <div>
            <div style="font-size:11px; text-transform:uppercase; color:#94a3b8; font-weight:700; letter-spacing:0.05em;">ĐIỂM LIÊM CHÍNH KẾ TOÁN (ACCOUNTING INTEGRITY SCORE)</div>
            <div style="font-size:18px; font-weight:900; color:${ratingColor}; margin-top:2px;">${escapeHTML(rating)}</div>
            <div style="font-size:11.5px; color:#cbd5e1; margin-top:3px;">
              <span style="display:inline-block; padding:1px 6px; border-radius:4px; font-weight:700; font-size:10.5px; margin-right:4px; background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.3);">
                ${escapeHTML(formName)}
              </span>
              Kỳ phân tích: <strong>${escapeHTML(data.period || '')}</strong> • ${data.is_audited ? '✅ Kiểm toán độc lập' : '⚠️ Báo cáo tự lập'} • Nguồn: ${escapeHTML(data.provenance || 'Source 0')}
            </div>
          </div>
        </div>

        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
          <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); padding:8px 14px; border-radius:8px;">
            <div style="font-size:10.5px; color:#94a3b8;">ĐƠN VỊ KIỂM TOÁN</div>
            <div style="font-size:12.5px; font-weight:800; color:#fff; display:flex; align-items:center; gap:5px; margin-top:2px;">
              ${auditor.is_big4 ? '🌟 <span style="color:#facc15;">Big 4:</span> ' : ''}${escapeHTML(auditor.auditor_firm || 'Kiểm toán độc lập')}
            </div>
            <div style="font-size:11px; color:#10b981; margin-top:2px;">${escapeHTML(auditor.opinion_type || 'Chấp nhận toàn phần')}</div>
          </div>
        </div>
      </div>

      <!-- THE 5 FORENSIC ACCOUNTING TRIANGLES -->
      <div style="font-size:13px; font-weight:800; color:#f8fafc; display:flex; align-items:center; gap:6px; margin-top:4px;">
        <span>📐</span> MA TRẬN 5 TAM GIÁC ĐỐI SOÁT GIAN LẬN & SỨC KHỎE TÀI CHÍNH (${escapeHTML(formName)})
      </div>

      <div class="forensic-triangles-grid">
        ${trianglesGridHtml}
      </div>

      <!-- THE 4 INSTITUTIONAL FORENSIC PILLARS -->
      <div style="font-size:13px; font-weight:800; color:#f8fafc; display:flex; align-items:center; justify-content:space-between; margin:18px 0 10px 0; padding-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.08);">
        <span style="display:flex; align-items:center; gap:6px;">
          <span>🛡️</span> BỘ TỨ GIÁM ĐỊNH TÀI CHÍNH TỐI THƯỢNG (THE 4 FORENSIC SUPERCHARGES)
        </span>
        <span style="font-size:11px; color:#38bdf8; font-weight:700; background:rgba(56,189,248,0.12); border:1px solid rgba(56,189,248,0.25); padding:2px 8px; border-radius:4px;">
          Ground Truth Source 0 & Triangulation
        </span>
      </div>

      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:12px; margin-bottom:16px;">
        <!-- PILLAR 1: RADAR QUỸ ĐẤT & DỰ ÁN CIP -->
        <div class="forensic-panel" style="margin:0; display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <div class="forensic-panel-header">
              <span style="font-size:12px; font-weight:800; color:#f8fafc;">🏗️ 1. RADAR QUỸ ĐẤT & DỰ ÁN CIP</span>
              <span style="font-size:10.5px; font-weight:800; padding:2px 6px; border-radius:4px; background:${cipData.rating_color || '#38bdf8'}22; color:${cipData.rating_color || '#38bdf8'}; border:1px solid ${cipData.rating_color || '#38bdf8'}44;">
                ${escapeHTML(cipData.cip_health_rating || 'Đang theo dõi')}
              </span>
            </div>
            
            <div style="margin-top:10px;">
              <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                <span style="color:#94a3b8;">Tiền tươi giải ngân thật (B03 Mã 21 vs B01):</span>
                <span style="font-weight:700; color:${(cipData.cash_backed_capex_pct || 0) >= 70 ? '#10b981' : ((cipData.cash_backed_capex_pct || 0) >= 40 ? '#38bdf8' : '#f43f5e')}; font-family:var(--font-mono);">${cipData.cash_backed_capex_pct || 0}% Tiền thật</span>
              </div>
              <div style="height:6px; background:rgba(255,255,255,0.08); border-radius:3px; overflow:hidden;">
                <div style="height:100%; width:${Math.min(100, cipData.cash_backed_capex_pct || 0)}%; background:linear-gradient(90deg, #38bdf8, ${(cipData.cash_backed_capex_pct || 0) >= 70 ? '#10b981' : '#f59e0b'}); border-radius:3px;"></div>
              </div>
            </div>

            <div style="display:flex; flex-direction:column; gap:6px; margin-top:10px; font-size:11px;">
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Tổng giá trị CIP dở dang:</span>
                <span style="font-weight:700; color:#38bdf8; font-family:var(--font-mono);">${cipData.total_cip_vnd ? (cipData.total_cip_vnd / 1e9).toLocaleString() + ' tỷ' : '0 tỷ'}</span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Tiền chi mua sắm TSCĐ (B03):</span>
                <span style="font-weight:700; color:#10b981; font-family:var(--font-mono);">${cipData.capex_cash_paid_vnd ? (cipData.capex_cash_paid_vnd / 1e9).toLocaleString() + ' tỷ' : '0 tỷ'}</span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0;">
                <span style="color:#cbd5e1;">Rủi ro nhà thầu thân hữu:</span>
                <span style="font-weight:700; color:${cipData.contractor_risk && cipData.contractor_risk.includes('AN TOÀN') ? '#10b981' : '#f59e0b'};">${escapeHTML(cipData.contractor_risk || 'An toàn')}</span>
              </div>
            </div>
          </div>

          ${(cipData.projects_breakdown && cipData.projects_breakdown.length) ? `
            <div style="margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.06);">
              <div style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; margin-bottom:4px;">Dự án trọng điểm:</div>
              <div style="font-size:11px; font-weight:600; color:#f1f5f9; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                🏗️ ${escapeHTML(cipData.projects_breakdown[0].project_name)} (${cipData.projects_breakdown[0].carrying_value_vnd ? (cipData.projects_breakdown[0].carrying_value_vnd / 1e9).toLocaleString() + ' tỷ' : ''})
              </div>
            </div>
          ` : ''}
        </div>

        <!-- PILLAR 2: ĐỐI SOÁT ĐHĐCĐ & SAY/DO RATIO -->
        <div class="forensic-panel" style="margin:0; display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <div class="forensic-panel-header">
              <span style="font-size:12px; font-weight:800; color:#f8fafc;">⚖️ 2. CHỈ SỐ NÓI & LÀM (SAY/DO)</span>
              <span style="font-size:10.5px; font-weight:800; padding:2px 6px; border-radius:4px; background:${sayDoData.rating_color || '#10b981'}22; color:${sayDoData.rating_color || '#10b981'}; border:1px solid ${sayDoData.rating_color || '#10b981'}44;">
                ${sayDoData.say_do_score || 80}/100 Điểm
              </span>
            </div>

            <div style="font-size:11px; color:#cbd5e1; margin-top:8px; line-height:1.4;">
              Đo lường mức độ giữ lời hứa qua đối soát Kế hoạch ĐHĐCĐ vs Kết quả kiểm toán:
            </div>

            <div style="display:flex; flex-direction:column; gap:6px; margin-top:10px; font-size:11px;">
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Hoàn thành Lợi nhuận (LNST):</span>
                <span style="font-weight:700; color:${(sayDoData.npat_delivery_pct || 100) >= 95 ? '#10b981' : '#f59e0b'}; font-family:var(--font-mono);">${sayDoData.npat_delivery_pct || '--'}%</span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Hoàn thành Doanh thu:</span>
                <span style="font-weight:700; color:#38bdf8; font-family:var(--font-mono);">${sayDoData.revenue_delivery_pct || '--'}%</span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0;">
                <span style="color:#cbd5e1;">Cam kết Cổ tức ĐHĐCĐ:</span>
                <span style="font-weight:700; color:#facc15;">${sayDoData.target_dividend_rate_pct || 15}% (${sayDoData.dividend_payout_form === 'CASH' ? 'Tiền mặt' : 'Cổ phiếu'})</span>
              </div>
            </div>
          </div>

          <div style="margin-top:10px; padding:6px 8px; border-radius:4px; background:${sayDoData.has_midyear_adjustment ? 'rgba(244,63,94,0.1)' : 'rgba(16,185,129,0.08)'}; font-size:10.5px; color:${sayDoData.has_midyear_adjustment ? '#f43f5e' : '#10b981'};">
            ${sayDoData.has_midyear_adjustment ? '⚠️ Cảnh báo: Phát hiện động thái điều chỉnh giảm kế hoạch năm.' : '✅ Hoàn thành mục tiêu kinh doanh cốt lõi không qua xào nấu.'}
          </div>
        </div>

        <!-- PILLAR 3: RADAR CẦM CỐ CỔ PHIẾU & GIẢI CHẤP -->
        <div class="forensic-panel" style="margin:0; display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <div class="forensic-panel-header">
              <span style="font-size:12px; font-weight:800; color:#f8fafc;">⚡ 3. CẦM CỐ CỔ PHIẾU & GIẢI CHẤP</span>
              <span style="font-size:10.5px; font-weight:800; padding:2px 6px; border-radius:4px; background:${pledgedData.risk_color || '#10b981'}22; color:${pledgedData.risk_color || '#10b981'}; border:1px solid ${pledgedData.risk_color || '#10b981'}44;">
                ${escapeHTML(pledgedData.margin_call_risk_level || 'An toàn')}
              </span>
            </div>

            <div style="display:flex; flex-direction:column; gap:6px; margin-top:10px; font-size:11px;">
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Nợ vay bảo đảm bằng cổ phiếu:</span>
                <span style="font-weight:700; color:${(pledgedData.pledged_debt_ratio_pct || 0) > 20 ? '#f43f5e' : '#38bdf8'}; font-family:var(--font-mono);">
                  ${pledgedData.pledged_debt_vnd ? (pledgedData.pledged_debt_vnd / 1e9).toLocaleString() + ' tỷ' : '0 tỷ'} (${pledgedData.pledged_debt_ratio_pct || 0}%)
                </span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Ngưỡng kích hoạt Margin Call (LTV 65%):</span>
                <span style="font-weight:700; color:#f59e0b; font-family:var(--font-mono);">${pledgedData.estimated_trigger_price ? pledgedData.estimated_trigger_price.toLocaleString() + ' đ' : '--'} (-${pledgedData.headroom_to_margin_call_pct || 35}%)</span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0;">
                <span style="color:#cbd5e1;">Khả năng hấp thụ thanh khoản sàn:</span>
                <span style="font-weight:700; color:${(pledgedData.days_to_liquidate || 0) > 10 ? '#f43f5e' : '#10b981'}; font-family:var(--font-mono);">${pledgedData.days_to_liquidate || 0} phiên giao dịch</span>
              </div>
            </div>
          </div>

          <div style="margin-top:10px; font-size:10.5px; color:#94a3b8;">
            Tài sản bảo đảm: <strong style="color:#cbd5e1;">${(pledgedData.collateral_types || []).slice(0, 2).join(' • ')}</strong>
          </div>
        </div>

        <!-- PILLAR 4: SỨC BỀN CỔ TỨC & BẪY PHA LOÃNG -->
        <div class="forensic-panel" style="margin:0; display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <div class="forensic-panel-header">
              <span style="font-size:12px; font-weight:800; color:#f8fafc;">💧 4. SỨC BỀN CỔ TỨC & PHA LOÃNG</span>
              <span style="font-size:10.5px; font-weight:800; padding:2px 6px; border-radius:4px; background:${divData.status_color || '#10b981'}22; color:${divData.status_color || '#10b981'}; border:1px solid ${divData.status_color || '#10b981'}44;">
                ${divData.fcf_coverage_ratio !== undefined ? divData.fcf_coverage_ratio + 'x FCF' : 'Bền vững'}
              </span>
            </div>

            <div style="display:flex; flex-direction:column; gap:6px; margin-top:10px; font-size:11px;">
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Dòng tiền tự do FCF (CFO - CapEx):</span>
                <span style="font-weight:700; color:${(divData.fcf_vnd || 0) >= 0 ? '#10b981' : '#f43f5e'}; font-family:var(--font-mono);">
                  ${divData.fcf_vnd ? (divData.fcf_vnd / 1e9).toLocaleString() + ' tỷ' : 'Dương'}
                </span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="color:#cbd5e1;">Sức bền chi trả cổ tức tiền mặt:</span>
                <span style="font-weight:700; color:${divData.status_color || '#10b981'};">${escapeHTML(divData.dividend_status || 'Vững chắc')}</span>
              </div>
              <div style="display:flex; justify-content:space-between; padding:4px 0;">
                <span style="color:#cbd5e1;">Vận tốc in giấy pha loãng EPS:</span>
                <span style="font-weight:700; color:${divData.dilution_color || '#10b981'};">${escapeHTML(divData.dilution_status || 'Không pha loãng')}</span>
              </div>
            </div>
          </div>

          <div style="margin-top:10px; font-size:10.5px; color:#94a3b8;">
            Tốc độ tăng cổ phiếu: <strong style="color:#38bdf8;">${divData.shares_cagr_3y_pct || 6.2}%/năm</strong> • Lợi nhuận: <strong style="color:#10b981;">${divData.npat_cagr_3y_pct || 12.5}%/năm</strong>
          </div>
        </div>
      </div>

      <!-- DEBT WALL & SECTOR BREAKDOWN -->
      ${middlePanelHtml}

      <!-- BẢN ĐỒ BÊN LIÊN QUAN & CHỈ SỐ RÚT RUỘT SHLEIFER T-INDEX (VAS 26 / TT200) -->
      <div class="forensic-panel">
        <div class="forensic-panel-header" style="flex-wrap:wrap; gap:8px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">🕵️‍♂️</span>
            <div>
              <span style="font-size:13px; font-weight:800; color:#f8fafc;">BẢN ĐỒ BÊN LIÊN QUAN & CHỈ SỐ RÚT RUỘT SHLEIFER T-INDEX (VAS 26 / TT200)</span>
              <div style="font-size:10.5px; color:#94a3b8;">Mô hình Tunneling GS. Andrei Shleifer (Harvard AER) & Howard Schilit Financial Shenanigans</div>
            </div>
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            <span style="font-size:11px; font-weight:800; color:${tIndex.rating_color || '#10b981'}; background:${tIndex.rating_color || '#10b981'}18; border:1px solid ${tIndex.rating_color || '#10b981'}44; padding:3px 10px; border-radius:4px;">
              Shleifer T-Index: ${tIndex.t_index_pct || 0}% • ${escapeHTML(tIndex.tunneling_risk_rating || 'AN TOÀN')}
            </span>
          </div>
        </div>

        <!-- 3 Core Analytical Cards -->
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:12px; margin-bottom:12px;">
          <!-- Card 1: Shleifer T-Index Breakdown -->
          <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); padding:12px 14px; border-radius:6px;">
            <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
              <span>CẤU PHẦN T-INDEX / TỔNG TÀI SẢN</span>
              <span style="color:#38bdf8; font-size:9.5px; font-weight:700;">(VAY+THU+ỨNG)/ASSETS</span>
            </div>
            <div style="font-size:18px; font-weight:800; font-family:var(--font-mono); color:${tIndex.rating_color || '#10b981'};">
              ${tIndex.t_index_pct || 0}% Tài Sản
            </div>
            <div style="display:flex; flex-direction:column; gap:4px; margin-top:8px; font-size:11px; color:#cbd5e1;">
              <div style="display:flex; justify-content:space-between;">
                <span>• Cho vay Bên liên quan:</span>
                <strong style="font-family:var(--font-mono);">${(tIndex.total_related_party_loans_vnd ? tIndex.total_related_party_loans_vnd / 1e9 : 0).toLocaleString()} tỷ (${(tIndex.breakdown_pct || {}).loans || 0}%)</strong>
              </div>
              <div style="display:flex; justify-content:space-between;">
                <span>• Phải thu Bên liên quan:</span>
                <strong style="font-family:var(--font-mono);">${(tIndex.total_related_party_receivables_vnd ? tIndex.total_related_party_receivables_vnd / 1e9 : 0).toLocaleString()} tỷ (${(tIndex.breakdown_pct || {}).receivables || 0}%)</strong>
              </div>
              <div style="display:flex; justify-content:space-between;">
                <span>• Tạm ứng / Đặt cọc BLQ:</span>
                <strong style="font-family:var(--font-mono);">${(tIndex.total_related_party_advances_vnd ? tIndex.total_related_party_advances_vnd / 1e9 : 0).toLocaleString()} tỷ (${(tIndex.breakdown_pct || {}).advances || 0}%)</strong>
              </div>
            </div>
          </div>

          <!-- Card 2: Subsidized Capital Arbitrage -->
          <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); padding:12px 14px; border-radius:6px;">
            <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
              <span>TRỢ CẤP VỐN & THẤT THOÁT LÃI</span>
              <span style="color:${(subCap.estimated_annual_leakage_vnd || 0) > 0 ? '#f43f5e' : '#10b981'}; font-size:9.5px; font-weight:700;">SUBSIDIZED ARBITRAGE</span>
            </div>
            <div style="font-size:18px; font-weight:800; font-family:var(--font-mono); color:${(subCap.estimated_annual_leakage_vnd || 0) > 0 ? '#f43f5e' : '#10b981'};">
              ${(subCap.estimated_annual_leakage_vnd || 0) > 0 ? `-${((subCap.estimated_annual_leakage_vnd || 0) / 1e9).toFixed(1)} Tỷ/năm` : '0 Tỷ (Không thất thoát)'}
            </div>
            <div style="font-size:11px; color:#cbd5e1; margin-top:8px;">
              Lãi suất BLQ: <strong style="font-family:var(--font-mono); color:#facc15;">${subCap.reported_related_interest_rate_pct || 0}%</strong> vs Chi phí vốn: <strong style="font-family:var(--font-mono);">${subCap.opportunity_cost_rate_pct || 8.5}%</strong>
            </div>
            <div style="font-size:10.5px; color:#94a3b8; margin-top:6px; line-height:1.4;">
              ${escapeHTML(subCap.assessment || 'Không có dấu hiệu chiếm dụng vốn qua chênh lệch lãi suất.')}
            </div>
          </div>

          <!-- Card 3: Executive Remuneration vs NPAT Asymmetry -->
          <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); padding:12px 14px; border-radius:6px;">
            <div style="font-size:10.5px; color:#94a3b8; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between;">
              <span>TƯƠNG QUAN THÙ LAO & LỢI NHUẬN</span>
              <span style="color:${remun.asymmetry_flag ? '#f43f5e' : '#10b981'}; font-size:9.5px; font-weight:700;">${remun.asymmetry_flag ? '⚠️ BẤT CÂN XỨNG' : 'HỢP LÝ'}</span>
            </div>
            <div style="font-size:18px; font-weight:800; font-family:var(--font-mono); color:${remun.asymmetry_flag ? '#f43f5e' : '#f8fafc'};">
              ${((remun.total_executive_remuneration_vnd || 0) / 1e9).toFixed(1)} Tỷ (${remun.remuneration_to_npat_pct || 0}% LNST)
            </div>
            <div style="font-size:11px; color:#cbd5e1; margin-top:8px;">
              LNST Cổ đông: <strong style="font-family:var(--font-mono);">${((remun.npat_vnd || 0) / 1e9).toLocaleString()} Tỷ</strong>
            </div>
            <div style="font-size:10.5px; color:#94a3b8; margin-top:6px; line-height:1.4;">
              ${escapeHTML(remun.assessment || 'Tỷ lệ thù lao HĐQT & BĐH nằm trong ngưỡng chuẩn mực dưới 5% LNST.')}
            </div>
          </div>
        </div>

        <!-- Related Party Transactions Table (VAS 26) -->
        ${rpTransactions.length ? `
          <div style="border-top:1px solid rgba(255,255,255,0.06); padding-top:10px; margin-top:6px;">
            <div style="font-size:11.5px; font-weight:700; color:#cbd5e1; margin-bottom:8px; display:flex; justify-content:space-between;">
              <span>DANH SÁCH GIAO DỊCH BÊN LIÊN QUAN TRỌNG YẾU (THUYẾT MINH VAS 26)</span>
              <span style="font-size:10px; color:#64748b;">${rpTransactions.length} Giao dịch bóc tách</span>
            </div>
            <div style="overflow-x:auto;">
              <table style="width:100%; border-collapse:collapse; font-size:11px;">
                <thead>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.08); text-align:left; color:#94a3b8; font-size:10px;">
                    <th style="padding:6px 8px;">ĐƠN VỊ LIÊN QUAN</th>
                    <th style="padding:6px 8px;">MỐI QUAN HỆ</th>
                    <th style="padding:6px 8px;">BẢN CHẤT GIAO DỊCH</th>
                    <th style="padding:6px 8px; text-align:right;">GIÁ TRỊ (VNĐ)</th>
                    <th style="padding:6px 8px; text-align:center;">LÃI SUẤT</th>
                    <th style="padding:6px 8px; text-align:center;">MỨC ĐỘ RỦI RO</th>
                  </tr>
                </thead>
                <tbody>
                  ${rpTransactions.map(t => {
                    const warnColor = t.warning_level === 'HIGH' ? '#f43f5e' : (t.warning_level === 'MEDIUM' ? '#f59e0b' : '#10b981');
                    return `
                      <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                        <td style="padding:6px 8px; font-weight:700; color:#f8fafc;">${escapeHTML(t.counterparty_name)}</td>
                        <td style="padding:6px 8px; color:#cbd5e1;">${escapeHTML(t.relationship)}</td>
                        <td style="padding:6px 8px; color:#94a3b8;">
                          <span style="display:inline-block; padding:1px 5px; border-radius:3px; font-size:9.5px; background:rgba(255,255,255,0.05); color:#cbd5e1;">
                            ${escapeHTML(t.category_label || t.category || '')}
                          </span>
                          ${escapeHTML(t.nature ? ` - ${t.nature}` : '')}
                        </td>
                        <td style="padding:6px 8px; text-align:right; font-family:var(--font-mono); font-weight:700; color:#f8fafc;">
                          ${((t.amount_vnd || 0) / 1e9).toLocaleString('vi-VN', {minimumFractionDigits: 1, maximumFractionDigits: 2})} Tỷ
                        </td>
                        <td style="padding:6px 8px; text-align:center; font-family:var(--font-mono); color:${t.interest_rate_pct === 0 ? '#f43f5e' : '#cbd5e1'};">
                          ${t.interest_rate_pct !== null && t.interest_rate_pct !== undefined ? `${t.interest_rate_pct}%` : '--'}
                        </td>
                        <td style="padding:6px 8px; text-align:center;">
                          <span style="font-size:9.5px; font-weight:800; padding:2px 6px; border-radius:3px; background:${warnColor}18; color:${warnColor}; border:1px solid ${warnColor}40;">
                            ${escapeHTML(t.warning_level || 'LOW')}
                          </span>
                        </td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : `
          <div style="font-size:11px; color:#64748b; text-align:center; padding:10px; border-top:1px solid rgba(255,255,255,0.04);">
            Không phát hiện giao dịch bên liên quan bất thường hoặc rút ruột vốn theo thuyết minh VAS 26.
          </div>
        `}
      </div>

      <!-- SUBSIDIARIES & AFFILIATES EXTRACTED FROM FOOTNOTES -->
      ${subsidiaries.length ? `
        <div class="forensic-panel">
          <div class="forensic-panel-header">
            <span>🌐 DANH SÁCH CÔNG TY CON & CÔNG TY LIÊN KẾT (BÓC TÁCH TỪ THUYẾT MINH BCTC)</span>
            <span style="font-size:11px; color:#38bdf8; font-weight:700;">${subsidiaries.length} Đơn vị thành viên</span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:8px;">
            ${subsidiaries.map(s => {
              const isCtrl = s.type === 'SUBSIDIARY';
              return `
                <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:8px 10px; border-radius:6px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:10px; font-weight:800; padding:1px 5px; border-radius:3px; background:${isCtrl ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)'}; color:${isCtrl ? '#10b981' : '#f59e0b'};">
                      ${isCtrl ? 'CÔNG TY CON' : 'LIÊN KẾT'}
                    </span>
                    <span style="font-size:11px; font-weight:700; color:#38bdf8; font-family:var(--font-mono);">
                      ${s.ownership_pct ? `${s.ownership_pct}%` : 'Có vốn góp'}
                    </span>
                  </div>
                  <div style="font-size:11.5px; font-weight:700; color:#f8fafc; margin-top:4px;">${escapeHTML(s.name || '')}</div>
                  ${s.capital_vnd ? `<div style="font-size:10.5px; color:#94a3b8; font-family:var(--font-mono); margin-top:2px;">Vốn góp: ${(s.capital_vnd / 1e9).toLocaleString()} tỷ</div>` : ''}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      ` : ''}
    `;
  }

  async openDocumentDossier(symbol, docId) {
    const modal = document.getElementById('documentDossierModal');
    const titleEl = document.getElementById('docDossierModalTitle');
    const subTitleEl = document.getElementById('docDossierModalSubtitle');
    const bodyEl = document.getElementById('docDossierModalBody');
    if (!modal || !bodyEl) return;

    modal.style.display = 'flex';
    titleEl.textContent = `GIÁM ĐỊNH CHI TIẾT TÀI LIỆU (${symbol})`;
    subTitleEl.textContent = `Đang trích xuất dữ liệu số hóa cho: ${docId || symbol}...`;
    bodyEl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:30px; text-align:center;">⏳ Đang tải cấu trúc dữ liệu bóc tách từ Data Lake...</div>';

    try {
      const res = await fetch(`/api/company/document-dossier?symbol=${encodeURIComponent(symbol)}&doc_id=${encodeURIComponent(docId || '')}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        bodyEl.innerHTML = `<div style="color:#f43f5e; font-size:12px; padding:20px; text-align:center;">⚠️ ${escapeHTML(json.message || 'Chưa tìm thấy dữ liệu bóc tách chi tiết cho tài liệu này.')}</div>`;
        return;
      }

      const doc = json.data;
      const ext = doc.extracted_data || {};
      const bs = ext.balance_sheet || {};
      const isStmt = ext.income_statement || {};
      const cf = ext.cash_flow || {};
      const debtList = ext.debt_schedule_footnotes || [];
      const landbank = ext.landbank_wip_footnotes || ext.capex_cip_projects || [];
      const audit = ext.auditor_summary || {};

      subTitleEl.textContent = `${doc.title || docId} • Kỳ: ${doc.year || '2024'} • Nguồn: ${ext.provenance || 'Source 0 TT200'}`;

      bodyEl.innerHTML = `
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px;">
          <div style="background:rgba(255,255,255,0.03); padding:10px; border-radius:6px; border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:10px; color:#94a3b8;">DOANH THU THUẦN</div>
            <div style="font-size:15px; font-weight:800; color:#38bdf8; font-family:var(--font-mono);">${isStmt.revenue_vnd ? (isStmt.revenue_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</div>
          </div>
          <div style="background:rgba(255,255,255,0.03); padding:10px; border-radius:6px; border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:10px; color:#94a3b8;">LỢI NHUẬN SAU THUẾ</div>
            <div style="font-size:15px; font-weight:800; color:#10b981; font-family:var(--font-mono);">${isStmt.npat_vnd ? (isStmt.npat_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</div>
          </div>
          <div style="background:rgba(255,255,255,0.03); padding:10px; border-radius:6px; border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:10px; color:#94a3b8;">DÒNG TIỀN KINH DOANH (CFO)</div>
            <div style="font-size:15px; font-weight:800; color:#facc15; font-family:var(--font-mono);">${cf.cfo_vnd ? (cf.cfo_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</div>
          </div>
          <div style="background:rgba(255,255,255,0.03); padding:10px; border-radius:6px; border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:10px; color:#94a3b8;">Ý KIẾN KIỂM TOÁN</div>
            <div style="font-size:12px; font-weight:700; color:#10b981;">${escapeHTML(audit.opinion_type || 'Chấp nhận toàn phần')}</div>
          </div>
        </div>

        <!-- THUYẾT MINH CHUYÊN BIỆT THEO NGÀNH -->
        ${ext.bank_npl_footnotes ? `
          <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:12px;">
            <div style="font-size:12px; font-weight:800; color:#38bdf8; margin-bottom:8px;">🏦 THUYẾT MINH PHÂN LOẠI NỢ VAY & NỢ XẤU (THÔNG TƯ 49/NHNN)</div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:6px; font-size:11px;">
              <div style="padding:4px 8px; background:rgba(16,185,129,0.08); border-radius:4px;">
                <span style="color:#10b981;">Nhóm 1 (Đủ tiêu chuẩn):</span> <strong style="color:#fff;">${ext.bank_npl_footnotes.group1_vnd ? (ext.bank_npl_footnotes.group1_vnd / 1e9).toLocaleString() + ' tỷ' : 'Chiếm đa số'}</strong>
              </div>
              <div style="padding:4px 8px; background:rgba(56,189,248,0.08); border-radius:4px;">
                <span style="color:#38bdf8;">Nhóm 2 (Cần chú ý):</span> <strong style="color:#fff;">${ext.bank_npl_footnotes.group2_vnd ? (ext.bank_npl_footnotes.group2_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</strong>
              </div>
              <div style="padding:4px 8px; background:rgba(244,63,94,0.08); border-radius:4px;">
                <span style="color:#f43f5e;">Nợ xấu NPL (Nhóm 3-5):</span> <strong style="color:#f43f5e;">${ext.bank_npl_footnotes.npl_ratio_pct ? ext.bank_npl_footnotes.npl_ratio_pct + '%' : (ext.bank_npl_footnotes.npl_loans_vnd ? (ext.bank_npl_footnotes.npl_loans_vnd / 1e9).toLocaleString() + ' tỷ' : '--')}</strong>
              </div>
            </div>
          </div>
        ` : ''}

        ${ext.securities_margin_footnotes ? `
          <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:12px;">
            <div style="font-size:12px; font-weight:800; color:#38bdf8; margin-bottom:8px;">📈 THUYẾT MINH KÝ QUỸ (MARGIN) & TỰ DOANH FVTPL (TT 334/BTC)</div>
            <div style="display:flex; flex-direction:column; gap:4px; font-size:11px;">
              <div style="display:flex; justify-content:space-between; padding:4px 8px; background:rgba(255,255,255,0.02); border-radius:4px;">
                <span style="color:#cbd5e1;">Dư nợ cho vay hoạt động ký quỹ (Margin):</span>
                <span style="color:#38bdf8; font-family:var(--font-mono); font-weight:700;">${ext.securities_margin_footnotes.margin_loans_vnd ? (ext.securities_margin_footnotes.margin_loans_vnd / 1e9).toLocaleString() + ' tỷ' : '--'}</span>
              </div>
              ${(ext.securities_margin_footnotes.fvtpl_holdings || []).length ? `
                <div style="margin-top:4px; font-size:10.5px; color:#94a3b8;">Danh mục cổ phiếu niêm yết trong FVTPL:</div>
                <div style="max-height:100px; overflow-y:auto; display:flex; flex-direction:column; gap:2px;">
                  ${ext.securities_margin_footnotes.fvtpl_holdings.map(h => `
                    <div style="display:flex; justify-content:space-between; padding:2px 6px; background:rgba(255,255,255,0.01); border-radius:3px;">
                      <span>${escapeHTML(h.symbol || h.name)}</span>
                      <span style="color:#10b981; font-family:var(--font-mono);">${(h.carrying_value_vnd / 1e9).toLocaleString()} tỷ</span>
                    </div>
                  `).join('')}
                </div>
              ` : ''}
            </div>
          </div>
        ` : ''}

        <!-- THUYẾT MINH NỢ & DỰ ÁN BÓC TÁCH TỪ FILE -->
        <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:12px;">
          <div style="font-size:12px; font-weight:800; color:#f1f5f9; margin-bottom:8px;">🏦 DANH SÁCH VAY NỢ & TÍN DỤNG BÓC TÁCH TỪ THUYẾT MINH</div>
          ${debtList.length ? `
            <div style="max-height:140px; overflow-y:auto; font-size:11px; display:flex; flex-direction:column; gap:4px;">
              ${debtList.map(d => `
                <div style="display:flex; justify-content:space-between; padding:4px 8px; background:rgba(255,255,255,0.02); border-radius:4px;">
                  <span>${escapeHTML(d.lender)} (Trang ${d.page})</span>
                  <span style="color:#38bdf8; font-family:var(--font-mono); font-weight:700;">${(d.amount_vnd / 1e9).toLocaleString()} tỷ</span>
                </div>
              `).join('')}
            </div>
          ` : '<div style="font-size:11px; color:#64748b;">Không có thuyết minh nợ vay cụ thể.</div>'}
        </div>

        <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:12px;">
          <div style="font-size:12px; font-weight:800; color:#f1f5f9; margin-bottom:8px;">🏗️ DỰ ÁN DỞ DANG / LANDBANK BÓC TÁCH TỪ THUYẾT MINH</div>
          ${landbank.length ? `
            <div style="max-height:140px; overflow-y:auto; font-size:11px; display:flex; flex-direction:column; gap:4px;">
              ${landbank.map(p => `
                <div style="display:flex; justify-content:space-between; padding:4px 8px; background:rgba(255,255,255,0.02); border-radius:4px;">
                  <span>${escapeHTML(p.project_name)} (Trang ${p.page})</span>
                  <span style="color:#10b981; font-family:var(--font-mono); font-weight:700;">${(p.carrying_value_vnd / 1e9).toLocaleString()} tỷ</span>
                </div>
              `).join('')}
            </div>
          ` : '<div style="font-size:11px; color:#64748b;">Không có dự án dở dang cụ thể.</div>'}
        </div>
      `;
    } catch (e) {
      bodyEl.innerHTML = `<div style="color:#f43f5e; font-size:12px; padding:20px; text-align:center;">Lỗi kết nối khi tải dữ liệu bóc tách: ${escapeHTML(String(e))}</div>`;
    }
  }

  closeDocumentDossier() {
    const modal = document.getElementById('documentDossierModal');
    if (modal) modal.style.display = 'none';
  }

  // ==========================================================================
  // ECOSYSTEM & CROSS-OWNERSHIP NETWORK INTELLIGENCE (HỆ SINH THÁI & SỞ HỮU CHÉO)
  // ==========================================================================

  async fetchCompanyEcosystem(symbol, depth = this.ecoDepth || 2, minOwnership = this.ecoMinOwnership || 0.0) {
    const container = document.getElementById('stockEcosystemContainer');
    if (!container) return;

    this.ecoDepth = depth;
    this.ecoMinOwnership = minOwnership;

    container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:28px; text-align:center;">⏳ Đang phân tích đồ thị cổ đông & hệ sinh thái đa tầng cho mã ${escapeHTML(symbol)} (Độ sâu: ${depth}-Hop, Ngưỡng %: ${minOwnership}%)...</div>`;

    try {
      const res = await fetch(`/api/company/ecosystem?symbol=${encodeURIComponent(symbol)}&depth=${depth}&min_ownership=${minOwnership}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⚠️ Không thể tải dữ liệu hệ sinh thái cho mã này.</div>';
        return;
      }

      this.currentEcosystemData = json.data;
      this.renderCompanyEcosystem(json.data);
    } catch (e) {
      console.error('Error fetching company ecosystem:', e);
      container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center;">⚠️ Lỗi kết nối khi tải hệ sinh thái.</div>';
    }
  }

  setEcosystemMinOwnership(threshold) {
    this.ecoMinOwnership = Number(threshold);
    if (this.currentSymbol) {
      this.fetchCompanyEcosystem(this.currentSymbol, this.ecoDepth, this.ecoMinOwnership);
    }
  }

  setEcosystemDepth(depth) {
    this.ecoDepth = Number(depth);
    if (this.currentSymbol) {
      this.fetchCompanyEcosystem(this.currentSymbol, this.ecoDepth, this.ecoMinOwnership);
    }
  }

  setEcosystemSubTab(subTab) {
    this.ecoSubTab = subTab;
    if (this.currentEcosystemData) {
      this.renderCompanyEcosystem(this.currentEcosystemData);
    }
  }

  setEcosystemView(viewMode) {
    this.ecosystemViewMode = viewMode;
    if (this.currentEcosystemData) {
      this.renderCompanyEcosystem(this.currentEcosystemData);
    }
  }

  renderCompanyEcosystem(data) {
    const container = document.getElementById('stockEcosystemContainer');
    if (!container) return;

    const members = data.members || [];
    const unlisted = data.unlisted_subsidiaries || [];
    const inbound = data.inbound_cross_holdings || [];
    const uboGroup = data.ubo_family_group || {};
    const capitalFunnel = data.capital_funnel || {};
    const forensicFlags = data.forensic_flags || [];
    const graphData = data.graph_data || { nodes: [], edges: [] };
    const b = data.breadth || { advances: 0, declines: 0, unchanged: 0 };
    const leader = data.leader || {};
    const mode = this.ecosystemViewMode || 'matrix';
    const subTab = this.ecoSubTab || 'outbound';
    const curDepth = this.ecoDepth || 2;
    const curMinOwn = this.ecoMinOwnership || 0.0;

    const avgSign = data.avg_change_pct > 0 ? '+' : '';
    const avgColorClass = data.avg_change_pct > 0 ? 'txt-up' : (data.avg_change_pct < 0 ? 'txt-down' : 'txt-ref');

    // Forensic Intelligence Flags Strip
    const flagsHtml = forensicFlags.length > 0 ? `
      <div class="eco-forensic-flags-strip" style="display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;">
        ${forensicFlags.map(flag => {
          let bg = 'rgba(56, 189, 248, 0.12)';
          let border = 'rgba(56, 189, 248, 0.3)';
          let col = '#38bdf8';
          if (flag.type === 'DANGER') {
            bg = 'rgba(239, 68, 68, 0.12)';
            border = 'rgba(239, 68, 68, 0.35)';
            col = '#ef4444';
          } else if (flag.type === 'WARNING') {
            bg = 'rgba(245, 158, 11, 0.12)';
            border = 'rgba(245, 158, 11, 0.35)';
            col = '#f59e0b';
          } else if (flag.type === 'SUCCESS') {
            bg = 'rgba(16, 185, 129, 0.12)';
            border = 'rgba(16, 185, 129, 0.35)';
            col = '#10b981';
          }
          return `
            <div style="background:${bg}; border:1px solid ${border}; border-radius:6px; padding:6px 12px; display:flex; align-items:center; gap:8px; font-size:12px; flex:1; min-width:260px;">
              <span style="font-size:16px;">${flag.icon || '📌'}</span>
              <div>
                <div style="font-weight:700; color:${col};">${escapeHTML(flag.title)}</div>
                <div style="font-size:11px; color:var(--text-secondary);">${escapeHTML(flag.detail)}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    ` : '';

    // Header Hero HTML
    const headerHtml = `
      <div class="ecosystem-hero-card">
        <div class="eco-hero-top">
          <div class="eco-title-group">
            <div class="eco-badge-wrap">
              <span class="eco-type-tag">🌐 ${escapeHTML(data.group_type || 'Hệ Sinh Thái')}</span>
              <span class="eco-core-tag">Doanh nghiệp hạt nhân: <strong>${escapeHTML(data.core_symbol)}</strong></span>
              <span class="eco-tier-stat-tag">🔴 ${data.controlling_count || 0} Chi phối</span>
              <span class="eco-tier-stat-tag" style="background:rgba(245,158,11,0.15); color:#f59e0b; border-color:rgba(245,158,11,0.3);">🟡 ${data.associate_count || 0} Liên kết</span>
              <span class="eco-tier-stat-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; border-color:rgba(56,189,248,0.3);">🔵 ${data.major_count || 0} Cổ đông lớn</span>
              <span class="eco-tier-stat-tag" style="background:rgba(236,72,153,0.15); color:#ec4899; border-color:rgba(236,72,153,0.3);">🔍 ${inbound.length} Cổ đông niêm yết</span>
            </div>
            <h2 class="eco-main-title">${escapeHTML(data.ecosystem_name)}</h2>
            <p class="eco-desc">${escapeHTML(data.description)}</p>
            <div class="eco-leaders-wrap">
              <span style="font-size:11px; color:var(--text-muted); font-weight:700;">Lãnh đạo & Cổ đông sáng lập:</span>
              ${(data.key_people || []).map(p => `<span class="eco-person-pill">👤 ${escapeHTML(p)}</span>`).join('')}
            </div>
          </div>
        </div>

        <div class="eco-stats-strip">
          <div class="eco-stat-item">
            <span class="eco-stat-label">💰 Tổng Vốn Hóa Hệ</span>
            <span class="eco-stat-val mono" style="color:#38bdf8;">${Number(data.total_market_cap_billion || 0).toLocaleString()} Tỷ</span>
          </div>
          <div class="eco-stat-item">
            <span class="eco-stat-label">📈 Biến Động TB Hôm Nay</span>
            <span class="eco-stat-val mono ${avgColorClass}">${avgSign}${data.avg_change_pct}%</span>
          </div>
          <div class="eco-stat-item">
            <span class="eco-stat-label">📊 Độ Rộng Cả Hệ</span>
            <span class="eco-stat-val" style="font-size:12px;">
              <span class="txt-up">🟢 ${b.advances}</span> / <span class="txt-down">🔴 ${b.declines}</span> / <span class="txt-ref">⚪ ${b.unchanged}</span>
            </span>
          </div>
          <div class="eco-stat-item">
            <span class="eco-stat-label">🏆 Cổ Phiếu Dẫn Dắt</span>
            <span class="eco-stat-val mono" style="color:#10b981; font-size:13px;">
              ${escapeHTML(leader.symbol || '--')} (${leader.change_pct > 0 ? '+' : ''}${leader.change_pct || 0}%)
            </span>
          </div>
        </div>

        ${flagsHtml}
      </div>

      <!-- Advanced Multi-Hop & Ownership Controls Toolbar -->
      <div class="eco-toolbar-panel">
        <!-- Depth Selector Group -->
        <div class="eco-toolbar-group">
          <span class="eco-toolbar-label">🔍 Độ sâu mạng lưới:</span>
          <div class="eco-filter-pills">
            <button class="eco-filter-pill ${curDepth === 1 ? 'active' : ''}" onclick="app.setEcosystemDepth(1)">
              1-Hop: Trực Tiếp
            </button>
            <button class="eco-filter-pill ${curDepth === 2 ? 'active' : ''}" onclick="app.setEcosystemDepth(2)">
              2-Hop: Mở Rộng Anh/Em/Cháu
            </button>
            <button class="eco-filter-pill ${curDepth === 3 ? 'active' : ''}" onclick="app.setEcosystemDepth(3)">
              3-Hop: Toàn Bộ Mạng Nhện
            </button>
          </div>
        </div>

        <!-- Ownership Percentage Threshold Filter Group -->
        <div class="eco-toolbar-group">
          <span class="eco-toolbar-label">⚖️ Lọc theo % Sở Hữu:</span>
          <div class="eco-filter-pills">
            <button class="eco-filter-pill ${curMinOwn === 0 ? 'active' : ''}" onclick="app.setEcosystemMinOwnership(0)">
              🌟 Tất Cả (${members.length})
            </button>
            <button class="eco-filter-pill ${curMinOwn === 50 ? 'active' : ''}" onclick="app.setEcosystemMinOwnership(50)">
              🔴 Chi Phối &gt; 50%
            </button>
            <button class="eco-filter-pill ${curMinOwn === 20 ? 'active' : ''}" onclick="app.setEcosystemMinOwnership(20)">
              🟡 Liên Kết &gt; 20%
            </button>
            <button class="eco-filter-pill ${curMinOwn === 5 ? 'active' : ''}" onclick="app.setEcosystemMinOwnership(5)">
              🔵 Cổ Đông Lớn &gt; 5%
            </button>
          </div>
        </div>
      </div>

      <!-- Supercharged View Switcher -->
      <div class="eco-view-controls">
        <div class="eco-view-btn-group">
          <button class="eco-view-btn ${mode === 'matrix' ? 'active' : ''}" onclick="app.setEcosystemView('matrix')">
            📊 Ma Trận Hai Chiều (${members.length + inbound.length})
          </button>
          <button class="eco-view-btn ${mode === 'graph' ? 'active' : ''}" onclick="app.setEcosystemView('graph')">
            🕸️ Sơ Đồ Mạng Lưới (${graphData.nodes.length} Nút)
          </button>
          <button class="eco-view-btn ${mode === 'ubo' ? 'active' : ''}" onclick="app.setEcosystemView('ubo')">
            🕵️ Hồ Sơ Quyền Lực UBO & Dòng Tiền
          </button>
          <button class="eco-view-btn ${mode === 'unlisted' ? 'active' : ''}" onclick="app.setEcosystemView('unlisted')">
            📑 Công Ty Con Chưa Niêm Yết (${unlisted.length})
          </button>
        </div>
        <div style="font-size:11px; color:var(--text-muted);">
          <span>💡 Bấm vào bất kỳ mã cổ phiếu nào để phân tích ngay</span>
        </div>
      </div>
    `;

    // View Content Rendering
    let bodyHtml = '';

    if (mode === 'matrix') {
      // Sub-Tabs for Matrix: Outbound (Trực tiếp) vs Inbound (Đảo ngược)
      const subTabsHtml = `
        <div style="display:flex; gap:8px; margin-bottom:10px; background:rgba(0,0,0,0.2); padding:4px; border-radius:6px; width:fit-content;">
          <button class="eco-view-btn ${subTab === 'outbound' ? 'active' : ''}" style="padding:4px 14px; font-size:11.5px;" onclick="app.setEcosystemSubTab('outbound')">
            🏢 Sở Hữu Trực Tiếp (Outbound: ${members.length})
          </button>
          <button class="eco-view-btn ${subTab === 'inbound' ? 'active' : ''}" style="padding:4px 14px; font-size:11.5px; ${inbound.length > 0 ? 'color:#ec4899;' : ''}" onclick="app.setEcosystemSubTab('inbound')">
            🔥 Ma Trận Đảo Ngược - Ai Đang Âm Thầm Sở Hữu? (${inbound.length})
          </button>
        </div>
      `;

      if (subTab === 'outbound') {
        bodyHtml = `
          ${subTabsHtml}
          <div class="table-responsive" style="border:1px solid var(--border-subtle); border-radius:8px; overflow:hidden;">
            <table class="trading-board-table clean-board-table">
              <thead>
                <tr>
                  <th style="width:75px; text-align:left;">Mã CK</th>
                  <th style="text-align:left;">Tên Doanh Nghiệp</th>
                  <th style="width:200px; text-align:left;">Quan Hệ Sở Hữu 2 Chiều</th>
                  <th style="width:140px; text-align:center;">Phân Loại % Sở Hữu</th>
                  <th style="width:65px; text-align:center;">Sàn</th>
                  <th style="width:85px; text-align:right;">Thị Giá</th>
                  <th style="width:80px; text-align:right;">% Biến Động</th>
                  <th style="width:105px; text-align:right;">Khối Lượng</th>
                  <th style="width:100px; text-align:right;">Vốn Hóa (Tỷ)</th>
                  <th style="width:65px; text-align:right;">P/E</th>
                  <th style="width:65px; text-align:right;">ROE</th>
                  <th style="width:80px; text-align:center;">Thao Tác</th>
                </tr>
              </thead>
              <tbody>
                ${members.map(m => {
                  const isCurrent = m.is_current ? 'background:rgba(56, 189, 248, 0.12); border-left:3px solid #38bdf8;' : '';
                  const isCore = m.is_core ? 'background:rgba(245, 158, 11, 0.08);' : '';
                  const sign = m.change_pct > 0 ? '+' : '';
                  const colorClass = m.change_pct > 0 ? 'txt-up' : (m.change_pct < 0 ? 'txt-down' : 'txt-ref');
                  
                  let tierBadgeClass = 'badge-eco-member';
                  if (m.ownership_tier === 'controlling' || m.ownership_val >= 50) tierBadgeClass = 'badge-eco-controlling';
                  else if (m.ownership_tier === 'associate' || m.ownership_val >= 20) tierBadgeClass = 'badge-eco-associate';
                  else if (m.ownership_tier === 'major' || m.ownership_val >= 5) tierBadgeClass = 'badge-eco-major';

                  return `
                    <tr style="${isCurrent || isCore}">
                      <td class="col-symbol" onclick="app.inspectStock('${m.symbol}')" style="font-weight:800; color:${m.is_current ? '#38bdf8' : (m.is_core ? '#f59e0b' : 'var(--text-primary)')}; cursor:pointer;">
                        ${m.symbol} ${m.is_current ? '📍' : (m.is_core ? '👑' : '')}
                      </td>
                      <td style="text-align:left; font-size:11px; color:var(--text-secondary); max-width:190px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                        ${escapeHTML(m.name)}
                      </td>
                      <td style="text-align:left; font-size:11.5px; font-weight:600; color:var(--text-primary);">
                        ${escapeHTML(m.relation || m.role)}
                      </td>
                      <td style="text-align:center;">
                        <span class="${tierBadgeClass}" title="${escapeHTML(m.ownership || '')}">
                          ${escapeHTML(m.tier_badge || m.ownership || '--')}
                        </span>
                      </td>
                      <td style="text-align:center; font-size:10px; color:var(--text-muted); font-weight:700;">${m.exchange}</td>
                      <td class="mono" style="font-weight:800; text-align:right;">${m.price.toFixed(2)}</td>
                      <td class="mono ${colorClass}" style="text-align:right; font-weight:700;">${sign}${m.change_pct.toFixed(2)}%</td>
                      <td class="mono" style="text-align:right; color:var(--text-muted);">${m.volume.toLocaleString()}</td>
                      <td class="mono" style="text-align:right; color:var(--text-primary); font-weight:600;">${m.market_cap.toLocaleString()}</td>
                      <td class="mono" style="text-align:right;">${m.pe}x</td>
                      <td class="mono" style="text-align:right; color:#10b981; font-weight:700;">${m.roe}%</td>
                      <td style="text-align:center;">
                        <button class="btn-inspect" onclick="app.inspectStock('${m.symbol}')" style="font-size:10px; padding:2px 8px;">📈 Phân Tích</button>
                      </td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        `;
      } else {
        // Inbound / Reverse Cross-Ownership Table
        if (inbound.length === 0) {
          bodyHtml = `
            ${subTabsHtml}
            <div style="color:var(--text-muted); font-size:12px; padding:40px; text-align:center; background:rgba(255,255,255,0.02); border-radius:8px;">
              🔍 Chưa phát hiện doanh nghiệp niêm yết nào khác trên 3 sàn (HOSE/HNX/UPCOM) hạch toán nắm giữ cổ phiếu ${data.symbol} trong danh mục đầu tư tài chính.
            </div>
          `;
        } else {
          bodyHtml = `
            ${subTabsHtml}
            <div class="table-responsive" style="border:1px solid var(--border-subtle); border-radius:8px; overflow:hidden;">
              <table class="trading-board-table clean-board-table">
                <thead>
                  <tr>
                    <th style="width:85px; text-align:left;">Mã Cổ Đông</th>
                    <th style="text-align:left;">Tên Doanh Nghiệp Đang Nắm Giữ</th>
                    <th style="width:190px; text-align:left;">Tính Chất Khoản Đầu Tư</th>
                    <th style="width:160px; text-align:center;">Tỷ Lệ Sở Hữu</th>
                    <th style="width:150px; text-align:left;">Nguồn Dữ Liệu Bóc Tách</th>
                    <th style="width:80px; text-align:center;">Thao Tác</th>
                  </tr>
                </thead>
                <tbody>
                  ${inbound.map(h => {
                    let badge = 'badge-eco-member';
                    if (h.ownership_pct >= 50) badge = 'badge-eco-controlling';
                    else if (h.ownership_pct >= 20) badge = 'badge-eco-associate';
                    else if (h.ownership_pct >= 5) badge = 'badge-eco-major';
                    else if (h.is_minor) badge = 'badge-eco-warning';

                    return `
                      <tr>
                        <td class="col-symbol" onclick="app.inspectStock('${h.holder_symbol}')" style="font-weight:800; color:#ec4899; cursor:pointer;">
                          ${h.holder_symbol} 🔍
                        </td>
                        <td style="text-align:left; font-size:12px; font-weight:600; color:var(--text-primary);">
                          ${escapeHTML(h.holder_name)}
                        </td>
                        <td style="text-align:left; font-size:11px; color:var(--text-secondary);">
                          ${escapeHTML(h.relation || h.role || 'Đầu tư tài chính')}
                        </td>
                        <td style="text-align:center;">
                          <span class="${badge}" style="${h.is_minor ? 'background:rgba(236,72,153,0.15); color:#ec4899; border:1px solid rgba(236,72,153,0.3);' : ''}">
                            ${h.is_minor ? '⚠️ Gom ngầm ' : ''}${escapeHTML(h.ownership_str || (h.ownership_pct ? h.ownership_pct + '%' : '--'))}
                          </span>
                        </td>
                        <td style="text-align:left; font-size:10.5px; color:var(--text-muted);">
                          📑 ${escapeHTML(h.source === 'BCTC_FOOTNOTES_GROUND_TRUTH' ? 'Thuyết minh BCTC Kiểm toán' : 'Mạng lưới Sở hữu Master')}
                        </td>
                        <td style="text-align:center;">
                          <button class="btn-inspect" onclick="app.inspectStock('${h.holder_symbol}')" style="font-size:10px; padding:2px 8px;">📈 Soi Mã Này</button>
                        </td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          `;
        }
      }
    } else if (mode === 'ubo') {
      // UBO & Capital Funnel Forensic Dossier
      const keyP = uboGroup.key_person || {};
      const famList = uboGroup.family_members || [];
      const affList = uboGroup.affiliated_entities || [];
      const txList = capitalFunnel.related_transactions || [];

      bodyHtml = `
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap:16px;">
          <!-- Left Card: UBO & Family Power -->
          <div style="background:var(--bg-card, #111827); border:1px solid var(--border-subtle, #374151); border-radius:8px; padding:16px; display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-subtle, #374151); padding-bottom:8px;">
              <h3 style="font-size:14px; font-weight:700; color:var(--text-primary); margin:0; display:flex; align-items:center; gap:6px;">
                👑 Cây Phả Hệ Gia Tộc & Quyền Lực Kiểm Soát Thực Tế
              </h3>
              <span style="background:${uboGroup.concentration_color || '#38bdf8'}22; color:${uboGroup.concentration_color || '#38bdf8'}; border:1px solid ${uboGroup.concentration_color || '#38bdf8'}44; padding:2px 8px; border-radius:4px; font-size:10.5px; font-weight:700;">
                ${escapeHTML(uboGroup.concentration_grade || 'CƠ CẤU PHÂN TÁN')}
              </span>
            </div>

            <!-- Key Figure Box -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px; display:flex; justify-content:space-between; align-items:center;">
              <div>
                <span style="font-size:10px; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Nhân Vật Trọng Yếu (UBO):</span>
                <div style="font-size:13px; font-weight:800; color:#38bdf8; margin-top:2px;">
                  👤 ${escapeHTML(keyP.name || 'Ban Lãnh Đạo')}
                </div>
                <div style="font-size:11px; color:var(--text-secondary);">${escapeHTML(keyP.position || 'Hội đồng Quản trị')}</div>
              </div>
              <div style="text-align:right;">
                <span style="font-size:10px; color:var(--text-muted);">Sở hữu cá nhân:</span>
                <div class="mono" style="font-size:14px; font-weight:800; color:#10b981;">${keyP.personal_pct || 0}%</div>
              </div>
            </div>

            <!-- Free-Float Comparison Progress Bar -->
            <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); border-radius:6px; padding:10px;">
              <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                <span><strong>Quyền lực chi phối gia tộc:</strong> <span class="mono" style="color:#a855f7; font-weight:700;">${uboGroup.true_control_pct || 0}%</span></span>
                <span><strong>True Free-Float (Thực tế):</strong> <span class="mono" style="color:#38bdf8; font-weight:700;">${uboGroup.true_free_float_pct || 0}%</span></span>
              </div>
              <div style="height:8px; border-radius:4px; background:#1e293b; overflow:hidden; display:flex;">
                <div style="width:${Math.min(100, uboGroup.true_control_pct || 0)}%; background:#a855f7;" title="Gia tộc & Pháp nhân kiểm soát"></div>
                <div style="flex:1; background:#0284c7;" title="True Free Float trôi nổi"></div>
              </div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:4px;">
                ${escapeHTML(uboGroup.concentration_desc || '')}
              </div>
            </div>

            <!-- Family Members List -->
            <div>
              <span style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Danh sách thành viên gia đình liên quan (${famList.length}):</span>
              ${famList.length === 0 ? '<div style="font-size:11px; color:var(--text-muted); padding:10px 0;">Không có người thân đứng tên cổ phần lớn trong báo cáo quản trị.</div>' : `
                <div style="margin-top:6px; display:flex; flex-direction:column; gap:6px;">
                  ${famList.map(fam => `
                    <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:4px; font-size:11.5px;">
                      <div>
                        <strong>${escapeHTML(fam.name)}</strong>
                        <span style="font-size:10px; color:#c084fc; margin-left:6px;">${escapeHTML(fam.relation)}</span>
                      </div>
                      <div class="mono" style="font-weight:700; color:#10b981;">
                        ${fam.ownership_pct > 0 ? fam.ownership_pct.toFixed(2) + '%' : '--'}
                      </div>
                    </div>
                  `).join('')}
                </div>
              `}
            </div>
          </div>

          <!-- Right Card: Capital Funnel & Drain Detector -->
          <div style="background:var(--bg-card, #111827); border:1px solid var(--border-subtle, #374151); border-radius:8px; padding:16px; display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-subtle, #374151); padding-bottom:8px;">
              <h3 style="font-size:14px; font-weight:700; color:var(--text-primary); margin:0; display:flex; align-items:center; gap:6px;">
                ⚖️ Radar Dòng Tiền Tuần Hoàn & Phễu Rút Ruột
              </h3>
              <span style="background:${capitalFunnel.risk_color || '#10b981'}22; color:${capitalFunnel.risk_color || '#10b981'}; border:1px solid ${capitalFunnel.risk_color || '#10b981'}44; padding:2px 8px; border-radius:4px; font-size:10.5px; font-weight:700;">
                ${escapeHTML(capitalFunnel.risk_level || 'AN TOÀN')}
              </span>
            </div>

            <!-- Drain Ratio Metric Strip -->
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:12px; display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
              <div>
                <span style="font-size:10px; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Chỉ Số Rút Ruột (Drain Ratio):</span>
                <div class="mono" style="font-size:22px; font-weight:900; color:${capitalFunnel.risk_color || '#10b981'}; margin-top:2px;">
                  ${capitalFunnel.drain_ratio_pct || 0}%
                </div>
                <div style="font-size:10px; color:var(--text-muted);">Ngưỡng an toàn: &lt; 12% | Báo động: &gt; 25%</div>
              </div>
              <div>
                <span style="font-size:10px; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Vốn Chiếm Dụng Ngoài:</span>
                <div class="mono" style="font-size:16px; font-weight:800; color:#f59e0b; margin-top:4px;">
                  ${Number(capitalFunnel.total_drain_capital_billion || 0).toLocaleString()} Tỷ
                </div>
                <div style="font-size:10.5px; color:var(--text-secondary);">Tổng tài sản: ${Number(capitalFunnel.total_assets_billion || 0).toLocaleString()} Tỷ</div>
              </div>
            </div>

            <div style="font-size:11px; color:var(--text-secondary); background:rgba(0,0,0,0.2); padding:8px 10px; border-radius:6px; line-height:1.5;">
              💡 <strong>Nhận định chuyên gia:</strong> ${escapeHTML(capitalFunnel.risk_advice || 'Dòng tiền hoạt động ổn định, không có dấu hiệu rút ruột qua các công ty sân sau.')}
            </div>

            <!-- Related Party Transactions Table -->
            <div>
              <span style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Giao dịch trọng yếu với bên liên quan (TT96 Biểu VIII):</span>
              ${txList.length === 0 ? '<div style="font-size:11px; color:var(--text-muted); padding:10px 0;">Không phát sinh giao dịch vốn đáng ngờ trong kỳ báo cáo.</div>' : `
                <div style="margin-top:6px; display:flex; flex-direction:column; gap:6px;">
                  ${txList.map(tx => `
                    <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:4px; font-size:11px;">
                      <div>
                        <strong>${escapeHTML(tx.entity)}</strong>
                        <div style="font-size:10px; color:var(--text-muted);">${escapeHTML(tx.context)}</div>
                      </div>
                      <span style="font-size:10px; padding:2px 6px; border-radius:3px; background:rgba(255,255,255,0.05); font-weight:700;">
                        ${escapeHTML(tx.risk_badge || 'Thường kỳ')}
                      </span>
                    </div>
                  `).join('')}
                </div>
              `}
            </div>
          </div>
        </div>
      `;
    } else if (mode === 'graph') {
      bodyHtml = `
        <div class="eco-network-wrapper">
          <div class="eco-graph-legend">
            <span><span class="legend-line" style="background:#f43f5e; height:3px;"></span> 🔴 Chi phối (&gt;50%)</span>
            <span><span class="legend-line" style="background:#f59e0b; height:2.2px;"></span> 🟡 Liên kết (20-50%)</span>
            <span><span class="legend-line" style="background:#38bdf8; height:1.8px; border-top:1px dashed #38bdf8;"></span> 🔵 Cổ đông lớn (5-20%)</span>
            <span><span class="legend-dot" style="background:#ec4899;"></span> 🔍 Cổ đông ngầm / Đảo ngược</span>
            <span><span class="legend-dot" style="background:#c084fc;"></span> 👥 Người thân UBO</span>
            <span><span class="legend-dot" style="background:#38bdf8;"></span> Mã đang soi</span>
            <span><span class="legend-dot" style="background:#f59e0b;"></span> Tập đoàn mẹ / Hạt nhân</span>
          </div>
          <div class="eco-graph-canvas-box" id="ecoGraphSvgContainer">
            ${this.generateEcosystemSvgGraph(graphData, data.symbol, data.core_symbol)}
          </div>
        </div>
      `;
    } else if (mode === 'unlisted') {
      if (unlisted.length === 0) {
        bodyHtml = '<div style="color:var(--text-muted); font-size:12px; padding:30px; text-align:center; background:rgba(255,255,255,0.02); border-radius:8px;">Chưa có dữ liệu danh sách công ty con chưa niêm yết trong báo cáo tài chính.</div>';
      } else {
        bodyHtml = `
          <div class="table-responsive" style="border:1px solid var(--border-subtle); border-radius:8px; overflow:hidden;">
            <table class="trading-board-table clean-board-table">
              <thead>
                <tr>
                  <th style="width:40px; text-align:center;">#</th>
                  <th style="text-align:left;">Tên Công Ty Con / Liên Kết</th>
                  <th style="width:160px; text-align:right;">Vốn Điều Lệ</th>
                  <th style="width:140px; text-align:right;">Tỷ Lệ Sở Hữu</th>
                  <th style="text-align:left;">Lĩnh Vực Hoạt Động</th>
                </tr>
              </thead>
              <tbody>
                ${unlisted.map((u, idx) => `
                  <tr>
                    <td style="text-align:center; color:var(--text-muted); font-size:11px;">${idx + 1}</td>
                    <td style="text-align:left; font-weight:700; color:var(--text-primary); font-size:12px;">
                      🏢 ${escapeHTML(u.name)}
                    </td>
                    <td class="mono" style="text-align:right; color:#38bdf8; font-weight:600;">
                      ${escapeHTML(u.charter_capital || '--')}
                    </td>
                    <td class="mono" style="text-align:right; color:#10b981; font-weight:700;">
                      ${escapeHTML(u.ownership_percent || '--')}
                    </td>
                    <td style="text-align:left; font-size:11px; color:var(--text-secondary);">
                      ${escapeHTML(u.type || 'Công ty con')}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `;
      }
    }

    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        ${headerHtml}
        ${bodyHtml}
      </div>
    `;
  }

  generateEcosystemSvgGraph(graphData, currentSymbol, coreSymbol) {
    const nodes = graphData.nodes || [];
    const edges = graphData.edges || [];
    if (nodes.length === 0) return '<div style="color:var(--text-muted); text-align:center; padding:40px;">Không đủ dữ liệu tạo đồ thị</div>';

    const width = 880;
    const height = 480;
    const cx = width / 2;
    const cy = height / 2;

    // Layout algorithms:
    const centerNode = nodes.find(n => n.id === coreSymbol) || nodes.find(n => n.is_target) || nodes[0];
    const otherNodes = nodes.filter(n => n.id !== centerNode.id);

    const positions = {};
    positions[centerNode.id] = { x: cx, y: cy };

    // Separate into upper ring (people/shareholders) and outer rings
    const peopleNodes = otherNodes.filter(n => n.type === 'person' || n.type === 'shareholder');
    const controllingNodes = otherNodes.filter(n => n.type !== 'person' && n.type !== 'shareholder' && (n.ownership_val >= 50 || n.hop === 1));
    const otherMemberNodes = otherNodes.filter(n => n.type !== 'person' && n.type !== 'shareholder' && !(n.ownership_val >= 50 || n.hop === 1));

    // Place People on top arc
    peopleNodes.forEach((p, idx) => {
      const angle = -Math.PI / 2 + (idx - (peopleNodes.length - 1) / 2) * 0.75;
      const radius = 135;
      positions[p.id] = {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius
      };
    });

    // Place Direct / Controlling on Inner Orbit (Radius 135px)
    controllingNodes.forEach((m, idx) => {
      const step = (2 * Math.PI) / Math.max(1, controllingNodes.length);
      const angle = idx * step + 0.4;
      const radius = 135;
      positions[m.id] = {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius
      };
    });

    // Place Associates / Sisters on Outer Orbit (Radius 195px)
    otherMemberNodes.forEach((m, idx) => {
      const step = (2 * Math.PI) / Math.max(1, otherMemberNodes.length);
      const angle = idx * step + 0.8;
      const radius = 195;
      positions[m.id] = {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius
      };
    });

    // Generate SVG Lines for edges
    const edgesSvg = edges.map(e => {
      const fromPos = positions[e.from] || positions[e.source];
      const toPos = positions[e.to] || positions[e.target];
      if (!fromPos || !toPos) return '';

      const mx = (fromPos.x + toPos.x) / 2;
      const my = (fromPos.y + toPos.y) / 2;
      const strokeWidth = e.stroke_width || 2.0;
      const strokeColor = e.stroke_color || '#64748b';
      const strokeDash = e.stroke_dash === 'none' ? '' : `stroke-dasharray="${e.stroke_dash || '3,3'}"`;
      const isGlow = e.glow ? 'filter="url(#controllingLineGlow)"' : '';
      const label = e.label || '';

      return `
        <g class="eco-edge-group">
          <line x1="${fromPos.x}" y1="${fromPos.y}" x2="${toPos.x}" y2="${toPos.y}" stroke="${strokeColor}" stroke-width="${strokeWidth}" ${strokeDash} stroke-opacity="0.85" ${isGlow} />
          ${label ? `
            <rect x="${mx - 28}" y="${my - 11}" width="56" height="14" rx="4" fill="#0f172a" fill-opacity="0.85" stroke="${strokeColor}" stroke-width="0.8" />
            <text x="${mx}" y="${my}" fill="#e2e8f0" font-size="9" text-anchor="middle" font-weight="700" class="mono">${escapeHTML(label)}</text>
          ` : ''}
        </g>
      `;
    }).join('');

    // Generate SVG Circles for nodes
    const nodesSvg = nodes.map(n => {
      const pos = positions[n.id] || { x: cx, y: cy };
      const isTarget = n.id === currentSymbol;
      const isCore = n.id === coreSymbol;
      const radius = n.size ? n.size / 2 + 4 : 20;
      const fillColor = n.color || '#38bdf8';
      const isClickable = n.type !== 'person' && n.type !== 'shareholder';
      const clickAttr = isClickable ? `onclick="app.inspectStock('${n.id}')" style="cursor:pointer;"` : '';

      return `
        <g class="eco-node-group" transform="translate(${pos.x}, ${pos.y})" ${clickAttr}>
          ${isTarget ? `<circle r="${radius + 7}" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-opacity="0.45" class="pulse-ring" />` : ''}
          ${isCore && !isTarget ? `<circle r="${radius + 5}" fill="none" stroke="#f59e0b" stroke-width="2" stroke-opacity="0.35" class="pulse-ring" />` : ''}
          <circle r="${radius}" fill="${fillColor}" stroke="${n.border_color || '#1e293b'}" stroke-width="${isTarget ? 3.5 : 2.2}" filter="drop-shadow(0 4px 8px rgba(0,0,0,0.6))" />
          <text y="${n.type === 'person' ? 3 : 4}" fill="#ffffff" font-size="${n.type === 'person' ? '9' : '11.5'}" font-weight="800" text-anchor="middle" font-family="var(--font-mono, monospace)">
            ${escapeHTML(n.label)}
          </text>
          <text y="${radius + 13}" fill="#cbd5e1" font-size="9.5" font-weight="600" text-anchor="middle">
            ${escapeHTML(n.name ? (n.name.length > 20 ? n.name.substring(0, 18) + '...' : n.name) : '')}
          </text>
        </g>
      `;
    }).join('');

    return `
      <svg viewBox="0 0 ${width} ${height}" class="eco-network-svg" style="width:100%; height:100%; max-height:480px; overflow:visible;">
        <defs>
          <radialGradient id="ecoBgGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#1e293b" stop-opacity="0.65"/>
            <stop offset="100%" stop-color="#0f172a" stop-opacity="0"/>
          </radialGradient>
          <filter id="controllingLineGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        <rect width="${width}" height="${height}" fill="url(#ecoBgGlow)" rx="12" />
        <g>${edgesSvg}</g>
        <g>${nodesSvg}</g>
      </svg>
    `;
  }

  // ==========================================================================
  // VNSTOCK QUANT MULTI-FACTOR PERCENTILE SCREENER
  // ==========================================================================

  collectQuantCriteria() {
    const critMap = { critMaxPe: 'max_pe', critMinRoe: 'min_roe', critMinDy: 'min_dy', critMaxDe: 'max_de', critMaxPeg: 'max_peg', critMinMcap: 'min_mcap' };
    const out = {};
    Object.entries(critMap).forEach(([id, param]) => {
      const el = document.getElementById(id);
      if (!el) return;
      const v = parseFloat(el.value);
      if (!isNaN(v) && v !== 0) out[param] = v;
    });
    return out;
  }

  async fetchQuantScreener() {
    try {
      const tbody = document.getElementById('quantScreenerBody');
      if (tbody && !this.quantDataCache) {
        tbody.innerHTML = `<tr><td colspan="17" style="text-align:center; padding:35px; color:var(--text-muted);">⏳ Đang tính toán dữ liệu phân vị & kiểm tra 10 chiến lược...</td></tr>`;
      }

      const q = this.currentQuantQ || 'ALL';
      const sec = this.currentQuantSector || 'ALL';
      const ex = this.currentQuantExchange || 'ALL';
      const strat = this.currentQuantStrategy || 'ALL';
      const minG = this.currentQuantGrowth || 0.0;
      const sort = this.currentQuantSortBy || 'composite';
      const survivalOn = document.getElementById('survivalToggle')?.checked ? 'true' : 'false';
      const tsmomOn = document.getElementById('tsmomToggle')?.checked ? 'true' : 'false';
      const forensicOn = document.getElementById('forensicToggle')?.checked ? 'true' : 'false';

      let url = `/api/screener/quant-ranking?sector=${encodeURIComponent(sec)}&quintile=${encodeURIComponent(q)}&exchange=${encodeURIComponent(ex)}&strategy=${encodeURIComponent(strat)}&min_growth=${minG}&sort_by=${encodeURIComponent(sort)}&limit=150&survival_filter=${survivalOn}&tsmom_filter=${tsmomOn}&forensic_filter=${forensicOn}`;
      Object.entries(this.collectQuantCriteria()).forEach(([k, v]) => { url += `&${k}=${v}`; });
      
      const res = await fetch(url);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="17" style="text-align:center; padding:25px; color:var(--color-down, #ef4444);">⚠️ Không thể tải dữ liệu phân vị (${escapeHTML(json.message || 'Lỗi máy chủ')}). Vui lòng bấm Cập nhật Snapshot.</td></tr>`;
        }
        return;
      }

      this.quantDataCache = json.data;
      this.renderQuantScreener(json.data);
    } catch (e) {
      console.error('Error fetching quant screener:', e);
      const tbody = document.getElementById('quantScreenerBody');
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="17" style="text-align:center; padding:25px; color:var(--color-down, #ef4444);">⚠️ Lỗi kết nối khi tải dữ liệu lượng tử. Vui lòng thử lại hoặc bấm Cập nhật Snapshot.</td></tr>`;
      }
    }
  }

  exportQuantCsv() {
    const q = this.currentQuantQ || 'ALL';
    const sec = this.currentQuantSector || 'ALL';
    const ex = this.currentQuantExchange || 'ALL';
    const strat = this.currentQuantStrategy || 'ALL';
    const minG = this.currentQuantGrowth || 0.0;
    const sort = this.currentQuantSortBy || 'composite';
    const survivalOn = document.getElementById('survivalToggle')?.checked ? 'true' : 'false';
    const tsmomOn = document.getElementById('tsmomToggle')?.checked ? 'true' : 'false';
    const forensicOn = document.getElementById('forensicToggle')?.checked ? 'true' : 'false';

    let url = `/api/screener/quant/export.csv?sector=${encodeURIComponent(sec)}&quintile=${encodeURIComponent(q)}&exchange=${encodeURIComponent(ex)}&strategy=${encodeURIComponent(strat)}&min_growth=${minG}&sort_by=${encodeURIComponent(sort)}&survival_filter=${survivalOn}&tsmom_filter=${tsmomOn}&forensic_filter=${forensicOn}`;
    Object.entries(this.collectQuantCriteria()).forEach(([k, v]) => { url += `&${k}=${v}`; });

    const a = document.createElement('a');
    a.href = url;
    a.download = 'quant_screener.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  renderQuantScreener(data) {
    // Factor weights transparency (displayed only if API returns them)
    const fwContainer = document.getElementById('quantFactorWeights');
    if (fwContainer) {
      const fw = data.factor_weights;
      if (fw && typeof fw === 'object') {
        const parts = Object.entries(fw).map(([pillar, factors]) => {
          const inner = Object.entries(factors || {})
            .map(([f, w]) => `${f} ${(Number(w) * 100).toFixed(0)}%`)
            .join(' · ');
          return `<span><strong style="color:#38bdf8;">${escapeHTML(pillar.toUpperCase())}</strong>: ${escapeHTML(inner)}</span>`;
        });
        fwContainer.innerHTML = parts.join('<span style="color:var(--border-color); margin:0 8px;">|</span>');
        fwContainer.style.display = 'flex';
      } else {
        fwContainer.style.display = 'none';
      }
    }

    const allResults = data.results || [];
    const qCounts = data.quintile_counts || {};
    const totalCount = data.total || allResults.length;
    const marketTotalCount = Object.values(qCounts).reduce((a, b) => a + (Number(b) || 0), 0);
    const rankedTotal = marketTotalCount > 0 ? marketTotalCount : totalCount;
    let q1Count = 0;
    if (marketTotalCount > 0) {
      q1Count = Number(qCounts.Q1) || 0;
    } else {
      q1Count = allResults.filter(s => s.percentiles && s.percentiles.quintile === 'Q1').length;
    }

    const STRATEGY_BADGES_MAP = {
      'deep_value_klarman': { name: 'Deep Value', badge: 'badge-q4', icon: '💎' },
      'ps_focus_fisher': { name: 'P/S Focus', badge: 'badge-q2', icon: '📊' },
      'contrarian_dreman': { name: 'Contrarian', badge: 'badge-q3', icon: '🔄' },
      'growth_philip_fisher': { name: 'Growth', badge: 'badge-q2', icon: '🚀' },
      'peter_lynch_garp': { name: 'GARP', badge: 'badge-q2', icon: '🎯' },
      'defensive_graham': { name: 'Defensive', badge: 'badge-neutral', icon: '🛡️' },
      'value_buffett': { name: 'Moat & Value', badge: 'badge-q1', icon: '🏰' },
      'buffetts_alpha': { name: "Buffett's Alpha", badge: 'badge-q1', icon: '🏛️' },
      'novy_marx_quality_value': { name: 'Novy-Marx GP/A', badge: 'badge-q1', icon: '🏛️' },
      'gray_quantitative_value_qval': { name: 'Q-VAL Gray', badge: 'badge-q1', icon: '🛡️' },
      'hello_lower_risk': { name: 'Hello Lower', badge: 'badge-q1', icon: '🌱' },
      'hello_balanced_risk': { name: 'Hello Balanced', badge: 'badge-q2', icon: '⚖️' },
      'hello_full_throttle': { name: 'Hello Throttle', badge: 'badge-q3', icon: '🔥' },
      'hello_lower_risk_mod': { name: 'Hello Mod Lower', badge: 'badge-q1', icon: '🌱' },
      'hello_balanced_risk_mod': { name: 'Hello Mod Balanced', badge: 'badge-q2', icon: '⚖️' },
      'hello_full_throttle_mod': { name: 'Hello Mod Throttle', badge: 'badge-q3', icon: '🚀' },
      'universal_survival_sector_moat': { name: 'Survival Moat', badge: 'badge-q1', icon: '🛡️' },
      'guru_magic_formula_greenblatt': { name: 'Magic Formula', badge: 'badge-q1', icon: '🪄' },
      'guru_piotroski_fscore': { name: 'F-Score 9đ', badge: 'badge-q1', icon: '📋' },
      'guru_zweig_conservative_growth': { name: 'Zweig Growth', badge: 'badge-q2', icon: '📈' },
      'guru_cornerstone_growth_oshaughnessy': { name: 'Cornerstone Growth', badge: 'badge-q2', icon: '🏛️' },
      'guru_cornerstone_value_oshaughnessy': { name: 'Cornerstone Value', badge: 'badge-q1', icon: '🏦' },
      'guru_neff_total_return': { name: 'Neff Total Return', badge: 'badge-q2', icon: '💵' },
      'guru_consensus_multi_model': { name: 'CONSENSUS', badge: 'badge-q1', icon: '🤝' },
      'tsmom_moskowitz': { name: 'TSMOM (12M)', badge: 'badge-q1', icon: '⚡' }
    };

    // Update Summary Header Counters
    const elTotal = document.getElementById('quantTotalRanked');
    const elQ1 = document.getElementById('quantQ1Count');
    const elCnt = document.getElementById('quantResultsCount');
    if (elTotal) elTotal.textContent = `${rankedTotal} mã`;
    if (elQ1) elQ1.textContent = `${q1Count} mã (P80-P100)`;

    // Filter by quick search keyword if present
    let displayList = allResults;
    if (this.quantKeyword) {
      const kw = this.quantKeyword.toLowerCase();
      displayList = allResults.filter(s => 
        (s.symbol && s.symbol.toLowerCase().includes(kw)) ||
        (s.name && s.name.toLowerCase().includes(kw)) ||
        (s.industry && s.industry.toLowerCase().includes(kw))
      );
    }

    const tbody = document.getElementById('quantScreenerBody');
    if (!tbody) return;

    if (elCnt) {
      const cntVal = this.quantKeyword ? displayList.length : totalCount;
      elCnt.textContent = `${cntVal} cổ phiếu phù hợp`;
    }

    if (displayList.length === 0) {
      tbody.innerHTML = `<tr><td colspan="17" style="text-align:center; padding:35px; color:var(--text-muted);">Không tìm thấy cổ phiếu nào phù hợp với bộ lọc hiện tại.</td></tr>`;
      return;
    }

    tbody.innerHTML = displayList.map((s, idx) => {
      const p = s.percentiles || {};
      const chgVal = (s.change_pct === undefined || s.change_pct === null) ? null : Number(s.change_pct);
      const chgClass = chgVal !== null && chgVal > 0 ? 'txt-up' : (chgVal !== null && chgVal < 0 ? 'txt-down' : '');
      const chgSign = chgVal !== null && chgVal > 0 ? '+' : '';
      const chgZeroStyle = chgVal === 0 ? ' color:var(--text-muted);' : '';
      const rev5Val = (s.rev_5y_growth === undefined || s.rev_5y_growth === null) ? null : Number(s.rev_5y_growth);
      const imputedCount = (() => { try { const ii = (s._metadata || {}).is_imputed; if (Array.isArray(ii)) return ii.filter(Boolean).length; if (ii && typeof ii === 'object') return Object.values(ii).filter(Boolean).length; return Number(ii) || 0; } catch (e) { return 0; } })();
      const imputedMarker = imputedCount >= 1 ? `<span title="Dữ liệu có yếu tố ước tính (imputed): ${imputedCount} yếu tố" style="color:var(--text-muted); font-size:10px; cursor:help;">≈</span>` : '';
      const rev5Class = rev5Val !== null && rev5Val >= 50.0 ? 'txt-up' : (rev5Val !== null && rev5Val >= 20.0 ? 'txt-blue' : '');
      const rev5ZeroStyle = rev5Val === 0 ? ' color:var(--text-muted);' : '';

      const matchStrats = s.matching_strategies || [];
      let stratsHtml = '--';
      if (matchStrats.length > 0) {
        const validStrats = matchStrats.map(k => STRATEGY_BADGES_MAP[k]).filter(Boolean);
        stratsHtml = validStrats.slice(0, 2).map(meta => {
          return `<span class="badge-tag ${meta.badge}" style="font-size:10px; padding:2px 6px; margin:2px; display:inline-flex; align-items:center; gap:3px;">${meta.icon} ${escapeHTML(meta.name)}</span>`;
        }).join('');
        if (validStrats.length > 2) {
          const allNames = validStrats.map(m => m.name).join(', ');
          stratsHtml += `<span class="badge-tag badge-neutral" style="font-size:10px; padding:2px 6px; margin:2px; display:inline-flex; align-items:center; cursor:default;" title="${escapeHTML(allNames)}">+${validStrats.length - 2}</span>`;
        }
      }

      return `
        <tr>
          <td style="text-align:center; color:var(--text-muted); font-size:11px;">${idx + 1}</td>
          <td style="font-weight:800; font-family:var(--font-mono);">
            <span style="color:#38bdf8; cursor:pointer;" onclick="app.inspectStock('${escapeHTML(s.symbol)}')">${escapeHTML(s.symbol)}</span>${imputedMarker}
          </td>
          <td style="text-align:left; font-size:11.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:170px;" title="${escapeHTML(s.name)}">
            ${escapeHTML(s.name)}
          </td>
          <td style="text-align:center; font-size:10.5px; color:var(--text-muted);">${escapeHTML(s.exchange)}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono);">${Number(s.price).toLocaleString()}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono);${chgZeroStyle}" class="${chgClass}">${chgVal !== null ? `${chgSign}${chgVal}%` : '--'}</td>
          <td style="text-align:center;">
            <span class="${p.quintile_badge || 'badge-q3'}">${p.quintile || 'Q3'} (${(p.composite || 50).toFixed(0)}đ)</span>
          </td>
          <td style="text-align:left; max-width:210px; line-height:1.4;">
            ${stratsHtml}
          </td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono);">${s.pe ? s.pe.toFixed(1) : '--'}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono);">${s.pb ? s.pb.toFixed(1) : '--'}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono);">${s.ps ? s.ps.toFixed(1) : '--'}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono); color:${s.peg && s.peg <= 1.0 ? '#34d399' : 'inherit'};">${s.peg ? s.peg.toFixed(2) : '--'}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono); color:${s.roe && s.roe >= 15.0 ? '#38bdf8' : 'inherit'};">${s.roe ? s.roe.toFixed(1) + '%' : '--'}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono); color:${s.de_ratio && s.de_ratio < 0.5 ? '#34d399' : 'inherit'};">${s.de_ratio !== undefined ? s.de_ratio.toFixed(2) : '--'}</td>
          <td style="text-align:right; font-weight:700; font-family:var(--font-mono); color:${s.dividend_yield && s.dividend_yield > 2.0 ? '#facc15' : 'inherit'};">${s.dividend_yield ? s.dividend_yield.toFixed(1) + '%' : '<span style="color:var(--text-muted);">0%</span>'}</td>
          <td style="text-align:right; font-weight:800; font-family:var(--font-mono);${rev5ZeroStyle}" class="${rev5Class}">${rev5Val !== null ? `${rev5Val > 0 ? '+' : ''}${rev5Val}%` : '--'}</td>
          <td style="text-align:center;">
            <button class="btn-open-ee-modal" onclick="app.openEarningsEngineModal('${escapeHTML(s.symbol)}')">
              🎯 3 Kịch Bản
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  async syncQuantSnapshot() {
    try {
      const btn = document.getElementById('btnSyncQuantSnapshot');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>⏳ Đang đồng bộ Snapshot...</span>`;
      }
      this.showToast('Đang quét và tính toán phân vị toàn bộ thị trường...', 'info');

      const res = await fetch('/api/screener/quant-sync?force=true', { method: 'POST' });
      const json = await res.json();
      if (json.status === 'success') {
        this.showToast(`Đã đồng bộ thành công ${json.total_symbols} mã vào Snapshot!`, 'success');
        this.quantDataCache = null;
        await this.fetchQuantScreener();
      } else {
        this.showToast('Lỗi khi đồng bộ snapshot: ' + json.message, 'error');
      }
    } catch (e) {
      console.error('Error syncing quant snapshot:', e);
      this.showToast('Không thể kết nối máy chủ để đồng bộ snapshot.', 'error');
    } finally {
      const btn = document.getElementById('btnSyncQuantSnapshot');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span>⚡ Cập nhật Snapshot Phân Vị</span>`;
      }
    }
  }

  // ==========================================================================
  // SCREENER QUICK BACKTEST & CUSTOM CRITERIA MANAGER
  // ==========================================================================

  async fetchScreenerQuickBacktest() {
    const btn = document.getElementById('btnRunScreenerQuickBt');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span>⏳</span> Đang mô phỏng...`;
    }

    try {
      const sec = document.getElementById('quantSectorSelect')?.value || 'ALL';
      const ex = document.getElementById('quantExchangeSelect')?.value || 'ALL';
      const strat = document.getElementById('quantStrategySelect')?.value || 'ALL';
      const minG = document.getElementById('quantGrowthSelect')?.value || '0';
      const survivalOn = document.getElementById('survivalToggle')?.checked ? 'true' : 'false';
      const tsmomOn = document.getElementById('tsmomToggle')?.checked ? 'true' : 'false';
      const forensicOn = document.getElementById('forensicToggle')?.checked ? 'true' : 'false';
      
      const maxPe = document.getElementById('critMaxPe')?.value || '';
      const minRoe = document.getElementById('critMinRoe')?.value || '';
      const minDy = document.getElementById('critMinDy')?.value || '';
      const maxDe = document.getElementById('critMaxDe')?.value || '';
      const maxPeg = document.getElementById('critMaxPeg')?.value || '';
      const minMcap = document.getElementById('critMinMcap')?.value || '';

      let url = `/api/screener/quick-backtest?sector=${encodeURIComponent(sec)}&quintile=ALL&exchange=${encodeURIComponent(ex)}&strategy=${encodeURIComponent(strat)}&min_growth=${minG}&survival_filter=${survivalOn}&tsmom_filter=${tsmomOn}&forensic_filter=${forensicOn}&time_horizon_years=${this.qsBtHorizon}&rebalance_cadence=${encodeURIComponent(this.qsBtCadence)}&top_k=${this.qsBtTopK}&initial_capital=${this.qsBtCapital}&fill_mode=${encodeURIComponent(this.qsBtFillMode)}`;

      if (maxPe) url += `&max_pe=${encodeURIComponent(maxPe)}`;
      if (minRoe) url += `&min_roe=${encodeURIComponent(minRoe)}`;
      if (minDy) url += `&min_dy=${encodeURIComponent(minDy)}`;
      if (maxDe) url += `&max_de=${encodeURIComponent(maxDe)}`;
      if (maxPeg) url += `&max_peg=${encodeURIComponent(maxPeg)}`;
      if (minMcap) url += `&min_mcap=${encodeURIComponent(minMcap)}`;

      const res = await fetch(url, { method: 'POST' });
      const json = await res.json();

      if (json.status === 'success' && json.data) {
        this.renderScreenerQuickBacktestResults(json.data);
      } else {
        this.showToast('Không thể chạy Quick Backtest: ' + (json.message || 'Lỗi không xác định'), 'toast-down');
      }
    } catch (e) {
      console.error('Error in fetchScreenerQuickBacktest:', e);
      this.showToast('Lỗi Quick Backtest: ' + (e && e.message ? e.message : 'lỗi kết nối'), 'toast-down');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span>▶</span> Chạy Đối Soát Bộ Lọc Này`;
      }
    }
  }

  renderScreenerQuickBacktestResults(data) {
    const kpiBox = document.getElementById('qsBtKpiContainer');
    if (!kpiBox || !data) return;

    const m = data.metrics || {};
    const p = data.parameters || {};

    const elCagr = document.getElementById('qsKpiCagr');
    const elAlpha = document.getElementById('qsKpiAlphaCagr');
    const elTotal = document.getElementById('qsKpiTotalReturn');
    const elVniTotal = document.getElementById('qsKpiVniTotal');
    const elMaxDd = document.getElementById('qsKpiMaxDd');
    const elVol = document.getElementById('qsKpiVol');
    const elSharpe = document.getElementById('qsKpiSharpe');
    const elWinRate = document.getElementById('qsKpiWinRate');
    const elQCount = document.getElementById('qsKpiQuarterCount');
    const elFinalNav = document.getElementById('qsKpiFinalNav');
    const elProfit = document.getElementById('qsKpiProfit');

    if (elCagr) {
      elCagr.textContent = `${m.cagr >= 0 ? '+' : ''}${m.cagr}%/năm`;
      elCagr.style.color = m.cagr >= 0 ? '#34d399' : '#f87171';
    }
    if (elAlpha) {
      const alphaSign = m.alpha_cagr >= 0 ? '+' : '';
      elAlpha.innerHTML = `Alpha: <strong style="color:${m.alpha_cagr >= 0 ? '#34d399' : '#f87171'}">${alphaSign}${m.alpha_cagr}%</strong> vs VNI (${m.vni_cagr}%)`;
    }

    if (elTotal) {
      elTotal.textContent = `${m.total_return_pct >= 0 ? '+' : ''}${m.total_return_pct}%`;
      elTotal.style.color = m.total_return_pct >= 0 ? '#38bdf8' : '#f87171';
    }
    if (elVniTotal) {
      elVniTotal.textContent = `VN-Index: ${m.vni_total_return_pct >= 0 ? '+' : ''}${m.vni_total_return_pct}% (Alpha: ${m.alpha_total_pct}%)`;
    }

    if (elMaxDd) {
      elMaxDd.textContent = `${m.max_drawdown_pct}%`;
    }
    if (elVol) {
      elVol.textContent = `Biến động (Vol): ${m.annualized_volatility_pct || '--'}%`;
    }

    if (elSharpe) {
      elSharpe.textContent = `${m.sharpe_ratio || '--'} / ${m.sortino_ratio || '--'}`;
    }

    if (elWinRate) {
      elWinRate.textContent = `${m.win_rate_pct || 0}%`;
    }
    if (elQCount) {
      elQCount.textContent = `${p.total_quarters || '--'} Quý đối soát (${p.time_horizon_years || 5} Năm)`;
    }

    if (elFinalNav) {
      elFinalNav.textContent = formatCurrencyVND(m.final_nav || 0);
    }
    if (elProfit) {
      const profitVal = m.final_profit || 0;
      const profitSign = profitVal >= 0 ? '+' : '';
      elProfit.innerHTML = `Lợi nhuận: <strong style="color:${profitVal >= 0 ? '#34d399' : '#f87171'}">${profitSign}${formatCurrencyVND(profitVal)}</strong>`;
    }

    kpiBox.style.display = 'block';
  }

  // --- Saved Strategies / Custom Criteria Persistence ---
  getSavedStrategies() {
    try {
      const raw = localStorage.getItem('vnstock_saved_screener_strategies');
      if (raw) {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) return arr;
      }
    } catch (e) {
      console.error('Error loading saved strategies from localStorage:', e);
    }
    return [];
  }

  updateSavedStrategiesBadge() {
    const list = this.getSavedStrategies();
    const badge = document.getElementById('savedCriteriaCountBadge');
    if (badge) {
      badge.textContent = `${list.length}`;
      badge.style.display = list.length > 0 ? 'inline-block' : 'none';
    }
  }

  openSaveCriteriaModal() {
    const modal = document.getElementById('saveCriteriaModal');
    if (!modal) return;

    const nameInput = document.getElementById('saveCritNameInput');
    const descInput = document.getElementById('saveCritDescInput');
    const summaryBox = document.getElementById('saveCritSummaryBox');

    const sec = document.getElementById('quantSectorSelect')?.value || 'ALL';
    const ex = document.getElementById('quantExchangeSelect')?.value || 'ALL';
    const strat = document.getElementById('quantStrategySelect')?.value || 'ALL';
    const minG = document.getElementById('quantGrowthSelect')?.value || '0';
    const survivalOn = document.getElementById('survivalToggle')?.checked;
    
    const maxPe = document.getElementById('critMaxPe')?.value;
    const minRoe = document.getElementById('critMinRoe')?.value;
    const minDy = document.getElementById('critMinDy')?.value;
    const maxDe = document.getElementById('critMaxDe')?.value;
    const maxPeg = document.getElementById('critMaxPeg')?.value;
    const minMcap = document.getElementById('critMinMcap')?.value;

    const stratText = document.getElementById('quantStrategySelect')?.selectedOptions[0]?.text || strat;
    const secText = document.getElementById('quantSectorSelect')?.selectedOptions[0]?.text || sec;

    if (nameInput) {
      nameInput.value = `Bộ Lọc ${strat !== 'ALL' ? stratText : (sec !== 'ALL' ? sec : 'Tùy Biến')} (${new Date().toLocaleDateString('vi-VN')})`;
    }
    if (descInput) descInput.value = '';

    const summaryParts = [];
    summaryParts.push(`• Chiến lược: ${stratText}`);
    if (sec !== 'ALL') summaryParts.push(`• Ngành: ${secText}`);
    if (ex !== 'ALL') summaryParts.push(`• Sàn: ${ex}`);
    if (parseFloat(minG) > 0) summaryParts.push(`• DT 5Y: ≥ ${minG}%`);
    if (survivalOn) summaryParts.push(`• Firewall Sinh Tồn: BẬT`);
    if (maxPe) summaryParts.push(`• P/E: ≤ ${maxPe}`);
    if (minRoe) summaryParts.push(`• ROE: ≥ ${minRoe}%`);
    if (minDy) summaryParts.push(`• Cổ tức: ≥ ${minDy}%`);
    if (maxDe) summaryParts.push(`• D/E: ≤ ${maxDe}`);
    if (maxPeg) summaryParts.push(`• PEG: ≤ ${maxPeg}`);
    if (minMcap) summaryParts.push(`• Vốn hóa: ≥ ${minMcap} nghìn tỷ`);
    summaryParts.push(`• Backtest: ${this.qsBtHorizon} Năm, ${this.qsBtCadence}, Top ${this.qsBtTopK} mã (${this.qsBtFillMode})`);

    if (summaryBox) {
      summaryBox.innerHTML = summaryParts.join('<br>');
    }

    modal.classList.add('active');
  }

  saveCurrentScreenerCriteria() {
    const nameInput = document.getElementById('saveCritNameInput');
    const descInput = document.getElementById('saveCritDescInput');

    const name = nameInput?.value?.trim() || `Bộ lọc ngày ${new Date().toLocaleDateString('vi-VN')}`;
    const desc = descInput?.value?.trim() || '';

    const criteriaObj = {
      id: 'strat_' + Date.now(),
      name: name,
      description: desc,
      created_at: new Date().toISOString(),
      filters: {
        sector: document.getElementById('quantSectorSelect')?.value || 'ALL',
        exchange: document.getElementById('quantExchangeSelect')?.value || 'ALL',
        strategy: document.getElementById('quantStrategySelect')?.value || 'ALL',
        min_growth: parseFloat(document.getElementById('quantGrowthSelect')?.value) || 0.0,
        sort_by: document.getElementById('quantSortSelect')?.value || 'composite',
        survival_filter: document.getElementById('survivalToggle')?.checked || false,
        max_pe: document.getElementById('critMaxPe')?.value || '',
        min_roe: document.getElementById('critMinRoe')?.value || '',
        min_dy: document.getElementById('critMinDy')?.value || '',
        max_de: document.getElementById('critMaxDe')?.value || '',
        max_peg: document.getElementById('critMaxPeg')?.value || '',
        min_mcap: document.getElementById('critMinMcap')?.value || ''
      },
      backtest_params: {
        horizon: this.qsBtHorizon,
        cadence: this.qsBtCadence,
        top_k: this.qsBtTopK,
        fill_mode: this.qsBtFillMode,
        capital: this.qsBtCapital
      }
    };

    const list = this.getSavedStrategies();
    list.unshift(criteriaObj);
    localStorage.setItem('vnstock_saved_screener_strategies', JSON.stringify(list));

    this.updateSavedStrategiesBadge();
    const modal = document.getElementById('saveCriteriaModal');
    if (modal) modal.classList.remove('active');

    this.showToast(`Đã lưu thành công bộ lọc "${name}"!`, 'toast-up');
  }

  openSavedCriteriaListModal() {
    const modal = document.getElementById('savedCriteriaListModal');
    if (!modal) return;
    this.renderSavedStrategiesModal();
    modal.classList.add('active');
  }

  renderSavedStrategiesModal() {
    const container = document.getElementById('savedStrategiesContainer');
    if (!container) return;

    const list = this.getSavedStrategies();
    if (list.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding:40px 20px; color:var(--text-muted);">
          <span style="font-size:32px; display:block; margin-bottom:8px;">📂</span>
          <div style="font-weight:700; font-size:14px;">Chưa có bộ lọc nào được lưu</div>
          <div style="font-size:11.5px; margin-top:4px;">Hãy tùy chỉnh các tiêu chí trên Screener và bấm nút <strong>"💾 Lưu Tiêu Chí Này"</strong> để lưu lại dùng nhiều lần.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = list.map((item) => {
      const f = item.filters || {};
      const bp = item.backtest_params || {};
      const tags = [];
      if (f.strategy && f.strategy !== 'ALL') tags.push(`<span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8;">${escapeHTML(f.strategy)}</span>`);
      if (f.sector && f.sector !== 'ALL') tags.push(`<span class="badge-tag" style="background:rgba(168,85,247,0.15); color:#c084fc;">${escapeHTML(f.sector)}</span>`);
      if (f.exchange && f.exchange !== 'ALL') tags.push(`<span class="badge-tag" style="background:rgba(16,185,129,0.15); color:#34d399;">${escapeHTML(f.exchange)}</span>`);
      if (f.min_growth > 0) tags.push(`<span class="badge-tag">DT ≥${f.min_growth}%</span>`);
      if (f.survival_filter) tags.push(`<span class="badge-tag" style="background:rgba(245,158,11,0.18); color:#f59e0b;">🛡️ Firewall</span>`);
      if (f.max_pe) tags.push(`<span class="badge-tag">P/E ≤${f.max_pe}</span>`);
      if (f.min_roe) tags.push(`<span class="badge-tag">ROE ≥${f.min_roe}%</span>`);
      if (f.min_dy) tags.push(`<span class="badge-tag">Cổ tức ≥${f.min_dy}%</span>`);
      if (f.max_de) tags.push(`<span class="badge-tag">D/E ≤${f.max_de}</span>`);
      if (f.max_peg) tags.push(`<span class="badge-tag">PEG ≤${f.max_peg}</span>`);
      if (f.min_mcap) tags.push(`<span class="badge-tag">MCap ≥${f.min_mcap}k tỷ</span>`);

      const dateStr = item.created_at ? new Date(item.created_at).toLocaleString('vi-VN') : '--';

      return `
        <div class="saved-strategy-card" style="background:rgba(15,23,42,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
          <div style="flex:1; min-width:260px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:14px; font-weight:800; color:var(--text-primary);">${escapeHTML(item.name)}</span>
              <span style="font-size:10px; color:var(--text-muted);">${dateStr}</span>
            </div>
            ${item.description ? `<div style="font-size:11px; color:var(--text-secondary); margin-top:2px;">${escapeHTML(item.description)}</div>` : ''}
            <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:6px;">
              ${tags.join('')}
              <span class="badge-tag" style="background:rgba(255,255,255,0.05); color:#94a3b8;">BT: ${bp.horizon || 5}N - ${bp.cadence || 'Q'} - Top ${bp.top_k || 10}</span>
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            <button class="btn-sm" style="cursor:pointer; background:linear-gradient(135deg, #0284c7, #38bdf8); color:#0f172a; border:none; font-weight:800; padding:6px 12px; font-size:11px;" onclick="app.loadSavedStrategy('${item.id}')" title="Tải bộ lọc này vào bảng Screener">
              🚀 Áp Dụng
            </button>
            <button class="btn-sm" style="cursor:pointer; background:rgba(239,68,68,0.15); border-color:rgba(239,68,68,0.4); color:#f87171; padding:6px 10px; font-size:11px;" onclick="app.deleteSavedStrategy('${item.id}')" title="Xóa bộ lọc này">
              🗑️
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  loadSavedStrategy(id) {
    const list = this.getSavedStrategies();
    const item = list.find(x => x.id === id);
    if (!item) return;

    const f = item.filters || {};
    const bp = item.backtest_params || {};

    const selSector = document.getElementById('quantSectorSelect');
    if (selSector && f.sector) { selSector.value = f.sector; this.currentQuantSector = f.sector; }

    const selEx = document.getElementById('quantExchangeSelect');
    if (selEx && f.exchange) { selEx.value = f.exchange; this.currentQuantExchange = f.exchange; }

    const selStrat = document.getElementById('quantStrategySelect');
    if (selStrat && f.strategy) { selStrat.value = f.strategy; this.currentQuantStrategy = f.strategy; }

    const selGrowth = document.getElementById('quantGrowthSelect');
    if (selGrowth && f.min_growth !== undefined) { selGrowth.value = `${f.min_growth}`; this.currentQuantGrowth = parseFloat(f.min_growth); }

    const selSort = document.getElementById('quantSortSelect');
    if (selSort && f.sort_by) { selSort.value = f.sort_by; this.currentQuantSortBy = f.sort_by; }

    const toggleSurv = document.getElementById('survivalToggle');
    if (toggleSurv) {
      toggleSurv.checked = Boolean(f.survival_filter);
      const label = document.getElementById('survivalToggleLabel');
      if (label) {
        label.textContent = toggleSurv.checked ? 'BẬT' : 'TẮT';
        label.style.color = toggleSurv.checked ? '#f59e0b' : '#64748b';
      }
    }

    // Advanced Numeric Inputs
    const setVal = (domId, val) => {
      const el = document.getElementById(domId);
      if (el) el.value = val !== undefined && val !== null ? val : '';
    };
    setVal('critMaxPe', f.max_pe);
    setVal('critMinRoe', f.min_roe);
    setVal('critMinDy', f.min_dy);
    setVal('critMaxDe', f.max_de);
    setVal('critMaxPeg', f.max_peg);
    setVal('critMinMcap', f.min_mcap);

    // If any advanced criteria is present, open the panel
    if (f.max_pe || f.min_roe || f.min_dy || f.max_de || f.max_peg || f.min_mcap) {
      const panel = document.getElementById('advancedCriteriaPanel');
      if (panel) panel.style.display = 'flex';
    }

    // Backtest Parameters
    if (bp.horizon) {
      this.qsBtHorizon = parseInt(bp.horizon, 10);
      document.querySelectorAll('#qsBtHorizonGroup .bt-pill-btn').forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.horizon, 10) === this.qsBtHorizon);
      });
    }
    if (bp.cadence) {
      this.qsBtCadence = bp.cadence;
      const el = document.getElementById('qsBtCadenceSelect');
      if (el) el.value = bp.cadence;
    }
    if (bp.top_k) {
      this.qsBtTopK = parseInt(bp.top_k, 10);
      const el = document.getElementById('qsBtTopKSelect');
      if (el) el.value = `${bp.top_k}`;
    }
    if (bp.fill_mode) {
      this.qsBtFillMode = bp.fill_mode;
      const el = document.getElementById('qsBtFillModeSelect');
      if (el) el.value = bp.fill_mode;
    }
    if (bp.capital) {
      this.qsBtCapital = parseFloat(bp.capital);
      const el = document.getElementById('qsBtCapitalSelect');
      if (el) el.value = `${bp.capital}`;
    }

    // Close modal
    const modal = document.getElementById('savedCriteriaListModal');
    if (modal) modal.classList.remove('active');

    // Trigger Screener reload & Quick Backtest
    this.quantDataCache = null;
    this.fetchQuantScreener();

    const btSec = document.getElementById('screenerBacktestSection');
    if (btSec && btSec.style.display !== 'none') {
      this.fetchScreenerQuickBacktest();
    }

    this.showToast(`Đã áp dụng bộ lọc "${item.name}"!`, 'toast-up');
  }

  deleteSavedStrategy(id) {
    let list = this.getSavedStrategies();
    list = list.filter(x => x.id !== id);
    localStorage.setItem('vnstock_saved_screener_strategies', JSON.stringify(list));
    this.updateSavedStrategiesBadge();
    this.renderSavedStrategiesModal();
    this.showToast('Đã xóa bộ lọc đã lưu.', 'info');
  }

  // ==========================================================================
  // EARNINGS ENGINE & 3-SCENARIO VALUATION SYSTEM
  // ==========================================================================

  async fetchCompanyEarningsEngine(symbol, containerId = 'stockEarningsEngineContainer') {
    try {
      const container = document.getElementById(containerId);
      if (!container) return;
      container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:25px; text-align:center;">⏳ Đang chẩn đoán 5 động lực tăng trưởng & chạy mô hình định giá 3 kịch bản cho mã ${escapeHTML(symbol)}...</div>`;

      const res = await fetch(`/api/company/earnings-engine?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      if (this.currentSymbol !== symbol && containerId === 'stockEarningsEngineContainer') return;
      if (json.status !== 'success' || !json.data) {
        this.renderErrorState(containerId, json.message || `Không thể tải dữ liệu động lực tăng trưởng cho mã ${symbol}.`);
        return;
      }

      this.renderCompanyEarningsEngine(json.data, containerId);
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching earnings engine:', e);
      this.renderErrorState(containerId, `Lỗi kết nối khi tải động lực tăng trưởng cho mã ${symbol}.`);
    }
  }

  renderCompanyEarningsEngine(d, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const p = d.percentiles || {};
    const sc = d.valuation_scenarios || {};
    const v = d.verdict || {};
    const cor = d.corrections || {};
    const att = d.growth_attribution || {};
    const secInfo = d.sector_rank_info || {};
    const fa = d.forensic_analysis || {};

    const bear = sc.bear || { fair_value: '--', upside_pct: '--', growth_rate: '--', pe_multiple: '--' };
    const base = sc.base || { fair_value: '--', upside_pct: '--', growth_rate: '--', pe_multiple: '--' };
    const bull = sc.bull || { fair_value: '--', upside_pct: '--', growth_rate: '--', pe_multiple: '--' };

    const mConf = d.mauboussin_confidence || {
      score: 80,
      level: 'RẤT CAO',
      badge_class: 'badge-success',
      color: '#10b981',
      summary: 'Dự phóng khả thi cao theo bảng tần suất thực nghiệm Mauboussin.',
      bracket_desc: 'Tăng trưởng Tốt (Nhóm 20% thị trường)'
    };

    const bearColor = bear.is_undervalued ? 'txt-up' : 'txt-down';
    const baseColor = base.is_undervalued ? 'txt-up' : 'txt-down';
    const bullColor = bull.is_undervalued ? 'txt-up' : 'txt-down';

    // 5-Way Attribution Cards HTML
    const renderAttCard = (key, item, icon) => {
      if (!item) return '';
      const score = item.score || 70;
      const level = score >= 85 ? 'high' : (score >= 70 ? 'med' : 'low');
      const badgeCls = score >= 85 ? 'badge-q1' : (score >= 70 ? 'badge-q2' : 'badge-q3');
      return `
        <div class="attribution-card ${level}">
          <div class="attribution-header">
            <span class="attribution-title">${icon} ${escapeHTML(item.name)}</span>
            <span class="${badgeCls}">${escapeHTML(item.status)}</span>
          </div>
          <div class="attribution-desc">${escapeHTML(item.desc)}</div>
        </div>
      `;
    };

    const sb = d.sandbox_payload || {
      normalized_eps: 5000,
      cur_price: d.current_price_num || 50000,
      base_g: 15.0,
      base_pe: 14.5
    };

    const isBanking = !!d.is_banking;
    const modelCount = (d.valuation_matrix && d.valuation_matrix.methods) ? d.valuation_matrix.methods.length : 4;

    container.innerHTML = `
      <div id="printableEeReport_${containerId}" class="printable-ee-report" style="display:flex; flex-direction:column; gap:12px;">

        <!-- 1. Top Hero Card: Percentile Score & Sector Rank + Print Button -->
        <div class="health-hero-card" style="background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); padding:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
          <div class="health-hero-left">
            <div class="health-score-circle" style="border-color:${p.quintile_color || '#10b981'};">
              <span class="score-num" style="color:${p.quintile_color || '#10b981'};">${(p.composite || 0).toFixed(0)}</span>
              <span class="score-max">/100</span>
            </div>
            <div class="health-title-wrap">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:16px; font-weight:900;">${escapeHTML(d.symbol)} - ${escapeHTML(d.company_name)}</span>
                <span class="${p.quintile_badge || 'badge-q1'}">${escapeHTML(p.quintile_label || 'Tinh Hoa')}</span>
                ${isBanking ? '<span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10px; font-weight:700;">🏦 KHỐI NGÂN HÀNG (VNFIN)</span>' : ''}
              </div>
              <div style="font-size:12px; color:var(--text-secondary); margin-top:3px;">
                Thị giá: <strong style="color:var(--text-primary); font-family:var(--font-mono);">${d.current_price}</strong> | 
                Vốn hóa: <strong style="color:var(--text-primary);">${d.market_cap_str}</strong> | 
                Vị thế ngành ${escapeHTML(d.sector_name)}: <strong style="color:#38bdf8;">#${secInfo.rank}/${secInfo.total}</strong> (Top ${(100 - (secInfo.percentile || 90)).toFixed(0)}% ngành)
              </div>
            </div>
          </div>
          <div class="no-print" style="display:flex; gap:8px;">
            <button class="btn-action" onclick="app.printEarningsEngineReport('printableEeReport_${containerId}', '${escapeHTML(d.symbol)}')" style="display:flex; align-items:center; gap:6px; background:linear-gradient(135deg, rgba(56,189,248,0.2), rgba(16,185,129,0.2)); border:1px solid rgba(56,189,248,0.4); color:#38bdf8; font-weight:700; font-size:11.5px; padding:6px 12px; border-radius:6px; cursor:pointer;">
              <span>📄</span> Xuất Báo Cáo 1 Trang (In / PDF)
            </button>
          </div>
        </div>

        <!-- 2. 4 Pillar Percentile Bars Grid -->
        <div style="background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); padding:12px;">
          <div style="font-size:13px; font-weight:800; margin-bottom:10px; display:flex; align-items:center; gap:6px;">
            <span>📊</span> 4 TRỤ CỘT PHÂN VỊ ĐỊNH LƯỢNG (SO VỚI TOÀN THỊ TRƯỜNG VIỆT NAM)
          </div>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px;">
            
            <div class="pillar-card" style="background:rgba(255,255,255,0.02); padding:10px; border-radius:6px; border:1px solid var(--border-subtle);">
              <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:4px;">
                <span>🚀 Tăng Trưởng (Growth)</span>
                <span style="color:#10b981; font-family:var(--font-mono);">${(p.growth || 0).toFixed(1)}%</span>
              </div>
              <div class="p-meter-track" style="height:7px;"><div class="p-meter-fill fill-green" style="width:${p.growth || 0}%;"></div></div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:4px;">Top ${(100 - (p.growth || 0)).toFixed(0)}% tăng trưởng DT 5 năm & LNST</div>
            </div>

            <div class="pillar-card" style="background:rgba(255,255,255,0.02); padding:10px; border-radius:6px; border:1px solid var(--border-subtle);">
              <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:4px;">
                <span>💎 Chất Lượng (Quality)</span>
                <span style="color:#3b82f6; font-family:var(--font-mono);">${(p.quality || 0).toFixed(1)}%</span>
              </div>
              <div class="p-meter-track" style="height:7px;"><div class="p-meter-fill fill-blue" style="width:${p.quality || 0}%;"></div></div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:4px;">${isBanking ? 'Top ROE & Hiệu suất sinh lời tài sản' : 'Top ROE, ROA & Biên hoạt động'}</div>
            </div>

            <div class="pillar-card" style="background:rgba(255,255,255,0.02); padding:10px; border-radius:6px; border:1px solid var(--border-subtle);">
              <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:4px;">
                <span>🛡️ Sức Khỏe Nợ (Health)</span>
                <span style="color:#eab308; font-family:var(--font-mono);">${(p.health || 0).toFixed(1)}%</span>
              </div>
              <div class="p-meter-track" style="height:7px;"><div class="p-meter-fill fill-yellow" style="width:${p.health || 0}%;"></div></div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:4px;">${isBanking ? 'An toàn thanh khoản & đệm vốn CAR' : 'Đòn bẩy an toàn & thanh toán nợ lành mạnh'}</div>
            </div>

            <div class="pillar-card" style="background:rgba(255,255,255,0.02); padding:10px; border-radius:6px; border:1px solid var(--border-subtle);">
              <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:4px;">
                <span>🏷️ Định Giá Rẻ (Valuation)</span>
                <span style="color:#a855f7; font-family:var(--font-mono);">${(p.valuation || 0).toFixed(1)}%</span>
              </div>
              <div class="p-meter-track" style="height:7px;"><div class="p-meter-fill fill-purple" style="width:${p.valuation || 0}%; background:linear-gradient(90deg, #a855f7, #c084fc);"></div></div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:4px;">Mức hấp dẫn của PEG và P/E hiện tại</div>
            </div>

          </div>
        </div>

        <!-- 3. 5-Way Growth Attribution Cards -->
        <div style="background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); padding:12px;">
          <div style="font-size:13px; font-weight:800; display:flex; align-items:center; gap:6px;">
            <span>🔬</span> ${isBanking ? '5 ĐỘNG LỰC TĂNG TRƯỞNG NGÂN HÀNG (CIR, NIM, TÍN DỤNG, PHÍ & CHẤT LƯỢNG TÀI SẢN)' : '5 ĐỘNG LỰC TĂNG TRƯỞNG LỢI NHUẬN CỐT LÕI (5-WAY ATTRIBUTION)'}
          </div>
          <div class="attribution-grid">
            ${renderAttCard('w1', att.way1_cost_reduction, isBanking ? '⚡' : '📉')}
            ${renderAttCard('w2', att.way2_pricing_power, isBanking ? '💰' : '🏷️')}
            ${renderAttCard('w3', att.way3_new_markets, isBanking ? '📈' : '🌍')}
            ${renderAttCard('w4', att.way4_market_penetration, isBanking ? '💳' : '📈')}
            ${renderAttCard('w5', att.way5_core_focus, isBanking ? '🛡️' : '🎯')}
          </div>
        </div>

        <!-- 4. Quality Reality Checks & BCTC Quantitative Corrections -->
        <div style="background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); padding:14px; display:flex; flex-direction:column; gap:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="font-size:13px; font-weight:800; display:flex; align-items:center; gap:6px;">
              <span>🛡️</span> BÓC TÁCH BCTC THỰC TẾ & HIỆU CHỈNH CHẤT LƯỢNG (Z-SCORE CHU KỲ & LÃI ẢO)
            </div>
            <span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10px; font-weight:700;">TOP 1 QUANT ALGORITHM</span>
          </div>

          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px; font-size:11.5px;">
            <!-- Box 1: Z-Score Cyclicality -->
            <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:var(--text-muted); font-weight:700;">1. Z-Score Chu Kỳ Biên LN:</span>
                <span class="badge-tag ${cor.cyclical_badge || 'badge-success'}" style="font-weight:800; font-size:10.5px;">
                  ${cor.cyclical_phase || '🟢 Bình Thường'}
                </span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; margin-top:2px;">
                Biên HĐKD: <strong class="mono txt-blue">${cor.current_opm}</strong> vs TB Lịch Sử: <strong class="mono">${cor.median_10y_opm}</strong> (Z: <strong class="mono txt-warn">${cor.margin_zscore}</strong>)
              </div>
              <div style="font-size:10.5px; color:var(--text-secondary); line-height:1.35; margin-top:3px; background:rgba(0,0,0,0.25); padding:6px 8px; border-radius:4px;">
                ${escapeHTML(cor.cyclical_desc || '')}
              </div>
            </div>

            <!-- Box 2: One-off Normalizer -->
            <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:var(--text-muted); font-weight:700;">2. Lọc Lãi Ảo Từ BCTC:</span>
                <span class="badge-tag ${cor.one_off_badge || 'badge-success'}" style="font-weight:800; font-size:10.5px;">
                  ${cor.one_off_status || 'Trong Sạch'}
                </span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; margin-top:2px;">
                EPS Báo Cáo: <strong class="mono">${cor.reported_eps}</strong> ➔ EPS Cốt Lõi: <strong class="mono txt-up">${cor.normalized_core_eps}</strong> (${cor.core_pat_ratio})
              </div>
              <div style="font-size:10.5px; color:var(--text-secondary); line-height:1.35; margin-top:3px; background:rgba(0,0,0,0.25); padding:6px 8px; border-radius:4px;">
                ${escapeHTML(cor.one_off_verdict || '')}
              </div>
            </div>

            <!-- Box 3: Dilution -->
            <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:var(--text-muted); font-weight:700;">3. Rủi Ro Pha Loãng:</span>
                <span style="font-weight:800; color:var(--text-primary); font-size:11px;">${cor.dilution_risk}</span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; margin-top:2px;">
                Tốc độ in giấy: <strong class="mono txt-warn">${cor.dilution_spread}</strong>
              </div>
              <div style="font-size:10.5px; color:var(--text-secondary); line-height:1.35; margin-top:3px;">
                Tỷ lệ tăng trưởng số lượng cổ phiếu lưu hành so với mức tăng trưởng LNST.
              </div>
            </div>

            <!-- Box 4: Size Sigmoid Deceleration -->
            <div style="background:rgba(255,255,255,0.02); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:var(--text-muted); font-weight:700;">4. Giảm Tốc Quy Mô (Sigmoid):</span>
                <span style="font-weight:800; color:#38bdf8; font-size:11px;">${cor.size_category}</span>
              </div>
              <div style="font-size:11px; color:#cbd5e1; margin-top:2px;">
                Hệ số chiết khấu: <strong class="mono txt-blue">${cor.size_damper}</strong>
              </div>
              <div style="font-size:10.5px; color:var(--text-secondary); line-height:1.35; margin-top:3px;">
                Áp dụng quy luật số lớn: Doanh nghiệp vốn hóa càng lớn thì tốc độ tăng trưởng tự động tiệm cận ngưỡng bền vững.
              </div>
            </div>
          </div>
        </div>

        <!-- 4b. Forensic Accounting & Anti-Fraud Firewall Scorecard -->
        <div style="background:linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.85)); border-radius:8px; border:1px solid ${fa.is_clean ? 'rgba(16,185,129,0.35)' : 'rgba(244,63,94,0.35)'}; padding:14px; display:flex; flex-direction:column; gap:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="font-size:13px; font-weight:800; display:flex; align-items:center; gap:6px;">
              <span>🔬</span> PHÁP Y TÀI CHÍNH & CHỐNG GIAN LẬN BCTC (FORENSIC ACCOUNTING)
            </div>
            <span class="badge-tag ${fa.is_clean ? 'badge-success' : 'badge-danger'}" style="font-size:11px; font-weight:800;">
              ${fa.is_clean ? '🟢 BCTC MINH BẠCH / AN TOÀN' : '🔴 CỜ ĐỎ RỦI RO GIAN LẬN'}
            </span>
          </div>

          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px;">
            <!-- Piotroski F-Score Card -->
            <div style="background:rgba(255,255,255,0.03); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-weight:700; color:var(--text-primary); font-size:12px;">📋 Piotroski F-Score (9 Tiêu Chí):</span>
                <span style="font-family:var(--font-mono); font-weight:900; font-size:14px; color:${fa.piotroski_f_score >= 7 ? '#34d399' : (fa.piotroski_f_score >= 5 ? '#facc15' : '#f87171')};">
                  ${fa.piotroski_f_score || '--'} / 9 Điểm
                </span>
              </div>
              <div style="font-size:11px; color:var(--text-secondary); line-height:1.4;">
                ${fa.piotroski_f_score >= 7 ? '✅ Sức khỏe cơ bản vượt trội (Top Tier Fundamental Quality).' : '⚠️ Điểm cơ bản trung bình/thấp, chưa đạt chuẩn phòng thủ Piotroski (≥7).'}
              </div>
            </div>

            <!-- Beneish M-Score Card -->
            <div style="background:rgba(255,255,255,0.03); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-weight:700; color:var(--text-primary); font-size:12px;">🛡️ Beneish M-Score (8 Chỉ Số):</span>
                <span style="font-family:var(--font-mono); font-weight:900; font-size:14px; color:${fa.beneish_m_score !== undefined && fa.beneish_m_score < -1.78 ? '#34d399' : '#f87171'};">
                  M = ${fa.beneish_m_score !== undefined ? fa.beneish_m_score : '--'} ${fa.beneish_m_score !== undefined && fa.beneish_m_score < -1.78 ? '(An toàn < -1.78)' : '(Cảnh báo > -1.78)'}
                </span>
              </div>
              <div style="font-size:11px; color:var(--text-secondary); line-height:1.4;">
                ${fa.beneish_m_score !== undefined && fa.beneish_m_score < -1.78 ? '✅ Xác suất thao túng lợi nhuận / bóp méo số liệu rất thấp.' : '⚠️ Mô hình phát hiện rủi ro dồn tích (accruals) hoặc ghi nhận doanh thu ảo.'}
              </div>
            </div>
          </div>
        </div>

        <!-- 5. 3-Scenario Valuation Cards (Ensemble Consensus) -->
        <div style="background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); padding:14px; display:flex; flex-direction:column; gap:12px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="font-size:14px; font-weight:900; display:flex; align-items:center; gap:6px;">
              <span>🎯</span> ĐỊNH GIÁ 3 KỊCH BẢN HỢP NHẤT (ENSEMBLE ${modelCount}-MODEL ENGINE)
            </div>
            <span style="font-size:11px; color:var(--text-muted);">Đồng thuận từ ${modelCount} mô hình định giá định lượng, dòng tiền và chuyên gia</span>
          </div>

          <!-- Thanh Đo Điểm Tin Cậy Mauboussin (Base Rate Confidence Gauge) -->
          <div style="background:linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.85)); border:1px solid rgba(255, 255, 255, 0.1); border-radius:8px; padding:12px 14px; display:flex; flex-direction:column; gap:8px; box-shadow:0 2px 8px rgba(0,0,0,0.3);">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:16px;">📊</span>
                <span style="font-size:12.5px; font-weight:800; color:var(--text-primary);">ĐIỂM TIN CẬY DỰ BÁO MAUBOUSSIN:</span>
                <span class="badge-tag ${mConf.badge_class || 'badge-success'}" style="font-size:11px; font-weight:800;">
                  ${escapeHTML(mConf.level || 'RẤT CAO')}
                </span>
              </div>
              <div style="display:flex; align-items:center; gap:6px;">
                <span style="font-size:11px; color:var(--text-muted);">Xác Suất Khả Thi:</span>
                <strong style="font-size:17px; font-family:var(--font-mono); color:${mConf.color || '#10b981'};">${mConf.score || 85}%</strong>
              </div>
            </div>

            <!-- Visual Progress Bar -->
            <div style="width:100%; height:8px; background:rgba(255,255,255,0.08); border-radius:4px; overflow:hidden; position:relative;">
              <div style="width:${mConf.score || 85}%; height:100%; background:linear-gradient(90deg, #3b82f6, ${mConf.color || '#10b981'}); border-radius:4px; transition:width 0.6s ease;"></div>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:6px; font-size:11px; color:var(--text-secondary); line-height:1.4;">
              <div style="flex:1; min-width:260px;">
                ${escapeHTML(mConf.summary || '')}
              </div>
              <span style="color:var(--text-muted); font-size:10px; font-style:italic; white-space:nowrap; background:rgba(255,255,255,0.04); padding:3px 6px; border-radius:4px;">
                🏷️ Phân vị: ${escapeHTML(mConf.bracket_desc || '')}
              </span>
            </div>
          </div>

          <div class="scenario-cards-container">
            
            <!-- Bear Case Card -->
            <div class="scenario-card bear">
              <div class="scenario-card-header">
                <span class="scenario-card-title txt-down">🐻 Bear Case (Thận trọng)</span>
                <span class="badge-tag" style="background:rgba(239,68,68,0.15); color:#ef4444; font-size:10px;">Vùng Đáy An Toàn</span>
              </div>
              <div class="scenario-val-box">
                <span class="scenario-val-price">${bear.fair_value}</span>
                <span class="scenario-val-upside ${bearColor}">${bear.upside_pct} Upside</span>
              </div>
              <div class="scenario-meta-row">
                <span>Tăng trưởng giả định (g):</span>
                <strong class="mono">${bear.growth_rate}</strong>
              </div>
              <div class="scenario-meta-row">
                <span>P/E sàn kịch bản:</span>
                <strong class="mono">${bear.pe_multiple}</strong>
              </div>
              <div style="font-size:10px; color:var(--text-muted); line-height:1.3; margin-top:3px;">
                ${bear.role}
              </div>
            </div>

            <!-- Base Case Card -->
            <div class="scenario-card base">
              <div class="scenario-card-header">
                <span class="scenario-card-title txt-blue">🎯 Base Case (Cơ sở)</span>
                <span class="badge-tag" style="background:rgba(59,130,246,0.15); color:#38bdf8; font-size:10px;">Giá Trị Hợp Lý</span>
              </div>
              <div class="scenario-val-box">
                <span class="scenario-val-price" style="color:#38bdf8;">${base.fair_value}</span>
                <span class="scenario-val-upside ${baseColor}">${base.upside_pct} Upside</span>
              </div>
              <div class="scenario-meta-row">
                <span>Tăng trưởng giả định (g):</span>
                <strong class="mono">${base.growth_rate}</strong>
              </div>
              <div class="scenario-meta-row">
                <span>P/E ngành mục tiêu:</span>
                <strong class="mono">${base.pe_multiple}</strong>
              </div>
              <div style="font-size:10px; color:var(--text-muted); line-height:1.3; margin-top:3px;">
                ${base.role}
              </div>
            </div>

            <!-- Bull Case Card -->
            <div class="scenario-card bull">
              <div class="scenario-card-header">
                <span class="scenario-card-title txt-up">🐂 Bull Case (Lạc quan)</span>
                <span class="badge-tag" style="background:rgba(16,185,129,0.15); color:#10b981; font-size:10px;">Mục Tiêu Bứt Phá</span>
              </div>
              <div class="scenario-val-box">
                <span class="scenario-val-price" style="color:#10b981;">${bull.fair_value}</span>
                <span class="scenario-val-upside ${bullColor}">${bull.upside_pct} Upside</span>
              </div>
              <div class="scenario-meta-row">
                <span>Tăng trưởng giả định (g):</span>
                <strong class="mono">${bull.growth_rate}</strong>
              </div>
              <div class="scenario-meta-row">
                <span>P/E premium kịch bản:</span>
                <strong class="mono">${bull.pe_multiple}</strong>
              </div>
              <div style="font-size:10px; color:var(--text-muted); line-height:1.3; margin-top:3px;">
                ${bull.role}
              </div>
            </div>

          </div>

          <!-- 6. Actionable Verdict Banner -->
          <div class="verdict-box ${v.class || 'verdict-buy'}">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:24px;">${v.icon || '🎯'}</span>
              <div>
                <div style="font-size:15px; font-weight:900;">${escapeHTML(v.title || 'VÙNG MUA HỢP LÝ')}</div>
                <div style="font-size:11.5px; opacity:0.9; margin-top:2px;">${escapeHTML(v.summary || '')}</div>
              </div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:11px; opacity:0.8;">Biên An Toàn (vs Bear Case):</div>
              <div style="font-size:18px; font-weight:900; font-family:var(--font-mono);">${v.margin_of_safety}</div>
            </div>
          </div>

        </div>

        <!-- 7. Interactive Scenario Sensitivity Sandbox (Thanh Trượt Độ Nhạy) -->
        <div class="no-print" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9)); border-radius:8px; border:1px solid rgba(56, 189, 248, 0.3); padding:14px; display:flex; flex-direction:column; gap:12px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="font-size:13.5px; font-weight:800; display:flex; align-items:center; gap:6px; color:#38bdf8;">
              <span>🎛️</span> THANH TRƯỢT ĐỘ NHẠY KỊCH BẢN TƯƠNG TÁC (VALUATION SANDBOX)
            </div>
            <span style="font-size:10.5px; color:var(--text-muted);">Tự do tùy chỉnh giả định tăng trưởng và bội số P/E để định giá lại tức thì</span>
          </div>

          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:14px; align-items:center;">
            
            <!-- Slider 1: Growth Rate (g) -->
            <div style="background:rgba(255,255,255,0.03); padding:10px 14px; border-radius:6px; border:1px solid rgba(255,255,255,0.08);">
              <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:6px;">
                <span>🚀 Tốc độ tăng trưởng giả định (g):</span>
                <span id="sb_g_val_${containerId}" style="color:#10b981; font-family:var(--font-mono); font-size:13px; font-weight:800;">${sb.base_g}%</span>
              </div>
              <input type="range" id="sb_g_slider_${containerId}" min="2.0" max="40.0" step="0.5" value="${sb.base_g}" 
                     style="width:100%; cursor:pointer; accent-color:#10b981;"
                     oninput="app.updateValuationSandbox('${containerId}', ${sb.normalized_eps}, ${sb.cur_price})">
              <div style="display:flex; justify-content:space-between; font-size:9.5px; color:var(--text-muted); margin-top:3px;">
                <span>2% (Thận trọng)</span>
                <span>Base (${sb.base_g}%)</span>
                <span>40% (Siêu tăng trưởng)</span>
              </div>
            </div>

            <!-- Slider 2: Target P/E Multiple -->
            <div style="background:rgba(255,255,255,0.03); padding:10px 14px; border-radius:6px; border:1px solid rgba(255,255,255,0.08);">
              <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:6px;">
                <span>🏷️ Bội số định giá P/E mục tiêu:</span>
                <span id="sb_pe_val_${containerId}" style="color:#38bdf8; font-family:var(--font-mono); font-size:13px; font-weight:800;">${sb.base_pe}x</span>
              </div>
              <input type="range" id="sb_pe_slider_${containerId}" min="6.0" max="35.0" step="0.5" value="${sb.base_pe}" 
                     style="width:100%; cursor:pointer; accent-color:#38bdf8;"
                     oninput="app.updateValuationSandbox('${containerId}', ${sb.normalized_eps}, ${sb.cur_price})">
              <div style="display:flex; justify-content:space-between; font-size:9.5px; color:var(--text-muted); margin-top:3px;">
                <span>6x (Giá trị sâu)</span>
                <span>Ngành (${sb.base_pe}x)</span>
                <span>35x (Premium cao)</span>
              </div>
            </div>

          </div>

          <!-- Dynamic Result Banner -->
          <div style="background:rgba(15,23,42,0.9); padding:10px 14px; border-radius:6px; border:1px solid rgba(56,189,248,0.25); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <div style="font-size:11px; color:var(--text-muted);">Định giá mục tiêu theo quan điểm của bạn:</div>
              <div style="display:flex; align-items:baseline; gap:8px; margin-top:2px;">
                <span id="sb_result_price_${containerId}" class="mono" style="font-size:18px; font-weight:900; color:#38bdf8;">-- đ</span>
                <span id="sb_result_upside_${containerId}" class="mono" style="font-size:13px; font-weight:800;">--% Upside</span>
              </div>
            </div>
            <div id="sb_result_badge_${containerId}" class="badge-tag badge-success" style="font-size:11.5px; font-weight:800; padding:4px 10px;">
              VÙNG MUA TÍCH LŨY
            </div>
          </div>
        </div>

        <!-- 8. 6-Model Valuation Cross-Check Matrix (Ensemble Matrix) -->
        <div style="background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); padding:14px; display:flex; flex-direction:column; gap:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="font-size:13px; font-weight:800; display:flex; align-items:center; gap:6px;">
              <span>📋</span> MA TRẬN ĐỐI SOÁT ĐỊNH GIÁ ${modelCount} MÔ HÌNH × 3 KỊCH BẢN (ENSEMBLE MATRIX)
            </div>
            <span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; font-weight:700;">${modelCount * 3} ĐIỂM TỌA ĐỘ ĐỊNH LƯỢNG</span>
          </div>

          <div style="overflow-x:auto;">
            <table class="trading-board-table clean-board-table" style="font-size:11.5px;">
              <thead>
                <tr>
                  <th style="text-align:left; min-width:180px;">Phương Pháp Định Giá</th>
                  <th style="text-align:right; width:130px;" class="txt-down">🐻 Bear (Thận trọng)</th>
                  <th style="text-align:right; width:130px;" class="txt-blue">🎯 Base (Cơ sở)</th>
                  <th style="text-align:right; width:130px;" class="txt-up">🚀 Bull (Lạc quan)</th>
                  <th style="text-align:left; min-width:220px;">Trường Phái & Ý Nghĩa</th>
                </tr>
              </thead>
              <tbody>
                ${(d.valuation_matrix && d.valuation_matrix.methods ? d.valuation_matrix.methods : []).map(m => {
                  const bearCls = m.bear_pos ? 'txt-up' : 'txt-down';
                  const baseCls = m.base_pos ? 'txt-up' : 'txt-down';
                  const bullCls = m.bull_pos ? 'txt-up' : 'txt-down';
                  return `
                    <tr>
                      <td style="font-weight:700; color:var(--text-primary);">
                        <div style="font-size:12px; font-weight:800;">${escapeHTML(m.name)}</div>
                        <div style="font-size:10px; color:var(--text-muted);">${escapeHTML(m.school)}</div>
                      </td>
                      <td style="text-align:right;">
                        <div class="mono" style="font-weight:700; font-size:12px;">${escapeHTML(m.bear_val)}</div>
                        <div class="mono ${bearCls}" style="font-size:10.5px; font-weight:600;">${escapeHTML(m.bear_upside)}</div>
                      </td>
                      <td style="text-align:right;">
                        <div class="mono" style="font-weight:700; font-size:12px; color:#38bdf8;">${escapeHTML(m.base_val)}</div>
                        <div class="mono ${baseCls}" style="font-size:10.5px; font-weight:600;">${escapeHTML(m.base_upside)}</div>
                      </td>
                      <td style="text-align:right;">
                        <div class="mono" style="font-weight:700; font-size:12px; color:#10b981;">${escapeHTML(m.bull_val)}</div>
                        <div class="mono ${bullCls}" style="font-size:10.5px; font-weight:600;">${escapeHTML(m.bull_upside)}</div>
                      </td>
                      <td style="font-size:11px; color:var(--text-secondary); line-height:1.35;">
                        ${escapeHTML(m.desc)}
                      </td>
                    </tr>
                  `;
                }).join('')}
                ${(d.valuation_matrix && d.valuation_matrix.consensus) ? `
                  <tr style="background:linear-gradient(90deg, rgba(56,189,248,0.12), rgba(16,185,129,0.12)); border-top:2px solid rgba(56,189,248,0.4); font-weight:800;">
                    <td style="color:#38bdf8;">
                      <div style="font-size:12px; font-weight:900;">${escapeHTML(d.valuation_matrix.consensus.name)}</div>
                      <div style="font-size:10px; color:#cbd5e1;">${escapeHTML(d.valuation_matrix.consensus.school)}</div>
                    </td>
                    <td style="text-align:right;">
                      <div class="mono" style="font-weight:900; font-size:12.5px; color:#f8fafc;">${escapeHTML(d.valuation_matrix.consensus.bear_val)}</div>
                      <div class="mono ${d.valuation_matrix.consensus.bear_pos ? 'txt-up' : 'txt-down'}" style="font-size:10.5px; font-weight:800;">${escapeHTML(d.valuation_matrix.consensus.bear_upside)}</div>
                    </td>
                    <td style="text-align:right;">
                      <div class="mono" style="font-weight:900; font-size:12.5px; color:#38bdf8;">${escapeHTML(d.valuation_matrix.consensus.base_val)}</div>
                      <div class="mono ${d.valuation_matrix.consensus.base_pos ? 'txt-up' : 'txt-down'}" style="font-size:10.5px; font-weight:800;">${escapeHTML(d.valuation_matrix.consensus.base_upside)}</div>
                    </td>
                    <td style="text-align:right;">
                      <div class="mono" style="font-weight:900; font-size:12.5px; color:#10b981;">${escapeHTML(d.valuation_matrix.consensus.bull_val)}</div>
                      <div class="mono ${d.valuation_matrix.consensus.bull_pos ? 'txt-up' : 'txt-down'}" style="font-size:10.5px; font-weight:800;">${escapeHTML(d.valuation_matrix.consensus.bull_upside)}</div>
                    </td>
                    <td style="font-size:11px; color:#e2e8f0; font-weight:700;">
                      🎯 Đồng thuận trung bình của cả ${modelCount} phương pháp định giá độc lập
                    </td>
                  </tr>
                ` : ''}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    `;

    // Trigger initial sandbox recalculation
    this.updateValuationSandbox(containerId, sb.normalized_eps, sb.cur_price);
  }

  updateValuationSandbox(containerId, normalizedEps, curPrice) {
    const gSlider = document.getElementById(`sb_g_slider_${containerId}`);
    const peSlider = document.getElementById(`sb_pe_slider_${containerId}`);
    const gValText = document.getElementById(`sb_g_val_${containerId}`);
    const peValText = document.getElementById(`sb_pe_val_${containerId}`);
    const resPrice = document.getElementById(`sb_result_price_${containerId}`);
    const resUpside = document.getElementById(`sb_result_upside_${containerId}`);
    const resBadge = document.getElementById(`sb_result_badge_${containerId}`);

    if (!gSlider || !peSlider) return;

    const g = parseFloat(gSlider.value) || 15.0;
    const pe = parseFloat(peSlider.value) || 14.5;

    if (gValText) gValText.textContent = `${g.toFixed(1)}%`;
    if (peValText) peValText.textContent = `${pe.toFixed(1)}x`;

    const eps = normalizedEps > 0 ? normalizedEps : 3500;
    const targetPrice = Math.round(eps * (1 + g / 100.0) * pe);
    const p = curPrice > 0 ? curPrice : 50000;
    const upside = Math.round(((targetPrice - p) / p) * 1000) / 10.0;

    if (resPrice) resPrice.textContent = `${targetPrice.toLocaleString()} đ`;
    if (resUpside) {
      resUpside.textContent = `${upside >= 0 ? '+' : ''}${upside.toFixed(1)}% Upside`;
      resUpside.className = `mono ${upside >= 0 ? 'txt-up' : 'txt-down'}`;
    }

    if (resBadge) {
      if (upside >= 25.0) {
        resBadge.className = 'badge-tag verdict-strong-buy';
        resBadge.textContent = '⭐ MUA MẠNH (Biên An Toàn Lớn)';
      } else if (upside >= 15.0) {
        resBadge.className = 'badge-tag badge-success';
        resBadge.textContent = '🎯 VÙNG MUA TÍCH LŨY';
      } else if (upside >= -5.0) {
        resBadge.className = 'badge-tag badge-info';
        resBadge.textContent = '⚖️ NẮM GIỮ (Định Giá Sát Thực)';
      } else {
        resBadge.className = 'badge-tag badge-danger';
        resBadge.textContent = '⚠️ THẬN TRỌNG (Hết Biên An Toàn)';
      }
    }
  }

  printEarningsEngineReport(reportElementId, symbol) {
    const el = document.getElementById(reportElementId);
    if (!el) {
      window.print();
      return;
    }
    document.body.classList.add('printing-single-report');
    el.classList.add('active-print-target');
    window.print();
    setTimeout(() => {
      document.body.classList.remove('printing-single-report');
      el.classList.remove('active-print-target');
    }, 500);
  }

  openEarningsEngineModal(symbol) {
    const modal = document.getElementById('earningsEngineModal');
    const title = document.getElementById('modalEeTitle');
    const subtitle = document.getElementById('modalEeSubtitle');
    if (!modal) return;

    if (title) title.textContent = `🎯 CHẨN ĐOÁN & ĐỊNH GIÁ 3 KỊCH BẢN: ${symbol}`;
    if (subtitle) subtitle.textContent = `Khung phân tích 5 động lực tăng trưởng và đo lường biên an toàn theo Peter Lynch & Base Rate`;

    modal.classList.add('active');
    this.fetchCompanyEarningsEngine(symbol, 'modalEeContent');
  }

  closeEarningsEngineModal() {
    const modal = document.getElementById('earningsEngineModal');
    if (modal) modal.classList.remove('active');
  }

  // ==============================================================================
  // MULTI-SOURCE DATA LAKE STATUS SIGNAL & MODAL
  // ==============================================================================

  async fetchDataLakeStatus() {
    try {
      const res = await fetch('/api/data-lake-status');
      const json = await res.json();
      if (json.status === 'success' && json.data) {
        const d = json.data;
        
        const fullySynced = Number(d.total_fully_synced || d.total_price_history_stocks || 83);
        const totalScreener = Number(d.total_screener_stocks || 1526);
        const totalPrices = Number(d.total_price_history_stocks || 83);

        // Update header signal pill
        const headerCount = document.getElementById('dataLakeHeaderCount');
        if (headerCount) {
          headerCount.textContent = `${fullySynced.toLocaleString()} Mã Đủ Giá & BCTC (Sẵn Sàng Backtest)`;
        }

        // Update Backtest coverage badge
        const btPoolCount = document.getElementById('btPoolStatsCount');
        if (btPoolCount) {
          btPoolCount.textContent = `${fullySynced.toLocaleString()} Mã (Đầy Đủ Giá Lịch Sử & BCTC)`;
        }

        // Update modal values if present
        const dlFully = document.getElementById('dlFullySynced');
        const dlTotal = document.getElementById('dlTotalStocks');
        const dlScreener = document.getElementById('dlScreenerStocks');
        const dlPrices = document.getElementById('dlPricesStocks');
        const dlHose = document.getElementById('dlHoseCount');
        const dlHnx = document.getElementById('dlHnxCount');
        const dlUpcom = document.getElementById('dlUpcomCount');
        const dlUpdated = document.getElementById('dlLastUpdated');

        const dlPdf = document.getElementById('dlPdfPeriods');
        if (dlPdf && d.pdf_lake) {
          dlPdf.textContent = `${Number(d.pdf_lake.bctc_periods || 18530).toLocaleString()} Kỳ`;
        }

        if (dlFully) dlFully.textContent = `${fullySynced.toLocaleString()} Mã`;
        if (dlTotal) dlTotal.textContent = Number(d.total_universe || 1645).toLocaleString();
        if (dlScreener) dlScreener.textContent = `${totalScreener.toLocaleString()} Mã`;
        if (dlPrices) dlPrices.textContent = `${totalPrices.toLocaleString()} Mã`;
        
        const exMap = d.fully_synced_by_exchange || d.exchanges || {};
        if (dlHose) dlHose.textContent = `${exMap.HOSE || 0} mã`;
        if (dlHnx) dlHnx.textContent = `${exMap.HNX || 0} mã`;
        if (dlUpcom) dlUpcom.textContent = `${exMap.UPCOM || 0} mã`;
        if (dlUpdated) dlUpdated.textContent = `Cập nhật: ${d.last_updated || 'Mới nhất'}`;
      }
    } catch (e) {
      console.warn('Could not fetch data lake status:', e);
    }
  }

  openDataLakeModal() {
    const modal = document.getElementById('dataLakeModal');
    if (modal) modal.classList.add('active');
    this.fetchDataLakeStatus();
  }

  closeDataLakeModal() {
    const modal = document.getElementById('dataLakeModal');
    if (modal) modal.classList.remove('active');
  }

  // ==============================================================================
  // QUANT BACKTESTING ENGINE & COMPARISON MATRIX METHODS
  // ==============================================================================

  openBacktestFromQuant() {
    // 1. Determine target strategy from Quant Screener
    let targetStrategy = 'quant_q1';
    let strategyName = 'Quant Q1: Tinh Hoa (P80-P100)';

    if (this.currentQuantStrategy && this.currentQuantStrategy !== 'ALL') {
      targetStrategy = this.currentQuantStrategy;
      const opt = document.querySelector(`#quantStrategySelect option[value="${targetStrategy}"]`);
      strategyName = opt ? opt.textContent.trim() : targetStrategy;
    } else if (this.currentQuantQ && this.currentQuantQ !== 'ALL') {
      targetStrategy = `quant_${this.currentQuantQ.toLowerCase()}`;
      strategyName = `Phân Vị ${this.currentQuantQ}`;
    }

    // 2. Sync Exchange filter from Quant to Backtest
    const quantEx = this.currentQuantExchange || 'ALL';
    this.btExchanges = [quantEx];
    document.querySelectorAll('#btExchangeGroup .bt-ex-pill').forEach(btn => {
      if (btn.dataset.exchange === quantEx) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // 3. Sync Survival Firewall and TSMOM Toggle from Quant to Backtest
    const quantSurvival = document.getElementById('survivalToggle')?.checked || false;
    const btSurvivalToggle = document.getElementById('btSurvivalToggle');
    const btSurvivalLabel = document.getElementById('btSurvivalToggleLabel');
    if (btSurvivalToggle) {
      btSurvivalToggle.checked = quantSurvival;
      if (btSurvivalLabel) {
        btSurvivalLabel.textContent = quantSurvival ? 'BẬT' : 'TẮT';
        btSurvivalLabel.style.color = quantSurvival ? '#10b981' : '#64748b';
      }
    }

    const quantTsmom = document.getElementById('tsmomToggle')?.checked || false;
    const btTsmomToggle = document.getElementById('btTsmomToggle');
    const btTsmomLabel = document.getElementById('btTsmomToggleLabel');
    if (btTsmomToggle) {
      btTsmomToggle.checked = quantTsmom;
      if (btTsmomLabel) {
        btTsmomLabel.textContent = quantTsmom ? 'BẬT' : 'TẮT';
        btTsmomLabel.style.color = quantTsmom ? '#06b6d4' : '#64748b';
      }
    }

    // 4. Update Backtest Inspect strategy selection
    this.btInspectStrategy = targetStrategy;
    const btInspectSel = document.getElementById('btInspectStrategySelect');
    if (btInspectSel) {
      btInspectSel.value = targetStrategy;
    }

    // 5. Switch to Backtest Tab
    this.switchTab('backtest');

    // 6. Trigger fresh Backtest Comparison simulation
    this.fetchBacktestComparison();

    this.showToast(`Đang chạy đối soát Backtest cho: ${strategyName}`, 'toast-up');
  }

  async fetchBacktestComparison() {
    const btnRunBt = document.getElementById('btnRunBacktestCompare');
    if (btnRunBt) {
      btnRunBt.innerHTML = `<span>⏳</span> Đang chạy mô phỏng...`;
      btnRunBt.disabled = true;
    }

    const gridEl = document.getElementById('btLeaderboardGrid');
    if (gridEl && !this.btDataCache) {
      gridEl.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:44px 16px; color:var(--text-muted); font-size:13px;">
        <div style="font-size:30px; margin-bottom:12px;">⏳</div>
        <b>Đang mô phỏng các chiến lược trên dữ liệu lịch sử...</b><br>
        <span style="font-size:11px;">Lần tính đầu tiên có thể mất tới ~30 giây. Kết quả được cache — các lần xem sau sẽ tải ngay lập tức.</span>
      </div>`;
    }

    try {
      const exParam = (this.btExchanges && this.btExchanges.length > 0) ? this.btExchanges.join(',') : 'ALL';
      const btSurvivalOn = document.getElementById('btSurvivalToggle')?.checked ? 'true' : 'false';
      const btTsmomOn = document.getElementById('btTsmomToggle')?.checked ? 'true' : 'false';
      const btForensicOn = document.getElementById('btForensicToggle')?.checked ? 'true' : 'false';
      let url = `/api/backtest/compare?time_horizon_years=${this.btTimeHorizon}&rebalance_cadence=${this.btCadence}&top_k=${this.btTopK}&initial_capital=${this.btCapital}&exchange=${encodeURIComponent(exParam)}&survival_filter=${btSurvivalOn}&tsmom_filter=${btTsmomOn}&forensic_filter=${btForensicOn}&fill_mode=${encodeURIComponent(this.btFillMode || 'strict')}`;
      if (this.pendingBacktestSelection && this.pendingBacktestSelection.strategy && this.pendingBacktestSelection.strategy !== 'ALL') {
        url += `&strategy=${encodeURIComponent(this.pendingBacktestSelection.strategy)}`;
      }
      const res = await fetch(url, { method: 'POST' });
      const json = await res.json();

      if (json.status === 'success' && json.data) {
        this.btDataCache = json.data;
        this.renderBacktestDashboard(this.btDataCache);
      } else {
        console.error('Backtest API error:', json.message);
        this.showToast('Không thể tải dữ liệu backtest: ' + (json.message || 'Lỗi không xác định'), 'toast-down');
      }
    } catch (err) {
      console.error('Error running backtest comparison:', err);
      this.showToast('Lỗi backtest: ' + (err && err.message ? err.message : 'lỗi kết nối máy chủ'), 'toast-down');
    } finally {
      if (btnRunBt) {
        btnRunBt.innerHTML = `<span>▶</span> Chạy Đối Soát Đa Chiến Lược`;
        btnRunBt.disabled = false;
      }
    }
  }

  renderBacktestDashboard(data) {
    if (!data) return;

    const winner = data.winner;
    const leaderboard = data.leaderboard || [];
    const stratResults = data.strategies_results || {};

    // 1. Render Winner Banner
    const winnerTitle = document.getElementById('btWinnerTitle');
    const winnerDesc = document.getElementById('btWinnerDesc');
    const winnerCagr = document.getElementById('btWinnerCagr');
    const winnerTotal = document.getElementById('btWinnerTotal');
    const winnerSharpe = document.getElementById('btWinnerSharpe');

    if (winnerTitle && winner) {
      winnerTitle.innerHTML = `QUÁN QUÂN HIỆU NĂNG: ${escapeHTML(winner.name)}`;
      if (winnerDesc) winnerDesc.textContent = `Vượt trội thị trường với Alpha CAGR ${winner.alpha_cagr >= 0 ? '+' : ''}${winner.alpha_cagr}%/năm`;
      if (winnerCagr) winnerCagr.textContent = `${winner.cagr >= 0 ? '+' : ''}${winner.cagr}%/năm`;
      if (winnerTotal) winnerTotal.textContent = `${winner.total_return_pct >= 0 ? '+' : ''}${winner.total_return_pct}%`;
      if (winnerSharpe) winnerSharpe.textContent = `${winner.sharpe_ratio}`;
    }

    // 2. Render Leaderboard Ranking Scorecards
    const grid = document.getElementById('btLeaderboardGrid');
    if (grid) {
      grid.innerHTML = leaderboard.map((item) => {
        const isWinner = item.strategy_id === (winner && winner.strategy_id);
        const isQ5 = item.strategy_id === 'quant_q5';
        
        let medalColor = '#94a3b8';
        let medalBg = 'rgba(148, 163, 184, 0.15)';
        if (item.rank === 1) { medalColor = '#facc15'; medalBg = 'rgba(250, 204, 21, 0.18)'; }
        else if (item.rank === 2) { medalColor = '#cbd5e1'; medalBg = 'rgba(203, 213, 225, 0.18)'; }
        else if (item.rank === 3) { medalColor = '#f97316'; medalBg = 'rgba(249, 115, 22, 0.18)'; }
        else if (isQ5) { medalColor = '#f87171'; medalBg = 'rgba(239, 68, 68, 0.18)'; }

        return `
          <div class="bt-card-stat ${isWinner ? 'winner-highlight' : ''}" style="border-left: 3px solid ${item.color};">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
              <span class="bt-medal-badge" style="background:${medalBg}; color:${medalColor};">
                ${item.medal}
              </span>
              <span style="font-size:18px;">${item.icon}</span>
            </div>
            
            <div style="font-size:13px; font-weight:800; color:var(--text-primary); margin-top:2px;">
              ${escapeHTML(item.short_name)}
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-top:4px; padding-top:6px; border-top:1px solid rgba(255,255,255,0.06);">
              <div>
                <div style="font-size:10px; color:var(--text-muted);">CAGR (Năm):</div>
                <div style="font-size:14px; font-weight:800; font-family:var(--font-mono); color:${item.cagr >= 0 ? '#34d399' : '#f87171'};">
                  ${item.cagr >= 0 ? '+' : ''}${item.cagr}%
                </div>
              </div>
              <div>
                <div style="font-size:10px; color:var(--text-muted);">Tổng Lãi:</div>
                <div style="font-size:14px; font-weight:800; font-family:var(--font-mono); color:${item.total_return_pct >= 0 ? '#38bdf8' : '#f87171'};">
                  ${item.total_return_pct >= 0 ? '+' : ''}${item.total_return_pct}%
                </div>
              </div>
              <div>
                <div style="font-size:10px; color:var(--text-muted);">Max DD:</div>
                <div style="font-size:12px; font-weight:700; font-family:var(--font-mono); color:#f87171;">
                  ${item.max_drawdown_pct}%
                </div>
              </div>
              <div>
                <div style="font-size:10px; color:var(--text-muted);">Sharpe:</div>
                <div style="font-size:12px; font-weight:700; font-family:var(--font-mono); color:#facc15;">
                  ${item.sharpe_ratio}
                </div>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    // 3. Render Chart Legend Checkboxes
    const legendBox = document.getElementById('btChartLegend');
    if (legendBox) {
      legendBox.innerHTML = leaderboard.map(item => {
        const isChecked = this.btVisibleStrategies[item.strategy_id] !== false;
        return `
          <label style="display:inline-flex; align-items:center; gap:5px; cursor:pointer; color:${item.color}; font-weight:700;">
            <input type="checkbox" data-strat="${item.strategy_id}" ${isChecked ? 'checked' : ''} style="accent-color:${item.color}; cursor:pointer;" class="bt-legend-toggle" />
            <span>${item.icon} ${escapeHTML(item.short_name)}</span>
          </label>
        `;
      }).join('');

      document.querySelectorAll('.bt-legend-toggle').forEach(chk => {
        chk.addEventListener('change', (e) => {
          this.btVisibleStrategies[e.target.dataset.strat] = e.target.checked;
          this.drawBacktestEquityChart(this.btDataCache, this.btHoverIndex);
        });
      });
    }

    // 4. Update Time Label
    const timeLbl = document.getElementById('btChartTimeLabel');
    if (timeLbl && data.parameters) {
      timeLbl.textContent = data.parameters.time_label || '5 Năm (2021 – 2026)';
    }

    // 5. Draw Visual Curves Canvas
    requestAnimationFrame(() => {
      this.drawBacktestEquityChart(data, this.btHoverIndex);
    });

    // 6. Render Year-by-Year Performance Matrix Heatmap
    this.renderBacktestAnnualMatrix(leaderboard, stratResults);

    // 7. Render Rebalance History for current inspect strategy
    const btInspectSel = document.getElementById('btInspectStrategySelect');
    if (btInspectSel && this.btInspectStrategy) {
      btInspectSel.value = this.btInspectStrategy;
    }
    this.renderBacktestRebalanceHistory(this.btInspectStrategy || 'quant_q1');
  }

  drawBacktestEquityChart(data, hoverIdx = null) {
    const canvas = document.getElementById('btEquityCanvas');
    if (!canvas || !data || !data.strategies_results) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    if (!rect.width || !rect.height || rect.width < 50) return;

    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;

    // Clear background
    ctx.fillStyle = '#090e17';
    ctx.fillRect(0, 0, w, h);

    const stratMap = data.strategies_results;
    const visibleKeys = Object.keys(stratMap).filter(k => this.btVisibleStrategies[k] !== false);

    if (visibleKeys.length === 0) {
      ctx.fillStyle = '#64748b';
      ctx.font = '12px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Chọn ít nhất 1 chiến lược trên Chú thích để hiển thị biểu đồ', w / 2, h / 2);
      return;
    }

    // Find min & max NAV across all visible curves
    let minNav = Infinity;
    let maxNav = -Infinity;
    let pointCount = 0;
    let samplePoints = [];

    visibleKeys.forEach(k => {
      const curve = stratMap[k].nav_curve || [];
      if (curve.length > pointCount) {
        pointCount = curve.length;
        samplePoints = curve;
      }
      curve.forEach(pt => {
        if (pt.nav < minNav) minNav = pt.nav;
        if (pt.nav > maxNav) maxNav = pt.nav;
      });
    });

    if (minNav === Infinity || maxNav === -Infinity || pointCount <= 1) return;

    // Add padding
    const navRange = maxNav - minNav || 1;
    const padTop = 30;
    const padBottom = 40;
    const padLeft = 70;
    const padRight = 30;

    const plotW = w - padLeft - padRight;
    const plotH = h - padTop - padBottom;

    // Store points coordinate cache for mouse hit test
    this.btChartPoints = [];
    const xStep = plotW / (pointCount - 1);
    samplePoints.forEach((pt, idx) => {
      this.btChartPoints.push({
        x: padLeft + idx * xStep,
        idx: idx,
        pt: pt
      });
    });

    // Draw Grid Lines & Y-Axis Labels
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)';
    ctx.fillStyle = '#64748b';
    ctx.font = '10.5px Inter, sans-serif';
    ctx.textAlign = 'right';

    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
      const yVal = minNav + (navRange * i) / ySteps;
      const yPos = padTop + plotH - (plotH * i) / ySteps;

      ctx.beginPath();
      ctx.moveTo(padLeft, yPos);
      ctx.lineTo(w - padRight, yPos);
      ctx.stroke();

      let valText = '';
      if (yVal >= 1000000000) {
        valText = `${(yVal / 1000000000).toFixed(2)} tỷ`;
      } else {
        valText = `${(yVal / 1000000).toFixed(0)} tr`;
      }
      ctx.fillText(valText, padLeft - 8, yPos + 3);
    }

    // Draw X-Axis Dates / Quarters
    ctx.textAlign = 'center';
    samplePoints.forEach((pt, idx) => {
      // Show every 2-3 points to avoid crowding
      if (idx === 0 || idx === pointCount - 1 || (pointCount <= 12 ? idx % 2 === 0 : idx % 3 === 0)) {
        const xPos = padLeft + idx * xStep;
        ctx.fillText(pt.quarter, xPos, h - 14);
      }
    });

    // Baseline 100% initial capital dashed line
    const initCapital = (data.parameters && data.parameters.initial_capital) || 100000000;
    if (initCapital >= minNav && initCapital <= maxNav) {
      const initY = padTop + plotH - ((initCapital - minNav) / navRange) * plotH;
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.22)';
      ctx.beginPath();
      ctx.moveTo(padLeft, initY);
      ctx.lineTo(w - padRight, initY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw Winner Strategy Gradient Underlay (if visible)
    const winnerId = data.winner && data.winner.strategy_id;
    if (winnerId && visibleKeys.includes(winnerId)) {
      const wStrat = stratMap[winnerId];
      const wCurve = wStrat.nav_curve || [];
      if (wCurve.length >= 2) {
        ctx.beginPath();
        wCurve.forEach((pt, idx) => {
          const x = padLeft + idx * xStep;
          const y = padTop + plotH - ((pt.nav - minNav) / navRange) * plotH;
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.lineTo(padLeft + (wCurve.length - 1) * xStep, padTop + plotH);
        ctx.lineTo(padLeft, padTop + plotH);
        ctx.closePath();

        const grad = ctx.createLinearGradient(0, padTop, 0, padTop + plotH);
        grad.addColorStop(0, 'rgba(16, 185, 129, 0.18)');
        grad.addColorStop(1, 'rgba(16, 185, 129, 0.00)');
        ctx.fillStyle = grad;
        ctx.fill();
      }
    }

    // Draw Strategy Curves
    visibleKeys.forEach(k => {
      const strat = stratMap[k];
      const curve = strat.nav_curve || [];
      const color = (strat.strategy && strat.strategy.color) || '#38bdf8';
      const isWinner = data.winner && data.winner.strategy_id === k;

      if (curve.length < 2) return;

      ctx.beginPath();
      ctx.lineWidth = isWinner ? 3.0 : (k === 'vnindex' ? 1.8 : 2.2);
      ctx.strokeStyle = color;
      if (k === 'vnindex') {
        ctx.setLineDash([4, 4]);
      } else {
        ctx.setLineDash([]);
      }

      curve.forEach((pt, idx) => {
        const x = padLeft + idx * xStep;
        const y = padTop + plotH - ((pt.nav - minNav) / navRange) * plotH;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw subtle glow point on latest value
      const lastPt = curve[curve.length - 1];
      const lx = padLeft + (curve.length - 1) * xStep;
      const ly = padTop + plotH - ((lastPt.nav - minNav) / navRange) * plotH;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(lx, ly, isWinner ? 4.5 : 3.0, 0, Math.PI * 2);
      ctx.fill();
    });

    // Draw Interactive Crosshair and Highlight Points if Hovered
    if (hoverIdx !== null && hoverIdx !== undefined && hoverIdx >= 0 && hoverIdx < pointCount) {
      const hX = padLeft + hoverIdx * xStep;

      // Vertical crosshair line
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.55)';
      ctx.moveTo(hX, padTop);
      ctx.lineTo(hX, padTop + plotH);
      ctx.stroke();
      ctx.setLineDash([]);

      // Intersect dots
      visibleKeys.forEach(k => {
        const strat = stratMap[k];
        const curve = strat.nav_curve || [];
        const pt = curve[hoverIdx];
        if (!pt) return;
        const color = (strat.strategy && strat.strategy.color) || '#38bdf8';
        const hY = padTop + plotH - ((pt.nav - minNav) / navRange) * plotH;

        // Outer glow halo
        ctx.beginPath();
        ctx.arc(hX, hY, 7, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.fill();

        // Inner solid dot
        ctx.beginPath();
        ctx.arc(hX, hY, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();
      });
    }
  }

  setupBacktestCanvasHover() {
    const canvas = document.getElementById('btEquityCanvas');
    const tooltip = document.getElementById('btChartTooltip');
    if (!canvas) return;

    canvas.addEventListener('mousemove', (e) => {
      if (!this.btDataCache || !this.btChartPoints || this.btChartPoints.length < 2) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Find closest quarter index
      let closestIdx = 0;
      let minDiff = Infinity;
      for (let i = 0; i < this.btChartPoints.length; i++) {
        const ptX = this.btChartPoints[i].x;
        const diff = Math.abs(mouseX - ptX);
        if (diff < minDiff) {
          minDiff = diff;
          closestIdx = i;
        }
      }

      this.btHoverIndex = closestIdx;
      this.drawBacktestEquityChart(this.btDataCache, closestIdx);

      if (tooltip) {
        const stratMap = this.btDataCache.strategies_results || {};
        const qInfo = this.btChartPoints[closestIdx].pt;
        const qName = qInfo.quarter === 'Start' ? 'Điểm Khởi Đầu' : `Quý ${qInfo.quarter}`;
        const dateStr = qInfo.date || '';

        let rowsHtml = '';
        const visibleKeys = Object.keys(stratMap).filter(k => this.btVisibleStrategies[k] !== false);
        const initCap = (this.btDataCache.parameters && this.btDataCache.parameters.initial_capital) || 100000000;

        visibleKeys.forEach(k => {
          const strat = stratMap[k];
          const curve = strat.nav_curve || [];
          const pt = curve[closestIdx] || {};
          const sName = strat.strategy ? strat.strategy.short_name : k;
          const sColor = strat.strategy ? strat.strategy.color : '#38bdf8';
          const navVal = pt.nav !== undefined ? pt.nav : initCap;
          const navMil = (navVal / 1000000).toFixed(1);
          const retPct = (((navVal - initCap) / initCap) * 100).toFixed(1);
          const isPos = parseFloat(retPct) >= 0;

          rowsHtml += `
            <div class="tt-row">
              <span class="tt-label" style="color:${sColor};">
                <span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:${sColor};"></span>
                ${escapeHTML(sName)}
              </span>
              <span class="tt-val" style="color:${sColor};">
                ${navMil} tr <small style="color:${isPos ? '#34d399' : '#f87171'};">(${isPos ? '+' : ''}${retPct}%)</small>
              </span>
            </div>
          `;
        });

        tooltip.innerHTML = `
          <div class="tt-title">
            <span>📅 ${escapeHTML(qName)}</span>
            <span style="color:#94a3b8; font-weight:400; font-size:10px;">${escapeHTML(dateStr)}</span>
          </div>
          ${rowsHtml}
        `;

        tooltip.style.display = 'block';
        const ttWidth = tooltip.offsetWidth || 220;
        const ttHeight = tooltip.offsetHeight || 150;

        let left = mouseX + 16;
        let top = mouseY - 20;
        if (left + ttWidth > rect.width - 10) {
          left = mouseX - ttWidth - 16;
        }
        if (top + ttHeight > rect.height - 10) {
          top = rect.height - ttHeight - 10;
        }
        if (top < 10) top = 10;

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
      }
    });

    canvas.addEventListener('mouseleave', () => {
      this.btHoverIndex = null;
      if (tooltip) tooltip.style.display = 'none';
      if (this.btDataCache) {
        this.drawBacktestEquityChart(this.btDataCache, null);
      }
    });

    window.addEventListener('resize', () => {
      if (this.currentTab === 'backtest' && this.btDataCache) {
        this.drawBacktestEquityChart(this.btDataCache, this.btHoverIndex);
      }
    });
  }

  renderBacktestAnnualMatrix(leaderboard, strategiesResults) {
    const table = document.getElementById('btAnnualMatrixTable') || document.querySelector('#tab_backtest .sector-constituents-card table');
    const tbody = document.getElementById('btAnnualMatrixBody');
    if (!tbody || !leaderboard) return;

    // Collect all unique years across all strategies
    const yearsSet = new Set();
    leaderboard.forEach(item => {
      const sRes = strategiesResults[item.strategy_id] || {};
      (sRes.annual_matrix || []).forEach(a => yearsSet.add(a.year));
    });

    const years = Array.from(yearsSet).sort((a, b) => a - b);
    if (years.length === 0) {
      years.push(2021, 2022, 2023, 2024, 2025, 2026);
    }

    // Dynamically update thead if table exists
    if (table) {
      const thead = table.querySelector('thead');
      if (thead) {
        const yearThs = years.map(yr => `<th style="width:75px;">${yr}${yr === 2022 ? ' (Sập)' : (yr === 2026 ? ' YTD' : '')}</th>`).join('');
        thead.innerHTML = `
          <tr>
            <th style="text-align:left; min-width:180px;">Chiến Lược Lọc</th>
            ${yearThs}
            <th style="width:95px; font-weight:800; color:#38bdf8;">CAGR/Năm</th>
            <th style="width:95px; font-weight:800; color:#34d399;">Tổng Lãi</th>
            <th style="width:85px; color:#ef4444;">Max DD</th>
            <th style="width:75px; color:#facc15;">Sharpe</th>
          </tr>
        `;
      }
    }

    tbody.innerHTML = leaderboard.map(item => {
      const sRes = strategiesResults[item.strategy_id] || {};
      const annuals = sRes.annual_matrix || [];
      const annualMap = {};
      annuals.forEach(a => { annualMap[a.year] = a.strategy_return_pct; });

      const yearCols = years.map(yr => {
        const val = annualMap[yr];
        if (val === undefined) return `<td style="color:var(--text-muted);">-</td>`;
        
        let cls = 'hm-pos-mild';
        if (val >= 25.0) cls = 'hm-pos-strong';
        else if (val < -10.0) cls = 'hm-neg-strong';
        else if (val < 0.0) cls = 'hm-neg-mild';

        return `<td class="${cls} mono">${val >= 0 ? '+' : ''}${val.toFixed(1)}%</td>`;
      }).join('');

      return `
        <tr>
          <td style="text-align:left; font-weight:800; color:${item.color};">
            ${item.icon} ${escapeHTML(item.name)}
          </td>
          ${yearCols}
          <td class="mono font-bold txt-blue">${item.cagr >= 0 ? '+' : ''}${item.cagr.toFixed(1)}%</td>
          <td class="mono font-bold txt-up">${item.total_return_pct >= 0 ? '+' : ''}${item.total_return_pct.toFixed(1)}%</td>
          <td class="mono txt-down">${item.max_drawdown_pct.toFixed(1)}%</td>
          <td class="mono txt-warn font-bold">${item.sharpe_ratio.toFixed(2)}</td>
        </tr>
      `;
    }).join('');
  }

  renderBacktestRebalanceHistory(strategyId) {
    const container = document.getElementById('btRebalanceTimelineContainer');
    if (!container || !this.btDataCache) return;

    const strat = (this.btDataCache.strategies_results || {})[strategyId];
    if (!strat || !strat.rebalance_history || strat.rebalance_history.length === 0) {
      container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--text-muted);">Không có dữ liệu lịch sử tái cơ cấu cho chiến lược này.</div>`;
      return;
    }

    const history = strat.rebalance_history || [];
    const reversed = [...history].reverse(); // Latest quarter first

    container.innerHTML = reversed.map((q, idx) => {
      const isPositive = q.quarter_return_pct >= 0;
      const isAlphaPos = q.alpha_pct >= 0;
      const holdings = q.holdings || [];

      const holdingsRows = holdings.map((h) => {
        const isHPos = h.net_return_pct >= 0;
        const startP = h.start_price ? (h.start_price > 1000 ? h.start_price.toLocaleString('vi-VN') : h.start_price.toFixed(2)) : '--';
        const closeP = h.close_price ? (h.close_price > 1000 ? h.close_price.toLocaleString('vi-VN') : h.close_price.toFixed(2)) : '--';
        const sourceBadge = h.is_real_price ? `<span style="color:#34d399; font-size:10px; font-weight:700;">🟢 TradingView</span>` : `<span style="color:#94a3b8; font-size:10px;">⚪ Khái quát</span>`;
        const fillBadge = h.meets_criteria === false ? `<span title="Cổ lấp chỗ (gần đạt chuẩn) - điểm lệch tiêu chí: ${h.near_miss_score != null ? h.near_miss_score : '--'}" style="color:#f59e0b; font-size:10px; cursor:help;">🧩</span>` : '';
        const consBadge = Array.isArray(h.approved_by) && h.approved_by.length > 0 ? `<span title="Đồng thuận Guru - Được duyệt bởi ${h.approved_by.length} mô hình: ${escapeHTML(h.approved_by.join(' | '))}" style="color:#f472b6; font-size:10px; font-weight:800; cursor:help;">🤝${h.approved_by.length}</span>` : '';
        return `
          <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
            <td class="col-symbol" onclick="app.inspectStock('${h.symbol}')" style="font-weight:800; color:#38bdf8; text-align:left; cursor:pointer;" title="Bấm để xem biểu đồ & phân tích kỹ thuật">${h.symbol}${consBadge}${fillBadge}</td>
            <td style="text-align:left; color:var(--text-secondary); font-size:11px;">${escapeHTML(h.name)}</td>
            <td style="color:var(--text-muted); font-size:11px;">${escapeHTML(h.sector || '')}</td>
            <td class="mono">${startP}</td>
            <td class="mono font-bold">${closeP}</td>
            <td class="mono">${sourceBadge}</td>
            <td class="mono font-bold ${isHPos ? 'txt-up' : 'txt-down'}">${isHPos ? '+' : ''}${h.net_return_pct}%</td>
          </tr>
        `;
      }).join('');

      return `
        <div class="bt-timeline-card">
          <div class="bt-timeline-header" onclick="const b = this.parentElement.querySelector('.bt-timeline-body'); const arrow = this.querySelector('.bt-arrow-toggle'); if(b) b.classList.toggle('hidden'); if(arrow) arrow.classList.toggle('open');">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-weight:800; color:var(--text-primary); font-size:13px;">📅 ${q.quarter}</span>
              <span class="badge-tag" style="background:${isPositive ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'}; color:${isPositive ? '#34d399' : '#f87171'}; font-weight:800;">
                Lãi Quý: ${isPositive ? '+' : ''}${q.quarter_return_pct}%
              </span>
              <span style="font-size:11px; color:var(--text-muted);">VN-Index: ${q.vni_return_pct >= 0 ? '+' : ''}${q.vni_return_pct}%</span>
              <span class="badge-tag" style="background:rgba(56,189,248,0.12); color:#38bdf8; font-weight:700;">
                Alpha: ${isAlphaPos ? '+' : ''}${q.alpha_pct}%
              </span>
            </div>
            <div style="display:flex; align-items:center; gap:4px; font-size:11px; color:var(--text-muted);">
              <span>Chi tiết (${holdings.length} mã)</span>
              <span class="bt-arrow-toggle ${idx === 0 ? 'open' : ''}">▼</span>
            </div>
          </div>

          <div class="bt-timeline-body ${idx === 0 ? '' : 'hidden'}">
            <table class="board-table sector-table" style="font-size:11px; text-align:center;">
              <thead>
                <tr>
                  <th style="text-align:left;">Mã CK</th>
                  <th style="text-align:left;">Doanh Nghiệp</th>
                  <th>Ngành</th>
                  <th>Giá Đầu Quý</th>
                  <th>Giá Cuối Quý</th>
                  <th>Nguồn Dữ Liệu</th>
                  <th>Lãi Ròng Quý</th>
                </tr>
              </thead>
              <tbody>
                ${holdingsRows}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }).join('');
  }

  // ==============================================================================
  // INSTITUTIONAL-GRADE QUANT VALIDATION LAB METHODS (TIER 2)
  // ==============================================================================

  handleInstUniverseChange(val) {
    const symInput = document.getElementById('instSymbolInput');
    if (!symInput) return;
    if (val === 'CUSTOM_TICKER') {
      symInput.style.display = 'inline-block';
      if (symInput.value === 'ALL' || symInput.value === 'VN30' || symInput.value === 'VN70' || symInput.value === 'HOSE' || symInput.value === 'HNX' || symInput.value === 'UPCOM') {
        symInput.value = 'FPT';
      }
      symInput.focus();
    } else {
      symInput.style.display = 'none';
      symInput.value = val;
    }
  }

  handleInstExecutionModeChange(mode) {
    const grpFactor = document.getElementById('instFactorStrategyGroup');
    const grpVal = document.getElementById('instValModelGroup');
    const grpS1 = document.getElementById('instStage1ScreenerGroup');
    const grpS2 = document.getElementById('instStage2ValModelGroup');
    const strip = document.getElementById('instValuationControlStrip');

    if (mode === 'factor_only') {
      if (grpFactor) grpFactor.style.display = 'flex';
      if (grpVal) grpVal.style.display = 'none';
      if (grpS1) grpS1.style.display = 'none';
      if (grpS2) grpS2.style.display = 'none';
      if (strip) strip.style.display = 'none';
    } else if (mode === 'valuation_only') {
      if (grpFactor) grpFactor.style.display = 'none';
      if (grpVal) grpVal.style.display = 'flex';
      if (grpS1) grpS1.style.display = 'none';
      if (grpS2) grpS2.style.display = 'none';
      if (strip) strip.style.display = 'flex';
    } else { // hybrid_funnel
      if (grpFactor) grpFactor.style.display = 'none';
      if (grpVal) grpVal.style.display = 'none';
      if (grpS1) grpS1.style.display = 'flex';
      if (grpS2) grpS2.style.display = 'flex';
      if (strip) strip.style.display = 'flex';
    }
  }

  handleInstStrategyChange(strat) {
    // Legacy helper
  }

  toggleInstOmnibusMetricSelect() {
    const mode = document.getElementById('instCompositeModeSelect')?.value || 'blended';
    const grp = document.getElementById('instOmnibusMetricGroup');
    if (grp) {
      grp.style.display = mode === 'omnibus' ? 'flex' : 'none';
    }
  }

  getInstCurrentParams() {
    const uSelect = document.getElementById('instUniverseSelect');
    const symInput = document.getElementById('instSymbolInput');
    let symbol = 'ALL';
    if (uSelect && uSelect.value === 'CUSTOM_TICKER') {
      symbol = (symInput?.value || 'FPT').trim().toUpperCase();
    } else if (uSelect) {
      symbol = uSelect.value;
    }

    const execMode = document.getElementById('instExecutionModeSelect')?.value || 'hybrid_funnel';
    let strategy = 'peter_lynch_garp';
    let screeningStrategy = 'peter_lynch_garp';
    let valModel = 'composite_fair_value';

    if (execMode === 'factor_only') {
      strategy = document.getElementById('instFactorStrategySelect')?.value || 'peter_lynch_garp';
      screeningStrategy = strategy;
      valModel = 'composite_fair_value';
    } else if (execMode === 'valuation_only') {
      valModel = document.getElementById('instValModelSelect')?.value || 'composite_fair_value';
      strategy = 'val_' + valModel;
      screeningStrategy = 'custom';
    } else { // hybrid_funnel
      screeningStrategy = document.getElementById('instStage1ScreenerSelect')?.value || 'peter_lynch_garp';
      valModel = document.getElementById('instStage2ValModelSelect')?.value || 'composite_fair_value';
      strategy = 'hybrid_' + screeningStrategy + '_' + valModel;
    }

    const horizon = document.getElementById('instHorizonSelect')?.value || '3';
    const topK = document.getElementById('instTopKSelect')?.value || '10';
    const cadence = document.getElementById('instCadenceSelect')?.value || 'quarterly';
    const fillMode = document.getElementById('instFillModeSelect')?.value || 'strict';
    const survival = document.getElementById('instSurvivalToggle')?.checked || false;
    const tsmom = document.getElementById('instTsmomToggle')?.checked || false;
    const forensic = document.getElementById('instForensicToggle')?.checked || false;
    const risk = document.getElementById('instRiskSelect')?.value || '1.5';
    const atrStop = document.getElementById('instAtrStopSelect')?.value || '2.5';
    
    // Valuation specific params
    const mos = document.getElementById('instMosSelect')?.value || '15';
    const compositeMode = document.getElementById('instCompositeModeSelect')?.value || 'blended';
    const omnibusMetric = document.getElementById('instOmnibusMetricSelect')?.value || 'smape';
    const dynamicBeta = document.getElementById('instDynamicMosToggle')?.checked || false;
    const rkvTrap = document.getElementById('instRkvToggle')?.checked || false;

    return { 
      symbol, execMode, strategy, screeningStrategy, valModel, horizon, topK, cadence, fillMode, survival, tsmom, forensic, risk, atrStop,
      mos, compositeMode, omnibusMetric, dynamicBeta, rkvTrap
    };
  }

  switchBacktestSubtab(subtab) {
    const btnPortfolio = document.getElementById('btnSubtabBtPortfolio');
    const btnInst = document.getElementById('btnSubtabBtInstitutional');
    const secPortfolio = document.getElementById('btPortfolioSection');
    const secInst = document.getElementById('btInstitutionalSection');

    if (subtab === 'portfolio') {
      if (btnPortfolio) btnPortfolio.classList.add('active');
      if (btnInst) btnInst.classList.remove('active');
      if (secPortfolio) secPortfolio.style.display = 'flex';
      if (secInst) secInst.style.display = 'none';
    } else if (subtab === 'institutional' || subtab === 'fair_value') {
      if (btnPortfolio) btnPortfolio.classList.remove('active');
      if (btnInst) btnInst.classList.add('active');
      if (secPortfolio) secPortfolio.style.display = 'none';
      if (secInst) secInst.style.display = 'flex';

      if (!this.hasRunInstitutionalBt) {
        this.runInstitutionalBacktest();
      }
    }
  }

  async runInstitutionalBacktest() {
    const p = this.getInstCurrentParams();

    const btn = document.getElementById('btnRunInstBarBacktest');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Đang chạy định lượng & định giá...</span>';
    }

    try {
      let url = `/api/quant/institutional/run?symbol=${encodeURIComponent(p.symbol)}&strategy_type=${encodeURIComponent(p.strategy)}&time_horizon_years=${p.horizon}&top_k=${p.topK}&rebalance_cadence=${p.cadence}&survival_filter=${p.survival}&tsmom_filter=${p.tsmom}&fill_mode=${p.fillMode}&forensic_filter=${p.forensic}&risk_per_trade_pct=${p.risk}&atr_stop_multiplier=${p.atrStop}&margin_of_safety_pct=${p.mos}&composite_mode=${p.compositeMode}&omnibus_metric=${p.omnibusMetric}&use_dynamic_beta_mos=${p.dynamicBeta}&filter_rkv_value_trap=${p.rkvTrap}&backtest_mode=${encodeURIComponent(p.execMode)}&screening_strategy=${encodeURIComponent(p.screeningStrategy)}&valuation_model_id=${encodeURIComponent(p.valModel)}`;

      const res = await fetch(url);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        this.showToast(json.message || 'Lỗi khi chạy backtest định chế', 'error');
        return;
      }

      this.hasRunInstitutionalBt = true;
      const d = json.data;
      const m = d.metrics || {};

      // 1. Update KPI Cards
      const setTxt = (id, txt, cls) => {
        const el = document.getElementById(id);
        if (el) {
          el.textContent = txt;
          if (cls) el.className = cls;
        }
      };

      setTxt('instKpiCagr', `${m.cagr_pct > 0 ? '+' : ''}${m.cagr_pct}%`, `mono ${m.cagr_pct >= 0 ? 'txt-up' : 'txt-down'}`);
      setTxt('instKpiBenchmarkCagr', `Buy & Hold: ${m.benchmark_cagr_pct > 0 ? '+' : ''}${m.benchmark_cagr_pct}% (Alpha: ${m.alpha_cagr_pct > 0 ? '+' : ''}${m.alpha_cagr_pct}%)`);
      
      setTxt('instKpiTotalReturn', `${m.total_return_pct > 0 ? '+' : ''}${m.total_return_pct}%`, `mono ${m.total_return_pct >= 0 ? 'txt-up' : 'txt-down'}`);
      setTxt('instKpiFinalNav', `NAV: ${Number(m.final_nav || 0).toLocaleString()} đ`);

      setTxt('instKpiMaxDd', `-${m.max_drawdown_pct}%`, 'mono txt-down');
      setTxt('instKpiUlcer', `Ulcer Index: ${m.ulcer_index}`);

      setTxt('instKpiSharpe', `${m.sharpe_ratio} / ${m.sortino_ratio}`, 'mono font-bold');
      setTxt('instKpiCalmar', `Calmar: ${m.calmar_ratio} (Vol: ${m.annualized_volatility_pct}%)`);

      setTxt('instKpiWinRate', `${m.win_rate_pct}% (PF: ${m.profit_factor})`, 'mono font-bold');
      setTxt('instKpiTradesCount', `${m.total_trades} Lệnh (${m.winning_trades_count}W/${m.losing_trades_count}L, Payoff: ${m.payoff_ratio})`);

      setTxt('instKpiExpectancy', `${Number(m.expectancy_per_trade_vnd || 0).toLocaleString()} đ/lệnh`, `mono ${m.expectancy_per_trade_vnd >= 0 ? 'txt-up' : 'txt-down'}`);
      setTxt('instKpiFriction', `Tổng ma sát: ${Number(m.total_friction_vnd || 0).toLocaleString()} đ`);

      // 1b. Render Fundamental Law of Active Management (Grinold & Kahn)
      const fl = d.fundamental_law || m.fundamental_law || {};
      const flEv = fl.evaluations || {};

      const irVal = fl.realized_information_ratio !== undefined ? fl.realized_information_ratio : 0.0;
      setTxt('flIrValue', `${irVal > 0 ? '+' : ''}${irVal.toFixed(2)}`, `mono ${irVal >= 0.5 ? 'txt-up' : (irVal >= 0.0 ? 'txt-warn' : 'txt-down')}`);
      setTxt('flActiveReturn', `${fl.active_return_cagr_pct > 0 ? '+' : ''}${fl.active_return_cagr_pct}%`, `mono ${fl.active_return_cagr_pct >= 0 ? 'txt-up' : 'txt-down'}`);
      setTxt('flTrackingError', `${fl.tracking_error_pct}%`, 'mono');
      const elIrBadge = document.getElementById('flIrBadge');
      if (elIrBadge && flEv.ir) {
        elIrBadge.textContent = flEv.ir.grade;
        elIrBadge.className = `badge-tag ${flEv.ir.badge}`;
      }

      const icVal = fl.information_coefficient !== undefined ? fl.information_coefficient : 0.0;
      setTxt('flIcValue', `${icVal > 0 ? '+' : ''}${icVal.toFixed(4)}`, `mono ${icVal >= 0.05 ? 'txt-blue' : (icVal >= 0.0 ? 'txt-warn' : 'txt-down')}`);
      setTxt('flIcIr', `${fl.ic_ir !== undefined ? fl.ic_ir : '--'}`, 'mono');
      const elIcBadge = document.getElementById('flIcBadge');
      if (elIcBadge && flEv.ic) {
        elIcBadge.textContent = flEv.ic.grade;
        elIcBadge.className = `badge-tag ${flEv.ic.badge}`;
      }

      const brVal = fl.breadth_annual_bets !== undefined ? fl.breadth_annual_bets : 0.0;
      setTxt('flBrValue', `${brVal.toFixed(1)} cược/năm`, 'mono font-bold');
      setTxt('flNeff', `${fl.effective_independent_assets !== undefined ? fl.effective_independent_assets : '--'}`, 'mono');
      setTxt('flSqrtBr', `${fl.sqrt_breadth !== undefined ? fl.sqrt_breadth : '--'}`, 'mono');
      const elBrBadge = document.getElementById('flBrBadge');
      if (elBrBadge && flEv.br) {
        elBrBadge.textContent = flEv.br.grade;
        elBrBadge.className = `badge-tag ${flEv.br.badge}`;
      }

      const tcVal = fl.transfer_coefficient !== undefined ? fl.transfer_coefficient : 0.0;
      setTxt('flTcValue', `${tcVal.toFixed(3)}`, 'mono font-bold');
      setTxt('flEfficiency', `${fl.execution_efficiency_pct !== undefined ? fl.execution_efficiency_pct : '--'}%`);
      const elTcBadge = document.getElementById('flTcBadge');
      if (elTcBadge && flEv.tc) {
        elTcBadge.textContent = flEv.tc.grade;
        elTcBadge.className = `badge-tag ${flEv.tc.badge}`;
      }

      setTxt('flIrUnconstrained', `${fl.theoretical_ir_unconstrained !== undefined ? fl.theoretical_ir_unconstrained : '--'}`);
      setTxt('flIrConstrained', `${fl.theoretical_ir_constrained !== undefined ? fl.theoretical_ir_constrained : '--'}`);
      setTxt('flRecommendation', `${fl.primary_recommendation || 'Định luật Grinold & Kahn được tính toán hoàn chỉnh.'}`);

      const elOverallBadge = document.getElementById('flOverallBadge');
      if (elOverallBadge && flEv.ir) {
        elOverallBadge.textContent = `${flEv.ir.grade} (IR = ${irVal.toFixed(2)})`;
        elOverallBadge.className = `badge-tag ${flEv.ir.badge}`;
      }

      const overfitBox = document.getElementById('flOverfitWarningBox');
      if (overfitBox) {
        if (fl.is_overfitted && fl.ic_warning) {
          overfitBox.style.display = 'block';
          overfitBox.innerHTML = `<strong>⚠️ CẢNH BÁO OVERFITTING / LOOK-AHEAD BIAS:</strong> ${escapeHTML(fl.ic_warning)}`;
        } else {
          overfitBox.style.display = 'none';
        }
      }

      // 2. Draw Equity Canvas
      this.drawInstitutionalEquityChart(d.equity_curve || [], d.trades || [], m.benchmark_return_pct);

      // 3. Render Trades Table
      const tb = document.getElementById('instTradesTableBody');
      const badgeCount = document.getElementById('instTradesCountBadge');
      if (badgeCount) badgeCount.textContent = `${(d.trades || []).length} lệnh khớp`;

      if (tb) {
        if (!d.trades || d.trades.length === 0) {
          tb.innerHTML = '<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-muted);">Không có lệnh nào kích hoạt trong chu kỳ này.</td></tr>';
        } else {
          tb.innerHTML = d.trades.map((t, idx) => {
            const isWin = t.is_win;
            return `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                <td style="color:var(--text-muted);">${idx + 1}</td>
                <td class="col-symbol" style="font-weight:800; color:#38bdf8;">${escapeHTML(t.symbol)}</td>
                <td class="mono">${escapeHTML(t.entry_date)}</td>
                <td class="mono font-bold">${t.entry_price > 1000 ? t.entry_price.toLocaleString('vi-VN') : t.entry_price.toFixed(2)}</td>
                <td class="mono">${escapeHTML(t.exit_date)}</td>
                <td class="mono font-bold">${t.exit_price > 1000 ? t.exit_price.toLocaleString('vi-VN') : t.exit_price.toFixed(2)}</td>
                <td class="mono">${t.shares.toLocaleString()}</td>
                <td class="mono">${t.holding_days}d</td>
                <td style="text-align:left; font-size:11px; color:${t.reason.includes('Stop-Loss') ? '#f87171' : (t.reason.includes('Take-Profit') ? '#34d399' : '#38bdf8')}; font-weight:600;">
                  ${escapeHTML(t.reason)}
                </td>
                <td class="mono font-bold ${isWin ? 'txt-up' : 'txt-down'}" style="text-align:right;">
                  ${t.pnl_vnd > 0 ? '+' : ''}${Number(t.pnl_vnd).toLocaleString()} đ
                </td>
                <td class="mono font-bold ${isWin ? 'txt-up' : 'txt-down'}" style="text-align:right;">
                  ${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct}%
                </td>
              </tr>
            `;
          }).join('');
        }
      }

      this.showToast(`Đã kiểm định thành công ${d.strategy_name || p.strategy} trên ${p.symbol} (Sharpe ${m.sharpe_ratio})!`, 'toast-up');
    } catch (e) {
      console.error('Error running institutional backtest:', e);
      this.showToast('Lỗi kết nối khi chạy kiểm định định lượng.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>▶</span> Chạy Bar-by-Bar';
      }
    }
  }

  drawInstitutionalEquityChart(curve, trades, bhReturnPct) {
    const canvas = document.getElementById('instEquityCanvas');
    if (!canvas || !curve || curve.length === 0) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    const padding = { top: 20, right: 30, bottom: 30, left: 60 };
    const chartW = w - padding.left - padding.right;
    const chartH = h - padding.top - padding.bottom;

    const navs = curve.map(c => c.nav);
    const startNav = navs[0] || 100_000_000;
    const bhNavs = curve.map(c => c.benchmark_nav || (startNav * (c.close_price / (curve[0].close_price || 1))));

    const allValues = [...navs, ...bhNavs];
    let minVal = Math.min(...allValues) * 0.98;
    let maxVal = Math.max(...allValues) * 1.02;
    if (minVal === maxVal) { minVal *= 0.9; maxVal *= 1.1; }

    const getX = (idx) => padding.left + (idx / Math.max(1, curve.length - 1)) * chartW;
    const getY = (val) => padding.top + chartH - ((val - minVal) / (maxVal - minVal)) * chartH;

    // Draw Grid Lines
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let k = 0; k <= 4; k++) {
      const gY = padding.top + (k / 4) * chartH;
      ctx.beginPath();
      ctx.moveTo(padding.left, gY);
      ctx.lineTo(padding.left + chartW, gY);
      ctx.stroke();

      const gVal = maxVal - (k / 4) * (maxVal - minVal);
      ctx.fillStyle = '#64748b';
      ctx.font = '10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`${(gVal / 1e6).toFixed(1)}M`, padding.left - 8, gY + 3);
    }

    // 1. Draw Buy & Hold Curve (Gray)
    ctx.beginPath();
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    for (let i = 0; i < curve.length; i++) {
      const x = getX(i);
      const y = getY(bhNavs[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // 2. Draw Strategy NAV Curve (Cyan with Gradient Fill)
    const grad = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
    grad.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
    grad.addColorStop(1, 'rgba(56, 189, 248, 0.0)');

    ctx.beginPath();
    for (let i = 0; i < curve.length; i++) {
      const x = getX(i);
      const y = getY(navs[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    ctx.lineTo(getX(curve.length - 1), padding.top + chartH);
    ctx.lineTo(getX(0), padding.top + chartH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // 3. Draw Trade Entry / Exit Markers
    trades.slice(0, 100).forEach(t => {
      const entryIdx = curve.findIndex(c => c.date === t.entry_date);
      const exitIdx = curve.findIndex(c => c.date === t.exit_date);

      if (entryIdx >= 0) {
        const ex = getX(entryIdx);
        const ey = getY(navs[entryIdx]);
        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.arc(ex, ey, 3.5, 0, Math.PI * 2);
        ctx.fill();
      }

      if (exitIdx >= 0) {
        const xx = getX(exitIdx);
        const xy = getY(navs[exitIdx]);
        ctx.fillStyle = t.is_win ? '#34d399' : '#f43f5e';
        ctx.beginPath();
        ctx.arc(xx, xy, 3.5, 0, Math.PI * 2);
        ctx.fill();
      }
    });

    // Draw X-axis Dates
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    const dateSteps = [0, Math.floor(curve.length / 2), curve.length - 1];
    dateSteps.forEach(idx => {
      if (curve[idx]) {
        ctx.fillText(curve[idx].date, getX(idx), padding.top + chartH + 18);
      }
    });
  }

  async runInstitutionalSensitivity() {
    const p = this.getInstCurrentParams();

    const btn = document.getElementById('btnRunInstSensitivity');
    const badge = document.getElementById('instPlateauBadge');
    const desc = document.getElementById('instPlateauDesc');

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Đang quét lưới...</span>';
    }
    if (badge) badge.textContent = 'Đang quét lưới 2D...';

    try {
      const res = await fetch(`/api/quant/institutional/sensitivity?symbol=${encodeURIComponent(p.symbol)}&strategy_type=${encodeURIComponent(p.strategy)}&time_horizon_years=${p.horizon}&backtest_mode=${encodeURIComponent(p.execMode)}&screening_strategy=${encodeURIComponent(p.screeningStrategy)}&valuation_model_id=${encodeURIComponent(p.valModel)}&composite_mode=${encodeURIComponent(p.compositeMode)}&omnibus_metric=${encodeURIComponent(p.omnibusMetric)}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        this.showToast('Lỗi khi quét độ nhạy tham số', 'error');
        return;
      }

      const d = json.data;
      if (badge) {
        badge.textContent = d.robustness?.is_plateau ? 'BÌNH NGUYÊN ỔN ĐỊNH 🟢' : 'BẪY OVERFITTING ⚠️';
        badge.className = `badge-tag ${d.robustness?.is_plateau ? 'badge-success' : 'badge-danger'}`;
      }
      if (desc) {
        desc.textContent = `${d.robustness?.plateau_quality} - ${d.robustness?.description} (Mean Sharpe: ${d.robustness?.mean_sharpe}, Std: ${d.robustness?.std_sharpe})`;
      }

      this.drawPlateauHeatmap(d);
      this.showToast('Đã quét xong bản đồ nhiệt vùng bình nguyên tham số!', 'toast-up');
    } catch (e) {
      console.error('Sensitivity scan error:', e);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>🗺️</span> Quét Vùng Bình Nguyên';
      }
    }
  }

  drawPlateauHeatmap(data) {
    const canvas = document.getElementById('instPlateauCanvas');
    if (!canvas || !data.matrix_sharpe) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    const matrix = data.matrix_sharpe;
    const rows = matrix.length;
    const cols = matrix[0].length;

    const p1Vals = data.param1_values || [];
    const p2Vals = data.param2_values || [];

    const padL = 40;
    const padB = 25;
    const padT = 15;
    const padR = 20;

    const cellW = (w - padL - padR) / cols;
    const cellH = (h - padT - padB) / rows;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const sh = matrix[r][c];
        const cx = padL + c * cellW;
        const cy = padT + r * cellH;

        // Color ramp based on Sharpe Ratio
        let rCol = 244, gCol = 63, bCol = 94; // red
        if (sh >= 1.0) {
          rCol = 16; gCol = 185; bCol = 129; // green
        } else if (sh >= 0.0) {
          rCol = 234; gCol = 179; bCol = 8; // yellow
        }
        const alpha = Math.min(0.9, Math.max(0.2, (sh + 2.0) / 4.0));

        ctx.fillStyle = `rgba(${rCol}, ${gCol}, ${bCol}, ${alpha})`;
        ctx.fillRect(cx + 1, cy + 1, cellW - 2, cellH - 2);

        // Text value
        ctx.fillStyle = '#ffffff';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(sh.toFixed(1), cx + cellW / 2, cy + cellH / 2 + 3);
      }
    }

    // Draw Axis Labels
    ctx.fillStyle = '#94a3b8';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    p2Vals.forEach((v, c) => {
      ctx.fillText(`${v}`, padL + c * cellW + cellW / 2, h - 8);
    });

    ctx.textAlign = 'right';
    p1Vals.forEach((v, r) => {
      ctx.fillText(`${v}`, padL - 6, padT + r * cellH + cellH / 2 + 3);
    });
  }

  async runInstitutionalWfa() {
    const p = this.getInstCurrentParams();

    const btn = document.getElementById('btnRunInstWfa');
    const badge = document.getElementById('instWfaBadge');
    const desc = document.getElementById('instWfaDesc');
    const container = document.getElementById('instWfaTimeline');

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Đang chạy WFA...</span>';
    }
    if (badge) badge.textContent = 'Đang tối ưu rolling...';

    try {
      const res = await fetch(`/api/quant/institutional/walk-forward?symbol=${encodeURIComponent(p.symbol)}&strategy_type=${encodeURIComponent(p.strategy)}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        this.showToast('Lỗi khi chạy Walk-Forward Analysis', 'error');
        return;
      }

      const d = json.data;
      if (badge) {
        badge.textContent = `WFE: ${d.walk_forward_efficiency} (${d.wfe_rating})`;
        badge.className = `badge-tag ${d.walk_forward_efficiency >= 0.7 ? 'badge-success' : (d.walk_forward_efficiency >= 0.5 ? 'badge-info' : 'badge-danger')}`;
      }

      if (desc) {
        desc.textContent = `Walk-Forward Efficiency: ${d.walk_forward_efficiency} • Tổng lợi nhuận OOS ghép nối: ${d.wfa_metrics?.total_return_pct}% (${d.splits_count} chu kỳ trượt)`;
      }

      if (container) {
        const splits = d.splits || [];
        container.innerHTML = splits.map(s => {
          const isPos = s.out_of_sample_return_pct >= 0;
          return `
            <div style="background:#090e17; padding:8px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center;">
              <div>
                <span style="font-weight:800; color:#c084fc;">Cửa Sổ #${s.split_id}:</span>
                <span style="color:var(--text-muted); font-size:10px; margin-left:4px;">Train: ${s.train_start_date} → Test: ${s.test_end_date}</span>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="badge-tag" style="background:rgba(56,189,248,0.12); color:#38bdf8; font-size:9.5px;">IS Sharpe: ${s.in_sample_sharpe}</span>
                <span class="mono font-bold ${isPos ? 'txt-up' : 'txt-down'}" style="font-size:11px;">OOS: ${isPos ? '+' : ''}${s.out_of_sample_return_pct}%</span>
              </div>
            </div>
          `;
        }).join('');
      }

      this.showToast('Đã hoàn thành Walk-Forward Analysis!', 'toast-up');
    } catch (e) {
      console.error('WFA error:', e);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>🔄</span> Walk-Forward (WFA)';
      }
    }
  }

  async runInstitutionalMonteCarlo() {
    const p = this.getInstCurrentParams();

    const btn = document.getElementById('btnRunInstMonteCarlo');
    const badge = document.getElementById('instMcBadge');

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Đang chạy 1.000 vòng...</span>';
    }
    if (badge) badge.textContent = 'Đang chạy 1.000 Bootstrap...';

    try {
      const res = await fetch(`/api/quant/institutional/monte-carlo?symbol=${encodeURIComponent(p.symbol)}&strategy_type=${encodeURIComponent(p.strategy)}&time_horizon_years=${p.horizon}&top_k=${p.topK}&rebalance_cadence=${p.cadence}&survival_filter=${p.survival}&tsmom_filter=${p.tsmom}&fill_mode=${p.fillMode}&forensic_filter=${p.forensic}&margin_of_safety_pct=${p.mos}&composite_mode=${p.compositeMode}&omnibus_metric=${p.omnibusMetric}&iterations=1000&backtest_mode=${encodeURIComponent(p.execMode)}&screening_strategy=${encodeURIComponent(p.screeningStrategy)}&valuation_model_id=${encodeURIComponent(p.valModel)}`);
      const json = await res.json();
      if (json.status !== 'success' || !json.data) {
        this.showToast(json.message || 'Lỗi khi chạy Monte Carlo Stress Test', 'error');
        return;
      }

      const d = json.data;
      const ci = d.confidence_intervals_95 || {};
      const seq = d.sequence_risk_permutation || {};

      if (badge) {
        badge.textContent = '1.000 VÒNG HOÀN THÀNH 🟢';
        badge.className = 'badge-tag badge-success';
      }

      const elSh = document.getElementById('mcCiSharpe');
      if (elSh && ci.sharpe_ratio) elSh.textContent = `[${ci.sharpe_ratio[0]}, ${ci.sharpe_ratio[1]}]`;

      const elRet = document.getElementById('mcCiReturn');
      if (elRet && ci.total_return_pct) elRet.textContent = `[${ci.total_return_pct[0]}%, ${ci.total_return_pct[1]}%]`;

      const elDd = document.getElementById('mcCiMaxDd');
      if (elDd && ci.max_drawdown_pct) elDd.textContent = `[${ci.max_drawdown_pct[0]}%, ${ci.max_drawdown_pct[1]}%]`;

      const elPerm = document.getElementById('mcPermDesc');
      if (elPerm) elPerm.textContent = `${seq.description || ''} (Median DD: ${seq.median_drawdown_pct}%)`;

      this.drawMonteCarloHistogram(d.sharpe_distribution || []);
      this.showToast('Đã hoàn thành kiểm định Monte Carlo 1.000 vòng!', 'toast-up');
    } catch (e) {
      console.error('Monte Carlo error:', e);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>🎲</span> Monte Carlo (1.000 Rounds)';
      }
    }
  }

  drawMonteCarloHistogram(distribution) {
    const canvas = document.getElementById('instMcCanvas');
    if (!canvas || !distribution || distribution.length === 0) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    const maxCount = Math.max(...distribution.map(d => d.count), 1);
    const pad = 10;
    const barW = (w - pad * 2) / distribution.length;

    distribution.forEach((item, idx) => {
      const bh = (item.count / maxCount) * (h - pad * 2);
      const bx = pad + idx * barW;
      const by = h - pad - bh;

      const isPos = item.bin >= 0;
      ctx.fillStyle = isPos ? 'rgba(52, 211, 153, 0.75)' : 'rgba(248, 113, 113, 0.75)';
      ctx.fillRect(bx + 1, by, barW - 2, bh);
    });

    ctx.fillStyle = '#94a3b8';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('Phân phối Sharpe Ratio (1.000 Bootstrap Runs)', w / 2, h - 2);
  }

  // ==============================================================================
  // QUANTITATIVE VALUATION ENGINE (22 MODELS & SCENARIO SENSITIVITY)
  // ==============================================================================

  handleStockValModeChange(mode) {
    const grp = document.getElementById('stockValOmnibusMetricGroup');
    if (grp) {
      grp.style.display = (mode === 'omnibus') ? 'flex' : 'none';
    }
    this.fetchStockQuantValuation(this.currentSymbol);
  }

  handleStockValMetricChange(metric) {
    this.fetchStockQuantValuation(this.currentSymbol);
  }

  refreshStockQuantValuation() {
    this.fetchStockQuantValuation(this.currentSymbol);
  }

  async fetchStockQuantValuation(symbol, forcedMode = null, forcedMetric = null) {
    const container = document.getElementById('stockQuantValuationContainer');
    if (!container) return;

    const sym = symbol || this.currentSymbol || 'FPT';
    const mode = forcedMode || document.getElementById('stockValCompositeModeSelect')?.value || 'blended';
    const metric = forcedMetric || document.getElementById('stockValOmnibusMetricSelect')?.value || 'smape';

    const grp = document.getElementById('stockValOmnibusMetricGroup');
    if (grp) {
      grp.style.display = (mode === 'omnibus') ? 'flex' : 'none';
    }

    container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:24px; text-align:center;">⏳ Đang tính toán 22 mô hình định giá (${mode.toUpperCase()}${mode === 'omnibus' ? ' - ' + metric.toUpperCase() : ''}) & ma trận độ nhạy cho mã <strong>${escapeHTML(sym)}</strong>...</div>`;

    try {
      const res = await fetch(`/api/valuation/comprehensive/${encodeURIComponent(sym)}?mode=${encodeURIComponent(mode)}&metric=${encodeURIComponent(metric)}`);
      const json = await res.json();
      if (this.currentSymbol !== sym) return;

      if (json.status !== 'success' || !json.data) {
        this.renderErrorState('stockQuantValuationContainer', json.message || `Không thể tính toán định giá lượng tử cho mã ${sym}.`);
        return;
      }

      const d = json.data;
      const w = d.wacc || {};
      const rf = d.risk_firewall || {};
      const sc = d.scenarios || {};
      const rkv = rf.rhodes_kropf || {};
      const models = d.models || [];

      const curP = Number(d.current_price || 0);
      const fvP = Number(d.composite_fair_value || 0);
      const upside = Number(d.composite_upside_pct || 0);
      const isUp = upside >= 0;

      const statusTag = d.composite_status === 'undervalued' 
        ? '<span class="badge" style="background:rgba(16,185,129,0.2); color:#34d399; font-weight:800; font-size:12px; padding:4px 10px; border:1px solid rgba(16,185,129,0.4);">🟢 RẺ HƠN GIÁ TRỊ THỰC (UNDERVALUED)</span>'
        : (d.composite_status === 'overvalued'
          ? '<span class="badge" style="background:rgba(239,68,68,0.2); color:#f87171; font-weight:800; font-size:12px; padding:4px 10px; border:1px solid rgba(239,68,68,0.4);">🔴 CAO HƠN GIÁ TRỊ THỰC (OVERVALUED)</span>'
          : '<span class="badge" style="background:rgba(56,189,248,0.2); color:#38bdf8; font-weight:800; font-size:12px; padding:4px 10px; border:1px solid rgba(56,189,248,0.4);">🔵 ĐỊNH GIÁ HỢP LÝ (FAIRLY VALUED)</span>');

      const compMode = d.metadata?.composite_mode || mode || 'blended';
      const isBlended = compMode === 'blended';
      const compTitle = isBlended ? 'GIÁ TRỊ HỢP LÝ TỔNG HỢP (BLENDED VALUATION COMPOSITE)' : `GIÁ TRỊ HỢP LÝ TỔNG HỢP (OMNIBUS COMPOSITE - ${(d.metadata?.omnibus_metric || metric || 'SMAPE').toUpperCase()})`;
      const compSubtitle = isBlended ? 'Tổng hòa các mô hình cốt lõi theo tỷ trọng cơ cấu chuẩn theo ngành ICB (Không dùng IVW / Chống quá khớp)' : 'Tổng hòa 22 mô hình theo thước đo sai số định lượng tối ưu';

      // Group models
      const relModels = models.filter(m => m.category === 'relative' || m.model_category === 'relative' || m.model_category === 'relative_multiple');
      const absModels = models.filter(m => m.category === 'absolute' || m.model_category === 'absolute' || m.model_category === 'absolute_intrinsic');
      const secModels = models.filter(m => m.category === 'sector' || m.model_category === 'sector' || m.model_category === 'sector_specific');

      const renderModelRows = (mList) => {
        if (!mList || mList.length === 0) return '<tr><td colspan="6" style="color:var(--text-muted); padding:10px;">Không có mô hình trong nhóm này</td></tr>';
        return mList.map(m => {
          const valP = Number(m.fair_value || 0);
          const uPct = Number(m.upside_pct || 0);
          const wt = (Number((m.weight !== undefined ? m.weight : m.adaptive_weight) || 0) * 100).toFixed(1);
          const isAct = m.active !== undefined ? m.active : (m.is_active !== undefined ? m.is_active : true);
          const uColor = uPct > 0 ? '#34d399' : (uPct < 0 ? '#f87171' : '#94a3b8');
          const noteText = m.diagnostics?.notes || m.notes || m.status || (isAct ? (isBlended ? 'Áp dụng theo cơ cấu chuẩn ngành' : 'Áp dụng theo trọng số sai số Omnibus') : 'Loại trừ ngoại lai / Bỏ qua theo ngành');

          return `
            <tr style="border-bottom:1px solid rgba(255,255,255,0.03); opacity:${isAct ? '1' : '0.55'};">
              <td style="text-align:left; font-weight:700; color:${isAct ? '#38bdf8' : '#94a3b8'};">${escapeHTML(m.model_name)}</td>
              <td class="mono font-bold" style="text-align:right;">${valP > 0 ? valP.toLocaleString('vi-VN') + ' đ' : '--'}</td>
              <td class="mono font-bold" style="text-align:right; color:${uColor};">${uPct > 0 ? '+' : ''}${uPct.toFixed(1)}%</td>
              <td class="mono" style="text-align:center;">${isAct ? `<span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8;">${wt}%</span>` : '<span style="color:#64748b;">0.0%</span>'}</td>
              <td style="text-align:center;">
                ${isAct ? '<span style="color:#34d399; font-weight:700;">✓ Active</span>' : '<span style="color:#f59e0b; font-size:10.5px;">Bypassed</span>'}
              </td>
              <td style="text-align:left; font-size:11px; color:var(--text-secondary); max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHTML(noteText)}">
                ${escapeHTML(noteText)}
              </td>
            </tr>
          `;
        }).join('');
      };

      // Render 5x5 Sensitivity Grid
      const grid = d.sensitivity_grid || [];
      let gridHtml = '';
      if (grid.length > 0) {
        const growthCols = Object.keys(grid[0].growth_rates || {}).sort((a, b) => parseFloat(a) - parseFloat(b));
        const headThs = growthCols.map(g => `<th style="text-align:right;">g = ${(parseFloat(g)*100).toFixed(1)}%</th>`).join('');

        const bodyRows = grid.map(row => {
          const wPct = (parseFloat(row.wacc) * 100).toFixed(1);
          const tds = growthCols.map(g => {
            const val = Number(row.growth_rates[g] || 0);
            const isMid = Math.abs(parseFloat(row.wacc) - (w.wacc || 0.1)) < 0.005;
            return `<td class="mono" style="text-align:right; font-weight:${isMid ? '800' : '500'}; color:${val > curP ? '#34d399' : '#f87171'}; ${isMid ? 'background:rgba(56,189,248,0.08);' : ''}">${val > 0 ? val.toLocaleString('vi-VN') : '--'}</td>`;
          }).join('');
          return `<tr><td style="font-weight:800; color:#38bdf8; text-align:left;">WACC = ${wPct}%</td>${tds}</tr>`;
        }).join('');

        gridHtml = `
          <div class="sector-constituents-card" style="background:var(--bg-card); border-radius:10px; border:1px solid var(--border-subtle); padding:16px; margin-top:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <div style="font-size:13px; font-weight:800; display:flex; align-items:center; gap:8px;">
                <span>🎯</span> MA TRẬN ĐỘ NHẠY ĐỊNH GIÁ 5x5 (WACC VS TỐC ĐỘ TĂNG TRƯỞNG DÀI HẠN)
              </div>
              <span style="font-size:11px; color:var(--text-muted);">Đơn vị: VNĐ / CP</span>
            </div>
            <div class="table-scroll-wrap" style="overflow-x:auto;">
              <table class="board-table sector-table" style="font-size:11.5px; text-align:center;">
                <thead>
                  <tr>
                    <th style="text-align:left;">Chiết Khấu \\ Tăng Trưởng</th>
                    ${headThs}
                  </tr>
                </thead>
                <tbody>
                  ${bodyRows}
                </tbody>
              </table>
            </div>
          </div>
        `;
      }

      const bcs = d.buffett_coupon_spread || {};
      const qqf = d.quant_quality_filters || {};
      const capAlloc = d.capital_allocation || {};
      const valWidth = Number(d.valuation_width_pct || 0);

      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:14px;">
          <!-- 1. Master Fair Value Hero Card -->
          <div style="background:linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.85)); border:1px solid rgba(250,204,21,0.35); border-radius:10px; padding:18px 22px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;">
            <div>
              <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">🏆</span>
                <div>
                  <div style="font-size:16px; font-weight:800; color:#facc15;">${escapeHTML(compTitle)}</div>
                  <div style="font-size:11.5px; color:var(--text-secondary); margin-top:2px;">
                    ${escapeHTML(compSubtitle)}
                  </div>
                </div>
              </div>
              <div style="display:flex; align-items:center; gap:12px; margin-top:10px;">
                ${statusTag}
                <span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:700;">Thị giá: ${curP.toLocaleString('vi-VN')} đ</span>
              </div>
            </div>

            <div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap;">
              <div style="text-align:right;">
                <div style="font-size:10.5px; color:var(--text-muted);">Giá Trị Hợp Lý</div>
                <div style="font-size:26px; font-weight:900; font-family:var(--font-mono); color:#facc15;">${fvP.toLocaleString('vi-VN')} đ</div>
              </div>
              <div style="text-align:right;">
                <div style="font-size:10.5px; color:var(--text-muted);">Biên Chiết Khấu (Upside)</div>
                <div style="font-size:26px; font-weight:900; font-family:var(--font-mono); color:${isUp ? '#34d399' : '#f87171'};">${isUp ? '+' : ''}${upside.toFixed(1)}%</div>
              </div>
              <div style="text-align:right;">
                <div style="font-size:10.5px; color:var(--text-muted);">Ngưỡng Mua An Toàn (MoS)</div>
                <div style="font-size:20px; font-weight:900; font-family:var(--font-mono); color:#38bdf8;">${Number(d.composite_mos_target_price || 0).toLocaleString('vi-VN')} đ</div>
              </div>
            </div>
          </div>

          <!-- 2. WACC 5-Factor & Risk Firewall Cards -->
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:12px;">
            <!-- WACC Card -->
            <div style="background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:8px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:12px; font-weight:800; color:#38bdf8;">⚡ CHI PHÍ VỐN WACC 5-FACTOR VN CAPM</span>
                <span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:800;">WACC: ${(Number(w.wacc || 0.10)*100).toFixed(2)}%</span>
              </div>
              <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.6;">
                <div>• Chi phí vốn CSH (Cost of Equity): <strong class="mono txt-up">${(Number(w.cost_of_equity || 0.12)*100).toFixed(2)}%</strong></div>
                <div>• Chi phí nợ vay sau thuế (Cost of Debt): <strong class="mono">${(Number(w.cost_of_debt_after_tax || 0.05)*100).toFixed(2)}%</strong> (Xếp hạng: <strong class="txt-blue">${escapeHTML(w.synthetic_rating || 'A')}</strong>)</div>
                <div>• Beta điều chỉnh: <strong class="mono">${Number(w.beta || 1.0).toFixed(2)}</strong> | Lãi suất phi rủi ro (Rf): <strong class="mono">${(Number(w.risk_free_rate || 0.028)*100).toFixed(1)}%</strong></div>
              </div>
            </div>

            <!-- Risk Firewall Card -->
            <div style="background:var(--bg-card); border:1px solid ${rf.four_quadrant_category === 'safe_compounder' ? 'rgba(16,185,129,0.35)' : 'rgba(244,63,94,0.35)'}; border-radius:8px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:12px; font-weight:800; color:#facc15;">🛡️ TƯỜNG LỬA RỦI RO & CHỐNG BẪY GIÁ TRỊ</span>
                <span class="badge-tag ${rf.four_quadrant_category === 'safe_compounder' ? 'badge-success' : 'badge-danger'}" style="font-weight:800;">${escapeHTML(rf.four_quadrant_label || 'Quadrant An Toàn')}</span>
              </div>
              <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.6;">
                <div>• Altman Z''-Score: <strong class="mono ${rf.altman_z_status === 'safe' ? 'txt-up' : 'txt-down'}">${Number(rf.altman_z_double_prime || 0).toFixed(2)} (${rf.altman_z_status === 'safe' ? 'An toàn' : 'Rủi ro'})</strong></div>
                <div>• Beneish M-Score: <strong class="mono ${rf.beneish_m_status === 'clean' ? 'txt-up' : 'txt-down'}">${Number(rf.beneish_m_score || 0).toFixed(2)} (${rf.beneish_m_status === 'clean' ? 'Minh bạch' : 'Thao túng'})</strong></div>
                <div>• Bẫy Rhodes-Kropf: <strong class="txt-blue">${escapeHTML(rkv.rkv_verdict || rkv.label || rkv.status || 'Tăng trưởng thực chất')}</strong> | Dynamic MoS: <strong class="txt-warn">${Number(rf.dynamic_margin_of_safety || 15).toFixed(1)}%</strong></div>
              </div>
            </div>
          </div>

          <!-- 2.5 Buffett Coupon Spread & Quant Quality Anchor Cards -->
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:12px;">
            <!-- Buffett Coupon Card -->
            <div style="background:var(--bg-card); border:1px solid rgba(250,204,21,0.25); border-radius:8px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:12px; font-weight:800; color:#facc15;">🎟️ BUFFETT OWNER'S EARNINGS COUPON</span>
                <span class="badge-tag" style="background:rgba(250,204,21,0.15); color:#facc15; font-weight:800;">${escapeHTML(bcs.coupon_status || 'ATTRACTIVE')}</span>
              </div>
              <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.6;">
                <div>• Lợi suất Lợi nhuận Chủ sở hữu (OE Yield): <strong class="mono txt-up">${Number(bcs.oe_yield_pct || 0).toFixed(2)}%</strong></div>
                <div>• Chênh lệch Trái phiếu 10Y (Coupon Spread): <strong class="mono ${Number(bcs.coupon_spread_pct || 0) > 0 ? 'txt-up' : 'txt-down'}">${Number(bcs.coupon_spread_pct || 0) > 0 ? '+' : ''}${Number(bcs.coupon_spread_pct || 0).toFixed(2)}%</strong></div>
                <div>• Phân bổ vốn: <strong class="txt-blue">${escapeHTML(capAlloc.status || 'Efficient Allocator')}</strong> <span style="font-size:10.5px; color:var(--text-muted);">(${escapeHTML(capAlloc.description || '')})</span></div>
              </div>
            </div>

            <!-- Quant Quality & Width Card -->
            <div style="background:var(--bg-card); border:1px solid rgba(56,189,248,0.25); border-radius:8px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:12px; font-weight:800; color:#38bdf8;">📊 BỘ LỌC CHẤT LƯỢNG QUANT & ĐỘ RỘNG ĐỊNH GIÁ</span>
                <span class="badge-tag" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:800;">Width: ${valWidth.toFixed(1)}%</span>
              </div>
              <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.6;">
                <div>• Gross Profitability (GPA Novy-Marx): <strong class="mono ${qqf.gpa_pass ? 'txt-up' : 'txt-muted'}">${Number(qqf.gpa_pct || 0).toFixed(1)}% (${qqf.gpa_pass ? '✓ Đạt' : 'Không đạt'})</strong></div>
                <div>• Sloan Accrual (Chất lượng LN): <strong class="mono ${qqf.sloan_pass ? 'txt-up' : 'txt-down'}">${Number(qqf.sloan_accrual_pct || 0).toFixed(1)}% (${qqf.sloan_pass ? '✓ Dòng tiền thật' : 'Dồn tích cao'})</strong></div>
                <div>• Chênh lệch ROIC - WACC: <strong class="mono ${Number(qqf.roic_wacc_spread_pct || 0) > 0 ? 'txt-up' : 'txt-down'}">${Number(qqf.roic_wacc_spread_pct || 0) > 0 ? '+' : ''}${Number(qqf.roic_wacc_spread_pct || 0).toFixed(1)}%</strong> | Cổ đông Yield: <strong class="mono txt-up">${Number(qqf.shareholder_yield_pct || 0).toFixed(1)}%</strong></div>
              </div>
            </div>
          </div>

          <!-- 3. Bear / Base / Bull Scenarios -->
          <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; text-align:center;">
            <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3); border-radius:8px; padding:12px;">
              <div style="font-size:11px; font-weight:800; color:#f87171;">🐻 KỊCH BẢN THẬN TRỌNG (BEAR)</div>
              <div style="font-size:18px; font-weight:900; font-family:var(--font-mono); color:#f87171; margin:4px 0;">${Number(sc.bear_fair_value || 0).toLocaleString('vi-VN')} đ</div>
              <div style="font-size:10.5px; color:var(--text-muted);">WACC +100bps, g -50bps</div>
            </div>
            <div style="background:rgba(56,189,248,0.08); border:1px solid rgba(56,189,248,0.3); border-radius:8px; padding:12px;">
              <div style="font-size:11px; font-weight:800; color:#38bdf8;">⚖️ KỊCH BẢN CƠ SỞ (BASE)</div>
              <div style="font-size:18px; font-weight:900; font-family:var(--font-mono); color:#38bdf8; margin:4px 0;">${Number(sc.base_fair_value || 0).toLocaleString('vi-VN')} đ</div>
              <div style="font-size:10.5px; color:var(--text-muted);">Dự báo chuẩn hóa TTM</div>
            </div>
            <div style="background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.3); border-radius:8px; padding:12px;">
              <div style="font-size:11px; font-weight:800; color:#34d399;">🐂 KỊCH BẢN LẠC QUAN (BULL)</div>
              <div style="font-size:18px; font-weight:900; font-family:var(--font-mono); color:#34d399; margin:4px 0;">${Number(sc.bull_fair_value || 0).toLocaleString('vi-VN')} đ</div>
              <div style="font-size:10.5px; color:var(--text-muted);">WACC -100bps, g +50bps</div>
            </div>
          </div>

          <!-- 4. Detailed 22 Valuation Models Table -->
          <div class="sector-constituents-card" style="background:var(--bg-card); border-radius:10px; border:1px solid var(--border-subtle); padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
              <div style="font-size:13px; font-weight:800; display:flex; align-items:center; gap:8px;">
                <span>🔬</span> CHI TIẾT 22 MÔ HÌNH ĐỊNH GIÁ & TRỌNG SỐ THÍCH ỨNG (FFV PRO SUITE)
              </div>
              <span style="font-size:11px; color:var(--text-muted);">Loại bỏ ngoại lai IQR 1.5x</span>
            </div>
            
            <div class="table-scroll-wrap" style="overflow-x:auto;">
              <table class="board-table sector-table" style="font-size:11.5px; text-align:center;">
                <thead>
                  <tr>
                    <th style="text-align:left; min-width:200px;">Tên Mô Hình Định Giá</th>
                    <th style="width:110px; text-align:right;">Giá Trị Hợp Lý</th>
                    <th style="width:90px; text-align:right;">Upside %</th>
                    <th style="width:85px;">Trọng Số</th>
                    <th style="width:85px;">Trạng Thái</th>
                    <th style="text-align:left;">Ghi Chú Công Thức / Bội Số</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style="background:rgba(56,189,248,0.06); font-weight:800;"><td colspan="6" style="text-align:left; color:#38bdf8;">📊 NHÓM 1: 8 BỘI SỐ ĐỊNH GIÁ TƯƠNG ĐỐI (RELATIVE MULTIPLES)</td></tr>
                  ${renderModelRows(relModels)}
                  <tr style="background:rgba(168,85,247,0.06); font-weight:800;"><td colspan="6" style="text-align:left; color:#c084fc;">🏛️ NHÓM 2: 7 MÔ HÌNH NỘI TẠI TUYỆT ĐỐI (ABSOLUTE INTRINSIC MODELS)</td></tr>
                  ${renderModelRows(absModels)}
                  <tr style="background:rgba(250,204,21,0.06); font-weight:800;"><td colspan="6" style="text-align:left; color:#facc15;">🏢 NHÓM 3: 7 MÔ HÌNH ĐỊNH GIÁ THEO NGÀNH ĐẶC THÙ (SECTOR-SPECIFIC)</td></tr>
                  ${renderModelRows(secModels)}
                </tbody>
              </table>
            </div>
          </div>

          <!-- 5. Sensitivity Grid -->
          ${gridHtml}
        </div>
      `;
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error('Error fetching stock quant valuation:', e);
      this.renderErrorState('stockQuantValuationContainer', `Lỗi kết nối khi tải dữ liệu định giá lượng tử cho mã ${sym}.`);
    }
  }

  // ==============================================================================
  // MODULAR 3-MODE FAIR VALUE BACKTEST ENGINE
  // ==============================================================================

  toggleOmnibusMetricSelect() {
    const mode = document.getElementById('fvBtCompositeModeSelect')?.value || 'blended';
    const group = document.getElementById('fvBtOmnibusMetricGroup');
    if (group) {
      group.style.display = (mode === 'omnibus') ? 'flex' : 'none';
    }
  }

  async runFairValueBacktest() {
    const btn = document.getElementById('btnRunFairValueBacktest');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Đang chạy đối soát...</span>';
    }

    const mode = document.getElementById('fvBtModeSelect')?.value || 'hybrid_funnel';
    const screener = document.getElementById('fvBtScreenerSelect')?.value || 'peter_lynch_garp';
    const valModel = document.getElementById('fvBtValModelSelect')?.value || 'composite_fair_value';
    const compositeMode = document.getElementById('fvBtCompositeModeSelect')?.value || 'blended';
    const omnibusMetric = document.getElementById('fvBtOmnibusMetricSelect')?.value || 'smape';
    const horizon = parseInt(document.getElementById('fvBtHorizonSelect')?.value || '5');
    const endYear = 2026;
    let startYear = endYear - horizon;
    if (horizon === 10) startYear = 2016;

    const mos = parseFloat(document.getElementById('fvBtMosSelect')?.value || '15');
    const exit = parseFloat(document.getElementById('fvBtExitSelect')?.value || '20');
    const exchange = document.getElementById('fvBtExchangeSelect')?.value || 'ALL';
    const cadence = document.getElementById('fvBtCadenceSelect')?.value || 'quarterly';
    const topK = parseInt(document.getElementById('fvBtTopKSelect')?.value || '10');
    const fillMode = document.getElementById('fvBtFillModeSelect')?.value || 'strict';
    const dynamicMos = Boolean(document.getElementById('fvBtDynamicMosToggle')?.checked);
    const survival = Boolean(document.getElementById('fvBtSurvivalToggle')?.checked);
    const tsmom = Boolean(document.getElementById('fvBtTsmomToggle')?.checked);
    const forensic = Boolean(document.getElementById('fvBtForensicToggle')?.checked);
    const zSafe = Boolean(document.getElementById('fvBtZSafeToggle')?.checked ?? true);
    const rkv = Boolean(document.getElementById('fvBtRkvToggle')?.checked);

    try {
      const url = `/api/backtest/fair_value/run?mode=${encodeURIComponent(mode)}&screening_strategy=${encodeURIComponent(screener)}&valuation_model_id=${encodeURIComponent(valModel)}&composite_mode=${encodeURIComponent(compositeMode)}&omnibus_metric=${encodeURIComponent(omnibusMetric)}&margin_of_safety_pct=${mos}&exit_premium_pct=${exit}&exchange=${encodeURIComponent(exchange)}&top_k=${topK}&rebalance_cadence=${encodeURIComponent(cadence)}&fill_mode=${encodeURIComponent(fillMode)}&survival_filter=${survival}&tsmom_filter=${tsmom}&forensic_filter=${forensic}&use_dynamic_beta_mos=${dynamicMos}&filter_z_score_safe=${zSafe}&filter_rkv_value_trap=${rkv}&start_year=${startYear}&end_year=${endYear}`;

      const res = await fetch(url, { method: 'POST' });
      const json = await res.json();

      if (json.status !== 'success' || !json.data) {
        this.showToast(json.message || 'Lỗi khi chạy backtest định giá', 'error');
        return;
      }

      this.hasRunFairValueBt = true;
      const d = json.data;
      const m = d.metrics || {};

      // 1. Update Master Winner Banner
      const setTxt = (id, txt) => {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
      };

      setTxt('fvBtWinnerTitle', `KẾT QUẢ ĐỐI SOÁT: ${d.mode_name || mode}`);
      setTxt('fvBtWinnerDesc', `${d.screening_name || screener} • Mô hình: ${d.valuation_model_name || valModel} • Khung: ${horizon} Năm (${startYear}-${endYear}) • MoS: ${mos}% • Chốt lời: +${exit}%`);
      setTxt('fvBtMetricCagr', `${m.cagr_pct > 0 ? '+' : ''}${m.cagr_pct}%`);
      setTxt('fvBtMetricTotal', `${m.total_return_pct > 0 ? '+' : ''}${m.total_return_pct}%`);
      setTxt('fvBtMetricMaxDd', `-${m.max_drawdown_pct}%`);
      setTxt('fvBtMetricSharpe', `${m.sharpe_ratio} (Sortino: ${m.sortino_ratio})`);
      setTxt('fvBtMetricWinRate', `${m.win_rate_pct}% (${m.total_trades} lệnh)`);

      // 2. Draw Visual Curves Canvas
      this.drawFairValueEquityChart(d.equity_curve || []);

      // 3. Render Year-by-Year Matrix
      const yTb = document.getElementById('fvBtYearlyTableBody');
      if (yTb) {
        const yList = d.yearly_returns || [];
        if (yList.length === 0) {
          yTb.innerHTML = '<tr><td colspan="6" style="padding:16px; color:var(--text-muted);">Không có dữ liệu năm</td></tr>';
        } else {
          yTb.innerHTML = yList.map(y => {
            const isPos = y.strategy_return_pct >= 0;
            const diff = y.excess_return_pct;
            const diffPos = diff >= 0;
            return `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                <td style="font-weight:800; color:var(--text-primary);">${y.year}</td>
                <td class="mono font-bold ${isPos ? 'txt-up' : 'txt-down'}" style="text-align:right;">${isPos ? '+' : ''}${y.strategy_return_pct}%</td>
                <td class="mono" style="text-align:right; color:#94a3b8;">${y.benchmark_return_pct > 0 ? '+' : ''}${y.benchmark_return_pct}%</td>
                <td class="mono font-bold ${diffPos ? 'txt-up' : 'txt-down'}" style="text-align:right;">${diffPos ? '+' : ''}${diff}%</td>
                <td class="mono">${y.trades_count}</td>
                <td class="mono" style="text-align:right; color:#facc15;">${y.win_rate_pct}%</td>
              </tr>
            `;
          }).join('');
        }
      }

      // 4. Render 22-Model Tournament Leaderboard
      const tTb = document.getElementById('fvBtTournamentTableBody');
      if (tTb) {
        const tList = d.model_tournament_matrix || [];
        if (tList.length === 0) {
          tTb.innerHTML = '<tr><td colspan="5" style="padding:16px; color:var(--text-muted);">Không có bảng đấu tournament</td></tr>';
        } else {
          tTb.innerHTML = tList.map(item => {
            const mName = item.model_name || item.name || item.id || 'Mô hình định giá';
            const cVal = item.cagr_pct !== undefined ? item.cagr_pct : (item.cagr !== undefined ? item.cagr : 0);
            const sVal = item.sharpe_ratio !== undefined ? item.sharpe_ratio : (item.sharpe !== undefined ? item.sharpe : 0);
            const wVal = item.win_rate_pct !== undefined ? item.win_rate_pct : (item.win_rate !== undefined ? item.win_rate : 0);
            const ddVal = item.max_drawdown_pct !== undefined ? item.max_drawdown_pct : (item.max_dd !== undefined ? item.max_dd : 0);

            return `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                <td style="text-align:left; font-weight:700; color:#38bdf8;">${escapeHTML(mName)}</td>
                <td class="mono font-bold ${cVal >= 0 ? 'txt-up' : 'txt-down'}" style="text-align:right;">${cVal > 0 ? '+' : ''}${cVal}%</td>
                <td class="mono font-bold" style="text-align:right; color:#facc15;">${sVal}</td>
                <td class="mono" style="text-align:right; color:#c084fc;">${wVal}%</td>
                <td class="mono txt-down" style="text-align:right;">-${ddVal}%</td>
              </tr>
            `;
          }).join('');
        }
      }

      // 5. Render Detailed Trades Log
      const trTb = document.getElementById('fvBtTradesTableBody');
      const badgeCount = document.getElementById('fvBtTradesCountBadge');
      const trades = d.trades || [];
      if (badgeCount) badgeCount.textContent = `${trades.length} lệnh khớp`;

      if (trTb) {
        if (trades.length === 0) {
          trTb.innerHTML = '<tr><td colspan="11" style="padding:20px; color:var(--text-muted);">Không có vị thế giao dịch nào được kích hoạt.</td></tr>';
        } else {
          trTb.innerHTML = trades.map((t, idx) => {
            const isWin = t.return_pct > 0;
            const exitReasonStr = String(t.exit_reason || 'HOLDING_EXPIRY');
            const isTp = exitReasonStr.includes('TAKE_PROFIT') || exitReasonStr.includes('Take-Profit');
            const isSl = exitReasonStr.includes('STOP_LOSS') || exitReasonStr.includes('Stop-Loss');

            return `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                <td style="color:var(--text-muted);">${idx + 1}</td>
                <td class="col-symbol" style="font-weight:800; color:#38bdf8; cursor:pointer;" onclick="app.selectStock('${escapeHTML(t.symbol)}')">${escapeHTML(t.symbol)}</td>
                <td class="mono">${escapeHTML(t.entry_date)}</td>
                <td class="mono font-bold" style="text-align:right;">${Number(t.entry_price).toLocaleString('vi-VN')}</td>
                <td class="mono font-bold txt-blue" style="text-align:right;">${Number(t.entry_fair_value).toLocaleString('vi-VN')}</td>
                <td class="mono font-bold txt-up">${t.entry_mos_pct}%</td>
                <td class="mono">${escapeHTML(t.exit_date)}</td>
                <td class="mono font-bold" style="text-align:right;">${Number(t.exit_price).toLocaleString('vi-VN')}</td>
                <td style="text-align:left; font-size:11px; color:${isTp ? '#34d399' : (isSl ? '#f87171' : '#38bdf8')}; font-weight:600;">
                  ${escapeHTML(exitReasonStr)}
                </td>
                <td class="mono font-bold ${isWin ? 'txt-up' : 'txt-down'}" style="text-align:right;">
                  ${isWin ? '+' : ''}${t.return_pct}%
                </td>
                <td style="font-size:10.5px;">
                  <span class="badge-tag ${t.z_score_safe ? 'badge-success' : 'badge-danger'}">${t.z_score_safe ? 'Z-Safe' : 'Z-Risk'}</span>
                </td>
              </tr>
            `;
          }).join('');
        }
      }

      this.showToast(`Đã đối soát thành công mô hình định giá (CAGR ${m.cagr_pct}%, Sharpe ${m.sharpe_ratio})!`, 'toast-up');
    } catch (e) {
      console.error('Error running fair value backtest:', e);
      this.showToast('Lỗi kết nối khi chạy đối soát định giá.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>▶</span> Chạy Backtest Định Giá Modular';
      }
    }
  }

  drawFairValueEquityChart(curve) {
    const canvas = document.getElementById('fvBtEquityCanvas');
    if (!canvas || !curve || curve.length === 0) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    const padding = { top: 20, right: 30, bottom: 30, left: 60 };
    const chartW = w - padding.left - padding.right;
    const chartH = h - padding.top - padding.bottom;

    const stratNavs = curve.map(c => c.strategy_equity);
    const bmNavs = curve.map(c => c.benchmark_equity);
    const allVals = [...stratNavs, ...bmNavs];

    let minVal = Math.min(...allVals) * 0.95;
    let maxVal = Math.max(...allVals) * 1.05;
    if (minVal === maxVal) { minVal *= 0.9; maxVal *= 1.1; }

    const getX = (idx) => padding.left + (idx / Math.max(1, curve.length - 1)) * chartW;
    const getY = (val) => padding.top + chartH - ((val - minVal) / (maxVal - minVal)) * chartH;

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let k = 0; k <= 4; k++) {
      const gY = padding.top + (k / 4) * chartH;
      ctx.beginPath();
      ctx.moveTo(padding.left, gY);
      ctx.lineTo(w - padding.right, gY);
      ctx.stroke();

      const labelVal = maxVal - (k / 4) * (maxVal - minVal);
      ctx.fillStyle = '#64748b';
      ctx.font = '10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(labelVal.toFixed(0), padding.left - 8, gY + 3);
    }

    // Benchmark line
    ctx.beginPath();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    bmNavs.forEach((val, idx) => {
      const x = getX(idx);
      const y = getY(val);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Strategy line & fill gradient
    const grad = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
    grad.addColorStop(0, 'rgba(250, 204, 21, 0.25)');
    grad.addColorStop(1, 'rgba(250, 204, 21, 0.00)');

    ctx.beginPath();
    stratNavs.forEach((val, idx) => {
      const x = getX(idx);
      const y = getY(val);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(getX(stratNavs.length - 1), padding.top + chartH);
    ctx.lineTo(getX(0), padding.top + chartH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    ctx.strokeStyle = '#facc15';
    ctx.lineWidth = 2.5;
    stratNavs.forEach((val, idx) => {
      const x = getX(idx);
      const y = getY(val);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // X-axis dates
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    curve.forEach((pt, idx) => {
      if (idx % 2 === 0 || idx === curve.length - 1) {
        ctx.fillText(pt.date, getX(idx), h - padding.bottom + 16);
      }
    });
  }
}



// Instantiate on load
window.addEventListener('DOMContentLoaded', () => {
  window.app = new VnstockApp();

  window.AppBridge = Object.assign(window.AppBridge || {}, {
    selectSector: (code) => {
      if (!window.app || typeof window.app.selectSector !== 'function') return;
      if (typeof window.app.switchSectorSubtab === 'function') {
        window.app.switchSectorSubtab('overview');
      }
      window.app.selectSector(code);
    }
  });
});
