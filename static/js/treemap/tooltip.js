/**
 * TMTooltip - singleton treemap tooltip (cursor-following, viewport-aware).
 * API: TMTooltip.attach(containerEl) | show(htmlOrNode, x, y) | hide() | el
 */
(function () {
  'use strict';

  var OFFSET = 14;
  var el = null;
  var visible = false;
  var lastPos = { x: 0, y: 0 };
  var anchorRect = null;
  var touchTimer = null;
  var attachedRoots = typeof WeakSet === 'function' ? new WeakSet() : [];

  function ensureEl() {
    if (el && el.isConnected) return el;
    el = document.createElement('div');
    el.className = 'tm-tooltip treemap-tooltip';
    el.setAttribute('role', 'tooltip');
    var s = el.style;
    s.position = 'fixed';
    s.left = '0px';
    s.top = '0px';
    s.maxWidth = '280px';
    s.padding = '8px 10px';
    s.background = 'rgba(13,17,23,.95)';
    s.border = '1px solid rgba(148,163,184,.25)';
    s.borderRadius = '6px';
    s.boxShadow = '0 8px 24px rgba(0,0,0,.5)';
    s.color = '#e2e8f0';
    s.font = "600 12px/1.45 'Inter', system-ui, -apple-system, sans-serif";
    s.fontFamily = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";
    s.whiteSpace = 'pre-line';
    s.pointerEvents = 'none';
    s.zIndex = '2147483000';
    s.opacity = '0';
    s.visibility = 'hidden';
    s.transform = 'translateZ(0)';
    s.willChange = 'transform';
    document.body.appendChild(el);
    return el;
  }

  function setContent(content) {
    ensureEl();
    while (el.firstChild) el.removeChild(el.firstChild);
    if (content == null) return;
    if (typeof content === 'string') {
      el.innerHTML = content;
    } else if (content.nodeType === 1 || content.nodeType === 11 || content.nodeType === 3) {
      el.appendChild(content.nodeType === 1 && content.tagName === 'TEMPLATE'
        ? content.content.cloneNode(true)
        : (content.nodeType === 1 ? content : document.createTextNode(String(content.nodeValue))));
    } else {
      el.textContent = String(content);
    }
  }

  function position(x, y) {
    ensureEl();
    var w = el.offsetWidth;
    var h = el.offsetHeight;
    var vw = window.innerWidth || document.documentElement.clientWidth;
    var vh = window.innerHeight || document.documentElement.clientHeight;
    var left = x + OFFSET;
    var top = y + OFFSET;

    if (left + w > vw - 4) {
      left = (anchorRect ? anchorRect.left : x) - OFFSET - w;
      if (left < 4) left = Math.max(4, vw - w - 4);
    }
    if (top + h > vh - 4) {
      top = (anchorRect ? anchorRect.top : y) - OFFSET - h;
      if (top < 4) top = Math.max(4, vh - h - 4);
    }
    left = Math.min(Math.max(4, left), Math.max(4, vw - w - 4));
    top = Math.min(Math.max(4, top), Math.max(4, vh - h - 4));

    el.style.left = Math.round(left) + 'px';
    el.style.top = Math.round(top) + 'px';
  }

  function reveal(x, y) {
    ensureEl();
    el.style.opacity = '1';
    el.style.visibility = 'visible';
    visible = true;
    if (typeof x === 'number' && typeof y === 'number') {
      lastPos.x = x;
      lastPos.y = y;
      position(x, y);
    }
  }

  function clearTouchTimer() {
    if (touchTimer != null) {
      clearTimeout(touchTimer);
      touchTimer = null;
    }
  }

  function tileFromEvent(e) {
    var t = e.target;
    while (t && t !== document.body) {
      if (t.getAttribute && (t.hasAttribute('data-symbol') || t.classList.contains('treemap-tile'))) {
        return t;
      }
      t = t.parentNode;
    }
    return null;
  }

  function buildTileHtml(tile) {
    var sym = tile.getAttribute('data-symbol') ||
      ((tile.querySelector('.tile-symbol') || {}).textContent || '').trim();
    var name = tile.getAttribute('data-name') || '';
    var priceEl = tile.querySelector('.tile-price');
    var pctEl = tile.querySelector('.tile-pct');
    var exEl = tile.closest('[data-exchange]');
    var parts = ['<b style="font-size:13px">' + escapeHtml(sym || '') + '</b>'];
    if (name) parts.push('<span style="opacity:.75">' + escapeHtml(name) + '</span>');
    if (priceEl) parts.push('Giá: ' + escapeHtml(priceEl.textContent));
    if (pctEl) parts.push(escapeHtml(pctEl.textContent));
    if (exEl) parts.push('<span style="opacity:.6">Sàn: ' + escapeHtml(exEl.getAttribute('data-exchange')) + '</span>');
    return parts.join('<br>');
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function onPointerMove(e) {
    if (!visible) return;
    lastPos.x = e.clientX;
    lastPos.y = e.clientY;
    position(e.clientX, e.clientY);
  }

  function onMouseOver(e) {
    var tile = tileFromEvent(e);
    if (!tile) return;
    var html = tile.getAttribute('data-tip') || buildTileHtml(tile);
    anchorRect = null;
    setContent(html);
    reveal(e.clientX, e.clientY);
  }

  function onMouseOut(e) {
    var to = e.relatedTarget;
    if (to && tileFromEvent({ target: to })) return;
    hide();
  }

  function onFocusIn(e) {
    var tile = e.target;
    if (!tile || !tile.getAttribute || !tile.hasAttribute('data-symbol')) return;
    var r = tile.getBoundingClientRect();
    anchorRect = r;
    var html = tile.getAttribute('data-tip') || buildTileHtml(tile);
    setContent(html);
    reveal(r.left + r.width / 2, r.bottom);
    position(r.right, r.bottom + OFFSET);
  }

  function onFocusOut() {
    anchorRect = null;
    hide();
  }

  function onTouchStart(e) {
    var tile = tileFromEvent(e);
    if (!tile) {
      hide();
      return;
    }
    var t = e.touches[0];
    anchorRect = null;
    setContent(tile.getAttribute('data-tip') || buildTileHtml(tile));
    reveal(t.clientX, t.clientY);
    clearTouchTimer();
    touchTimer = setTimeout(hide, 2500);
  }

  function onGlobalScroll() {
    hide();
  }

  function onWindowBlur() {
    hide();
  }

  function attach(containerEl) {
    ensureEl();
    var root = containerEl || document;
    if (typeof WeakSet === 'function') {
      if (attachedRoots.has(root)) return;
      attachedRoots.add(root);
    } else {
      if (attachedRoots.indexOf(root) !== -1) return;
      attachedRoots.push(root);
    }
    root.addEventListener('mouseover', onMouseOver, true);
    root.addEventListener('mouseout', onMouseOut, true);
    root.addEventListener('focusin', onFocusIn, true);
    root.addEventListener('focusout', onFocusOut, true);
    root.addEventListener('touchstart', onTouchStart, true);
    root.addEventListener('touchend', hide, true);
  }

  function show(htmlOrNode, clientX, clientY) {
    anchorRect = null;
    setContent(htmlOrNode);
    var x = typeof clientX === 'number' ? clientX : lastPos.x + OFFSET;
    var y = typeof clientY === 'number' ? clientY : lastPos.y + OFFSET;
    reveal(x, y);
  }

  function hide() {
    clearTouchTimer();
    if (!el) return;
    visible = false;
    el.style.opacity = '0';
    el.style.visibility = 'hidden';
  }

  ensureEl();

  document.addEventListener('mousemove', onPointerMove, true);
  window.addEventListener('scroll', onGlobalScroll, true);
  window.addEventListener('blur', onWindowBlur);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') hide();
  });

  window.TMTooltip = {
    attach: attach,
    show: show,
    hide: hide,
    el: el
  };
})();
