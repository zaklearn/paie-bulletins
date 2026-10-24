"""Scénarios de non-régression. Toute modification des résultats doit être explicite :
relancer `python scripts/update_golden.py`, examiner le diff de `tests/golden/results.json`
et documenter la raison du changement.
"""

from __future__ import annotations

from decimal import Decimal as D

from src.calculations.defaults import DEFAULT_PARAMETERS
from src.models.parameters import METHODE_TAUX_CUMULE
from src.models.payroll import MonthlyInput
from src.services.demo import REFERENCE_INPUT

SCENARIOS: dict[str, tuple[MonthlyInput, int, str]] = {
    "reference_septembre_2026": (REFERENCE_INPUT, 0, "somme_lignes"),
    "reference_septembre_2026_mode_pdf": (REFERENCE_INPUT, 0, METHODE_TAUX_CUMULE),
    "smig_sans_charge": (MonthlyInput(salaire_base=D("3266.55"), jours_declares=D("26"),
                                      conges_acquis=D("1.5")), 0, "somme_lignes"),
    "cadre_plafond_ir_34": (MonthlyInput(salaire_base=D("12000"), jours_declares=D("26"),
                                         heures_sup=D("500"), prime_panier=D("300"),
                                         autre_prime=D("250")), 2, "somme_lignes"),
    "haut_salaire_ir_38": (MonthlyInput(salaire_base=D("25000"), jours_declares=D("26"),
                                        indemnite_representation=D("2000")), 6, "somme_lignes"),
    "temps_partiel_10_jours": (MonthlyInput(salaire_base=D("1500.40"), jours_declares=D("10"),
                                            indemnite_transport=D("200"), conges_reliquat=D("4"),
                                            conges_acquis=D("0.75"), conges_pris=D("2")), 1, "somme_lignes"),
}


def params_for(method: str):
    return DEFAULT_PARAMETERS.with_changes(methode_totaux=method)
