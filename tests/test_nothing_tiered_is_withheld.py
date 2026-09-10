"""A number worth tiering is a number worth publishing.

This audit has now found the same defect eighteen times, in the same
place, wearing a different name each time: a value is fetched or computed,
correctly tiered, and connected to nothing. da. tangible_equity.
current_assets. current_liabilities. retained_earnings. landbank_fq.
bank_loans_fq. gross_ppe_fq. delta_working_capital. dividend_per_share
nearly made it nineteen and was caught only by measuring the record end to
end, because every unit test one layer up was green throughout.

Each was found by a person noticing. This test is the attempt to stop
needing that. The rule it enforces is narrow and mechanical:

    if reconstruct_financial_triangles() thought a figure was worth
    assigning a provenance tier, then either that figure reaches the
    record, or its name appears in KEPT_INTERNAL below with a reason.

The allow-list is the point. Adding a name to it is a decision somebody
made and can be argued with in review; leaving a tiered value stranded is
a thing nobody decided and nobody sees.
"""

import pytest

from services.unified_data_service import normalize_stock_data
from tests.test_altman_inputs_are_measured import payload

#: Names that carry a tier and correctly never appear at the top level,
#: each with the reason it is not a leak.
KEPT_INTERNAL = {
    # Internal witness names. The figure DOES reach the record, under the
    # name the record spells it with; the witness is what the tier hangs on.
    "shares": "published as shares_out",
    "total_equity": "published as equity",
    "total_debt": "published as debt",
    # Denominated in billions for the screener UI. The engine reads the raw
    # figure as market_cap_vnd; a third spelling in a third unit is how a
    # unit error gets made.
    "mcap": "billions; published as market_cap and market_cap_vnd",
}


@pytest.fixture(scope="module")
def record():
    """A record built from a payload that answers as much as possible."""
    return normalize_stock_data(
        "TEST",
        tv_data=payload(),
        vndirect_data={
            "landbank_fq": 8e12,
            "bank_loans_fq": 400e12,
            "gross_ppe_fq": 25e12,
            "delta_working_capital": 3e12,
        },
    )


def test_every_tiered_figure_is_readable_or_declared(record):
    stranded = sorted(
        name for name in record["field_provenance"]
        if name not in KEPT_INTERNAL and record.get(name) is None
    )
    assert not stranded, (
        "these figures were computed and given a provenance tier, then "
        "dropped before any consumer could read them: "
        f"{stranded}. Publish them, or add each to KEPT_INTERNAL with the "
        "reason it belongs there."
    )


def test_the_allow_list_stays_honest(record):
    """A name that no longer needs an exemption must not keep one."""
    unnecessary = sorted(
        name for name in KEPT_INTERNAL
        if name not in record["field_provenance"]
    )
    assert not unnecessary, (
        f"{unnecessary} no longer carry a tier, so exempting them hides "
        f"nothing and only makes the list harder to trust"
    )


@pytest.mark.parametrize("name,reason", sorted(KEPT_INTERNAL.items()))
def test_each_exemption_states_a_reason(name, reason):
    assert reason.strip(), name


# ---------------------------------------------------------------------
# The other half of the same defect.
#
# The guard above sees a figure that was TIERED and then stranded. It is
# blind to the earlier failure: a column requested from a vendor and read
# by no line of code, which never gets a tier and so never becomes
# visible to it. retained_earnings_fq sat in TV_COLUMNS unread for the
# whole life of this service while Altman Z'' asserted that retained
# earnings are 20% of book equity for every company in Vietnam, and the
# guard above would not have noticed.
#
# Asking a vendor for a column costs bandwidth on every sync of 1,523
# symbols. Asking and not reading costs that plus a wrong answer
# downstream, delivered confidently.
# ---------------------------------------------------------------------

import pathlib
import re

import services.unified_data_service as U

REPO_ROOT = pathlib.Path(U.__file__).resolve().parent.parent

#: Columns requested for a reason other than being read by name here.
UNREAD_ON_PURPOSE: dict = {}


def _source_text() -> str:
    """Every line of the service and engine, minus the request lists."""
    parts = []
    for path in (REPO_ROOT / "services").glob("*.py"):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _requested_columns() -> set:
    columns = set(getattr(U, "TV_COLUMNS", ()) or ())
    columns |= set(getattr(U, "TRADINGVIEW_SUPPLEMENTARY_COLUMNS", ()) or ())
    return {c for c in columns if isinstance(c, str)}


def test_every_column_this_service_asks_for_is_read_by_something():
    text = _source_text()
    unread = []
    for column in sorted(_requested_columns()):
        if column in UNREAD_ON_PURPOSE:
            continue
        # One occurrence is the request list itself; a column that is
        # actually used appears at least twice.
        if len(re.findall(re.escape(column), text)) < 2:
            unread.append(column)
    assert not unread, (
        "these columns are requested from the vendor on every sync and "
        f"read by no line of code: {unread}. Either read them, or stop "
        "paying for them on 1,523 symbols."
    )
