/**
 * TreemapLayout - Bruls et al. squarified treemap layout (pure, dependency-free).
 * Exposes:
 *   window.TreemapLayout.squarify(items, width, height, padding) -> [{item, x, y, w, h}]
 *   window.TreemapLayout.aspectStats(rects) -> {count, avgAspect, worstAspect}
 */
(function () {
  'use strict';

  function toFiniteNum(v) {
    var n = Number(v);
    return isFinite(n) ? n : NaN;
  }

  function normalizeItems(items) {
    var list = [];
    if (!Array.isArray(items)) return list;
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var v = it && typeof it === 'object' ? toFiniteNum(it.value) : NaN;
      list.push({ idx: i, item: it, value: v > 0 ? v : 0 });
    }
    return list;
  }

  function worstRatio(rowArea, shortSide) {
    if (!(rowArea > 0) || !(shortSide > 0)) return Infinity;
    var thickness = rowArea / shortSide;
    if (!(thickness > 0)) return Infinity;
    var worst = 0;
    for (var i = 0; i < arguments.length - 2; i++) {
      var area = arguments[i + 2];
      if (!(area > 0)) continue;
      var extent = area / thickness;
      var ratio = extent >= thickness ? extent / thickness : thickness / extent;
      if (ratio > worst) worst = ratio;
    }
    return worst;
  }

  /**
   * Compute a squarified treemap layout.
   * @param {Array<{value:number}>} items
   * @param {number} width
   * @param {number} height
   * @param {number} [padding]
   * @returns {Array<{item:*, x:number, y:number, w:number, h:number}>}
   */
  function squarify(items, width, height, padding) {
    var all = normalizeItems(items);
    var out = new Array(all.length);
    var i;

    for (i = 0; i < all.length; i++) {
      out[all[i].idx] = { item: all[i].item, x: 0, y: 0, w: 0, h: 0 };
    }

    width = toFiniteNum(width);
    height = toFiniteNum(height);
    padding = toFiniteNum(padding);
    if (!isFinite(padding) || padding < 0) padding = 0;

    var ix = Math.round(padding);
    var iy = Math.round(padding);
    var iw = Math.round(width) - ix * 2;
    var ih = Math.round(height) - iy * 2;

    var valid = all.filter(function (e) { return e.value > 0; });

    if (valid.length === 0 || !(iw > 0) || !(ih > 0)) {
      return out;
    }

    var total = 0;
    for (i = 0; i < valid.length; i++) total += valid[i].value;
    if (!(total > 0)) return out;

    var scale = (iw * ih) / total;
    for (i = 0; i < valid.length; i++) {
      valid[i].area = valid[i].value * scale;
    }

    // Sort descending for best aspect ratios; output stays in original order.
    var sorted = valid.slice().sort(function (a, b) { return b.area - a.area; });

    var rx = ix, ry = iy, rw = iw, rh = ih;
    var pos = 0;

    while (pos < sorted.length) {
      var shortSide = Math.min(rw, rh);
      if (!(shortSide > 0)) break;

      var row = [sorted[pos]];
      var rowArea = sorted[pos].area;
      pos++;
      var worst = worstRatio(rowArea, shortSide, sorted[pos - 1].area);

      while (pos < sorted.length) {
        var nextArea = rowArea + sorted[pos].area;
        var nextWorst = worstRatio.apply(null, [nextArea, shortSide].concat(
          row.map(function (e) { return e.area; }), [sorted[pos].area]
        ));
        if (nextWorst <= worst) {
          row.push(sorted[pos]);
          rowArea = nextArea;
          worst = nextWorst;
          pos++;
        } else {
          break;
        }
      }

      var horizontalStrip = rw <= rh; // narrower than tall -> lay row across full width
      var thickness = horizontalStrip ? rowArea / rw : rowArea / rh;
      if (!(thickness > 0)) thickness = 0.0001;
      // Integer-snap the strip thickness so rows advance on the same grid
      // they are drawn on — kills +/-1px seams (critic C3 #3).
      var tInt = Math.max(1, Math.round(thickness));
      if (tInt > (horizontalStrip ? rh : rw)) tInt = Math.max(1, Math.round(horizontalStrip ? rh : rw));

      var offset = 0;
      var lastIdx = -1;
      for (i = 0; i < row.length; i++) {
        var ext = row[i].area / thickness;
        var rect;
        if (horizontalStrip) {
          var x0 = Math.round(rx + offset);
          var x1 = Math.round(rx + offset + ext);
          if (x1 <= x0) x1 = x0 + 1;
          rect = { item: row[i].item, x: x0, y: Math.round(ry), w: x1 - x0, h: tInt };
        } else {
          var y0 = Math.round(ry + offset);
          var y1 = Math.round(ry + offset + ext);
          if (y1 <= y0) y1 = y0 + 1;
          rect = { item: row[i].item, x: Math.round(rx), y: y0, w: tInt, h: y1 - y0 };
        }
        out[row[i].idx] = rect;
        lastIdx = row[i].idx;
        offset += ext;
      }

      if (horizontalStrip) {
        if (lastIdx >= 0) out[lastIdx].w = Math.max(1, Math.round(rx + rw) - out[lastIdx].x);
        ry += tInt;
        rh -= tInt;
      } else {
        if (lastIdx >= 0) out[lastIdx].h = Math.max(1, Math.round(ry + rh) - out[lastIdx].y);
        rx += tInt;
        rw -= tInt;
      }
    }

    return out;
  }

  /**
   * Aspect-ratio statistics over produced rects.
   * @param {Array<{x:number,y:number,w:number,h:number}>} rects
   * @returns {{count:number, avgAspect:number, worstAspect:number}}
   */
  function aspectStats(rects) {
    var count = 0;
    var sum = 0;
    var worst = 0;
    if (Array.isArray(rects)) {
      for (var i = 0; i < rects.length; i++) {
        var r = rects[i];
        if (!r) continue;
        var w = toFiniteNum(r.w);
        var h = toFiniteNum(r.h);
        if (!(w > 0) || !(h > 0)) continue;
        var ar = w >= h ? w / h : h / w;
        count++;
        sum += ar;
        if (ar > worst) worst = ar;
      }
    }
    return {
      count: count,
      avgAspect: count > 0 ? sum / count : 0,
      worstAspect: count > 0 ? worst : 0
    };
  }

  window.TreemapLayout = {
    squarify: squarify,
    aspectStats: aspectStats
  };
})();
