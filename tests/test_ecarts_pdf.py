"""Écarts entre le classeur et le PDF de référence (docs/AUDIT_SOURCES.md, §4).

Règle retenue par défaut : méthode du classeur (somme des lignes arrondies).
La méthode du PDF (taux cumulé arrondi une fois) est disponible comme paramètre explicite.
"""

from __future__ import annotations

from decimal import Decimal as D

from src.calculations.engine import compute_payslip
from src.models.parameters import METHODE_SOMME_LIGNES, METHODE_TAUX_CUMULE


def test_default_method_is_workbook(params):
    assert params.methode_totaux == METHODE_SOMME_LIGNES


def test_e1_e2_workbook_sums_rounded_lines(ref_input, params):
    r = compute_payslip(ref_input, params, 0)
    assert r.total_cotisations_salariales == r.cnss_salarie + r.amo_salarie == D("366.43")
    assert r.total_cotisations_patronales == (r.cnss_patronal + r.amo_patronal + r.participation_amo
                                              + r.formation_pro + r.allocations_familiales) == D("1146.57")


def test_e1_e2_pdf_rounds_cumulated_rate_once(ref_input, params):
    r = compute_payslip(ref_input, params.with_changes(methode_totaux=METHODE_TAUX_CUMULE), 0)
    # 5 436,51 × 6,74 % = 366,420774 ; 5 436,51 × 21,09 % = 1 146,559959
    assert r.total_cotisations_salariales == D("366.42")
    assert r.total_cotisations_patronales == D("1146.56")
    # Les lignes affichées restent identiques, et ne totalisent plus le total (incohérence du PDF).
    assert (r.cnss_salarie, r.amo_salarie) == (D("243.56"), D("122.87"))
    assert r.cnss_salarie + r.amo_salarie != r.total_cotisations_salariales


def test_e3_e4_e5_consequences_in_pdf_mode(ref_input, params):
    r = compute_payslip(ref_input, params.with_changes(methode_totaux=METHODE_TAUX_CUMULE), 0)
    assert r.net_imposable == D("3167.31")       # E3 : valeur du PDF
    assert r.arrondi == D("-0.09")               # E4 : arrondi 0,09 en retenue
    assert r.net_a_payer == D("7000")            # E5 : net identique
    assert r.cout_employeur == D("8513.07")      # E6


def test_e3_e4_workbook_mode(ref_input, params):
    r = compute_payslip(ref_input, params, 0)
    assert (r.net_imposable, r.arrondi, r.net_a_payer) == (D("3167.30"), D("-0.08"), D("7000"))


def test_e8_daily_rate_shown_on_pdf(ref_input, params):
    assert compute_payslip(ref_input, params, 0).taux_journalier == D("209.10")


def test_methods_diverge_with_capped_cnss(params, ref_input):
    """Assiette CNSS plafonnée ≠ assiette AMO : chaque méthode reste déterministe (hypothèse A1)."""
    from dataclasses import replace
    inp = replace(ref_input, salaire_base=D("9876.54"))
    excel = compute_payslip(inp, params, 0)
    pdf = compute_payslip(inp, params.with_changes(methode_totaux=METHODE_TAUX_CUMULE), 0)
    assert excel.assiette_cnss_plafonnee == D("6000")
    assert excel.total_cotisations_salariales == D("268.80") + D("223.21")
    # ROUND(6000 × 4,48 % + 9 876,54 × 2,26 %, 2) = ROUND(268,8 + 223,209804, 2)
    assert pdf.total_cotisations_salariales == D("492.01")
