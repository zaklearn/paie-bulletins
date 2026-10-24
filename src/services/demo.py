"""Données de démonstration **entièrement fictives**.

Les montants reprennent la saisie du classeur de référence (juillet à septembre 2026) ;
l'identité de la société et du salarié est inventée (décision D13).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from src.models.entities import Company, Employee
from src.models.payroll import MonthlyInput
from src.repositories import repos
from src.repositories.db import Database
from src.services import master_data, payroll

DEMO_COMPANY = Company(
    raison_sociale="SOCIÉTÉ EXEMPLE SARL",
    adresse="12, rue de l'Exemple",
    ville="Ville-Exemple",
    ice="000000000000000",
    cnss_employeur="0000000",
    rc="RC-EXEMPLE",
    identifiant_fiscal="IF-EXEMPLE",
)

DEMO_EMPLOYEE = Employee(
    matricule="0001",
    nom="EXEMPLE",
    prenom="Salarié",
    date_naissance=date(1990, 1, 1),
    cin="XX000000",
    cnss="000000000",
    situation_familiale="Célibataire",
    nb_personnes_charge=0,
    date_embauche=date(2026, 7, 1),
    fonction="Employé",
    mode_paiement="Virement",
    banque="BANQUE EXEMPLE",
    compte_bancaire="000 000 0000000000000000 00",
)

# Saisie!B21:D30 du classeur de référence.
REFERENCE_INPUT = MonthlyInput(
    salaire_base=D("5436.51"), jours_declares=D("26"), heures_sup=D("0"),
    prime_panier=D("930"), indemnite_transport=D("500"), indemnite_representation=D("500"),
    autre_prime=D("0"), conges_reliquat=D("0"), conges_acquis=D("1.5"), conges_pris=D("0"),
)


def seed_demo(db: Database, close_months: tuple[int, ...] = (7, 8, 9)) -> bool:
    """Crée la démonstration si la base est vide. Renvoie True si des données ont été créées."""
    with db.read() as conn:
        if repos.get_company(conn) is not None or repos.list_employees(conn):
            return False
    actor = "démonstration"
    master_data.ensure_initial_parameters(db)
    master_data.save_company(db, actor, DEMO_COMPANY)
    employee_id, _ = master_data.create_employee(db, actor, DEMO_EMPLOYEE)
    for month in close_months:
        payslip_id, _ = payroll.save_draft(db, actor, employee_id, 2026, month, REFERENCE_INPUT)
        payroll.calculate(db, actor, payslip_id)
        payroll.close(db, actor, payslip_id, confirm_warnings=True)
    return True
