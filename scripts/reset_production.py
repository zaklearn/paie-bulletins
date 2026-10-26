"""Remise à zéro de l'application avant une mise en production avec une société réelle.

    python scripts/reset_production.py              (confirmation demandée : taper EFFACER)
    python scripts/reset_production.py --confirm EFFACER

Étapes, chacune bloquante en cas d'échec :
1. inventaire de la base actuelle (démonstration seule ou non) ;
2. confirmation explicite ;
3. sauvegarde de la base actuelle, puis vérification de cette sauvegarde ;
4. déplacement de l'ancienne base (et de ses fichiers -wal/-shm) dans un dossier d'archive —
   rien n'est supprimé, les paies clôturées et les bulletins restent récupérables ;
5. création d'une base neuve : schéma et version initiale des paramètres, sans démonstration ;
6. `PAIE_SEED_DEMO=0` dans `.env`, pour que la démonstration ne soit pas rechargée au démarrage.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import PROJECT_ROOT, load_settings  # noqa: E402
from src.repositories import repos  # noqa: E402
from src.repositories.db import Database  # noqa: E402
from src.services import backup, master_data  # noqa: E402
from src.services.demo import DEMO_COMPANY, DEMO_EMPLOYEE  # noqa: E402
from src.services.errors import PayrollError  # noqa: E402

CONFIRMATION = "EFFACER"
ACTOR = "reinitialisation"


class ResetAborted(Exception):
    """Remise à zéro interrompue avant toute modification de la base."""


@dataclass
class Inventory:
    exists: bool
    company: str = ""
    employees: int = 0
    payslips: int = 0
    closed_payslips: int = 0
    documents: int = 0
    demo_only: bool = True

    def lines(self) -> list[str]:
        if not self.exists:
            return ["Aucune base existante : une base neuve sera créée."]
        return [
            f"Entreprise : {self.company or '(non renseignée)'}",
            f"Salariés : {self.employees}",
            f"Paies : {self.payslips} (dont {self.closed_payslips} clôturées)",
            f"Bulletins PDF archivés : {self.documents}",
            "Contenu : démonstration uniquement" if self.demo_only
            else "ATTENTION : la base contient des données qui ne sont PAS la démonstration",
        ]


@dataclass
class ResetReport:
    backup_path: Path | None
    archive_dir: Path | None
    env_path: Path
    warnings: list[str] = field(default_factory=list)


def inventory(db_path: Path) -> Inventory:
    """Lecture seule de la base actuelle."""
    if not db_path.exists():
        return Inventory(exists=False)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT raison_sociale FROM company WHERE id = 1").fetchone()
        company = row[0] if row else ""
        employees = conn.execute("SELECT matricule, nom FROM employees").fetchall()
        count = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        inv = Inventory(
            exists=True, company=company, employees=len(employees),
            payslips=count("SELECT COUNT(*) FROM payslips"),
            closed_payslips=count("SELECT COUNT(*) FROM payslips WHERE status IN ('cloturee', 'remplacee')"),
            documents=count("SELECT COUNT(*) FROM documents"),
        )
    except sqlite3.DatabaseError as exc:
        raise ResetAborted(f"Base illisible ({exc}) : opération annulée.") from exc
    finally:
        conn.close()
    demo_employee = (DEMO_EMPLOYEE.matricule, DEMO_EMPLOYEE.nom)
    inv.demo_only = (company in ("", DEMO_COMPANY.raison_sociale)
                     and all(tuple(e) == demo_employee for e in employees))
    return inv


def set_env_value(env_path: Path, key: str, value: str) -> None:
    """Définit `KEY=VALUE` dans le fichier .env en conservant toutes les autres lignes."""
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    output, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key and not line.lstrip().startswith("#"):
            if not done:
                output.append(f"{key}={value}")
                done = True
            continue
        output.append(line)
    if not done:
        output.append(f"{key}={value}")
    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def env_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("#") and "=" in line and line.split("=", 1)[0].strip() == key:
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _ensure_not_in_use(db_path: Path) -> None:
    """Échoue si une autre connexion écrit dans la base, puis intègre le journal WAL."""
    conn = sqlite3.connect(db_path, timeout=2)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError as exc:
        raise ResetAborted("La base est en cours d'utilisation : fermez l'application "
                           "(fenêtre Streamlit) puis relancez la remise à zéro.") from exc
    finally:
        conn.close()


def _move_database(db_path: Path, archive_dir: Path) -> None:
    """Déplace la base et ses fichiers annexes ; en cas d'échec, remet tout en place."""
    archive_dir.mkdir(parents=True, exist_ok=False)
    moved: list[tuple[Path, Path]] = []
    try:
        for suffix in ("", "-wal", "-shm"):
            source = Path(f"{db_path}{suffix}")
            if source.exists():
                target = archive_dir / source.name
                shutil.move(str(source), str(target))
                moved.append((source, target))
    except OSError as exc:
        for source, target in reversed(moved):
            shutil.move(str(target), str(source))
        archive_dir.rmdir()
        raise ResetAborted("Impossible de déplacer la base (fichier verrouillé ?) : fermez "
                           "l'application puis relancez. Aucune donnée n'a été modifiée.") from exc


