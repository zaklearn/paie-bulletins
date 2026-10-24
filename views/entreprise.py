"""Fiche entreprise."""

import streamlit as st

from src.models.entities import Company
from src.services import master_data
from src.ui.common import actor, get_db, page_header, run_action, show_issues

db = get_db()
page_header("Entreprise", "Informations reprises dans l'en-tête de chaque bulletin. "
            "Les paies clôturées conservent la copie en vigueur lors de leur calcul.")
company = master_data.get_company(db) or Company()

with st.form("entreprise"):
    raison = st.text_input("Raison sociale *", company.raison_sociale)
    c1, c2 = st.columns(2)
    adresse = c1.text_input("Adresse", company.adresse)
    ville = c2.text_input("Ville", company.ville)
    ice = c1.text_input("ICE", company.ice, help="Chiffres uniquement")
    cnss = c2.text_input("N° CNSS employeur", company.cnss_employeur)
    rc = c1.text_input("Registre du commerce (RC)", company.rc)
    if_ = c2.text_input("Identifiant fiscal (IF)", company.identifiant_fiscal)
    tel = c1.text_input("Téléphone", company.telephone)
    email = c2.text_input("E-mail", company.email)
    logo_file = st.file_uploader("Logo (facultatif, PNG ou JPEG, 1 Mo max.)", type=["png", "jpg", "jpeg"])
    remove_logo = st.checkbox("Supprimer le logo actuel", disabled=company.logo is None)
    submitted = st.form_submit_button("Enregistrer", type="primary")

if company.logo:
    st.image(company.logo, caption="Logo actuel", width=160)

if submitted:
    logo = company.logo
    if remove_logo:
        logo = None
    if logo_file is not None:
        logo = logo_file.getvalue()
    updated = Company(raison_sociale=raison.strip(), adresse=adresse.strip(), ville=ville.strip(),
                      ice=ice.strip(), cnss_employeur=cnss.strip(), rc=rc.strip(),
                      identifiant_fiscal=if_.strip(), telephone=tel.strip(), email=email.strip(), logo=logo)
    issues = run_action(master_data.save_company, db, actor(), updated,
                        success="Informations de l'entreprise enregistrées.")
    if issues:
        show_issues(issues)

st.info("Les données de démonstration (« SOCIÉTÉ EXEMPLE SARL ») sont fictives : remplacez-les "
        "avant tout usage réel.", icon="ℹ️")
