"""Bulletins et archives : consultation par année, mois, salarié ; toutes versions."""

import pandas as pd
import streamlit as st

from src.formatting import fmt_money
from src.models.payroll import MOIS_FR, STATUT_CLOTUREE, STATUT_REMPLACEE, STATUTS_LIBELLES
from src.services import master_data, payroll
from src.ui.common import get_db, page_header
from src.ui.payslip_view import show_result

db = get_db()
page_header("Bulletins et archives", "Bulletins clôturés et versions remplacées, tels qu'émis.")

employees = {e.id: e for e in master_data.list_employees(db)}
c1, c2, c3 = st.columns(3)
years = sorted({s.year for s in payroll.list_payslips(db)}, reverse=True)
if not years:
    st.info("Aucune paie enregistrée.")
    st.stop()
year = c1.selectbox("Année", years)
month = c2.selectbox("Mois", [None, *range(1, 13)], format_func=lambda m: "Tous" if m is None else MOIS_FR[m - 1])
emp_id = c3.selectbox("Salarié", [None, *employees],
                      format_func=lambda i: "Tous" if i is None else f"{employees[i].matricule} — {employees[i].nom_complet}")
include_replaced = st.checkbox("Inclure les versions remplacées par une rectification", value=True)
statuses = (STATUT_CLOTUREE, STATUT_REMPLACEE) if include_replaced else (STATUT_CLOTUREE,)
slips = payroll.list_payslips(db, year=year, month=month, employee_id=emp_id, statuses=statuses)

if not slips:
    st.info("Aucun bulletin pour ces critères.")
    st.stop()

st.dataframe(pd.DataFrame([{
    "Période": f"{MOIS_FR[s.month - 1]} {s.year}",
    "Matricule": (s.employee_snapshot or {}).get("matricule", ""),
    "Salarié": f"{(s.employee_snapshot or {}).get('nom', '')} {(s.employee_snapshot or {}).get('prenom', '')}",
    "Version": s.version, "Statut": STATUTS_LIBELLES[s.status],
    "Brut (MAD)": fmt_money(s.result.salaire_brut), "Net à payer (MAD)": fmt_money(s.result.net_a_payer),
    "Clôturée le": (s.closed_at or "").replace("T", " "),
} for s in slips]), hide_index=True)

chosen = st.selectbox("Bulletin à consulter", slips, format_func=lambda s: (
    f"{MOIS_FR[s.month - 1]} {s.year} — {(s.employee_snapshot or {}).get('matricule', '')} — "
    f"v{s.version} ({STATUTS_LIBELLES[s.status]})"))
document = payroll.get_document(db, chosen.id)
if document:
    st.download_button(f"Télécharger {document.filename}", document.content, file_name=document.filename,
                       mime="application/pdf", type="primary")
    st.caption(f"Archivé le {document.created_at.replace('T', ' ')} — SHA-256 `{document.sha256}`")
if chosen.status == STATUT_REMPLACEE:
    st.warning("Version remplacée par une rectification : conservée pour l'historique, elle ne fait plus foi.")
if chosen.rectification_reason:
    st.caption(f"Motif de rectification : {chosen.rectification_reason}")
with st.expander("Montants de la paie (valeurs figées à la clôture)", expanded=True):
    show_result(chosen.result, chosen.cumuls)
with st.expander("Paramètres appliqués (copie figée)"):
    st.json(chosen.parameters.to_dict())
