"""Affichage d'un résultat de paie (récapitulatif gains / retenues / charges / cumuls)."""

from __future__ import annotations

import streamlit as st

from src.formatting import fmt_days, fmt_mad, fmt_percent
from src.models.payroll import Cumuls, PayslipResult
from src.ui.common import money_table


def show_result(result: PayslipResult, cumuls: Cumuls | None = None) -> None:
    top = st.columns(4)
    top[0].metric("Salaire brut", fmt_mad(result.salaire_brut))
    top[1].metric("Cotisations salariales", fmt_mad(result.total_cotisations_salariales))
    top[2].metric("IR", fmt_mad(result.ir_mensuel))
    top[3].metric("Net à payer", fmt_mad(result.net_a_payer))

    left, right = st.columns(2)
    with left:
        st.markdown("**Gains**")
        money_table([
            ("Salaire de base", result.salaire_base), ("Heures supplémentaires", result.heures_sup),
            ("Prime de panier", result.prime_panier), ("Indemnité de transport", result.indemnite_transport),
            ("Indemnité de représentation", result.indemnite_representation),
            ("Autre prime", result.autre_prime), ("Salaire brut", result.salaire_brut),
        ])
        st.markdown("**Retenues salariales**")
        money_table([
            ("Assiette des cotisations", result.assiette_cotisations),
            ("Assiette CNSS plafonnée", result.assiette_cnss_plafonnee),
            ("CNSS salarié", result.cnss_salarie), ("AMO salarié", result.amo_salarie),
            ("Total cotisations salariales", result.total_cotisations_salariales),
            ("Impôt sur le revenu", result.ir_mensuel),
            ("Net avant arrondi", result.net_avant_arrondi), ("Arrondi", result.arrondi),
            ("Net à payer", result.net_a_payer),
        ])
    with right:
        st.markdown("**Charges patronales**")
        money_table([
            ("CNSS patronale", result.cnss_patronal), ("AMO patronale", result.amo_patronal),
            ("Participation AMO", result.participation_amo), ("Formation professionnelle", result.formation_pro),
            ("Allocations familiales", result.allocations_familiales),
            ("Total cotisations patronales", result.total_cotisations_patronales),
            ("Coût total employeur", result.cout_employeur),
        ])
        st.markdown("**Calcul de l'IR**")
        money_table([
            ("Revenu brut imposable", result.revenu_brut_imposable),
            ("Frais professionnels", result.frais_professionnels),
            ("Cotisations déduites", result.cotisations_deduites),
            ("Net imposable", result.net_imposable),
            ("Déduction charges de famille", result.deduction_charges_famille),
            ("Net imposable après charges de famille", result.net_imposable_apres_famille),
            ("IR annuel (barème)", result.ir_annuel), ("IR mensuel", result.ir_mensuel),
        ])
        st.caption(f"Taux des frais professionnels : {fmt_percent(result.taux_frais_pro)} — "
                   f"personnes à charge : {result.nb_personnes_charge}")

    st.markdown(f"**Congés** — reliquat {fmt_days(result.conges_reliquat)} j + acquis "
                f"{fmt_days(result.conges_acquis)} j − pris {fmt_days(result.conges_pris)} j = "
                f"**solde {fmt_days(result.conges_solde)} j**")
    if cumuls is not None:
        st.markdown("**Cumuls depuis le début de l'année** (paies clôturées antérieures + ce mois)")
        money_table([
            ("Salaire brut", cumuls.salaire_brut), ("Cotisations salariales", cumuls.cotisations_salariales),
            ("Cotisations patronales", cumuls.cotisations_patronales), ("Net imposable", cumuls.net_imposable),
            ("Impôt sur le revenu", cumuls.ir), ("Jours déclarés", cumuls.jours_declares),
            ("Heures supplémentaires", cumuls.heures_sup), ("Net à payer", cumuls.net_a_payer),
        ], columns=("Cumul", "Valeur"))
