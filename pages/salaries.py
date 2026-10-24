"""Gestion des salariés : liste, recherche, création, modification, activation."""

from dataclasses import replace
from datetime import date

import pandas as pd
import streamlit as st

from src.formatting import fmt_date, mask
from src.models.entities import MODES_PAIEMENT, SITUATIONS_FAMILIALES, Employee
from src.services import master_data
from src.ui.common import actor, get_db, page_header, run_action, show_issues

db = get_db()
page_header("Salariés", "Les modifications de fiche ne changent jamais les bulletins déjà clôturés.")

search = st.text_input("Rechercher par nom ou matricule", key="emp_search")
show_inactive = st.checkbox("Afficher les salariés désactivés")
employees = master_data.list_employees(db, active_only=not show_inactive, search=search)
reveal = st.toggle("Afficher les identifiants complets (CIN, CNSS, compte)", value=False,
                   help="Masqués par défaut pour limiter l'exposition à l'écran.")

if employees:
    st.dataframe(pd.DataFrame([{
        "Matricule": e.matricule, "Nom": e.nom, "Prénom": e.prenom, "Fonction": e.fonction,
        "CIN": e.cin if reveal else mask(e.cin), "N° CNSS": e.cnss if reveal else mask(e.cnss),
        "Compte": e.compte_bancaire if reveal else mask(e.compte_bancaire),
        "Embauche": fmt_date(e.date_embauche), "Actif": "Oui" if e.actif else "Non",
    } for e in employees]), hide_index=True)
else:
    st.info("Aucun salarié ne correspond.")


def employee_form(emp: Employee, key: str) -> Employee | None:
    """Formulaire complet de la fiche (champs de la feuille Saisie + champs techniques)."""
    with st.form(key):
        c1, c2, c3 = st.columns(3)
        matricule = c1.text_input("Matricule *", emp.matricule)
        nom = c2.text_input("Nom *", emp.nom)
        prenom = c3.text_input("Prénom", emp.prenom)
        naissance = c1.date_input("Date de naissance", emp.date_naissance, min_value=date(1930, 1, 1),
                                  max_value=date.today(), format="DD/MM/YYYY")
        cin = c2.text_input("N° CIN", emp.cin)
        cnss = c3.text_input("N° CNSS", emp.cnss)
        situation = c1.selectbox("Situation familiale", SITUATIONS_FAMILIALES,
                                 index=SITUATIONS_FAMILIALES.index(emp.situation_familiale)
                                 if emp.situation_familiale in SITUATIONS_FAMILIALES else 0)
        charges = c2.number_input("Nombre de personnes à charge (déductions)", min_value=0, max_value=20,
                                  value=emp.nb_personnes_charge, step=1,
                                  help="Le calcul retient au plus le maximum défini dans les paramètres.")
        embauche = c3.date_input("Date d'embauche", emp.date_embauche, min_value=date(1950, 1, 1),
                                 format="DD/MM/YYYY")
        sortie = c1.date_input("Date de sortie (facultatif)", emp.date_sortie, min_value=date(1950, 1, 1),
                               format="DD/MM/YYYY")
        fonction = c2.text_input("Fonction", emp.fonction)
        departement = c3.text_input("Département", emp.departement)
        cimr = c1.text_input("N° CIMR", emp.cimr)
        categorie = c2.text_input("Catégorie", emp.categorie)
        mode = c3.selectbox("Mode de paiement", MODES_PAIEMENT,
                            index=MODES_PAIEMENT.index(emp.mode_paiement) if emp.mode_paiement in MODES_PAIEMENT else 0)
        banque = c1.text_input("Banque", emp.banque)
        compte = c2.text_input("N° compte bancaire", emp.compte_bancaire)
        adresse = c3.text_input("Adresse", emp.adresse)
        if not st.form_submit_button("Enregistrer la fiche", type="primary"):
            return None
    return replace(emp, matricule=matricule.strip(), nom=nom.strip(), prenom=prenom.strip(),
                   date_naissance=naissance, cin=cin.strip(), cnss=cnss.strip(),
                   situation_familiale=situation, nb_personnes_charge=int(charges),
                   date_embauche=embauche, date_sortie=sortie, fonction=fonction.strip(),
                   departement=departement.strip(), cimr=cimr.strip(), categorie=categorie.strip(),
                   mode_paiement=mode, banque=banque.strip(), compte_bancaire=compte.strip(),
                   adresse=adresse.strip())


tab_new, tab_edit = st.tabs(["Nouveau salarié", "Modifier une fiche"])
with tab_new:
    new = employee_form(Employee(matricule="", nom=""), "new_employee")
    if new is not None:
        created = run_action(master_data.create_employee, db, actor(), new,
                             success=f"Salarié {new.matricule} créé.")
        if created:
            show_issues(created[1])

with tab_edit:
    all_employees = master_data.list_employees(db)
    if all_employees:
        chosen = st.selectbox("Fiche à modifier", all_employees,
                              format_func=lambda e: f"{e.matricule} — {e.nom_complet}"
                              + ("" if e.actif else " (désactivé)"))
        edited = employee_form(chosen, f"edit_{chosen.id}")
        if edited is not None:
            issues = run_action(master_data.update_employee, db, actor(), edited, success="Fiche mise à jour.")
            if issues:
                show_issues(issues)
        st.divider()
        if chosen.actif:
            if st.button("Désactiver ce salarié", help="La fiche et l'historique sont conservés."):
                run_action(master_data.set_employee_active, db, actor(), chosen.id, False,
                           success="Salarié désactivé.")
                st.rerun()
        elif st.button("Réactiver ce salarié"):
            run_action(master_data.set_employee_active, db, actor(), chosen.id, True, success="Salarié réactivé.")
            st.rerun()
        st.caption("Aucune suppression n'est proposée : un salarié payé doit rester dans l'historique.")
