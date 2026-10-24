"""Cumuls annuels (feuilles Bulletin, ligne 41).

Le classeur calcule `SUMPRODUCT((n° d'ordre <= mois) * rubrique)`. Ici, le service
fournit les résultats des paies **faisant foi** (clôturées, non remplacées) de la même
année et des mois antérieurs ; ce module se contente d'additionner.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.models.payroll import Cumuls, PayslipResult


def add_to_cumuls(cumuls: Cumuls, result: PayslipResult) -> Cumuls:
    """Ajoute une paie aux cumuls."""
    return Cumuls(
        salaire_brut=cumuls.salaire_brut + result.salaire_brut,
        cotisations_salariales=cumuls.cotisations_salariales + result.total_cotisations_salariales,
        cotisations_patronales=cumuls.cotisations_patronales + result.total_cotisations_patronales,
        net_imposable=cumuls.net_imposable + result.net_imposable,
        ir=cumuls.ir + result.ir_mensuel,
        jours_declares=cumuls.jours_declares + result.jours_declares,
        heures_sup=cumuls.heures_sup + result.heures_sup,
        net_a_payer=cumuls.net_a_payer + result.net_a_payer,
    )


def compute_cumuls(previous: Iterable[PayslipResult], current: PayslipResult | None) -> Cumuls:
    """Cumuls = Σ paies antérieures faisant foi + paie courante."""
    total = Cumuls()
    for result in previous:
        total = add_to_cumuls(total, result)
    if current is not None:
        total = add_to_cumuls(total, current)
    return total
