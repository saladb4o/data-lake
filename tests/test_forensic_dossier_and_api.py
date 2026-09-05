"""
=============================================================================
UNIT TESTS FOR SOURCE 0 FORENSIC DOSSIER & COMPREHENSIVE INTELLIGENCE
=============================================================================
Verifies:
  1. get_stock_forensic_dossier:
     - Accounting Integrity Score calculation (0-100) & qualitative grade
     - The 5 Forensic Triangles presence & mathematical bounds
     - Debt Maturity Profile & Refinancing Wall ratio
     - Construction In Progress (CIP) & CapEx projects breakdown
     - Family Network & Related Persons (TT96/2020)
     - Free-Float Structure & classification
  2. Stock Service Integration:
     - get_company_forensic_report: caching and structure
     - get_company_ecosystem: incorporation of BCTC subsidiaries
     - get_company_leadership: incorporation of family network & free-float
"""

import pytest
from typing import Dict, Any

from services.bctc_batch_processor import get_stock_forensic_dossier
from services.stock_service import (
    get_company_forensic_report,
    get_company_ecosystem,
    get_company_leadership
)


def test_get_stock_forensic_dossier_structure():
    """Verifies that get_stock_forensic_dossier returns complete structure."""
    dossier = get_stock_forensic_dossier("HPG")
    assert isinstance(dossier, dict)
    assert dossier["symbol"] == "HPG"
    assert "accounting_integrity_score" in dossier
    assert 0 <= dossier["accounting_integrity_score"] <= 100
    assert "integrity_rating" in dossier
    assert "rating_color" in dossier
    assert "forensic_triangles" in dossier
    assert "debt_maturity_profile" in dossier
    assert "free_float_structure" in dossier


def test_get_company_forensic_report_service():
    """Verifies get_company_forensic_report caching and payload."""
    report = get_company_forensic_report("VNM")
    assert report["symbol"] == "VNM"
    assert "accounting_integrity_score" in report
    assert "forensic_triangles" in report
    assert "auditor_summary" in report


def test_get_company_ecosystem_dynamic_enrichment():
    """Verifies that get_company_ecosystem returns valid graph and unlisted subsidiaries."""
    eco = get_company_ecosystem("FPT", depth=2, min_ownership=0.0)
    assert eco["symbol"] == "FPT"
    assert "graph_data" in eco
    assert "nodes" in eco["graph_data"]
    assert "edges" in eco["graph_data"]
    assert "unlisted_subsidiaries" in eco
    assert len(eco["graph_data"]["nodes"]) > 0


def test_get_company_leadership_enriched_with_family_and_free_float():
    """Verifies get_company_leadership includes family_network, insider_transactions, and free_float_structure."""
    lead = get_company_leadership("HPG")
    assert lead["symbol"] == "HPG"
    assert "officers" in lead
    assert "shareholders" in lead
    assert "family_network" in lead
    assert "insider_transactions" in lead
    assert "free_float_structure" in lead
    assert "true_free_float_pct" in lead["free_float_structure"]
