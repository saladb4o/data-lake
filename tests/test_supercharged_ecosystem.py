"""
=============================================================================
UNIT TESTS FOR SUPERCHARGED FORENSIC ECOSYSTEM & CROSS-OWNERSHIP ENGINE
=============================================================================
Verifies:
  1. Inverted Cross-Ownership Indexing (Both Outbound & Inbound Matrix)
  2. UBO & Family Power Clustering (True Control % vs Free-Float Thật)
  3. Related-Party Capital Funnel & Drain Detector (Capital Drain Ratio)
  4. Integration with get_company_ecosystem API Contract & Graph Data
  5. Robustness & Fallback across diverse stock profiles
"""

import pytest
from typing import Dict, Any

from services.cross_ownership_engine import get_cross_ownership_engine
from services.stock_service import get_company_ecosystem


def test_cross_ownership_engine_inbound_and_outbound():
    """Verifies bidirectional inverted matrix lookup."""
    engine = get_cross_ownership_engine()
    
    # 1. Inbound check: Who owns VHM? (VIC holds 66.66%)
    inbound_vhm = engine.get_inbound_cross_holdings("VHM")
    assert isinstance(inbound_vhm, list)
    assert len(inbound_vhm) > 0
    holders = [h.get("holder_symbol") for h in inbound_vhm]
    assert "VIC" in holders

    # 2. Outbound check: What does VIC hold?
    outbound_vic = engine.get_outbound_cross_holdings("VIC")
    assert isinstance(outbound_vic, list)
    targets = [t.get("target_symbol") for t in outbound_vic]
    assert "VHM" in targets


def test_family_and_ubo_power_clustering():
    """Verifies UBO & family group clustering for major tycoons (e.g. HPG)."""
    engine = get_cross_ownership_engine()
    ubo_hpg = engine.cluster_family_and_ubo_power("HPG")

    assert isinstance(ubo_hpg, dict)
    assert ubo_hpg["symbol"] == "HPG"
    assert "key_person" in ubo_hpg
    assert "personal_pct" in ubo_hpg["key_person"]
    assert ubo_hpg["family_members_count"] >= 1
    assert ubo_hpg["true_control_pct"] >= 25.0
    assert 0.0 < ubo_hpg["true_free_float_pct"] <= 100.0
    assert "concentration_grade" in ubo_hpg
    assert "concentration_color" in ubo_hpg


def test_capital_funnel_and_drain_detection():
    """Verifies related-party capital drain ratio calculation and ranking."""
    engine = get_cross_ownership_engine()
    funnel = engine.analyze_capital_funnel("HPG")

    assert isinstance(funnel, dict)
    assert funnel["symbol"] == "HPG"
    assert "drain_ratio_pct" in funnel
    assert funnel["drain_ratio_pct"] >= 0.0
    assert "risk_level" in funnel
    assert "risk_color" in funnel
    assert "total_assets_billion" in funnel
    assert isinstance(funnel.get("related_transactions"), list)


def test_get_company_ecosystem_supercharged_payload():
    """Verifies that get_company_ecosystem integrates all 4 forensic pillars into API payload."""
    eco = get_company_ecosystem("VHM", depth=2, min_ownership=0.0)

    # Core ecosystem fields
    assert eco["symbol"] == "VHM"
    assert "members" in eco
    assert "graph_data" in eco
    assert "nodes" in eco["graph_data"]
    assert "edges" in eco["graph_data"]

    # Supercharged Forensic Fields
    assert "inbound_cross_holdings" in eco
    assert len(eco["inbound_cross_holdings"]) > 0
    assert "ubo_family_group" in eco
    assert "true_control_pct" in eco["ubo_family_group"]
    assert "true_free_float_pct" in eco["ubo_family_group"]
    assert "capital_funnel" in eco
    assert "drain_ratio_pct" in eco["capital_funnel"]
    assert "forensic_flags" in eco
    assert len(eco["forensic_flags"]) >= 1

    # Graph Data Enrichment check (should include inbound investor node)
    node_types = {n.get("type") for n in eco["graph_data"]["nodes"]}
    assert "inbound_investor" in node_types or "core" in node_types


def test_ecosystem_independent_stock_fallback():
    """Verifies fallback on non-group independent ticker."""
    eco = get_company_ecosystem("VCS", depth=2, min_ownership=0.0)
    assert eco["symbol"] == "VCS"
    assert "inbound_cross_holdings" in eco
    assert "ubo_family_group" in eco
    assert "capital_funnel" in eco
    assert "graph_data" in eco
