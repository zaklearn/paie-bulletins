"""Tests unitaires du moteur, rubrique par rubrique."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from src.calculations import engine
from src.calculations.money import excel_round, to_decimal
from src.models.parameters import IRBracket
from src.models.payroll import MonthlyInput


# --- Arrondis ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, digits, expected", [
    ("2.675", 2, "2.68"), ("2.665", 2, "2.67"), ("-2.675", 2, "-2.68"),
    ("7000.5", 0, "7001"), ("-0.005", 2, "-0.01"), ("7000.08", 0, "7000"), ("7000.49", 0, "7000"),
])
def test_excel_round_half_away_from_zero(value, digits, expected):
    assert excel_round(D(value), digits) == D(expected)


def test_to_decimal_avoids_float_error():
    assert to_decimal(0.1) + to_decimal(0.2) == D("0.3")
    assert to_decimal("1 234,56") == D("1234.56")
    assert to_decimal(None) == D("0")
    with pytest.raises(ValueError):
        to_decimal("abc")


# --- Assiettes et cotisations -----------------------------------------------------------

def test_assiette_excludes_allowances(ref_input):
    inp = replace(ref_input, heures_sup=D("100"), autre_prime=D("50"))
    assert engine.assiette_cotisations(inp) == D("5586.51")


def test_cnss_capped_amo_not_capped(params):
    inp = MonthlyInput(salaire_base=D("10000"), jours_declares=D("26"))
    r = engine.compute_payslip(inp, params, 0)
    assert r.assiette_cnss_plafonnee == D("6000")
    assert r.cnss_salarie == D("268.80")             # 6000 × 4,48 %
    assert r.amo_salarie == D("226.00")              # 10000 × 2,26 %
    assert r.cnss_patronal == D("538.80")            # 6000 × 8,98 %
    assert r.allocations_familiales == D("640.00")   # 10000 × 6,40 % (non plafonné)
    assert r.formation_pro == D("160.00")
    assert r.participation_amo == D("185.00")


def test_cap_boundary_exactly_at_ceiling(params):
    inp = MonthlyInput(salaire_base=D("6000"), jours_declares=D("26"))
    assert engine.compute_payslip(inp, params, 0).cnss_salarie == D("268.80")


# --- Impôt sur le revenu -----------------------------------------------------------------

def test_taxable_shares(params, ref_input):
    inp = replace(ref_input, heures_sup=D("200"), autre_prime=D("100"))
    # base + HS×100 % + panier×0 + transport×0 + représentation×0 + autre×100 %
    assert engine.revenu_brut_imposable(inp, params) == D("5736.51")
    custom = params.with_changes(imposable_prime_panier=D("0.5"))
    assert engine.revenu_brut_imposable(inp, custom) == D("6201.51")


def test_professional_expenses_rate_threshold(params):
    assert engine.taux_frais_professionnels(D("6500"), params) == D("0.35")       # 78 000 ≤ seuil
    assert engine.taux_frais_professionnels(D("6500.01"), params) == D("0.25")


def test_professional_expenses_cap(params):
    # 25 % × 20 000 = 5 000 > 35 000 / 12 = 2 916,666… -> 2 916,67
    assert engine.frais_professionnels(D("20000"), D("0.25"), params) == D("2916.67")


@pytest.mark.parametrize("nb, expected", [(0, "0.00"), (1, "41.67"), (3, "125.00"), (6, "250.00"),
                                          (9, "250.00")])
def test_family_deduction_capped_at_six(params, nb, expected):
    assert engine.deduction_charges_famille(nb, params) == D(expected)


@pytest.mark.parametrize("annual, rate", [
    ("0", "0"), ("40000", "0"), ("40000.005", "0"), ("40000.01", "0.1"), ("60000", "0.1"),
    ("80000.01", "0.3"), ("180000", "0.34"), ("180000.01", "0.38"), ("1000000", "0.38"),
])
def test_bracket_lookup_like_excel_match(params, annual, rate):
    assert engine.tranche_bareme(D(annual), params.bareme).rate == D(rate)


def test_bracket_lookup_rejects_empty_scale():
    with pytest.raises(ValueError):
        engine.tranche_bareme(D("1"), ())


@pytest.mark.parametrize("monthly_ni, expected_annual", [
    ("3000", "0"),                    # 36 000 : tranche 0 %
    ("4000", "800"),                  # 48 000 × 10 % − 4 000
    ("6000", "4400"),                 # 72 000 × 20 % − 10 000
    ("10000", "16800"),               # 120 000 × 34 % − 24 000
    ("20000", "51200"),               # 240 000 × 38 % − 40 000
])
def test_annual_income_tax(params, monthly_ni, expected_annual):
    assert engine.ir_annuel(D(monthly_ni), params) == D(expected_annual)


def test_full_payslip_with_tax_and_dependants(params):
    inp = MonthlyInput(salaire_base=D("12000"), jours_declares=D("26"), heures_sup=D("500"),
                       prime_panier=D("300"), autre_prime=D("250"))
    r = engine.compute_payslip(inp, params, nb_personnes_charge=2)
    assert r.salaire_brut == D("13050")
    assert r.assiette_cotisations == D("12750")
    assert r.cnss_salarie == D("268.80")
    assert r.amo_salarie == D("288.15")
    assert r.total_cotisations_salariales == D("556.95")
    assert r.revenu_brut_imposable == D("12750")
    assert r.taux_frais_pro == D("0.25")
    assert r.frais_professionnels == D("2916.67")
    assert r.net_imposable == D("9276.38")
    assert r.deduction_charges_famille == D("83.33")
    assert r.net_imposable_apres_famille == D("9193.05")
    # 110 316,60 × 34 % − 24 000 = 13 507,644 ; / 12 = 1 125,637 -> 1 125,64
    assert r.ir_annuel == D("13507.6440")
    assert r.ir_mensuel == D("1125.64")
    assert r.net_avant_arrondi == D("11367.41")
    assert r.arrondi == D("-0.41")
    assert r.net_a_payer == D("11367")
    assert r.cout_employeur == r.salaire_brut + r.total_cotisations_patronales


def test_positive_rounding_adjustment(params):
    inp = MonthlyInput(salaire_base=D("3000.60"), jours_declares=D("26"))
    r = engine.compute_payslip(inp, params, 0)
    assert r.net_avant_arrondi - r.net_a_payer == -r.arrondi
    assert r.net_avant_arrondi == D("2798.36")
    assert r.arrondi == D("-0.36")
    inp2 = MonthlyInput(salaire_base=D("3001.20"), jours_declares=D("26"))
    r2 = engine.compute_payslip(inp2, params, 0)
    assert r2.arrondi > 0 and r2.net_a_payer == r2.net_avant_arrondi + r2.arrondi


def test_zero_days_gives_no_daily_rate(params):
    inp = MonthlyInput(salaire_base=D("1000"), jours_declares=D("0"))
    assert engine.compute_payslip(inp, params, 0).taux_journalier == D("0")


def test_net_taxable_never_negative(params):
    inp = MonthlyInput(salaire_base=D("100"), jours_declares=D("1"))
    r = engine.compute_payslip(inp, params, 6)
    assert r.net_imposable >= 0 and r.net_imposable_apres_famille == D("0")


# --- Congés ------------------------------------------------------------------------------

def test_leave_balance():
    inp = MonthlyInput(conges_reliquat=D("3"), conges_acquis=D("1.5"), conges_pris=D("2"))
    assert engine.solde_conges(inp) == D("2.5")


def test_custom_scale_is_used(params):
    flat = params.with_changes(bareme=(IRBracket(D("0"), None, D("0.1"), D("0")),))
    assert engine.ir_annuel(D("1000"), flat) == D("1200.0")
