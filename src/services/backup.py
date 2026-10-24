"""Sauvegarde et restauration de la base SQLite (API de sauvegarde en ligne de SQLite).

Une sauvegarde est un fichier `.db` autonome : base, paramètres, journal et bulletins PDF
archivés (stockés en base). Toute restauration est précédée d'une sauvegarde automatique.
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from src.repositories import repos
from src.repositories.db import SCHEMA_VERSION, Database
from src.services.errors import PayrollError


def create_backup(db: Database, backup_dir: Path, actor: str, label: str = "manuelle") -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"paie_{stamp}_{label}.db"
    src = db.connect()
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    with db.transaction() as conn:
        repos.log(conn, actor, "sauvegarde.creation", "backup", target.name)
    return target


def list_backups(backup_dir: Path) -> list[Path]:
    if not backup_dir.is_dir():
        return []
    return sorted(backup_dir.glob("paie_*.db"), reverse=True)


def validate_backup_file(path: Path) -> None:
    """Vérifie qu'un fichier est une base de paie intègre et compatible."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise PayrollError("Le fichier de sauvegarde est corrompu.")
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            for table in ("company", "employees", "parameter_sets", "payslips", "documents", "audit_log"):
                conn.execute(f"SELECT COUNT(*) FROM {table}")
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise PayrollError("Ce fichier n'est pas une sauvegarde de paie valide.") from exc
    if version is None or version > SCHEMA_VERSION:
        raise PayrollError("Version de schéma incompatible avec cette application.")


def restore_backup(db: Database, content: bytes, backup_dir: Path, actor: str) -> Path:
    """Remplace le contenu de la base par la sauvegarde fournie. Renvoie la sauvegarde de sécurité."""
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "restore.db"
        candidate.write_bytes(content)
        validate_backup_file(candidate)
        safety = create_backup(db, backup_dir, actor, label="avant_restauration")
        src = sqlite3.connect(candidate)
        dst = db.connect()
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    db.migrate()
    with db.transaction() as conn:
        repos.log(conn, actor, "sauvegarde.restauration", "backup", safety.name)
    return safety
