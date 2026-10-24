"""Tableau de bord."""

import pandas as pd
import streamlit as st

from src.formatting import fmt_money
from src.models.payroll import MOIS_FR, STATUTS_LIBELLES
from src.services import master_data, reporting
from src.ui.common import get_db, page_header, period_selector

db = get_db()
company = master_data.get_company(db)
page_header("Tableau de bord",
            f"Entreprise active : **{company.raison_sociale}**" if company else "Entreprise non renseignée")
year, _ = period_selector("dash_", show_month=False)
stats = reporting.dashboard(db, year)

cols = st.columns(4)
cols[0].metric("Salariés actifs", stats.nb_salaries_actifs, help=f"{stats.nb_salaries_total} fiches au total")
cols[1].metric("Mois clôturés", len(stats.mois_clotures))
cols[2].metric("Mois ouverts", len(stats.mois_ouverts),
               help="Mois comportant au moins une paie en brouillon ou calculée")
cols[3].metric("Paies à finaliser", stats.nb_brouillons + stats.nb_calculees,
               help=f"{stats.nb_brouillons} brouillon(s), {stats.nb_calculees} calculée(s)")

st.subheader(f"Calendrier {year}")
calendar = []
for m in range(1, 13):
    state = "Ouvert" if m in stats.mois_ouverts else "Clôturé" if m in stats.mois_clotures else "—"
    calendar.append({"Mois": MOIS_FR[m - 1], "État": state})
st.dataframe(pd.DataFrame(calendar).set_index("Mois").T)

st.subheader("Accès rapides")
links = st.columns(4)
links[0].page_link("views/saisie.py", label="Saisie mensuelle", icon="✏️")
links[1].page_link("views/calcul.py", label="Calcul et validation", icon="🧮")
links[2].page_link("views/archives.py", label="Bulletins archivés", icon="🗂️")
links[3].page_link("views/parametres.py", label="Paramètres", icon="⚙️")

st.subheader("Alertes")
if stats.alertes:
    for alert in stats.alertes:
        st.warning(alert, icon="⚠️")
else:
    st.success("Aucune alerte.", icon="✅")

st.subheader("Dernières paies clôturées")
employees = {e.id: e for e in master_data.list_employees(db)}
if stats.dernieres_paies:
    st.dataframe(pd.DataFrame([{
        "Période": f"{MOIS_FR[s.month - 1]} {s.year}",
        "Salarié": employees[s.employee_id].nom_complet if s.employee_id in employees else str(s.employee_id),
        "Version": s.version,
        "Statut": STATUTS_LIBELLES[s.status],
        "Net à payer (MAD)": fmt_money(s.result.net_a_payer),
        "Clôturée le": (s.closed_at or "").replace("T", " "),
    } for s in stats.dernieres_paies]), hide_index=True)
else:
    st.info("Aucune paie clôturée pour l'instant.")

st.caption("Les taux, plafonds et barèmes sont des paramètres configurables dont la conformité "
           "légale doit être validée par un professionnel compétent.")
