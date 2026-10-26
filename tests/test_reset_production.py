"""Remise à zéro avant production : sauvegarde vérifiée, rien de détruit, démonstration supprimée."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import reset_production as rp
from src.repositories.db import Database
from src.services import backup, demo, master_data, payroll
from src.services.demo import DEMO_COMPANY

from .conftest import ACTOR, make_employee

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(tmp_path):
    """Base de démonstration (3 paies clôturées), dossier de sauvegarde et .env avec mot de passe."""
    db = Database(tmp_path / "data" / "paie.db")
    db.migrate()
    demo.seed_demo(db)
    env_file = tmp_path / ".env"
    env_file.write_text("PAIE_DB_PATH=data/paie.db\nPAIE_AUTH_PASSWORD_HASH=pbkdf2_sha256$1$abc$def\n"
                        "PAIE_SEED_DEMO=1\n", encoding="utf-8")
    return db, tmp_path / "backups", env_file


def counts(db_path: Path) -> tuple[int, int, int, int]:
    conn = sqlite3.connect(db_path)
    try:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("company", "employees", "payslips", "documents"))
    finally:
        conn.close()


def test_inventory_detects_demo_only(env):
    db, _, _ = env
    inv = rp.inventory(db.path)
    assert (inv.exists, inv.employees, inv.closed_payslips, inv.documents) == (True, 1, 3, 3)
    assert inv.demo_only


def test_inventory_flags_real_data(env):
    db, _, _ = env
    master_data.save_company(db, ACTOR, replace(DEMO_COMPANY, raison_sociale="SOCIÉTÉ RÉELLE"))
    assert not rp.inventory(db.path).demo_only
    db2 = Database(db.path.parent / "autre.db")
    db2.migrate()
    master_data.save_company(db2, ACTOR, DEMO_COMPANY)
    master_data.create_employee(db2, ACTOR, make_employee("0042"))
    assert not rp.inventory(db2.path).demo_only


def test_reset_empties_application_without_destroying_anything(env):
    db, backup_dir, env_file = env
    before = counts(db.path)
    report = rp.reset(db.path, backup_dir, env_file)
    # Base neuve : vide, seule la version initiale des paramètres
    assert counts(db.path) == (0, 0, 0, 0)
    assert len(master_data.list_parameter_sets(db)) == 1
    conn = sqlite3.connect(db.path)
    assert conn.execute("SELECT action FROM audit_log").fetchall()[-1] == ("application.reinitialisation",)
    conn.close()
    # Sauvegarde vérifiée et complète
    backup.validate_backup_file(report.backup_path)
    assert counts(report.backup_path) == before
    # Ancienne base conservée intégralement
    archived = report.archive_dir / "paie.db"
    assert archived.exists() and counts(archived) == before
    # La démonstration ne sera plus rechargée ; les autres réglages sont conservés
    text = env_file.read_text(encoding="utf-8")
    assert "PAIE_SEED_DEMO=0" in text and "PAIE_SEED_DEMO=1" not in text
    assert "PAIE_AUTH_PASSWORD_HASH=pbkdf2_sha256$1$abc$def" in text and "PAIE_DB_PATH=data/paie.db" in text
    assert report.warnings == []


def test_new_database_is_usable_for_a_real_company(env):
    db, backup_dir, env_file = env
    rp.reset(db.path, backup_dir, env_file)
    restarted = Database(db.path)
    restarted.migrate()
    master_data.save_company(restarted, ACTOR, replace(DEMO_COMPANY, raison_sociale="SOCIÉTÉ RÉELLE"))
    employee_id, _ = master_data.create_employee(restarted, ACTOR, make_employee("0001"))
    payslip_id, _ = payroll.save_draft(restarted, ACTOR, employee_id, 2026, 11, demo.REFERENCE_INPUT)
    payroll.calculate(restarted, ACTOR, payslip_id)
    closed = payroll.close(restarted, ACTOR, payslip_id, confirm_warnings=True)
    assert closed.cumuls.salaire_brut == closed.result.salaire_brut      # aucun cumul hérité de la démonstration


def test_seed_flag_is_honoured_after_reset(env, monkeypatch):
    """Au démarrage, la démonstration n'est chargée que si PAIE_SEED_DEMO vaut 1."""
    db, backup_dir, env_file = env
    rp.reset(db.path, backup_dir, env_file)
    monkeypatch.setenv("PAIE_SEED_DEMO", rp.env_value(env_file, "PAIE_SEED_DEMO"))
    from src.config import load_settings
    assert load_settings().seed_demo is False


