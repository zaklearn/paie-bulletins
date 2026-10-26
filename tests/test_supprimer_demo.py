"""Suppression du salarié de démonstration : données réelles intactes, protections rétablies."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from scripts import supprimer_demo as sd
from scripts.reset_production import ResetAborted
from src.repositories.db import SCHEMA_VERSION, Database
from src.services import backup, demo, master_data, payroll, reporting
from src.services.backup import _expected_protections, _protections
from src.services.demo import DEMO_COMPANY, REFERENCE_INPUT

from .conftest import ACTOR, make_employee

ROOT = Path(__file__).resolve().parent.parent
REAL_COMPANY = replace(DEMO_COMPANY, raison_sociale="SOCIÉTÉ RÉELLE SARL", ice="111111111111111")


@pytest.fixture
def mixed(tmp_path):
    """Base de démonstration à laquelle l'utilisateur a ajouté sa société et un salarié réel."""
    db = Database(tmp_path / "data" / "paie.db")
    db.migrate()
    demo.seed_demo(db)
    master_data.save_company(db, ACTOR, REAL_COMPANY)
    real_id, _ = master_data.create_employee(
        db, ACTOR, make_employee("R100", nom="REEL", prenom="Salarié", cin="RR111111", cnss="222222222",
                                 date_embauche=date(2026, 7, 1)))
    july, _ = payroll.save_draft(db, ACTOR, real_id, 2026, 7, REFERENCE_INPUT)
    payroll.calculate(db, ACTOR, july)
    payroll.close(db, ACTOR, july, confirm_warnings=True)
    aug, _ = payroll.save_draft(db, ACTOR, real_id, 2026, 8, REFERENCE_INPUT)
    payroll.calculate(db, ACTOR, aug)                     # paie réelle calculée, non clôturée
    env_file = tmp_path / ".env"
    env_file.write_text("PAIE_AUTH_PASSWORD_HASH=pbkdf2_sha256$1$a$b\nPAIE_SEED_DEMO=1\n", encoding="utf-8")
    return db, real_id, tmp_path / "backups", env_file


def real_state(db, real_id):
    """Empreinte des données réelles : société, fiche, paies (résultats) et bulletins."""
    company = master_data.get_company(db).snapshot()
    employee = master_data.get_employee(db, real_id).snapshot()
    slips = [(s.id, s.status, s.result.to_dict() if s.result else None, s.cumuls.to_dict() if s.cumuls else None)
             for s in payroll.list_payslips(db, employee_id=real_id)]
    docs = [(d.filename, d.sha256) for s in payroll.list_payslips(db, employee_id=real_id)
            if (d := payroll.get_document(db, s.id))]
    return company, employee, slips, docs


def test_inventory(mixed):
    db, _, _, _ = mixed
    inv = sd.find_demo(db.path)
    assert (inv.payslips, inv.closed_payslips, inv.documents) == (3, 3, 3)
    assert (inv.other_employees, inv.other_payslips) == (1, 2)
    assert inv.company == "SOCIÉTÉ RÉELLE SARL" and not inv.company_is_demo


def test_deletes_only_demo_and_keeps_real_data(mixed):
    db, real_id, backup_dir, env_file = mixed
    before = real_state(db, real_id)
    demo_id = sd.find_demo(db.path).employee_id
    inv, saved = sd.delete_demo(db.path, backup_dir, env_file)
    # Démonstration supprimée
    assert master_data.get_employee(db, demo_id) is None
    assert payroll.list_payslips(db, employee_id=demo_id) == []
    conn = sqlite3.connect(db.path)
    assert conn.execute("SELECT COUNT(*) FROM documents d LEFT JOIN payslips p ON p.id = d.payslip_id "
                        "WHERE p.id IS NULL").fetchone()[0] == 0
    # Données réelles identiques, paramètres et journal conservés
    assert real_state(db, real_id) == before
    assert len(master_data.list_parameter_sets(db)) == 1
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert "salarie.creation" in actions and actions[-1] == "demo.suppression"
    conn.close()
    # Sauvegarde valide, contenant encore la démonstration
    backup.validate_backup_file(saved)
    assert sqlite3.connect(saved).execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 2
    # Démonstration non rechargée ensuite
    assert "PAIE_SEED_DEMO=0" in env_file.read_text(encoding="utf-8")
    assert "PAIE_AUTH_PASSWORD_HASH=pbkdf2_sha256$1$a$b" in env_file.read_text(encoding="utf-8")


