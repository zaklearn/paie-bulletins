"""Calcul, contrôles, clôture, génération du bulletin et rectification."""

import pandas as pd
import streamlit as st

from src.formatting import fmt_money
from src.models.payroll import (
    STATUT_BROUILLON, STATUT_CALCULEE, STATUT_CLOTUREE, STATUTS_LIBELLES, period_label,
)
from src.pdf.bulletin import bulletin_filename
from src.services import master_data, payroll
from src.ui.common import (
    actor, employee_selector, get_db, page_header, period_selector, run_action, show_issues,
)
from src.ui.payslip_view import show_result
from src.validation.validators import AVERTISSEMENT, has_errors

db = get_db()
page_header("Calcul et validation", "Étapes 6 à 13 : calcul, récapitulatif, contrôles, clôture, archivage.")
year, month = period_selector("calc_")

# Vue d'ensemble du mois pour tous les salariés actifs.
employees = master_data.list_employees(db, active_only=True)
overview = []
for emp in employees:
    slip = payroll.current_payslip(db, emp.id, year, month)
    overview.append({
        "Matricule": emp.matricule, "Salarié": emp.nom_complet,
        "Statut": STATUTS_LIBELLES[slip.status] if slip else "Non saisie",
        "Version": str(slip.version) if slip else "",
        "Net à payer (MAD)": fmt_money(slip.result.net_a_payer) if slip and slip.result else "",
    })
if overview:
    st.dataframe(pd.DataFrame(overview), hide_index=True)

employee = employee_selector(db, key="calc_employee")
if employee is None:
    st.stop()
slip = payroll.current_payslip(db, employee.id, year, month)
if slip is None:
    st.info(f"Aucune saisie pour {period_label(year, month)}. Commencez par la page **Saisie mensuelle**.")
    st.page_link("views/saisie.py", label="Saisie mensuelle", icon="✏️")
    st.stop()

company = master_data.get_company(db)
logo = company.logo if company else None
st.subheader(f"{employee.nom_complet} — {period_label(year, month)} — version {slip.version}")
st.markdown(f"Statut : **{STATUTS_LIBELLES[slip.status]}**"
            + (f" · rectification de la version précédente (motif : {slip.rectification_reason})"
               if slip.replaces_id else ""))

# --- Paie ouverte : calcul et clôture --------------------------------------------------------
if slip.status in (STATUT_BROUILLON, STATUT_CALCULEE):
    if st.button("Calculer la paie" if slip.status == STATUT_BROUILLON else "Recalculer", type="primary"):
        if run_action(payroll.calculate, db, actor(), slip.id, success="Paie calculée."):
            st.rerun()
    if slip.status == STATUT_CALCULEE:
        show_result(slip.result, slip.cumuls)
        st.download_button("Aperçu du bulletin (PDF provisoire)", payroll.provisional_pdf(db, slip.id, logo),
                           file_name=bulletin_filename(slip).replace(".pdf", "_PROVISOIRE.pdf"),
                           mime="application/pdf")
        st.subheader("Contrôles avant clôture")
        checks = payroll.closure_checks(db, slip.id)
        show_issues(checks)
        if not checks:
            st.success("Tous les contrôles sont satisfaits.", icon="✅")
        if not has_errors(checks):
            st.warning("La clôture est **définitive** : la paie, les cumuls et le bulletin PDF seront figés "
                       "et archivés. Une correction ultérieure passera par une rectification tracée.", icon="🔒")
            confirm_warn = True
            if any(i.level == AVERTISSEMENT for i in checks):
                confirm_warn = st.checkbox("J'ai pris connaissance des avertissements ci-dessus.")
            confirm = st.checkbox("Je confirme la clôture et la génération du bulletin.")
            if st.button("Clôturer et générer le bulletin", type="primary", disabled=not (confirm and confirm_warn)):
                closed = run_action(payroll.close, db, actor(), slip.id, confirm_warnings=confirm_warn, logo=logo,
                                    success="Paie clôturée, bulletin généré et archivé.")
                if closed:
                    st.rerun()
    else:
        st.info("Calculez la paie pour afficher le récapitulatif et les contrôles.")
    with st.expander("Supprimer ce brouillon"):
        sure = st.checkbox("Je confirme la suppression de cette version non clôturée.", key="del_confirm")
        if st.button("Supprimer", disabled=not sure):
            if run_action(lambda: payroll.delete_draft(db, actor(), slip.id) or True):
                st.rerun()

# --- Paie clôturée : consultation et rectification ------------------------------------------
elif slip.status == STATUT_CLOTUREE:
    st.success(f"Clôturée le {slip.closed_at.replace('T', ' ')} par {slip.closed_by}.", icon="🔒")
    document = payroll.get_document(db, slip.id)
    if document:
        st.download_button(f"Télécharger {document.filename}", document.content, file_name=document.filename,
                           mime="application/pdf", type="primary")
        st.caption(f"Empreinte SHA-256 : `{document.sha256}`")
    show_result(slip.result, slip.cumuls)
    st.subheader("Rectification")
    st.caption("Crée une nouvelle version modifiable. La version actuelle reste en vigueur jusqu'à la "
               "clôture de la rectification, puis elle est conservée avec le statut « Remplacée ».")
    reason = st.text_input("Motif de la rectification *")
    if st.button("Ouvrir une rectification"):
        if run_action(payroll.open_rectification, db, actor(), slip.id, reason,
                      success="Rectification ouverte : modifiez la saisie puis recalculez."):
            st.rerun()
