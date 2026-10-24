"""Sauvegardes, restauration et journal des opérations."""

import streamlit as st

from src.services import backup, reporting
from src.ui.common import actor, get_db, page_header, run_action, settings

db = get_db()
cfg = settings()
page_header("Sauvegardes et administration",
            "Une sauvegarde contient toutes les données de paie, y compris les bulletins archivés : "
            "conservez-la dans un emplacement protégé.")

st.subheader("Sauvegarde")
if st.button("Créer une sauvegarde maintenant", type="primary"):
    path = run_action(backup.create_backup, db, cfg.backup_dir, actor(), success="Sauvegarde créée.")
    if path:
        st.caption(f"Fichier : {path.name}")

backups = backup.list_backups(cfg.backup_dir)
if backups:
    chosen = st.selectbox("Sauvegardes disponibles", backups, format_func=lambda p: p.name)
    st.download_button("Télécharger cette sauvegarde", chosen.read_bytes(), file_name=chosen.name,
                       mime="application/octet-stream")
else:
    st.info("Aucune sauvegarde dans le répertoire configuré.")

st.subheader("Restauration")
st.warning("La restauration **remplace toutes les données actuelles** par celles de la sauvegarde. "
           "Une sauvegarde de sécurité de l'état actuel est créée automatiquement juste avant.", icon="⚠️")
uploaded = st.file_uploader("Fichier de sauvegarde (.db)", type=["db"])
confirm = st.text_input("Pour confirmer, saisissez RESTAURER")
if st.button("Restaurer", disabled=uploaded is None or confirm != "RESTAURER"):
    safety = run_action(backup.restore_backup, db, uploaded.getvalue(), cfg.backup_dir, actor(),
                        success="Données restaurées.")
    if safety:
        st.caption(f"Sauvegarde de sécurité de l'état précédent : {safety.name}")

st.subheader("Journal des opérations")
actions = ["", "paie.cloture", "paie.rectification.ouverture", "paie.calcul", "paie.brouillon.creation",
           "salarie.creation", "salarie.modification", "parametres.nouvelle_version", "entreprise.modification",
           "sauvegarde.creation", "sauvegarde.restauration"]
action = st.selectbox("Filtrer par opération", actions, format_func=lambda a: a or "Toutes")
st.dataframe(reporting.audit_log(db, action=action or None), hide_index=True)
st.caption("Le journal enregistre les opérations sans valeurs personnelles ou bancaires.")
