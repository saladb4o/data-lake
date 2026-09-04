/**
 * TMLabel - adaptive label typography for treemap tiles (ES2018, no deps)
 */
(function () {
  'use strict';

  var CHAR_W = 0.62;
  var PAD_X = 4;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fitFont(text, availW, availH, cap) {
    var byW = availW > 0 && text.length > 0 ? availW / (CHAR_W * text.length) : cap;
    var byH = availH;
    return Math.max(7, Math.floor(Math.min(cap, byW, byH)));
  }

  window.TMLabel = {
    plan: function (tileW, tileH) {
      var w = Number(tileW) || 0;
      var h = Number(tileH) || 0;
      var plan = {
        symPx: 0,
        pctPx: 0,
        pricePx: 0,
        showPrice: false,
        showPct: false,
        showSym: false
      };
      var isLarge = w > 110 && h > 64;
      var isVerySmall = w < 34 || h < 20;
      var symCap = isLarge ? 22 : (w >= 62 ? 15 : 12);

      if (isVerySmall) {
        return plan;
      }

      var availW = w - PAD_X * 2;
      var symTextLen = Math.min(Math.max(Math.ceil(availW / (CHAR_W * 9)), 3), 6);
      plan.showSym = true;
      plan.symPx = fitFont('MMMMMM'.slice(0, symTextLen), availW, h * 0.42, symCap);

      if (isLarge) {
        plan.showPct = true;
        plan.pctPx = fitFont('+00.00%', availW, h * 0.3, Math.max(11, Math.round(plan.symPx * 0.72)));
        plan.showPrice = true;
        plan.pricePx = fitFont('0,000.00', availW, h * 0.24, Math.max(10, Math.round(plan.symPx * 0.6)));
      } else if (w >= 52 && h >= 28) {
        plan.showPct = true;
        plan.pctPx = fitFont('+00.00%', availW, h * 0.36, Math.max(9, Math.round(plan.symPx * 0.78)));
      }

      return plan;
    },

    pctText: function (changePct) {
      var v = Number(changePct) || 0;
      var fixed = Math.abs(v).toFixed(2);
      if (v > 0) return '+' + fixed + '%';
      if (v < 0) return '-' + fixed + '%';
      return '0.00%';
    },

    priceText: function (price) {
      var v = Number(price);
      if (!isFinite(v)) v = 0;
      var parts = v.toFixed(2).split('.');
      var intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return intPart + '.' + parts[1];
    },

    html: function (stock, plan) {
      var s = stock || {};
      var p = plan || {};
      var out = '';
      if (p.showSym && p.symPx > 0) {
        out += '<span class="tile-symbol tm-tile-sym" style="font-size:' + p.symPx + 'px">' +
          esc(s.symbol) + '</span>';
      }
      if (p.showPct && p.pctPx > 0) {
        out += '<span class="tile-pct tm-tile-pct" style="font-size:' + p.pctPx + 'px">' +
          esc(this.pctText(s.change_pct)) + '</span>';
      }
      if (p.showPrice && p.pricePx > 0) {
        out += '<span class="tile-price tm-tile-price" style="font-size:' + p.pricePx + 'px">' +
          esc(this.priceText(s.price)) + '</span>';
      }
      return out;
    }
  };
})();
