"""Procédure mensuelle : brouillon, calcul, clôture, rectification, cumuls, historique."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from src.models.payroll import (
    STATUT_BROUILLON, STATUT_CALCULEE, STATUT_CLOTUREE, STATUT_REMPLACEE, MonthlyInput,
)
from src.repositories.db import Database
from src.services import master_data, payroll
from src.services.errors import PayrollError, ValidationFailed

from .conftest import ACTOR, make_employee


def run_month(db, employee_id, year, month, inputs, confirm=True):
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, year, month, inputs)
    payroll.calculate(db, ACTOR, payslip_id)
    return payroll.close(db, ACTOR, payslip_id, confirm_warnings=confirm)


# --- Salariés ---------------------------------------------------------------------------

def test_create_and_search_employee(setup):
    db, employee_id = setup
    found = master_data.list_employees(db, search="exem")
    assert [e.id for e in found] == [employee_id]
    assert master_data.list_employees(db, search="0001")[0].matricule == "0001"


def test_duplicate_matricule_cin_cnss_rejected(setup):
    db, _ = setup
    with pytest.raises(ValidationFailed) as exc:
        master_data.create_employee(db, ACTOR, make_employee("0001"))
    assert {i.field for i in exc.value.issues} >= {"matricule"}
    with pytest.raises(ValidationFailed) as exc:
        master_data.create_employee(db, ACTOR, make_employee("0009", cin="XX000000"))
    assert "cin" in {i.field for i in exc.value.issues}


def test_deactivated_employee_cannot_be_paid(setup, ref_input):
    db, employee_id = setup
    master_data.set_employee_active(db, ACTOR, employee_id, False)
    with pytest.raises(ValidationFailed):
        payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)


def test_no_payslip_before_hiring(setup, ref_input):
    db, employee_id = setup
    with pytest.raises(ValidationFailed) as exc:
        payroll.save_draft(db, ACTOR, employee_id, 2026, 6, ref_input)
    assert "embauche" in str(exc.value)


# --- Brouillon, calcul, clôture -----------------------------------------------------------

def test_full_cycle_and_statuses(setup, ref_input):
    db, employee_id = setup
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    assert payroll.get_payslip(db, payslip_id).status == STATUT_BROUILLON
    calc = payroll.calculate(db, ACTOR, payslip_id)
    assert calc.status == STATUT_CALCULEE and calc.result.net_a_payer == D("7000")
    closed = payroll.close(db, ACTOR, payslip_id, confirm_warnings=False)
    assert closed.status == STATUT_CLOTUREE
    doc = payroll.get_document(db, payslip_id)
    assert doc.filename == "bulletin_2026-07_0001.pdf" and doc.content.startswith(b"%PDF")


def test_editing_draft_invalidates_calculation(setup, ref_input):
    db, employee_id = setup
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    payroll.calculate(db, ACTOR, payslip_id)
    payroll.save_draft(db, ACTOR, employee_id, 2026, 7, replace(ref_input, prime_panier=D("0")))
    slip = payroll.get_payslip(db, payslip_id)
    assert slip.status == STATUT_BROUILLON and slip.result is None
    with pytest.raises(ValidationFailed):
        payroll.close(db, ACTOR, payslip_id, confirm_warnings=True)


def test_cannot_close_without_calculation(setup, ref_input):
    db, employee_id = setup
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    with pytest.raises(ValidationFailed):
        payroll.close(db, ACTOR, payslip_id, confirm_warnings=True)


def test_closed_payslip_cannot_be_silently_modified(setup, ref_input):
    db, employee_id = setup
    closed = run_month(db, employee_id, 2026, 7, ref_input)
    with pytest.raises(PayrollError, match="rectification"):
        payroll.save_draft(db, ACTOR, employee_id, 2026, 7, replace(ref_input, prime_panier=D("1")))
    with pytest.raises(PayrollError):
        payroll.calculate(db, ACTOR, closed.id)
    with pytest.raises(PayrollError):
        payroll.delete_draft(db, ACTOR, closed.id)


def test_database_triggers_protect_closed_payslips(setup, ref_input):
    """Même en contournant les services, la base refuse la modification et la suppression."""
    db, employee_id = setup
    closed = run_month(db, employee_id, 2026, 7, ref_input)
    conn = db.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE payslips SET inputs = '{}' WHERE id = ?", (closed.id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM payslips WHERE id = ?", (closed.id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM documents WHERE payslip_id = ?", (closed.id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE parameter_sets SET data = '{}'")
    finally:
        conn.close()


def test_no_double_closure(setup, ref_input):
    db, employee_id = setup
    closed = run_month(db, employee_id, 2026, 7, ref_input)
    with pytest.raises(ValidationFailed, match="déjà clôturée"):
        payroll.close(db, ACTOR, closed.id, confirm_warnings=True)


def test_unique_active_payslip_constraint(setup, ref_input):
    db, employee_id = setup
    payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    conn = db.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO payslips (employee_id, year, month, version, status, inputs, created_at, "
                "updated_at) VALUES (?, 2026, 7, 2, 'brouillon', '{}', 'x', 'x')", (employee_id,))
    finally:
        conn.close()


def test_closure_requires_recalculation_after_parameter_change(setup, ref_input, params):
    db, employee_id = setup
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    payroll.calculate(db, ACTOR, payslip_id)
    master_data.create_parameter_version(db, ACTOR, 2026, 7, params.with_changes(amo_salarial=D("0.03")),
                                         "Test", "Changement de taux de test")
    with pytest.raises(ValidationFailed, match="recalculez"):
        payroll.close(db, ACTOR, payslip_id, confirm_warnings=True)
    recalculated = payroll.calculate(db, ACTOR, payslip_id)
    assert recalculated.result.amo_salarie == D("163.10")


def test_closure_requires_recalculation_after_employee_change(setup, ref_input):
    db, employee_id = setup
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    payroll.calculate(db, ACTOR, payslip_id)
    emp = master_data.get_employee(db, employee_id)
    master_data.update_employee(db, ACTOR, replace(emp, nb_personnes_charge=2))
    with pytest.raises(ValidationFailed):
        payroll.close(db, ACTOR, payslip_id, confirm_warnings=True)


# --- Historique figé -----------------------------------------------------------------------

def test_employee_change_does_not_alter_closed_payslip(setup, ref_input):
    db, employee_id = setup
    closed = run_month(db, employee_id, 2026, 7, ref_input)
    pdf_before = payroll.get_document(db, closed.id).content
    emp = master_data.get_employee(db, employee_id)
    master_data.update_employee(db, ACTOR, replace(emp, nom="NOUVEAU", nb_personnes_charge=3))
    after = payroll.get_payslip(db, closed.id)
    assert after.employee_snapshot["nom"] == "EXEMPLE"
    assert after.employee_snapshot["nb_personnes_charge"] == 0
    assert after.result == closed.result
    assert payroll.get_document(db, closed.id).content == pdf_before


def test_parameter_version_not_retroactive(setup, ref_input, params):
    db, employee_id = setup
    july = run_month(db, employee_id, 2026, 7, ref_input)
    issues = master_data.create_parameter_version(
        db, ACTOR, 2026, 7, params.with_changes(cnss_salarial=D("0.05")), "Test", "Test rétroactivité")
    assert any("ne sont pas recalculées" in i.message for i in issues)
    assert payroll.get_payslip(db, july.id).result.cnss_salarie == D("243.56")
    assert payroll.get_payslip(db, july.id).parameters.cnss_salarial == D("0.0448")
    august = run_month(db, employee_id, 2026, 8, ref_input)
    assert august.result.cnss_salarie == D("271.83")


def test_parameter_version_validity_period(db, params):
    master_data.create_parameter_version(db, ACTOR, 2027, 1, params.with_changes(plafond_cnss=D("7000")),
                                         "LF 2027", "Hypothèse de test")
    assert master_data.parameters_for_period(db, 2026, 12).params.plafond_cnss == D("6000")
    assert master_data.parameters_for_period(db, 2027, 1).params.plafond_cnss == D("7000")
    with pytest.raises(PayrollError):
        master_data.create_parameter_version(db, ACTOR, 2027, 1, params, "Doublon", "Doublon")


def test_invalid_parameters_rejected(db, params):
    with pytest.raises(ValidationFailed):
        master_data.create_parameter_version(db, ACTOR, 2027, 1, params.with_changes(amo_salarial=D("1.5")),
                                             "x", "Taux invalide")


# --- Cumuls --------------------------------------------------------------------------------

def test_cumuls_frozen_at_closure_reproduce_workbook(setup, ref_input):
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, ref_input)
    run_month(db, employee_id, 2026, 8, ref_input)
    sept = run_month(db, employee_id, 2026, 9, ref_input)
    assert sept.cumuls.salaire_brut == D("22099.53")
    assert sept.cumuls.cotisations_salariales == D("1099.29")
    assert sept.cumuls.cotisations_patronales == D("3439.71")
    assert sept.cumuls.net_imposable == D("9501.90")
    assert sept.cumuls.jours_declares == D("78")
    assert sept.cumuls.net_a_payer == D("21000")


def test_drafts_excluded_from_cumuls_and_chronology_enforced(setup, ref_input):
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, ref_input)
    aug_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 8, ref_input)
    sep_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 9, ref_input)
    sep = payroll.calculate(db, ACTOR, sep_id)
    assert sep.cumuls.salaire_brut == D("14733.02")   # juillet clôturé + septembre ; août en brouillon exclu
    with pytest.raises(ValidationFailed, match="ordre chronologique"):
        payroll.close(db, ACTOR, sep_id, confirm_warnings=True)
    payroll.calculate(db, ACTOR, aug_id)
    payroll.close(db, ACTOR, aug_id, confirm_warnings=True)
    sep = payroll.calculate(db, ACTOR, sep_id)
    assert payroll.close(db, ACTOR, sep_id, confirm_warnings=True).cumuls.salaire_brut == D("22099.53")


def test_future_months_not_included(setup, ref_input):
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, ref_input)
    run_month(db, employee_id, 2026, 8, ref_input)
    preview = payroll.preview(db, employee_id, 2026, 7, ref_input)
    assert preview.cumuls.salaire_brut == D("7366.51")


def test_missing_month_requires_confirmation(hired_january, ref_input):
    db, employee_id = hired_january
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 3, ref_input)
    payroll.calculate(db, ACTOR, payslip_id)
    warnings = payroll.closure_checks(db, payslip_id)
    assert sum("Aucune paie" in i.message for i in warnings) == 2   # janvier et février
    with pytest.raises(PayrollError, match="confirmés"):
        payroll.close(db, ACTOR, payslip_id, confirm_warnings=False)
    assert payroll.close(db, ACTOR, payslip_id, confirm_warnings=True).status == STATUT_CLOTUREE


def test_december_to_january_resets_cumuls(hired_january, ref_input):
    db, employee_id = hired_january
    dec = run_month(db, employee_id, 2025, 12, ref_input)
    assert dec.cumuls.salaire_brut == D("7366.51")       # seul décembre 2025 est clôturé
    jan = run_month(db, employee_id, 2026, 1, ref_input)
    assert jan.cumuls.salaire_brut == D("7366.51")       # remise à zéro au 1er janvier
    assert jan.cumuls.jours_declares == D("26")


def test_twelve_months(hired_january, ref_input):
    db, employee_id = hired_january
    last = None
    for month in range(1, 13):
        last = run_month(db, employee_id, 2026, month, ref_input)
    assert last.cumuls.salaire_brut == D("7366.51") * 12
    assert last.cumuls.net_a_payer == D("84000")
    assert len(payroll.list_payslips(db, year=2026, statuses=(STATUT_CLOTUREE,))) == 12


# --- Rectification -------------------------------------------------------------------------

def test_rectification_keeps_previous_version(setup, ref_input):
    db, employee_id = setup
    v1 = run_month(db, employee_id, 2026, 7, ref_input)
    with pytest.raises(PayrollError, match="motif"):
        payroll.open_rectification(db, ACTOR, v1.id, "")
    v2_id = payroll.open_rectification(db, ACTOR, v1.id, "Prime oubliée")
    with pytest.raises(PayrollError, match="déjà en cours"):
        payroll.open_rectification(db, ACTOR, v1.id, "Encore")
    payroll.save_draft(db, ACTOR, employee_id, 2026, 7, replace(ref_input, autre_prime=D("100")))
    payroll.calculate(db, ACTOR, v2_id)
    assert payroll.get_payslip(db, v1.id).status == STATUT_CLOTUREE   # l'ancienne fait foi jusqu'à la clôture
    v2 = payroll.close(db, ACTOR, v2_id, confirm_warnings=True)
    versions = payroll.list_versions(db, employee_id, 2026, 7)
    assert [(v.version, v.status) for v in versions] == [(1, STATUT_REMPLACEE), (2, STATUT_CLOTUREE)]
    assert versions[0].result == v1.result                             # ancienne version intacte
    assert payroll.get_document(db, v1.id) is not None
    assert payroll.get_document(db, v2.id).filename == "bulletin_2026-07_0001_v2.pdf"


def test_rectification_no_double_counting(setup, ref_input):
    db, employee_id = setup
    v1 = run_month(db, employee_id, 2026, 7, ref_input)
    v2_id = payroll.open_rectification(db, ACTOR, v1.id, "Correction prime")
    payroll.save_draft(db, ACTOR, employee_id, 2026, 7, replace(ref_input, autre_prime=D("100")))
    payroll.calculate(db, ACTOR, v2_id)
    payroll.close(db, ACTOR, v2_id, confirm_warnings=True)
    aug = run_month(db, employee_id, 2026, 8, ref_input)
    assert aug.cumuls.salaire_brut == D("7466.51") + D("7366.51")


def test_rectification_warns_about_later_closed_bulletins(setup, ref_input):
    db, employee_id = setup
    v1 = run_month(db, employee_id, 2026, 7, ref_input)
    aug = run_month(db, employee_id, 2026, 8, ref_input)
    v2_id = payroll.open_rectification(db, ACTOR, v1.id, "Correction")
    payroll.calculate(db, ACTOR, v2_id)
    assert any("Août 2026" in i.message for i in payroll.closure_checks(db, v2_id))
    payroll.close(db, ACTOR, v2_id, confirm_warnings=True)
    assert payroll.get_payslip(db, aug.id).cumuls == aug.cumuls        # cumuls émis conservés


def test_audit_log_records_operations_without_sensitive_data(setup, ref_input):
    from src.services.reporting import audit_log
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, ref_input)
    emp = master_data.get_employee(db, employee_id)
    master_data.update_employee(db, ACTOR, replace(emp, compte_bancaire="999 SECRET 999"))
    log = audit_log(db)
    assert {"paie.cloture", "salarie.modification", "paie.calcul"} <= set(log["action"])
    assert not log["details"].str.contains("SECRET").any()
    assert not log["details"].str.contains("XX000000").any()


# --- Préremplissage et congés ---------------------------------------------------------------

def test_prefill_from_previous_closed_month(setup, ref_input):
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, replace(ref_input, heures_sup=D("300"), conges_pris=D("0")))
    pre = payroll.prefill_inputs(db, employee_id, 2026, 8)
    assert pre.inputs.salaire_base == D("5436.51")
    assert pre.inputs.heures_sup == D("0")                  # non récurrent : remis à zéro
    assert pre.inputs.conges_reliquat == D("1.5")           # solde de juillet proposé (D5)
    assert pre.warnings


def test_prefill_warns_when_gap(setup, ref_input):
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, ref_input)
    pre = payroll.prefill_inputs(db, employee_id, 2026, 9)
    assert any("pas le mois précédent" in w.message for w in pre.warnings)


def test_reliquat_mismatch_warning(setup, ref_input):
    """Le classeur saisit un reliquat de 0 chaque mois : accepté, mais signalé (ambiguïté A3)."""
    db, employee_id = setup
    run_month(db, employee_id, 2026, 7, ref_input)
    issues = payroll.check_inputs(db, employee_id, 2026, 8, ref_input)
    assert any(i.field == "conges_reliquat" and i.level == "avertissement" for i in issues)
    _, warnings = payroll.save_draft(db, ACTOR, employee_id, 2026, 8, ref_input)
    assert warnings


def test_months_are_independent(setup, ref_input):
    db, employee_id = setup
    payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    payroll.save_draft(db, ACTOR, employee_id, 2026, 8, replace(ref_input, prime_panier=D("1")))
    assert payroll.current_payslip(db, employee_id, 2026, 7).inputs.prime_panier == D("930")
    assert payroll.current_payslip(db, employee_id, 2026, 8).inputs.prime_panier == D("1")


def test_invalid_monthly_input_rejected(setup):
    db, employee_id = setup
    with pytest.raises(ValidationFailed):
        payroll.save_draft(db, ACTOR, employee_id, 2026, 7,
                           MonthlyInput(salaire_base=D("-5"), jours_declares=D("40")))


def test_delete_draft(setup, ref_input):
    db, employee_id = setup
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    payroll.delete_draft(db, ACTOR, payslip_id)
    assert payroll.get_payslip(db, payslip_id) is None


# --- Persistance -------------------------------------------------------------------------

def test_data_persists_after_restart(setup, ref_input):
    db, employee_id = setup
    closed = run_month(db, employee_id, 2026, 7, ref_input)
    restarted = Database(db.path)          # nouvelle instance, comme après un redémarrage
    assert restarted.migrate() == 1
    again = payroll.get_payslip(restarted, closed.id)
    assert again.result == closed.result and again.cumuls == closed.cumuls
    assert master_data.get_company(restarted).raison_sociale == "SOCIÉTÉ EXEMPLE SARL"
    assert payroll.get_document(restarted, closed.id) is not None


def test_company_required_before_calculation(db, ref_input):
    employee_id, _ = master_data.create_employee(db, ACTOR, make_employee("0003", date_embauche=date(2026, 1, 1)))
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, ref_input)
    with pytest.raises(PayrollError, match="entreprise"):
        payroll.calculate(db, ACTOR, payslip_id)
