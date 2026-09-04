/**
 * TMPerf - treemap performance helpers: timing marks, rAF batching, offscreen culling.
 */
(function () {
  'use strict';

  var debugEnabled = false;
  try {
    debugEnabled = /[?&]tmdebug=1/.test(window.location.search);
  } catch (e) { /* noop */ }

  var marks = {};
  var pendingFn = null;
  var rafId = null;
  var observer = null;

  function record(name, duration) {
    var entry = marks[name];
    if (!entry) {
      entry = marks[name] = { last: 0, total: 0, avg: 0, count: 0 };
    }
    entry.last = duration;
    entry.total += duration;
    entry.count += 1;
    entry.avg = entry.total / entry.count;
    if (debugEnabled) {
      console.debug('[TMPerf]', name, duration.toFixed(2) + 'ms', 'avg=' + entry.avg.toFixed(2) + 'ms', 'n=' + entry.count);
    }
  }

  function measure(name, fn) {
    var start = (window.performance && window.performance.now) ? performance.now() : Date.now();
    try {
      return fn();
    } finally {
      var end = (window.performance && window.performance.now) ? performance.now() : Date.now();
      record(name, Math.max(0, end - start));
    }
  }

  function batch(fn) {
    if (typeof fn !== 'function') {
      return function cancelBatchNoop() {};
    }
    if (pendingFn) {
      var previous = pendingFn;
      pendingFn = function () {
        previous();
        fn();
      };
    } else {
      pendingFn = fn;
      rafId = requestAnimationFrame(function () {
        var run = pendingFn;
        pendingFn = null;
        rafId = null;
        if (run) measure('batch', run);
      });
    }
    return function cancelBatch() {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      pendingFn = null;
    };
  }

  function cull(containerEl, tileSelector) {
    disconnectObserver();
    if (!containerEl || typeof IntersectionObserver === 'undefined') {
      return;
    }
    observer = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        var el = entries[i].target;
        if (entries[i].isIntersecting) {
          el.classList.remove('tm-cull');
        } else {
          el.classList.add('tm-cull');
        }
      }
    }, { threshold: 0, rootMargin: '200px' });
    var targets = containerEl.querySelectorAll(tileSelector || '.treemap-sector-card');
    for (var j = 0; j < targets.length; j++) {
      observer.observe(targets[j]);
    }
  }

  function disconnectObserver() {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
  }

  function disconnect() {
    disconnectObserver();
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    pendingFn = null;
  }

  window.TMPerf = {
    measure: measure,
    batch: batch,
    cull: cull,
    disconnect: disconnect,
    marks: marks
  };
})();