def test_protections_restored_identically(mixed):
    db, real_id, backup_dir, env_file = mixed
    sd.delete_demo(db.path, backup_dir, env_file)
    conn = db.connect()
    try:
        assert _protections(conn) == _expected_protections(SCHEMA_VERSION)
        closed = [s for s in payroll.list_payslips(db, employee_id=real_id) if s.status == "cloturee"][0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM payslips WHERE id = ?", (closed.id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM documents WHERE payslip_id = ?", (closed.id,))
    finally:
        conn.close()
    backup.validate_backup_file(db.path)


def test_recap_contains_only_real_data_afterwards(mixed):
    db, real_id, backup_dir, env_file = mixed
    before = reporting.monthly_summary(reporting.payroll_journal(db, 2026, include_open=True))
    assert list(before["Nombre de paies"]) == [2, 2, 1]               # démonstration incluse
    sd.delete_demo(db.path, backup_dir, env_file)
    journal = reporting.payroll_journal(db, 2026, include_open=True)
    assert set(journal["Matricule"]) == {"R100"}
    monthly = reporting.monthly_summary(journal)
    assert list(monthly["Nombre de paies"]) == [1, 1]
    assert monthly.loc[0, "Salaire brut"] == pytest.approx(7366.51)


def test_refuses_when_demo_record_was_turned_into_a_real_employee(mixed):
    db, _, backup_dir, env_file = mixed
    demo_emp = master_data.get_employee(db, sd.find_demo(db.path).employee_id)
    master_data.update_employee(db, ACTOR, replace(demo_emp, cin="ZZ999999"))
    count = sqlite3.connect(db.path).execute("SELECT COUNT(*) FROM payslips").fetchone()[0]
    with pytest.raises(ResetAborted, match="salarié réel"):
        sd.delete_demo(db.path, backup_dir, env_file)
    assert sqlite3.connect(db.path).execute("SELECT COUNT(*) FROM payslips").fetchone()[0] == count
    assert not backup_dir.exists()


def test_nothing_to_do_without_demo(tmp_path, capsys):
    db = Database(tmp_path / "paie.db")
    db.migrate()
    master_data.save_company(db, ACTOR, REAL_COMPANY)
    assert sd.main(["--confirm", "EFFACER", "--db", str(db.path), "--backup-dir", str(tmp_path / "b"),
                    "--env-file", str(tmp_path / ".env")]) == 0
    assert "rien à faire" in capsys.readouterr().out
    assert not (tmp_path / "b").exists() and not (tmp_path / ".env").exists()


def test_failure_inside_transaction_rolls_everything_back(mixed, monkeypatch):
    db, real_id, backup_dir, env_file = mixed
    conn = sqlite3.connect(db.path)
    snapshot = lambda: [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
                        for t in ("employees", "payslips", "documents", "audit_log")]
    before = snapshot()

    def fail(_conn):
        raise ResetAborted("contrôle simulé en échec")

    monkeypatch.setattr(sd, "_verify_protections", fail)
    with pytest.raises(ResetAborted, match="simulé"):
        sd.delete_demo(db.path, backup_dir, env_file)
    after = snapshot()
    assert after[:3] == before[:3]                     # rien supprimé
    assert _protections(conn) == _expected_protections(SCHEMA_VERSION)   # déclencheurs présents
    assert "PAIE_SEED_DEMO=1" in env_file.read_text(encoding="utf-8")
    conn.close()


def test_database_in_use_aborts(mixed):
    db, _, backup_dir, env_file = mixed
    blocker = sqlite3.connect(db.path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ResetAborted, match="fermez l'application"):
            sd.delete_demo(db.path, backup_dir, env_file)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert sd.find_demo(db.path).employee_id is not None


@pytest.mark.parametrize("answer, code", [("non", 1), ("effacer", 1), ("EFFACER", 0)])
def test_command_requires_exact_confirmation(mixed, answer, code, capsys):
    db, _, backup_dir, env_file = mixed
    result = sd.main(["--confirm", answer, "--db", str(db.path), "--backup-dir", str(backup_dir),
                      "--env-file", str(env_file)])
    out = capsys.readouterr().out
    assert result == code and "À SUPPRIMER" in out and "SOCIÉTÉ RÉELLE SARL" in out
    assert (sd.find_demo(db.path).employee_id is None) is (code == 0)


def test_warns_when_company_is_still_demo(tmp_path, capsys):
    db = Database(tmp_path / "paie.db")
    db.migrate()
    demo.seed_demo(db)
    assert sd.main(["--confirm", "EFFACER", "--db", str(db.path), "--backup-dir", str(tmp_path / "b"),
                    "--env-file", str(tmp_path / ".env")]) == 0
    assert "encore celle de la démonstration" in capsys.readouterr().out


def test_windows_launcher():
    bat = (ROOT / "supprimer_demo.bat").read_bytes()
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")
    bat.decode("ascii")
    assert b"scripts\\supprimer_demo.py %*" in bat
