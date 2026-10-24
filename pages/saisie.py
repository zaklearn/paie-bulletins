"""Saisie mensuelle (feuille Saisie, lignes 21 à 30), avec prévisualisation du calcul."""

import streamlit as st

from src.formatting import fmt_days
from src.models.payroll import STATUT_CLOTUREE, STATUTS_LIBELLES, MonthlyInput, period_label
from src.services import payroll
from src.services.errors import PayrollError
from src.ui.common import (
    actor, decimal_input, employee_selector, get_db, page_header, period_selector, run_action, show_issues,
)
from src.ui.payslip_view import show_result

db = get_db()
page_header("Saisie mensuelle", "Étapes 1 à 9 : période, salarié, éléments variables, contrôles, brouillon.")
year, month = period_selector("saisie_")
employee = employee_selector(db)
if employee is None:
    st.stop()

current = payroll.current_payslip(db, employee.id, year, month)
if current is not None:
    st.info(f"Paie {period_label(year, month)} — version {current.version} — statut : "
            f"**{STATUTS_LIBELLES[current.status]}**", icon="📄")
if current is not None and current.status == STATUT_CLOTUREE:
    st.warning("Cette paie est clôturée : elle ne peut plus être modifiée ici. Pour la corriger, ouvrez "
               "une rectification depuis la page **Calcul et validation**.", icon="🔒")
    show_result(current.result, current.cumuls)
    st.stop()

try:
    prefill = payroll.prefill_inputs(db, employee.id, year, month)
except PayrollError as exc:
    st.error(str(exc))
    st.stop()
st.caption(f"Valeurs proposées : {prefill.source}")
show_issues(prefill.warnings)
previous_solde = payroll.previous_conges_solde(db, employee.id, year, month)

k = f"{employee.id}_{year}_{month}_{current.version if current else 0}"
v = prefill.inputs
st.subheader("Éléments de rémunération")
c1, c2, c3 = st.columns(3)
with c1:
    salaire_base = decimal_input("Salaire de base mensuel (MAD) *", v.salaire_base, f"sb_{k}")
    jours = decimal_input("Jours déclarés", v.jours_declares, f"jd_{k}", step=1.0,
                          help="Nombre de jours déclarés à la CNSS (26 au maximum en principe).")
    heures_sup = decimal_input("Heures supplémentaires — montant (MAD)", v.heures_sup, f"hs_{k}")
with c2:
    panier = decimal_input("Prime de panier (MAD)", v.prime_panier, f"pp_{k}")
    transport = decimal_input("Indemnité de transport — périmètre urbain (MAD)", v.indemnite_transport, f"it_{k}")
    representation = decimal_input("Indemnité de représentation (MAD)", v.indemnite_representation, f"ir_{k}")
with c3:
    autre = decimal_input("Autre prime (MAD)", v.autre_prime, f"ap_{k}")

st.subheader("Congés (jours)")
c1, c2, c3 = st.columns(3)
reliquat = c1.number_input("Reliquat de congés", value=float(v.conges_reliquat), step=0.5, min_value=0.0,
                           format="%.2f", key=f"cr_{k}",
                           help="Solde reporté. Le classeur source ne reporte pas automatiquement : "
                                "la valeur proposée est le solde du dernier mois clôturé.")
acquis = c2.number_input("Congés acquis", value=float(v.conges_acquis), step=0.5, min_value=0.0,
                         format="%.2f", key=f"ca_{k}")
pris = c3.number_input("Congés pris", value=float(v.conges_pris), step=0.5, min_value=0.0,
                       format="%.2f", key=f"cp_{k}")
if previous_solde is not None:
    st.caption(f"Solde du dernier mois clôturé : {fmt_days(previous_solde)} j.")

inputs = MonthlyInput.from_dict({
    "salaire_base": salaire_base, "jours_declares": jours, "heures_sup": heures_sup,
    "prime_panier": panier, "indemnite_transport": transport, "indemnite_representation": representation,
    "autre_prime": autre, "conges_reliquat": f"{reliquat:.2f}", "conges_acquis": f"{acquis:.2f}",
    "conges_pris": f"{pris:.2f}",
})

st.subheader("Contrôles")
issues = payroll.check_inputs(db, employee.id, year, month, inputs)
if issues:
    show_issues(issues)
else:
    st.success("Aucune anomalie détectée.", icon="✅")

st.subheader("Prévisualisation (non enregistrée)")
try:
    preview = payroll.preview(db, employee.id, year, month, inputs)
    st.caption(f"Paramètres en vigueur depuis {preview.parameter_set.valid_from} : {preview.parameter_set.label}")
    show_result(preview.result, preview.cumuls)
except PayrollError as exc:
    st.error(str(exc))

if st.button("Enregistrer le brouillon", type="primary"):
    saved = run_action(payroll.save_draft, db, actor(), employee.id, year, month, inputs,
                       success="Brouillon enregistré. Poursuivez dans « Calcul et validation ».")
    if saved:
        st.page_link("pages/calcul.py", label="Aller au calcul et à la validation", icon="🧮")
