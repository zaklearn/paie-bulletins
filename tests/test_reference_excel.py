"""Reproduction des valeurs du classeur de référence (feuille Calcul, septembre 2026).

Ces tests vérifient la fidélité au fichier, pas la conformité légale du calcul.
"""

from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path

import pytest

from src.calculations.cumuls import compute_cumuls
from src.calculations.engine import compute_payslip

EXPECTED_SEPTEMBER = {
    "salaire_base": "5436.51",
    "jours_declares": "26",
    "heures_sup": "0",
    "prime_panier": "930.00",
    "indemnite_transport": "500.00",
    "indemnite_representation": "500.00",
    "autre_prime": "0",
    "salaire_brut": "7366.51",
    "assiette_cotisations": "5436.51",
    "assiette_cnss_plafonnee": "5436.51",
    "cnss_salarie": "243.56",
    "amo_salarie": "122.87",
    "total_cotisations_salariales": "366.43",
    "cnss_patronal": "488.20",
    "amo_patronal": "122.87",
    "participation_amo": "100.58",
    "formation_pro": "86.98",
    "allocations_familiales": "347.94",
    "total_cotisations_patronales": "1146.57",
    "revenu_brut_imposable": "5436.51",
    "taux_frais_pro": "0.35",
    "frais_professionnels": "1902.78",
    "cotisations_deduites": "366.43",
    "net_imposable": "3167.30",
    "deduction_charges_famille": "0",
    "net_imposable_apres_famille": "3167.30",
    "ir_annuel": "0",
    "ir_mensuel": "0",
    "net_avant_arrondi": "7000.08",
    "arrondi": "-0.08",
    "net_a_payer": "7000",
    "cout_employeur": "8513.08",
    "conges_reliquat": "0",
    "conges_acquis": "1.5",
    "conges_pris": "0",
    "conges_solde": "1.5",
}


@pytest.mark.parametrize("field, expected", EXPECTED_SEPTEMBER.items())
def test_september_2026_matches_workbook(ref_input, params, field, expected):
    result = compute_payslip(ref_input, params, nb_personnes_charge=0)
    assert getattr(result, field) == D(expected)


def test_net_imposable_is_not_3167_31(ref_input, params):
    """La note Paramètres!A47 annonce 3 167,31 ; le classeur calcule 3 167,30 (écart E3)."""
    assert compute_payslip(ref_input, params, 0).net_imposable == D("3167.30")


def test_cumuls_july_to_september_match_bulletin_sheets(ref_input, params):
    """Bulletin Juillet/Août/Septembre, ligne 41 (valeurs en cache)."""
    result = compute_payslip(ref_input, params, 0)
    expected = {
        1: ("7366.51", "366.43", "1146.57", "3167.30", "0", "26", "7000"),
        2: ("14733.02", "732.86", "2293.14", "6334.60", "0", "52", "14000"),
        3: ("22099.53", "1099.29", "3439.71", "9501.90", "0", "78", "21000"),
    }
    for n, values in expected.items():
        cumuls = compute_cumuls([result] * (n - 1), result)
        actual = (cumuls.salaire_brut, cumuls.cotisations_salariales, cumuls.cotisations_patronales,
                  cumuls.net_imposable, cumuls.ir, cumuls.jours_declares, cumuls.net_a_payer)
        assert actual == tuple(D(v) for v in values)


# --- Comparaison cellule par cellule avec le classeur, si le fichier est disponible --------
# Le classeur n'est pas versionné (données potentiellement personnelles) : indiquer son chemin
# dans PAIE_REFERENCE_XLSX pour activer ce test.

CALCUL_ROWS = {
    6: "salaire_base", 7: "heures_sup", 8: "prime_panier", 9: "indemnite_transport",
    10: "indemnite_representation", 11: "autre_prime", 12: "salaire_brut",
    13: "assiette_cotisations", 14: "assiette_cnss_plafonnee", 16: "cnss_salarie",
    17: "amo_salarie", 18: "total_cotisations_salariales", 20: "cnss_patronal",
    21: "amo_patronal", 22: "participation_amo", 23: "formation_pro",
    24: "allocations_familiales", 25: "total_cotisations_patronales",
    27: "revenu_brut_imposable", 28: "taux_frais_pro", 29: "frais_professionnels",
    30: "cotisations_deduites", 31: "net_imposable", 32: "deduction_charges_famille",
    33: "net_imposable_apres_famille", 34: "ir_annuel", 35: "ir_mensuel",
    37: "net_avant_arrondi", 38: "arrondi", 39: "net_a_payer", 40: "cout_employeur",
}

REFERENCE_XLSX = os.environ.get("PAIE_REFERENCE_XLSX", "")


@pytest.mark.skipif(not REFERENCE_XLSX or not Path(REFERENCE_XLSX).is_file(),
                    reason="PAIE_REFERENCE_XLSX non défini : classeur source absent du dépôt")
def test_every_calcul_cell_matches_workbook(params):
    import openpyxl

    from src.models.payroll import MonthlyInput

    wb = openpyxl.load_workbook(REFERENCE_XLSX, data_only=True)
    saisie, calcul = wb["Saisie"], wb["Calcul"]
    nb_personnes = int(saisie["B10"].value or 0)
    for col in "BCDE":
        inp = MonthlyInput.from_dict({
            "salaire_base": saisie[f"{col}21"].value, "jours_declares": saisie[f"{col}22"].value,
            "heures_sup": saisie[f"{col}23"].value, "prime_panier": saisie[f"{col}24"].value,
            "indemnite_transport": saisie[f"{col}25"].value,
            "indemnite_representation": saisie[f"{col}26"].value,
            "autre_prime": saisie[f"{col}27"].value, "conges_reliquat": saisie[f"{col}28"].value,
            "conges_acquis": saisie[f"{col}29"].value, "conges_pris": saisie[f"{col}30"].value,
        })
        result = compute_payslip(inp, params, nb_personnes)
        for row, field in CALCUL_ROWS.items():
            cached = D(repr(float(calcul[f"{col}{row}"].value)))
            assert abs(getattr(result, field) - cached) < D("0.000001"), (col, row, field)
