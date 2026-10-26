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
from src.repositories.db import MIGRATIONS, SCHEMA_VERSION, Database, _split_sql
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


_PROTECTIONS_SQL = ("SELECT type, name, sql FROM sqlite_master "
                    "WHERE type IN ('trigger', 'index') AND sql IS NOT NULL")


def _protections(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """Déclencheurs et index explicites d'une base, SQL normalisé (espaces)."""
    return {(kind, name): " ".join(sql.split()) for kind, name, sql in conn.execute(_PROTECTIONS_SQL)}


def _expected_protections(version: int) -> dict[tuple[str, str], str]:
    """Déclencheurs et index produits par les migrations jusqu'à `version` (base en mémoire)."""
    conn = sqlite3.connect(":memory:")
    try:
        for migration_version, script in MIGRATIONS:
            if migration_version <= version:
                for statement in _split_sql(script):
                    conn.execute(statement)
        return _protections(conn)
    finally:
        conn.close()


def validate_backup_file(path: Path) -> None:
    """Vérifie qu'un fichier est une base de paie intègre et compatible.

    Les déclencheurs (immuabilité des paies clôturées, des bulletins, du journal) et les index
    d'unicité doivent être exactement ceux du schéma : une sauvegarde où ils manquent, diffèrent
    ou sont complétés serait restaurée sans ces protections, et `migrate()` ne les recréerait pas.
    """
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise PayrollError("Le fichier de sauvegarde est corrompu.")
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            for table in ("company", "employees", "parameter_sets", "payslips", "documents", "audit_log"):
                conn.execute(f"SELECT COUNT(*) FROM {table}")
            if version is None or version > SCHEMA_VERSION:
                raise PayrollError("Version de schéma incompatible avec cette application.")
            if _protections(conn) != _expected_protections(version):
                raise PayrollError("Sauvegarde refusée : les protections de la base (déclencheurs ou "
                                   "index d'unicité) ne correspondent pas au schéma attendu.")
            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise PayrollError("Sauvegarde refusée : références incohérentes entre les tables.")
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise PayrollError("Ce fichier n'est pas une sauvegarde de paie valide.") from exc


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
