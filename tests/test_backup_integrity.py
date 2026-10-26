"""Restauration : refus des sauvegardes dont les protections de la base ont été altérées."""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from src.services import backup, demo, payroll
from src.services.errors import PayrollError

from .conftest import ACTOR


@pytest.fixture
def seeded(db, tmp_path):
    """Base de démonstration (3 paies clôturées) et une sauvegarde valide."""
    demo.seed_demo(db)
    saved = backup.create_backup(db, tmp_path / "backups", ACTOR)
    return db, saved, tmp_path


def _altered_copy(saved, tmp_path, *statements: str, foreign_keys_off: bool = False):
    target = tmp_path / "altered.db"
    shutil.copy(saved, target)
    conn = sqlite3.connect(target)
    if foreign_keys_off:
        conn.execute("PRAGMA foreign_keys = OFF")
    for statement in statements:
        conn.execute(statement)
    conn.commit()
    conn.close()
    return target


def _snapshot(db):
    conn = db.connect()
    try:
        return (conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM payslips").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
    finally:
        conn.close()


ALTERATIONS = {
    "déclencheur supprimé": ("DROP TRIGGER trg_payslips_closed_immutable",),
    "tous les déclencheurs supprimés": (
        "DROP TRIGGER trg_payslips_closed_immutable", "DROP TRIGGER trg_payslips_closed_nodelete",
        "DROP TRIGGER trg_documents_immutable", "DROP TRIGGER trg_documents_nodelete",
        "DROP TRIGGER trg_audit_append_only", "DROP TRIGGER trg_parameter_sets_immutable"),
    "index d'unicité supprimé": ("DROP INDEX ux_payslips_closed",),
    "déclencheur neutralisé": (
        "DROP TRIGGER trg_documents_nodelete",
        "CREATE TRIGGER trg_documents_nodelete BEFORE DELETE ON documents WHEN 0 "
        "BEGIN SELECT RAISE(ABORT, 'x'); END"),
    "déclencheur ajouté": (
        "CREATE TRIGGER trg_extra AFTER INSERT ON audit_log BEGIN DELETE FROM employees; END",),
}


@pytest.mark.parametrize("label", ALTERATIONS)
def test_altered_backup_is_rejected_and_current_data_untouched(seeded, label):
    db, saved, tmp_path = seeded
    before = _snapshot(db)
    altered = _altered_copy(saved, tmp_path, *ALTERATIONS[label])
    with pytest.raises(PayrollError, match="protections"):
        backup.restore_backup(db, altered.read_bytes(), tmp_path / "backups", ACTOR)
    assert _snapshot(db) == before
    assert not list((tmp_path / "backups").glob("*avant_restauration*"))   # refus avant toute action


def test_backup_with_broken_references_is_rejected(seeded):
    db, saved, tmp_path = seeded
    altered = _altered_copy(saved, tmp_path,
                            "INSERT INTO documents (payslip_id, filename, content, sha256, created_at) "
                            "VALUES (999, 'x.pdf', x'00', 'x', 'x')", foreign_keys_off=True)
    with pytest.raises(PayrollError, match="références"):
        backup.validate_backup_file(altered)


def test_valid_backup_restores_with_protections_and_archives(seeded):
    db, saved, tmp_path = seeded
    before = _snapshot(db)
    backup.restore_backup(db, saved.read_bytes(), tmp_path / "backups", ACTOR)
    assert _snapshot(db) == before
    closed = [s for s in payroll.list_payslips(db) if s.status == "cloturee"]
    assert len(closed) == 3 and all(payroll.get_document(db, s.id) for s in closed)
    conn = db.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM documents WHERE payslip_id = ?", (closed[0].id,))
    finally:
        conn.close()


def test_application_database_matches_expected_protections(seeded):
    """La base créée par les migrations est elle-même conforme au contrôle."""
    db, _, _ = seeded
    backup.validate_backup_file(db.path)
