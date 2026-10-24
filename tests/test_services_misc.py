"""Validation, exports, sauvegarde/restauration, authentification, formats, démonstration."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from src.formatting import anciennete, fmt_date, fmt_money, fmt_rate, mask
from src.models.parameters import IRBracket
from src.models.payroll import MonthlyInput
from src.repositories.db import Database
from src.services import auth, backup, demo, master_data, payroll, reporting
from src.services.errors import PayrollError
from src.validation.validators import (
    ERREUR, validate_bareme, validate_company, validate_employee, validate_monthly_input,
)

from .conftest import ACTOR, make_employee


# --- Validation -------------------------------------------------------------------------

def test_monthly_input_rules():
    issues = validate_monthly_input(MonthlyInput(salaire_base=D("1000.123"), jours_declares=D("32"),
                                                 prime_panier=D("-1")))
    fields = {i.field for i in issues if i.level == ERREUR}
    assert {"salaire_base", "jours_declares", "prime_panier"} <= fields
    warn = validate_monthly_input(MonthlyInput(salaire_base=D("1000"), jours_declares=D("27"),
                                               conges_pris=D("5")))
    assert {i.field for i in warn} == {"jours_declares", "conges_pris"}
    assert all(i.level != ERREUR for i in warn)


def test_employee_rules():
    bad = make_employee("", nom="", date_naissance=date(2030, 1, 1), situation_familiale="?",
                        nb_personnes_charge=-1)
    fields = {i.field for i in validate_employee(bad, today=date(2026, 10, 1)) if i.level == ERREUR}
    assert {"matricule", "nom", "date_naissance", "situation_familiale", "nb_personnes_charge"} <= fields
    exit_before = make_employee("0005", date_sortie=date(2026, 1, 1))
    assert any(i.field == "date_sortie" for i in validate_employee(exit_before))


def test_company_rules():
    assert any(i.field == "raison_sociale" for i in validate_company(demo.DEMO_COMPANY.__class__()))
    assert any(i.field == "ice" for i in validate_company(replace(demo.DEMO_COMPANY, ice="ABC")))


def test_scale_rules(params):
    gap = params.with_changes(bareme=(IRBracket(D("0"), D("100"), D("0"), D("0")),
                                      IRBracket(D("50"), None, D("0.1"), D("0"))))
    assert any(i.level == ERREUR for i in validate_bareme(gap))
    assert not [i for i in validate_bareme(params) if i.level == ERREUR]


# --- Exports -----------------------------------------------------------------------------

@pytest.fixture
def closed_quarter(setup, ref_input):
    db, employee_id = setup
    for month in (7, 8, 9):
        payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, month, ref_input)
        payroll.calculate(db, ACTOR, payslip_id)
        payroll.close(db, ACTOR, payslip_id, confirm_warnings=True)
    payroll.save_draft(db, ACTOR, employee_id, 2026, 10, ref_input)
    return db


def test_journal_and_summaries(closed_quarter):
    journal = reporting.payroll_journal(closed_quarter, 2026)
    assert len(journal) == 3                      # le brouillon d'octobre est exclu
    annual = reporting.annual_summary(journal)
    assert annual.loc[0, "Salaire brut"] == pytest.approx(22099.53)
    assert annual.loc[0, "Net à payer"] == pytest.approx(21000)
    monthly = reporting.monthly_summary(journal)
    assert list(monthly["Période"]) == ["2026-07", "2026-08", "2026-09"]


def test_exports_exclude_sensitive_data(closed_quarter):
    journal = reporting.payroll_journal(closed_quarter, 2026, include_open=True)
    csv = reporting.to_csv_bytes(journal).decode("utf-8-sig")
    assert "7366,51" in csv and ";" in csv
    for secret in ("XX000000", "000000000", "BANQUE EXEMPLE", "1990"):
        assert secret not in csv
    xlsx = reporting.to_excel_bytes({"Livre de paie": journal})
    assert xlsx[:2] == b"PK"


def test_dashboard(closed_quarter):
    stats = reporting.dashboard(closed_quarter, 2026)
    assert stats.nb_salaries_actifs == 1
    assert stats.mois_clotures == [7, 8, 9] and stats.mois_ouverts == [10]
    assert any("non clôturée" in a for a in stats.alertes)


# --- Sauvegarde et restauration --------------------------------------------------------------

def test_backup_and_restore(closed_quarter, tmp_path):
    db = closed_quarter
    backup_dir = tmp_path / "backups"
    saved = backup.create_backup(db, backup_dir, ACTOR)
    assert saved in backup.list_backups(backup_dir)
    master_data.create_employee(db, ACTOR, make_employee("0099"))
    assert len(master_data.list_employees(db)) == 2
    safety = backup.restore_backup(db, saved.read_bytes(), backup_dir, ACTOR)
    assert safety.exists()
    assert len(master_data.list_employees(db)) == 1
    assert len(reporting.payroll_journal(db, 2026)) == 3
    assert payroll.get_document(db, payroll.list_payslips(db)[0].id) is not None


def test_restore_rejects_invalid_file(db, tmp_path):
    with pytest.raises(PayrollError):
        backup.restore_backup(db, b"not a database", tmp_path, ACTOR)


# --- Authentification ----------------------------------------------------------------------

def test_password_hash_roundtrip():
    encoded = auth.hash_password("motdepasse-solide", iterations=1000)
    assert auth.verify_password("motdepasse-solide", encoded)
    assert not auth.verify_password("mauvais", encoded)
    assert not auth.verify_password("x", "garbage")
    with pytest.raises(ValueError):
        auth.hash_password("court")


# --- Formats --------------------------------------------------------------------------------

def test_french_formats():
    assert fmt_money(D("1146.57")) == "1 146,57"
    assert fmt_money(D("22099.53")) == "22 099,53"
    assert fmt_money(D("-0.08")) == "-0,08"
    assert fmt_money(D("0"), blank_zero=True) == ""
    assert fmt_rate(D("0.0448")) == "4,48"
    assert fmt_date("2026-07-01") == "01/07/2026"
    assert anciennete(date(2026, 7, 1), 2026, 9) == "2 mois"
    assert anciennete(date(2024, 6, 15), 2026, 9) == "2 an(s) 3 mois"
    assert mask("XY123456") == "••••3456"


# --- Démonstration ---------------------------------------------------------------------------

def test_demo_seed_is_idempotent_and_fictitious(tmp_path):
    db = Database(tmp_path / "demo.db")
    db.migrate()
    assert demo.seed_demo(db) is True
    assert demo.seed_demo(db) is False
    company = master_data.get_company(db)
    assert "EXEMPLE" in company.raison_sociale
    sept = [s for s in payroll.list_payslips(db) if s.month == 9][0]
    assert sept.cumuls.salaire_brut == D("22099.53")
