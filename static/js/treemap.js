/**
 * ==========================================================================
 * VNSTOCK TERMINAL - MARKET TREEMAP ORCHESTRATOR (v9.2.0)
 * ==========================================================================
 * Hierarchical squarified treemap: sectors sized by total_cap across one
 * canvas (TradingView-style), stocks nested inside their sector rect.
 * Integrates TreemapLayout / TMColor / TMLabel / TMTooltip / TMPerf with
 * graceful per-module fallback to legacy behavior.
 */

(function () {
  'use strict';

  function has(name) { return typeof window[name] === 'object' && window[name] !== null; }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtPct(v) {
    var n = Number(v) || 0;
    return (n > 0 ? '+' : '') + n.toFixed(2) + '%';
  }

  function chgClass(v) {
    var n = Number(v) || 0;
    return n > 0 ? 'txt-up' : (n < 0 ? 'txt-down' : 'txt-ref');
  }

  function legacyColor(chgPct) {
    var n = Number(chgPct) || 0;
    if (n >= 6.8) return { bg: '#c084fc', fg: '#090d16' };
    if (n <= -6.8) return { bg: '#22d3ee', fg: '#090d16' };
    if (n > 3.0) return { bg: '#047857', fg: '#ffffff' };
    if (n > 0.0) return { bg: '#10b981', fg: '#ffffff' };
    if (n === 0.0) return { bg: '#94a3b8', fg: '#090d16' };
    if (n < -3.0) return { bg: '#b91c1c', fg: '#ffffff' };
    return { bg: '#ef4444', fg: '#ffffff' };
  }

  function legacyLegend() {
    var items = [
      ['#c084fc', 'Trần'], ['#059669', '> +3%'], ['#10b981', '+0.1% ~ +3%'],
      ['#f59e0b', '0% (TC)'], ['#ef4444', '-0.1% ~ -3%'], ['#b91c1c', '< -3%'], ['#22d3ee', 'Sàn']
    ];
    return items.map(function (it) {
      return '<span class="legend-item"><span class="legend-box" style="background:' + it[0] + ';"></span>' + it[1] + '</span>';
    }).join('');
  }

  class MarketTreemap {
    constructor(containerId = 'treemapContainer') {
      this.containerId = containerId || 'treemapContainer';
      this.container = document.getElementById(this.containerId);
      this.data = null;
      this.state = { sizeBy: 'market_cap', query: '', drilledSector: null };
      this._onResizeBound = this._relayout.bind(this);
      window.addEventListener('resize', this._onResizeBound);
    }

    render(data) {
      const run = () => this._render(data);
      if (has('TMPerf') && typeof window.TMPerf.measure === 'function') window.TMPerf.measure('tm_render', run);
      else run();
    }

    drill(sectorKey) { this.state.drilledSector = sectorKey; this.render(this.data); }
    reset() { this.state.drilledSector = null; this.render(this.data); }
    highlight(query) { this.state.query = query || ''; this._applyHighlight(); }

    _render(data) {
      if (!this.container) this.container = document.getElementById(this.containerId);
      this.data = data;
      const sectors = Array.isArray(data) ? data : ((data && (data.sectors || data.children)) || []);
      if (!this.container || sectors.length === 0) {
        console.warn('MarketTreemap: Container or sector data not found', { container: this.container });
        return;
      }
      if (this.state.drilledSector && !sectors.some(s => this._key(s) === this.state.drilledSector)) {
        this.state.drilledSector = null;
      }

      const focusedSym = document.activeElement && document.activeElement.getAttribute
        ? document.activeElement.getAttribute('data-symbol') : null;

      const legendHTML = has('TMColor') && typeof window.TMColor.legendHTML === 'function'
        ? window.TMColor.legendHTML() : legacyLegend();

      let html = '<div class="tm-root">'
        + '<div class="tm-toolbar">'
        + '<label>Kích thước theo '
        + '<select id="tmSizeBy" aria-label="Kích thước ô theo">'
        + '<option value="market_cap"' + (this.state.sizeBy === 'market_cap' ? ' selected' : '') + '>Vốn hóa</option>'
        + '<option value="volume"' + (this.state.sizeBy === 'volume' ? ' selected' : '') + '>Thanh khoản</option>'
        + '</select></label>'
        + '<input id="tmSearch" type="search" placeholder="Tìm mã CP…" aria-label="Tìm kiếm cổ phiếu" value="' + esc(this.state.query) + '">'
        + '</div>'
        + '<nav class="tm-legend" aria-label="Chú giải màu">' + legendHTML + '</nav>';

      if (this.state.drilledSector) {
        const s = sectors.find(x => this._key(x) === this.state.drilledSector);
        html += '<div class="tm-breadcrumb">'
          + '<button type="button" class="tm-crumb tm-crumb--active" data-crumb="root">← Tổng quan</button>'
          + '<span class="tm-crumb-sep">›</span><span class="tm-crumb-current">' + esc((s && s.icon ? s.icon + ' ' : '') + ((s && (s.name || s.code)) || '')) + '</span>'
          + '</div>';
      }

      html += '<div class="tm-canvas" id="treemapGrid"></div></div>';
      this.container.innerHTML = html;

      this._layoutCanvas();
      this._bindEvents();

      if (has('TMTooltip') && typeof window.TMTooltip.attach === 'function') {
        try { window.TMTooltip.attach(this.container); } catch (e) { /* no-op */ }
      }
      if (focusedSym) {
        const t = this.container.querySelector('[data-symbol="' + CSS.escape(focusedSym) + '"]');
        if (t) { try { t.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
      }
      this._applyHighlight();
    }
    _key(s) { return String(s.code || s.key || s.name || 'Ngành'); }

    _visible() {
      const sectors = Array.isArray(this.data) ? this.data : ((this.data && (this.data.sectors || this.data.children)) || []);
      if (!this.state.drilledSector) return sectors;
      return sectors.filter(s => this._key(s) === this.state.drilledSector);
    }

    _layoutCanvas() {
      const canvas = this.container.querySelector('#treemapGrid');
      if (!canvas) return;
      const W = canvas.clientWidth || this.container.clientWidth || 1200;
      const H = Math.max(480, Math.min(900, Math.round(W * 0.62)));
      canvas.style.height = H + 'px';

      const sectors = this._visible().filter(s => s.children && s.children.length > 0);
      // Linear sizing keeps rank gaps far above pixel noise (critic C2):
      // area ∝ value exactly across both hierarchy levels.
      const items = sectors.map(s => {
        const vals = s.children.map(c => this.state.sizeBy === 'volume' ? Math.max(0, Number(c.volume) || 0) : Math.max(0, Number(c.market_cap) || 0));
        let total = vals.reduce((a, v) => a + v, 0);
        if (!(total > 0)) total = Math.max(1, Number(s.total_cap) || 0);
        return { sector: s, value: total };
      });

      let rects;
      if (has('TreemapLayout') && typeof window.TreemapLayout.squarify === 'function') {
        rects = window.TreemapLayout.squarify(items, W, H, 3);
      } else {
        rects = this._fallbackSectorLayout(items, W, H);
      }

      const frag = document.createDocumentFragment();
      rects.forEach(r => frag.appendChild(this._buildSector(r)));
      canvas.innerHTML = '';
      canvas.appendChild(frag);
    }

    _buildSector(rect) {
      const s = rect.item.sector;
      const bodyTop = 27; // measured head height ~24.4px (critic C3 #5)
      const up = s.breadth_up != null ? s.breadth_up : s.children.filter(c => Number(c.change_pct) > 0).length;
      const down = s.breadth_down != null ? s.breadth_down : s.children.filter(c => Number(c.change_pct) < 0).length;

      const sect = document.createElement('section');
      sect.className = 'tm-sector';
      sect.setAttribute('data-sector', this._key(s));
      const headId = 'tmsh-' + this._key(s).replace(/[^a-zA-Z0-9_-]/g, '_');
      sect.setAttribute('aria-labelledby', headId);
      sect.style.cssText = 'position:absolute;left:' + rect.x + 'px;top:' + rect.y + 'px;width:' + rect.w + 'px;height:' + rect.h + 'px;';
      sect.innerHTML =
        '<header class="tm-sector-head">'
        + '<span class="tm-sector-name" id="' + headId + '">' + esc(s.icon || '📊') + ' ' + esc(s.name || s.code || 'Ngành') + '</span>'
        + '<span class="tm-breadth mono">' + up + '\u25B2/' + down + '\u25BC</span>'
        + '<span class="tm-sector-chg mono ' + chgClass(s.avg_change_pct) + '">' + fmtPct(s.avg_change_pct) + '</span>'
        + '</header>'
        + '<div class="tm-sector-body" style="position:absolute;left:0;top:' + bodyTop + 'px;width:100%;height:' + Math.max(0, rect.h - bodyTop) + 'px;"></div>';

      this._layoutStocks(sect.querySelector('.tm-sector-body'), s, rect.w, rect.h - bodyTop);
      return sect;
    }

    _layoutStocks(body, sector, availW, availH) {
      // Use the real pixel geometry of the sector body (never parseFloat on
      // "100%", which silently yields 100px and squeezes tiles into a strip).
      const W = (Number(availW) > 0 ? Number(availW) : (body.clientWidth || 300)) - 2;
      const H = Math.max(40, (Number(availH) > 0 ? Number(availH) : (body.clientHeight || 200)) - 2);
      // Linear value with a small floor so unknown-cap names stay visible
      // (smallest real name ~440px² at full canvas — still legible, critic C2).
      const rawVals = sector.children.map(c => this.state.sizeBy === 'volume' ? Number(c.volume) || 0 : Number(c.market_cap) || 0);
      const avgRaw = rawVals.reduce((a, v) => a + v, 0) / Math.max(1, rawVals.length);
      const items = sector.children.map((c, i) => {
        let v = rawVals[i];
        if (!(v > 0)) v = Math.max(1, avgRaw * 0.02);
        return { stock: c, value: v };
      });

      let rects;
      if (has('TreemapLayout') && typeof window.TreemapLayout.squarify === 'function') {
        rects = window.TreemapLayout.squarify(items, W, H, 1);
      } else {
        rects = items.map((it, i) => ({ item: it, x: (i % 10) * (W / 10), y: Math.floor(i / 10) * (H / 10), w: W / 10, h: H / 10 }));
      }

      const frag = document.createDocumentFragment();
      rects.forEach(r => { if (r.w > 0 && r.h > 0) frag.appendChild(this._buildTile(r)); });
      body.innerHTML = '';
      body.appendChild(frag);
    }

    _buildTile(rect) {
      const st = rect.item.stock;
      const chgPct = Number(st.change_pct) || 0;
      const price = Number(st.price) || 0;
      const cap = Number(st.market_cap) || 0;
      const col = has('TMColor') && typeof window.TMColor.scale === 'function'
        ? window.TMColor.scale(chgPct) : legacyColor(chgPct);

      const tile = document.createElement('div');
      tile.className = 'treemap-tile tm-tile';
      tile.setAttribute('role', 'button');
      tile.setAttribute('tabindex', '0');
      tile.setAttribute('data-symbol', st.symbol || '');
      tile.setAttribute('data-name', st.name || st.symbol || '');
      tile.setAttribute('data-price', String(price));
      tile.setAttribute('data-chgpct', String(chgPct));
      tile.setAttribute('data-cap', String(cap));
      tile.setAttribute('data-exchange', st.exchange || 'HOSE');
      tile.setAttribute('aria-label', (st.symbol || '') + ' ' + fmtPct(chgPct));
      tile.setAttribute('data-tip',
        '<strong>' + esc(st.symbol) + '</strong>' + (st.name ? ' — ' + esc(st.name) : '')
        + '<br>Giá: ' + price.toFixed(2) + ' (' + fmtPct(chgPct) + ')'
        + '<br>Vốn hóa: ' + Math.round(cap).toLocaleString('vi-VN') + ' tỷ'
        + '<br>Sàn: ' + esc(st.exchange || 'HOSE'));
      tile.style.cssText =
        'position:absolute;left:' + rect.x + 'px;top:' + rect.y + 'px;width:' + rect.w + 'px;height:' + rect.h + 'px;'
        + 'background-color:' + col.bg + ';color:' + col.fg + ';';

      let inner;
      if (has('TMLabel') && typeof window.TMLabel.html === 'function') {
        inner = window.TMLabel.html(st, window.TMLabel.plan(rect.w, rect.h));
      } else {
        inner = '<div class="tile-symbol">' + esc(st.symbol) + '</div><div class="tile-pct">' + fmtPct(chgPct) + '</div>';
      }
      tile.innerHTML = inner;
      return tile;
    }

    _fallbackSectorLayout(items, W, H) {
      const total = items.reduce((a, it) => a + it.value, 0) || 1;
      let x = 0;
      return items.map(it => {
        const w = (it.value / total) * W;
        const r = { item: it, x: Math.round(x), y: 0, w: Math.round(w), h: H };
        x += w;
        return r;
      });
    }

    _bindEvents() {
      const sizeSel = this.container.querySelector('#tmSizeBy');
      if (sizeSel) sizeSel.addEventListener('change', () => { this.state.sizeBy = sizeSel.value; this._relayout(); });

      const search = this.container.querySelector('#tmSearch');
      if (search) {
        let t = null;
        search.addEventListener('input', () => {
          clearTimeout(t);
          t = setTimeout(() => { this.state.query = search.value.trim(); this._applyHighlight(); }, 120);
        });
      }

      const crumb = this.container.querySelector('[data-crumb="root"]');
      if (crumb) crumb.addEventListener('click', () => this.reset());

      const grid = this.container.querySelector('.tm-canvas');
      if (!grid) return;
      grid.addEventListener('click', (ev) => {
        const tile = ev.target.closest('.treemap-tile');
        if (tile && window.app && typeof window.app.inspectStock === 'function') {
          window.app.inspectStock(tile.getAttribute('data-symbol'));
          return;
        }
        const head = ev.target.closest('.tm-sector-head');
        if (head && !this.state.drilledSector) this.drill(head.parentElement.getAttribute('data-sector'));
      });
      grid.addEventListener('keydown', (ev) => {
        const tile = ev.target.closest ? ev.target.closest('.treemap-tile') : null;
        if (!tile) return;
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault();
          if (window.app && typeof window.app.inspectStock === 'function') window.app.inspectStock(tile.getAttribute('data-symbol'));
        } else if (ev.key === 'Escape' && this.state.drilledSector) {
          ev.preventDefault();
          this.reset();
        }
      });
    }

    _relayout() {
      if (!this.container || !this.data) return;
      const run = () => { this._layoutCanvas(); this._applyHighlight(); };
      if (has('TMPerf') && typeof window.TMPerf.batch === 'function') window.TMPerf.batch(run);
      else requestAnimationFrame(run);
    }

    _applyHighlight() {
      const q = (this.state.query || '').toLowerCase();
      this.container.querySelectorAll('.treemap-tile').forEach(t => {
        if (!q) { t.classList.remove('tm-dim'); return; }
        const sym = (t.getAttribute('data-symbol') || '').toLowerCase();
        const name = (t.getAttribute('data-name') || '').toLowerCase();
        t.classList.toggle('tm-dim', !(sym.indexOf(q) === 0 || name.indexOf(q) !== -1));
      });
    }
  }

  window.MarketTreemap = MarketTreemap;
})();
