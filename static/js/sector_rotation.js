(function () {
  'use strict';

  var QUAD_COLORS = {
    Leading: '#10b981',
    Weakening: '#f59e0b',
    Lagging: '#ef4444',
    Improving: '#3b82f6'
  };

  var SVG_W = 1000;
  var SVG_H = 560;
  var M = { l: 64, r: 32, t: 24, b: 54 };

  var state = {
    inited: false,
    loading: false,
    lastPayload: null,
    lastParams: null,
    points: []
  };

  function $(id) { return document.getElementById(id); }

  function getPanel() { return $('sectorRotationPanel'); }
  function getContainer() { return $('rrgChartContainer'); }
  function getStatus() { return $('rrgStatus'); }

  function isVisible() {
    var p = getPanel();
    if (!p || p.style.display === 'none') return false;
    return !!(p.offsetWidth || p.offsetHeight || p.getClientRects().length);
  }

  function readParams() {
    var bench = $('rrgBenchmark');
    var itv = $('rrgInterval');
    var met = $('rrgMethod');
    var tail = $('rrgTail');
    return {
      benchmark: bench ? bench.value : 'VNINDEX',
      interval: itv ? itv.value : '1W',
      method: met ? met.value : 'jdk',
      tail: tail ? String(parseInt(tail.value, 10) || 8) : '8'
    };
  }

  function setStatus(msg) {
    var s = getStatus();
    if (s) s.textContent = msg || '';
  }

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmt(n, d) {
    var num = Number(n);
    if (!isFinite(num)) return '--';
    return num.toFixed(d == null ? 2 : d);
  }

  function fetchAndRender() {
    if (state.loading) return;
    var p = readParams();
    state.lastParams = p;
    var qs = 'benchmark=' + encodeURIComponent(p.benchmark) +
      '&interval=' + encodeURIComponent(p.interval) +
      '&tail=' + encodeURIComponent(p.tail) +
      '&method=' + encodeURIComponent(p.method);
    state.loading = true;
    setStatus('⏳ Đang tải dữ liệu RRG (' + p.benchmark + ' / ' + p.interval + ' / ' + p.method + ')...');
    fetch('/api/sectors/rrg?' + qs)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        state.loading = false;
        var d = (data && typeof data === 'object' && data.data) ? data.data : (data || {});
        state.lastPayload = d;
        state.points = Array.isArray(d.points) ? d.points : [];
        setStatus('✅ Cập nhật lúc ' + new Date().toLocaleTimeString('vi-VN') +
          ' • Benchmark: ' + esc(d.benchmark) +
          ' • Chu kỳ: ' + esc(d.interval) +
          ' • ' + countValid() + ' ngành hiển thị');
        draw(state.points);
      })
      .catch(function (err) {
        state.loading = false;
        setStatus('❌ Lỗi tải dữ liệu RRG: ' + err.message);
      });
  }

  function countValid() {
    var n = 0;
    for (var i = 0; i < state.points.length; i++) {
      var pt = state.points[i];
      if (pt && !pt.error && isFinite(Number(pt.rs_ratio)) && isFinite(Number(pt.rs_momentum))) n++;
    }
    return n;
  }

  function computeScales(points) {
    var xs = [], ys = [], i, pt;
    for (i = 0; i < points.length; i++) {
      pt = points[i];
      if (!pt || pt.error) continue;
      var x = Number(pt.rs_ratio), y = Number(pt.rs_momentum);
      if (isFinite(x)) xs.push(x);
      if (isFinite(y)) ys.push(y);
      var tl = Array.isArray(pt.tail) ? pt.tail : [];
      for (var j = 0; j < tl.length; j++) {
        var tx = Number(tl[j] && tl[j].x), ty = Number(tl[j] && tl[j].y);
        if (isFinite(tx)) xs.push(tx);
        if (isFinite(ty)) ys.push(ty);
      }
    }
    xs.push(100); ys.push(100);
    var xLo = Math.min(80, Math.min.apply(null, xs));
    var xHi = Math.max(120, Math.max.apply(null, xs));
    var yLo = Math.min(80, Math.min.apply(null, ys));
    var yHi = Math.max(120, Math.max.apply(null, ys));
    var xPad = Math.max((xHi - xLo) * 0.08, 1);
    var yPad = Math.max((yHi - yLo) * 0.08, 1);
    xLo -= xPad; xHi += xPad; yLo -= yPad; yHi += yPad;
    var pw = SVG_W - M.l - M.r;
    var ph = SVG_H - M.t - M.b;
    return {
      sx: function (v) { return M.l + ((v - xLo) / (xHi - xLo)) * pw; },
      sy: function (v) { return M.t + ph - ((v - yLo) / (yHi - yLo)) * ph; },
      xLo: xLo, xHi: xHi, yLo: yLo, yHi: yHi,
      pw: pw, ph: ph
    };
  }

  function svgEl(tag, attrs) {
    var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) {
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] != null) {
          el.setAttribute(k, attrs[k]);
        }
      }
    }
    return el;
  }

  function quadrantOf(x, y) {
    if (x >= 100 && y >= 100) return 'Leading';
    if (x >= 100 && y < 100) return 'Weakening';
    if (x < 100 && y < 100) return 'Lagging';
    return 'Improving';
  }

  function clearContainer(container) {
    while (container.firstChild) {
      if (container.firstChild.id === 'rrgTooltip') break;
      container.removeChild(container.firstChild);
    }
  }

  function getTooltip() {
    var c = getContainer();
    if (!c) return null;
    var t = $('rrgTooltip');
    if (!t) {
      t = document.createElement('div');
      t.id = 'rrgTooltip';
      t.style.cssText = 'display:none;position:absolute;z-index:20;pointer-events:none;background:rgba(9,14,23,0.95);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:8px 10px;font-size:11px;line-height:1.5;';
      c.appendChild(t);
    }
    return t;
  }

  function showTooltip(evt, pt) {
    var t = getTooltip();
    var c = getContainer();
    if (!t || !c || !pt) return;
    var quad = pt.quadrant || quadrantOf(Number(pt.rs_ratio), Number(pt.rs_momentum));
    var col = QUAD_COLORS[quad] || '#94a3b8';
    t.innerHTML =
      '<div style="font-weight:800;font-size:12px;">' + esc(pt.sector_code) +
      (pt.sector_name ? ' <span style="font-weight:400;color:#94a3b8;">' + esc(pt.sector_name) + '</span>' : '') +
      '</div>' +
      '<div>RS-Ratio: <strong>' + fmt(pt.rs_ratio) + '</strong></div>' +
      '<div>RS-Momentum: <strong>' + fmt(pt.rs_momentum) + '</strong></div>' +
      '<div><span style="color:' + col + ';font-weight:700;">● ' + esc(quad) + '</span></div>';
    t.style.display = 'block';
    var rect = c.getBoundingClientRect();
    var px = evt.clientX - rect.left + 14;
    var py = evt.clientY - rect.top + 14;
    if (px + 190 > rect.width) px = evt.clientX - rect.left - 195;
    if (py + 90 > rect.height) py = evt.clientY - rect.top - 95;
    t.style.left = Math.max(4, px) + 'px';
    t.style.top = Math.max(4, py) + 'px';
  }

  function hideTooltip() {
    var t = getTooltip();
    if (t) t.style.display = 'none';
  }

  function draw(points) {
    var container = getContainer();
    if (!container) return;
    var oldSvg = container.querySelector('svg.rrg-svg');
    if (oldSvg && oldSvg.parentNode) oldSvg.parentNode.removeChild(oldSvg);

    var note = $('rrgErrorNote');
    var errors = [];
    var valid = [];
    for (var i = 0; i < points.length; i++) {
      var pt = points[i];
      if (!pt) continue;
      if (pt.error || !isFinite(Number(pt.rs_ratio)) || !isFinite(Number(pt.rs_momentum))) {
        errors.push({ code: pt.sector_code || '?', error: pt.error || 'Dữ liệu không hợp lệ' });
      } else {
        valid.push(pt);
      }
    }
    if (note) {
      if (errors.length) {
        note.style.display = 'block';
        note.innerHTML = '⚠️ Không vẽ được: ' + errors.map(function (e) {
          return '<strong>' + esc(e.code) + '</strong> (' + esc(e.error) + ')';
        }).join(', ');
      } else {
        note.style.display = 'none';
        note.innerHTML = '';
      }
    }

    var svg = svgEl('svg', {
      class: 'rrg-svg',
      width: '100%',
      height: SVG_H,
      viewBox: '0 0 ' + SVG_W + ' ' + SVG_H,
      preserveAspectRatio: 'xMidYMid meet'
    });
    svg.style.display = 'block';
    svg.style.background = 'transparent';

    var sc = computeScales(valid);
    var pw = sc.pw, ph = sc.ph;

    var qRects = [
      { name: 'Improving', rx: sc.sx(sc.xLo), ry: sc.sy(sc.yHi), rw: sc.sx(100) - sc.sx(sc.xLo), rh: sc.sy(100) - sc.sy(sc.yHi), fill: QUAD_COLORS.Improving },
      { name: 'Leading', rx: sc.sx(100), ry: sc.sy(sc.yHi), rw: sc.sx(sc.xHi) - sc.sx(100), rh: sc.sy(100) - sc.sy(sc.yHi), fill: QUAD_COLORS.Leading },
      { name: 'Lagging', rx: sc.sx(sc.xLo), ry: sc.sy(100), rw: sc.sx(100) - sc.sx(sc.xLo), rh: sc.sy(sc.yLo) - sc.sy(100), fill: QUAD_COLORS.Lagging },
      { name: 'Weakening', rx: sc.sx(100), ry: sc.sy(100), rw: sc.sx(sc.xHi) - sc.sx(100), rh: sc.sy(sc.yLo) - sc.sy(100), fill: QUAD_COLORS.Weakening }
    ];
    qRects.forEach(function (q) {
      svg.appendChild(svgEl('rect', {
        x: q.rx, y: q.ry, width: q.rw, height: q.rh,
        fill: q.fill, 'fill-opacity': 0.06, stroke: 'none'
      }));
      var lx = q.name === 'Improving' || q.name === 'Leading' ? q.rx + 10 : q.rx + 10;
      var ly = q.name === 'Improving' || q.name === 'Leading' ? q.ry + 18 : q.ry + q.rh - 10;
      var lbl = svgEl('text', {
        x: lx, y: ly, fill: q.fill, 'fill-opacity': 0.55,
        'font-size': 13, 'font-weight': 800, 'letter-spacing': 1
      });
      lbl.textContent = q.name.toUpperCase();
      svg.appendChild(lbl);
    });

    [80, 90, 100, 110, 120].forEach(function (tick) {
      if (tick < sc.xLo || tick > sc.xHi) return;
      var gx = sc.sx(tick);
      svg.appendChild(svgEl('line', {
        x1: gx, y1: sc.sy(sc.yLo), x2: gx, y2: sc.sy(sc.yHi),
        stroke: 'rgba(148,163,184,0.12)', 'stroke-width': 1
      }));
      var xt = svgEl('text', { x: gx, y: sc.sy(sc.yLo) + 20, fill: '#64748b', 'font-size': 11, 'text-anchor': 'middle' });
      xt.textContent = String(tick);
      svg.appendChild(xt);
    });
    [80, 90, 100, 110, 120].forEach(function (tick) {
      if (tick < sc.yLo || tick > sc.yHi) return;
      var gy = sc.sy(tick);
      svg.appendChild(svgEl('line', {
        x1: sc.sx(sc.xLo), y1: gy, x2: sc.sx(sc.xHi), y2: gy,
        stroke: 'rgba(148,163,184,0.12)', 'stroke-width': 1
      }));
      var yt = svgEl('text', { x: sc.sx(sc.xLo) - 8, y: gy + 4, fill: '#64748b', 'font-size': 11, 'text-anchor': 'end' });
      yt.textContent = String(tick);
      svg.appendChild(yt);
    });

    svg.appendChild(svgEl('line', {
      x1: sc.sx(100), y1: sc.sy(sc.yLo), x2: sc.sx(100), y2: sc.sy(sc.yHi),
      stroke: 'rgba(226,232,240,0.45)', 'stroke-width': 1.4, 'stroke-dasharray': '6 5'
    }));
    svg.appendChild(svgEl('line', {
      x1: sc.sx(sc.xLo), y1: sc.sy(100), x2: sc.sx(sc.xHi), y2: sc.sy(100),
      stroke: 'rgba(226,232,240,0.45)', 'stroke-width': 1.4, 'stroke-dasharray': '6 5'
    }));

    svg.appendChild(svgEl('rect', {
      x: sc.sx(sc.xLo), y: sc.sy(sc.yHi), width: pw, height: ph,
      fill: 'none', stroke: 'rgba(148,163,184,0.3)', 'stroke-width': 1
    }));

    var axX = svgEl('text', {
      x: sc.sx(sc.xLo) + pw / 2, y: SVG_H - 10,
      fill: '#94a3b8', 'font-size': 13, 'font-weight': 700, 'text-anchor': 'middle'
    });
    axX.textContent = 'RS-Ratio →';
    svg.appendChild(axX);
    var axY = svgEl('text', {
      x: 18, y: sc.sy(sc.yHi) + ph / 2,
      fill: '#94a3b8', 'font-size': 13, 'font-weight': 700,
      'text-anchor': 'middle',
      transform: 'rotate(-90 18 ' + (sc.sy(sc.yHi) + ph / 2) + ')'
    });
    axY.textContent = 'RS-Momentum ↑';
    svg.appendChild(axY);

    valid.forEach(function (pt) {
      var x = Number(pt.rs_ratio), y = Number(pt.rs_momentum);
      var quad = pt.quadrant || quadrantOf(x, y);
      var color = QUAD_COLORS[quad] || '#94a3b8';
      var g = svgEl('g', { style: 'cursor:pointer;' });

      var tail = Array.isArray(pt.tail) ? pt.tail.filter(function (t) {
        return t && isFinite(Number(t.x)) && isFinite(Number(t.y));
      }) : [];
      var n = tail.length;
      for (var j = 1; j < n; j++) {
        var op = n <= 2 ? 0.8 : 0.15 + 0.65 * (j / (n - 1));
        g.appendChild(svgEl('line', {
          x1: sc.sx(Number(tail[j - 1].x)), y1: sc.sy(Number(tail[j - 1].y)),
          x2: sc.sx(Number(tail[j].x)), y2: sc.sy(Number(tail[j].y)),
          stroke: color, 'stroke-width': 2, 'stroke-opacity': op.toFixed(3),
          'stroke-linecap': 'round'
        }));
      }

      var cx = sc.sx(x), cy = sc.sy(y);
      var prev = n >= 2 ? tail[n - 2] : null;
      var ang = 0;
      if (prev) {
        var dxp = cx - sc.sx(Number(prev.x));
        var dyp = cy - sc.sy(Number(prev.y));
        var len = Math.sqrt(dxp * dxp + dyp * dyp);
        if (len > 0.5) ang = Math.atan2(dyp, dxp);
      }
      var aLen = 11, aWid = 5.5;
      function rot(a, r) {
        return (cx - Math.cos(ang + a) * r).toFixed(2) + ',' + (cy - Math.sin(ang + a) * r).toFixed(2);
      }
      g.appendChild(svgEl('polygon', {
        points: cx.toFixed(2) + ',' + cy.toFixed(2) + ' ' + rot(Math.PI - 0.42, aLen) + ' ' + rot(Math.PI + 0.42, aLen),
        fill: color, 'fill-opacity': 0.9
      }));

      g.appendChild(svgEl('circle', {
        cx: cx, cy: cy, r: 14,
        fill: color, 'fill-opacity': 0.16, stroke: 'none'
      }));
      var dot = svgEl('circle', {
        cx: cx, cy: cy, r: 8.5,
        fill: color, 'fill-opacity': 0.92,
        stroke: '#0b1220', 'stroke-width': 1.6
      });
      dot.setAttribute('data-sector-code', pt.sector_code || '');
      g.appendChild(dot);

      var lab = svgEl('text', {
        x: cx, y: cy - 17,
        fill: '#e2e8f0', 'font-size': 12, 'font-weight': 800,
        'text-anchor': 'middle',
        'paint-order': 'stroke', stroke: '#0b1220', 'stroke-width': 3
      });
      lab.textContent = pt.sector_code || '?';
      g.appendChild(lab);

      g.addEventListener('mousemove', function (evt) { showTooltip(evt, pt); });
      g.addEventListener('mouseleave', hideTooltip);
      g.addEventListener('click', function () {
        if (window.AppBridge && typeof window.AppBridge.selectSector === 'function' && pt.sector_code) {
          window.AppBridge.selectSector(pt.sector_code);
        }
      });

      svg.appendChild(g);
    });

    var first = container.firstChild;
    if (first) container.insertBefore(svg, first);
    else container.appendChild(svg);
  }

  function render() {
    fetchAndRender();
  }

  function refresh() {
    fetchAndRender();
  }

  function init() {
    if (state.inited) return;
    var bench = $('rrgBenchmark'), itv = $('rrgInterval'), met = $('rrgMethod'),
        tail = $('rrgTail'), btn = $('rrgRefresh'), tailVal = $('rrgTailVal');
    if (!bench || !itv || !met || !tail || !btn) return;
    ['change'].forEach(function (ev) {
      bench.addEventListener(ev, function () { fetchAndRender(); });
      itv.addEventListener(ev, function () { fetchAndRender(); });
      met.addEventListener(ev, function () { fetchAndRender(); });
    });
    tail.addEventListener('input', function () {
      if (tailVal) tailVal.textContent = tail.value;
    });
    tail.addEventListener('change', function () { fetchAndRender(); });
    btn.addEventListener('click', function () { fetchAndRender(); });
    state.inited = true;
  }

  window.SectorRotation = {
    init: init,
    render: render,
    refresh: refresh,
    isVisible: isVisible
  };
})();
