"""The browser reads element ids that the page must actually define.

`document.getElementById(...)` returning null is silent: every render path in
app.js guards with `if (!el) return`, so a whole panel can be wired, shipped
and dead without a single console error. That is exactly what happened to the
fair-value backtest — `fvBtWinnerTitle`, `fvBtYearlyTableBody` and thirty
others were written to by app.js and defined nowhere in index.html, so the
entire result-render path wrote into nothing.

These tests make that failure loud: an id read by app.js must exist in
index.html, be created by app.js itself, or be listed below with a reason.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "js" / "app.js"
INDEX_HTML = ROOT / "static" / "index.html"

# Ids read by app.js that index.html does not define, each with the reason it
# is acceptable. Anything not listed here must exist in the page.
KNOWN_ABSENT = {
    # Legacy alternates in `a || b || c` lookup chains: the first id in each
    # chain is present, so these never resolve and never need to.
    "boardFilterInput": "fallback alternate for boardQuickFilter",
    "quantKeyword": "fallback alternate for quantSearchInput",
    "btnBacktestThisScreen": "fallback alternate for btnBacktestFromQuant",
    "btnOpenBacktestFromQuant": "fallback alternate for btnBacktestFromQuant",
    # Genuinely dead path, documented rather than hidden: fetchCompanyHealth /
    # renderCompanyHealth have no caller and no container. Either wire them to
    # the stock-detail panel or delete them; do not silently grow the list.
    "healthOverviewContainer": "dead render path - fetchCompanyHealth has no caller",
}

_GET_BY_ID = re.compile(r"getElementById\(\s*['\"]([A-Za-z0-9_-]+)['\"]\s*\)")
_ID_ATTR = re.compile(r"""id=["']([A-Za-z0-9_-]+)["']""")


@pytest.fixture(scope="module")
def app_js() -> str:
    return APP_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _ids_read(js: str) -> set[str]:
    return set(_GET_BY_ID.findall(js))


def _ids_defined(html: str) -> set[str]:
    return set(_ID_ATTR.findall(html))


def test_every_id_read_by_app_js_exists_somewhere(app_js, index_html):
    """No new silently-dead element reads."""
    read = _ids_read(app_js)
    # Ids app.js injects itself, via template literals or createElement.
    created = set(_ID_ATTR.findall(app_js)) | set(
        re.findall(r"\.id\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", app_js)
    )
    missing = sorted(read - _ids_defined(index_html) - created - set(KNOWN_ABSENT))
    assert not missing, (
        "app.js reads element ids that index.html never defines, so those "
        f"render paths write into nothing: {missing}. Add the markup, or add "
        "the id to KNOWN_ABSENT with the reason it is acceptable."
    )


def test_known_absent_list_does_not_go_stale(index_html):
    """An id that has since been added must leave the exception list."""
    defined = _ids_defined(index_html)
    stale = sorted(i for i in KNOWN_ABSENT if i in defined)
    assert not stale, f"These ids now exist and should leave KNOWN_ABSENT: {stale}"


# --------------------------------------------------------------------------
# The fair-value backtest panel specifically.
# --------------------------------------------------------------------------

FV_RESULT_IDS = (
    "fvBtWinnerTitle",
    "fvBtWinnerDesc",
    "fvBtProvenanceBanner",
    "fvBtMetricCagr",
    "fvBtMetricTotal",
    "fvBtMetricMaxDd",
    "fvBtMetricSharpe",
    "fvBtMetricWinRate",
    "fvBtEquityCanvas",
    "fvBtYearlyTableBody",
    "fvBtTournamentTableBody",
    "fvBtTradesTableBody",
    "fvBtTradesCountBadge",
)

FV_CONTROL_IDS = (
    "fvBtModeSelect",
    "fvBtScreenerSelect",
    "fvBtValModelSelect",
    "fvBtFundamentalsModeSelect",
    "fvBtCompositeModeSelect",
    "fvBtOmnibusMetricSelect",
    "fvBtOmnibusMetricGroup",
    "fvBtHorizonSelect",
    "fvBtMosSelect",
    "fvBtExitSelect",
    "fvBtExchangeSelect",
    "fvBtCadenceSelect",
    "fvBtTopKSelect",
    "fvBtFillModeSelect",
    "fvBtDynamicMosToggle",
    "fvBtSurvivalToggle",
    "fvBtTsmomToggle",
    "fvBtForensicToggle",
    "fvBtZSafeToggle",
    "fvBtRkvToggle",
    "btnRunFairValueBacktest",
)


@pytest.mark.parametrize("element_id", FV_RESULT_IDS + FV_CONTROL_IDS)
def test_fair_value_backtest_element_exists(index_html, element_id):
    assert f'id="{element_id}"' in index_html, (
        f"{element_id} is read by app.js but not defined in index.html"
    )


def test_fair_value_panel_has_its_own_section(index_html):
    assert 'id="btFairValueSection"' in index_html
    assert 'id="btnSubtabBtFairValue"' in index_html
    assert "app.switchBacktestSubtab('fair_value')" in index_html


def test_subtab_switcher_gives_fair_value_its_own_pane(app_js):
    """'fair_value' must no longer alias to the institutional section."""
    assert "btFairValueSection" in app_js
    assert "subtab === 'institutional' || subtab === 'fair_value'" not in app_js


def test_run_sends_the_fundamentals_mode_the_user_picked(app_js):
    """The mode selector must reach the API, not be decoration."""
    assert "fvBtFundamentalsModeSelect" in app_js
    assert "fundamentals_mode=${encodeURIComponent(fundamentalsMode)}" in app_js


def test_fundamentals_mode_options_match_the_api(index_html):
    for value in ("point_in_time", "snapshot_projected"):
        assert f'value="{value}"' in index_html


def test_backtest_window_is_not_a_hardcoded_year(app_js):
    """A hardcoded end year goes stale and stays wrong for a whole year."""
    assert "const endYear = new Date().getFullYear();" in app_js
    code = "\n".join(
        line.split("//")[0] for line in app_js.splitlines()
    )
    assert "endYear = 2026" not in code
    assert "EARLIEST_MARKET_DATA_YEAR" in code


def test_trade_log_header_matches_the_rendered_column_count(index_html, app_js):
    """A colspan/……/th mismatch silently shears the table."""
    section = index_html.split('id="btFairValueSection"', 1)[1]
    body = section.split('id="fvBtTradesTableBody"', 1)[0]
    header = body.rsplit("<thead>", 1)[1]
    assert header.count("<th") == 11
    assert 'colspan="11"' in app_js
