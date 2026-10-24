"""Récapitulatifs mensuels et annuels, exports CSV et Excel."""

import streamlit as st

from src.models.payroll import MOIS_FR
from src.services import reporting
from src.ui.common import get_db, page_header, period_selector

db = get_db()
page_header("Récapitulatifs et exports",
            "Exports limités au matricule, au nom et aux montants : ni CIN, ni CNSS, ni coordonnées bancaires.")
year, _ = period_selector("exp_", show_month=False)
month = st.selectbox("Mois", [None, *range(1, 13)], format_func=lambda m: "Toute l'année" if m is None else MOIS_FR[m - 1])
include_open = st.checkbox("Inclure les paies non clôturées (brouillons calculés)", value=False,
                           help="Par défaut, seules les paies clôturées font foi.")

journal = reporting.payroll_journal(db, year, month, include_open=include_open)
if journal.empty:
    st.info("Aucune paie pour cette sélection.")
    st.stop()

st.subheader("Livre de paie")
st.dataframe(journal, hide_index=True)
monthly = reporting.monthly_summary(journal)
annual = reporting.annual_summary(journal)
st.subheader("Récapitulatif mensuel")
st.dataframe(monthly, hide_index=True)
st.subheader("Récapitulatif annuel par salarié")
st.dataframe(annual, hide_index=True)

suffix = f"{year}" + (f"-{month:02d}" if month else "")
c1, c2 = st.columns(2)
c1.download_button("Livre de paie (CSV)", reporting.to_csv_bytes(journal),
                   file_name=f"livre_de_paie_{suffix}.csv", mime="text/csv")
c2.download_button("Classeur complet (Excel)",
                   reporting.to_excel_bytes({"Livre de paie": journal, "Récap mensuel": monthly,
                                             "Récap annuel": annual}),
                   file_name=f"recapitulatif_paie_{suffix}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