def test_env_file_created_when_missing(tmp_path):
    db_path, env_file = tmp_path / "paie.db", tmp_path / ".env"
    report = rp.reset(db_path, tmp_path / "backups", env_file)
    assert report.backup_path is None and report.archive_dir is None
    assert env_file.read_text(encoding="utf-8") == "PAIE_SEED_DEMO=0\n"
    assert counts(db_path) == (0, 0, 0, 0)


def test_warns_when_no_password_mode_is_enabled(env):
    db, backup_dir, env_file = env
    env_file.write_text("PAIE_ALLOW_NO_AUTH=1\n", encoding="utf-8")
    report = rp.reset(db.path, backup_dir, env_file)
    assert report.warnings and "PAIE_ALLOW_NO_AUTH" in report.warnings[0]


def test_database_in_use_aborts_without_changes(env):
    db, backup_dir, env_file = env
    before = counts(db.path)
    blocker = sqlite3.connect(db.path)
    blocker.execute("BEGIN IMMEDIATE")                  # écriture en cours par l'application
    try:
        with pytest.raises(rp.ResetAborted, match="fermez l'application"):
            rp.reset(db.path, backup_dir, env_file)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert counts(db.path) == before
    assert not backup_dir.exists() or not list(backup_dir.iterdir())
    assert "PAIE_SEED_DEMO=1" in env_file.read_text(encoding="utf-8")


def test_failed_move_restores_database(env, monkeypatch):
    db, backup_dir, env_file = env
    before = counts(db.path)
    real_move = rp.shutil.move
    calls = []

    def flaky_move(src, dst):
        calls.append(src)
        if len(calls) == 2:                              # 2e fichier verrouillé (Windows)
            raise PermissionError("fichier verrouillé")
        return real_move(src, dst)

    keeper = sqlite3.connect(db.path)                    # connexion ouverte : -wal et -shm présents
    keeper.execute("SELECT COUNT(*) FROM payslips").fetchone()
    assert Path(f"{db.path}-wal").exists() and Path(f"{db.path}-shm").exists()
    monkeypatch.setattr(rp.shutil, "move", flaky_move)
    monkeypatch.setattr(rp, "_ensure_not_in_use", lambda path: None)
    try:
        with pytest.raises(rp.ResetAborted, match="Aucune donnée n'a été modifiée"):
            rp.reset(db.path, backup_dir, env_file)
    finally:
        keeper.close()
    monkeypatch.setattr(rp.shutil, "move", real_move)
    assert len(calls) == 3                               # 1 déplacé, 1 en échec, 1 remis en place
    assert db.path.exists() and counts(db.path) == before
    assert not list(backup_dir.glob("ancienne_base_*"))
    assert "PAIE_SEED_DEMO=1" in env_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("answer, code", [("non", 1), ("effacer", 1), ("", 1), ("EFFACER", 0)])
def test_command_requires_exact_confirmation(env, answer, code, capsys):
    db, backup_dir, env_file = env
    before = counts(db.path)
    result = rp.main(["--confirm", answer, "--db", str(db.path), "--backup-dir", str(backup_dir),
                      "--env-file", str(env_file)])
    assert result == code
    out = capsys.readouterr().out
    assert "démonstration uniquement" in out
    if code == 1:
        assert "Annulé" in out and counts(db.path) == before
    else:
        assert "Remise à zéro terminée" in out and counts(db.path) == (0, 0, 0, 0)


def test_interactive_confirmation(env, monkeypatch, capsys):
    db, backup_dir, env_file = env
    monkeypatch.setattr("builtins.input", lambda prompt: "EFFACER")
    assert rp.main(["--db", str(db.path), "--backup-dir", str(backup_dir), "--env-file", str(env_file)]) == 0


def test_windows_launcher():
    bat = (ROOT / "reinitialiser_production.bat").read_bytes()
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")      # fins de ligne Windows
    bat.decode("ascii")                                                     # aucun accent (page de code)
    assert b"scripts\\reset_production.py %*" in bat
    assert "*.bat text eol=crlf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