def reset(db_path: Path, backup_dir: Path, env_path: Path) -> ResetReport:
    """Remise à zéro. À n'appeler qu'après confirmation explicite."""
    backup_path = archive_dir = None
    if db_path.exists():
        _ensure_not_in_use(db_path)
        try:
            backup_path = backup.create_backup(Database(db_path), backup_dir, ACTOR, label="avant_reinitialisation")
            backup.validate_backup_file(backup_path)
        except (PayrollError, sqlite3.DatabaseError, OSError) as exc:
            raise ResetAborted(f"Sauvegarde impossible ou invalide ({exc}) : opération annulée, "
                               "aucune donnée modifiée.") from exc
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = backup_dir / f"ancienne_base_{stamp}"
        _move_database(db_path, archive_dir)

    db = Database(db_path)
    db.migrate()
    master_data.ensure_initial_parameters(db)
    with db.transaction() as conn:
        repos.log(conn, ACTOR, "application.reinitialisation", "database", db_path.name,
                  {"sauvegarde": backup_path.name if backup_path else None,
                   "ancienne_base": archive_dir.name if archive_dir else None})
    set_env_value(env_path, "PAIE_SEED_DEMO", "0")

    report = ResetReport(backup_path, archive_dir, env_path)
    if env_value(env_path, "PAIE_ALLOW_NO_AUTH") in ("1", "true", "oui", "yes"):
        report.warnings.append("Le fichier .env autorise l'accès SANS mot de passe (PAIE_ALLOW_NO_AUTH=1). "
                               "Avant de saisir une société réelle, définissez un mot de passe "
                               "(python scripts\\hash_password.py) et supprimez cette ligne.")
    return report


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Remise à zéro de l'application (suppression de la démonstration).")
    parser.add_argument("--confirm", help=f"Saisir {CONFIRMATION} pour confirmer sans question.")
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument("--backup-dir", type=Path, default=settings.backup_dir)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    args = parser.parse_args(argv)

    print("=== Remise à zéro de l'application de paie ===")
    print(f"Base : {args.db}")
    try:
        inv = inventory(args.db)
    except ResetAborted as exc:
        print(f"ARRÊT : {exc}")
        return 2
    for line in inv.lines():
        print(f"  - {line}")
    print("\nToutes les données ci-dessus seront retirées de l'application. Une sauvegarde vérifiée")
    print("est créée d'abord, et l'ancienne base est conservée dans le dossier des sauvegardes.")
    answer = args.confirm if args.confirm is not None else input(f"Pour confirmer, tapez {CONFIRMATION} : ")
    if answer.strip() != CONFIRMATION:
        print("Annulé : aucune modification.")
        return 1
    try:
        report = reset(args.db, args.backup_dir, args.env_file)
    except ResetAborted as exc:
        print(f"ARRÊT : {exc}")
        return 2
    print("\nRemise à zéro terminée.")
    if report.backup_path:
        print(f"  Sauvegarde vérifiée : {report.backup_path}")
        print(f"  Ancienne base conservée dans : {report.archive_dir}")
    print(f"  {report.env_path.name} : PAIE_SEED_DEMO=0 (la démonstration ne sera plus chargée)")
    for warning in report.warnings:
        print(f"\nAVERTISSEMENT : {warning}")
    print("\nÉtapes suivantes : lancer l'application, renseigner la page Entreprise, créer les")
    print("salariés, puis faire valider les paramètres de paie par un professionnel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
