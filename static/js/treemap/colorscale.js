/**
 * TMColor - TradingView-style continuous color scale for VN market treemap
 */
(function () {
  'use strict';

  var DARK = '#090d16';
  var LIGHT = '#ffffff';

  var STOPS = [
    { t: -3.0, c: [185, 28, 28] },
    { t: -2.0, c: [220, 38, 38] },
    { t: -1.0, c: [239, 68, 68] },
    { t: -0.35, c: [248, 113, 113] },
    { t: 0.0, c: [148, 163, 184] },
    { t: 0.35, c: [110, 231, 183] },
    { t: 1.0, c: [52, 211, 153] },
    { t: 2.0, c: [16, 185, 129] },
    { t: 3.0, c: [5, 150, 105] }
  ];

  function hex(n) {
    var s = Math.max(0, Math.min(255, Math.round(n))).toString(16);
    return s.length === 1 ? '0' + s : s;
  }

  function toHex(rgb) {
    return '#' + hex(rgb[0]) + hex(rgb[1]) + hex(rgb[2]);
  }

  function lerp(a, b, k) {
    return a + (b - a) * k;
  }

  function mix(c1, c2, k) {
    return [
      lerp(c1[0], c2[0], k),
      lerp(c1[1], c2[1], k),
      lerp(c1[2], c2[2], k)
    ];
  }

  function gradient(t) {
    if (t <= STOPS[0].t) return STOPS[0].c;
    if (t >= STOPS[STOPS.length - 1].t) {
      return STOPS[STOPS.length - 1].c;
    }
    for (var i = 0; i < STOPS.length - 1; i++) {
      var a = STOPS[i];
      var b = STOPS[i + 1];
      if (t >= a.t && t <= b.t) {
        var k = (t - a.t) / (b.t - a.t);
        var eased = k * k * (3 - 2 * k);
        return mix(a.c, b.c, eased);
      }
    }
    return STOPS[STOPS.length - 1].c;
  }

  function luminance(rgb) {
    function ch(v) {
      v = v / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2]);
  }

  function contrastPick(rgb) {
    return luminance(rgb) > 0.30 ? DARK : LIGHT;
  }

  window.TMColor = {
    scale: function (changePct) {
      var v = Number(changePct);
      if (!isFinite(v)) v = 0;
      if (v >= 6.9) {
        return { bg: '#c084fc', fg: DARK };
      }
      if (v <= -6.9) {
        return { bg: '#22d3ee', fg: DARK };
      }
      if (v === 0) {
        return { bg: '#94a3b8', fg: DARK };
      }
      var rgb;
      if (v < -3) {
        rgb = [185, 28, 28];
      } else if (v > 3) {
        rgb = [4, 120, 87];
      } else {
        rgb = gradient(v);
      }
      return { bg: toHex(rgb), fg: contrastPick(rgb) };
    },

    legendHTML: function () {
      var grad =
        'linear-gradient(to right, #b91c1c, #dc2626, #ef4444, #f87171, #94a3b8, #6ee7b7, #34d399, #10b981, #059669)';
      var tc = this.scale(0).bg;
      return (
        '<div class="tm-colorscale">' +
        '<span class="legend-item tm-scale-label">-3%</span>' +
        '<div class="tm-scale-bar" style="background: ' + grad + '; position: relative;">' +
        '<span class="tm-scale-mid" style="position: absolute; left: 50%; top: 100%; transform: translateX(-50%); font-size: 10px;">0</span>' +
        '</div>' +
        '<span class="legend-item tm-scale-label">+3%</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: #047857;"></span> &gt; +3%</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: #10b981;"></span> +0.1% ~ +3%</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: #c084fc;"></span> Trần</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: #22d3ee;"></span> Sàn</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: #ef4444;"></span> -0.1% ~ -3%</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: #b91c1c;"></span> &lt; -3%</span>' +
        '<span class="legend-item"><span class="legend-box" style="background: ' + tc + ';"></span> TC</span>' +
        '</div>'
      );
    }
  };
})();
