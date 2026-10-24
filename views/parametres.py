"""Paramètres de paie : consultation des versions et création d'une nouvelle version datée."""

from decimal import Decimal

import pandas as pd
import streamlit as st

from src.calculations.money import to_decimal
from src.formatting import fmt_money, fmt_percent
from src.models.parameters import METHODES_TOTAUX, IRBracket
from src.models.payroll import MOIS_FR
from src.services import master_data
from src.ui.common import actor, get_db, page_header, run_action, show_issues

db = get_db()
UPPER = "Jusqu'à"
page_header("Paramètres de paie",
            "Chaque modification crée une version avec une date d'effet. Les paies clôturées ne sont "
            "jamais recalculées. Les valeurs initiales proviennent du classeur et doivent être validées "
            "par un professionnel compétent.")

sets = master_data.list_parameter_sets(db)
st.subheader("Historique des versions")
st.dataframe(pd.DataFrame([{
    "En vigueur à partir de": s.valid_from, "Libellé": s.label, "Motif / source": s.comment,
    "Créée le": s.created_at.replace("T", " "), "Par": s.created_by,
} for s in sets]), hide_index=True)

chosen = st.selectbox("Version à consulter", sets, format_func=lambda s: f"{s.valid_from} — {s.label}")
p = chosen.params

RATES = [
    ("cnss_salarial", "CNSS — part salariale"), ("amo_salarial", "AMO — part salariale"),
    ("cnss_patronal", "CNSS — part patronale"), ("amo_patronal", "AMO — part patronale"),
    ("participation_amo", "Participation AMO"), ("formation_pro", "Taxe de formation professionnelle"),
    ("allocations_familiales", "Allocations familiales (patronal)"),
    ("fp_taux_bas", "Frais pro. — taux si revenu annuel ≤ seuil"),
    ("fp_taux_haut", "Frais pro. — taux si revenu annuel > seuil"),
    ("imposable_heures_sup", "Part imposable — heures supplémentaires"),
    ("imposable_prime_panier", "Part imposable — prime de panier"),
    ("imposable_transport", "Part imposable — indemnité de transport"),
    ("imposable_representation", "Part imposable — indemnité de représentation"),
    ("imposable_autre_prime", "Part imposable — autre prime"),
]
AMOUNTS = [
    ("plafond_cnss", "Plafond mensuel CNSS (MAD)"), ("fp_seuil_annuel", "Seuil annuel des frais pro. (MAD)"),
    ("fp_plafond_annuel", "Plafond annuel des frais pro. (MAD)"),
    ("deduction_par_personne", "Déduction annuelle par personne à charge (MAD)"),
]

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Taux**")
    st.dataframe(pd.DataFrame([(label, fmt_percent(getattr(p, key))) for key, label in RATES],
                              columns=["Paramètre", "Valeur"]), hide_index=True)
with c2:
    st.markdown("**Montants et règles**")
    rows = [(label, fmt_money(getattr(p, key))) for key, label in AMOUNTS]
    rows += [("Nombre maximum de personnes à charge", str(p.max_personnes)),
             ("Méthode des totaux de cotisations", METHODES_TOTAUX[p.methode_totaux]),
             ("Salaire de base", "toujours imposable à 100 %")]
    st.dataframe(pd.DataFrame(rows, columns=["Paramètre", "Valeur"]), hide_index=True)
    st.markdown("**Barème annuel de l'IR**")
    st.dataframe(pd.DataFrame([{
        "À partir de": fmt_money(b.lower), "Jusqu'à": "et plus" if b.upper is None else fmt_money(b.upper),
        "Taux": fmt_percent(b.rate), "Somme à déduire": fmt_money(b.deduction),
    } for b in p.bareme]), hide_index=True)

st.divider()
st.subheader("Créer une nouvelle version")
st.caption("Partez de la version consultée ci-dessus, modifiez les valeurs, indiquez la date d'effet et "
           "le motif (texte de loi, circulaire, avis du comptable…).")
with st.form("new_params"):
    d1, d2 = st.columns(2)
    eff_year = d1.number_input("Année d'effet", min_value=2000, max_value=2100, value=int(chosen.valid_from[:4]) if chosen.valid_from > "2000-01" else 2026)
    eff_month = d2.selectbox("Mois d'effet", list(range(1, 13)), format_func=lambda m: MOIS_FR[m - 1])
    label = st.text_input("Libellé", "Mise à jour des paramètres")
    comment = st.text_area("Motif ou source *")
    values: dict[str, Decimal] = {}
    cols = st.columns(3)
    for i, (key, text) in enumerate(RATES):
        pct = cols[i % 3].number_input(f"{text} (%)", value=float(getattr(p, key) * 100), min_value=0.0,
                                       max_value=100.0, step=0.01, format="%.2f", key=f"np_{key}")
        values[key] = to_decimal(f"{pct:.4f}") / 100
    for i, (key, text) in enumerate(AMOUNTS):
        amount = cols[i % 3].number_input(text, value=float(getattr(p, key)), min_value=0.0, step=100.0,
                                          format="%.2f", key=f"np_{key}")
        values[key] = to_decimal(f"{amount:.2f}")
    max_personnes = st.number_input("Nombre maximum de personnes à charge", value=p.max_personnes,
                                    min_value=0, max_value=20, step=1)
    methode = st.radio("Méthode des totaux de cotisations", list(METHODES_TOTAUX),
                       index=list(METHODES_TOTAUX).index(p.methode_totaux),
                       format_func=METHODES_TOTAUX.get,
                       help="« Somme des lignes » reproduit le classeur (366,43). « Taux cumulé » reproduit "
                            "le PDF source (366,42). Voir docs/AUDIT_SOURCES.md, écarts E1 à E4.")
    st.markdown("**Barème annuel de l'IR** (laisser « Jusqu'à » vide pour la dernière tranche)")
    bareme_df = st.data_editor(pd.DataFrame([{
        "À partir de": float(b.lower), "Jusqu'à": None if b.upper is None else float(b.upper),
        "Taux (%)": float(b.rate * 100), "Somme à déduire": float(b.deduction),
    } for b in p.bareme]), num_rows="dynamic", hide_index=True, key="np_bareme")
    submitted = st.form_submit_button("Créer la version", type="primary")

if submitted:
    try:
        bareme = tuple(
            IRBracket(lower=to_decimal(f"{row['À partir de']:.2f}"),
                      upper=None if pd.isna(row[UPPER]) else to_decimal(f"{row[UPPER]:.2f}"),
                      rate=to_decimal(f"{row['Taux (%)']:.4f}") / 100,
                      deduction=to_decimal(f"{row['Somme à déduire']:.2f}"))
            for _, row in bareme_df.dropna(subset=["À partir de"]).iterrows())
    except (TypeError, ValueError):
        st.error("Barème incomplet : chaque tranche doit avoir une borne basse, un taux et une somme à déduire.")
        st.stop()
    new_params = p.with_changes(**values, max_personnes=int(max_personnes), methode_totaux=methode, bareme=bareme)
    issues = run_action(master_data.create_parameter_version, db, actor(), int(eff_year), int(eff_month),
                        new_params, label, comment, success="Nouvelle version de paramètres créée.")
    if issues:
        show_issues(issues)
