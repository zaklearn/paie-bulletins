"""Suppression du seul salarié de démonstration, en conservant la société et les salariés réels.

    python scripts/supprimer_demo.py              (confirmation demandée : taper EFFACER)
    python scripts/supprimer_demo.py --confirm EFFACER

Le salarié de démonstration n'est reconnu que si ses trois identifiants correspondent à ceux
de la démonstration (matricule, nom, CIN). Ses paies clôturées et ses bulletins sont protégés
par la base : les deux protections de suppression sont levées puis rétablies à l'identique dans
une seule transaction, contrôlée avant validation. En cas d'échec, rien n'est modifié.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reset_production import (  # noqa: E402
    CONFIRMATION, ResetAborted, _ensure_not_in_use, set_env_value,
)
from src.config import PROJECT_ROOT, load_settings  # noqa: E402
from src.repositories import repos  # noqa: E402
from src.repositories.db import SCHEMA_VERSION, Database  # noqa: E402
from src.services import backup  # noqa: E402
from src.services.backup import _expected_protections, _protections  # noqa: E402
from src.services.demo import DEMO_COMPANY, DEMO_EMPLOYEE  # noqa: E402
from src.services.errors import PayrollError  # noqa: E402

ACTOR = "suppression_demo"
DELETE_TRIGGERS = ("trg_payslips_closed_nodelete", "trg_documents_nodelete")


@dataclass
class DemoInventory:
    employee_id: int | None
    payslips: int = 0
    closed_payslips: int = 0
    documents: int = 0
    company: str = ""
    other_employees: int = 0
    other_payslips: int = 0

    @property
    def company_is_demo(self) -> bool:
        return self.company == DEMO_COMPANY.raison_sociale

    def lines(self) -> list[str]:
        return [
            f"À SUPPRIMER : salarié de démonstration {DEMO_EMPLOYEE.matricule} {DEMO_EMPLOYEE.nom}, "
            f"{self.payslips} paie(s) dont {self.closed_payslips} clôturée(s), {self.documents} bulletin(s) PDF",
            f"CONSERVÉ : entreprise « {self.company or '(non renseignée)'} »",
            f"CONSERVÉ : {self.other_employees} autre(s) salarié(s) et leurs {self.other_payslips} paie(s)",
            "CONSERVÉ : paramètres de paie et journal des opérations",
        ]


def find_demo(db_path: Path) -> DemoInventory:
    """Repère le salarié de démonstration (lecture seule)."""
    if not db_path.exists():
        raise ResetAborted(f"Base introuvable : {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT id, nom, cin FROM employees WHERE matricule = ?",
                           (DEMO_EMPLOYEE.matricule,)).fetchone()
        company = conn.execute("SELECT raison_sociale FROM company WHERE id = 1").fetchone()
        company = company[0] if company else ""
        if row is None:
            return DemoInventory(None, company=company)
        employee_id, nom, cin = row
        if (nom, cin) != (DEMO_EMPLOYEE.nom, DEMO_EMPLOYEE.cin):
            raise ResetAborted(f"Le matricule {DEMO_EMPLOYEE.matricule} ne correspond plus au salarié de "
                               "démonstration (nom ou CIN modifié) : il s'agit peut-être d'un salarié réel. "
                               "Opération annulée, rien n'est modifié.")
        one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
        return DemoInventory(
            employee_id=employee_id,
            payslips=one("SELECT COUNT(*) FROM payslips WHERE employee_id = ?", employee_id),
            closed_payslips=one("SELECT COUNT(*) FROM payslips WHERE employee_id = ? "
                                "AND status IN ('cloturee', 'remplacee')", employee_id),
            documents=one("SELECT COUNT(*) FROM documents d JOIN payslips p ON p.id = d.payslip_id "
                          "WHERE p.employee_id = ?", employee_id),
            company=company,
            other_employees=one("SELECT COUNT(*) FROM employees WHERE id <> ?", employee_id),
            other_payslips=one("SELECT COUNT(*) FROM payslips WHERE employee_id <> ?", employee_id),
        )
    except sqlite3.DatabaseError as exc:
        raise ResetAborted(f"Base illisible ({exc}) : opération annulée.") from exc
    finally:
        conn.close()


def _verify_protections(conn: sqlite3.Connection) -> None:
    if _protections(conn) != _expected_protections(SCHEMA_VERSION):
        raise ResetAborted("Les protections de la base ne sont pas rétablies à l'identique : annulation.")
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ResetAborted("Références incohérentes après suppression : annulation.")


def delete_demo(db_path: Path, backup_dir: Path, env_path: Path) -> tuple[DemoInventory, Path]:
    """Supprime le salarié de démonstration. À n'appeler qu'après confirmation explicite."""
    inv = find_demo(db_path)
    if inv.employee_id is None:
        raise ResetAborted("Aucun salarié de démonstration dans la base : rien à faire.")
    _ensure_not_in_use(db_path)
    db = Database(db_path)
    try:
        saved = backup.create_backup(db, backup_dir, ACTOR, label="avant_suppression_demo")
        backup.validate_backup_file(saved)
    except (PayrollError, sqlite3.DatabaseError, OSError) as exc:
        raise ResetAborted(f"Sauvegarde impossible ou invalide ({exc}) : opération annulée.") from exc

    with db.transaction() as conn:                     # tout ou rien
        trigger_sql = {name: sql for name, sql in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name IN (?, ?)", DELETE_TRIGGERS)}
        if set(trigger_sql) != set(DELETE_TRIGGERS):
            raise ResetAborted("Protections de la base inattendues : opération annulée.")
        for name in DELETE_TRIGGERS:
            conn.execute(f"DROP TRIGGER {name}")
        conn.execute("DELETE FROM documents WHERE payslip_id IN "
                     "(SELECT id FROM payslips WHERE employee_id = ?)", (inv.employee_id,))
        conn.execute("DELETE FROM payslips WHERE employee_id = ?", (inv.employee_id,))
        conn.execute("DELETE FROM employees WHERE id = ?", (inv.employee_id,))
        for name in DELETE_TRIGGERS:
            conn.execute(trigger_sql[name])
        _verify_protections(conn)
        repos.log(conn, ACTOR, "demo.suppression", "employee", inv.employee_id,
                  {"paies": inv.payslips, "bulletins": inv.documents, "sauvegarde": saved.name})
    set_env_value(env_path, "PAIE_SEED_DEMO", "0")
    return inv, saved


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Supprime le salarié de démonstration, sans toucher aux données réelles.")
    parser.add_argument("--confirm", help=f"Saisir {CONFIRMATION} pour confirmer sans question.")
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument("--backup-dir", type=Path, default=settings.backup_dir)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    args = parser.parse_args(argv)

    print("=== Suppression du salarié de démonstration ===")
    print(f"Base : {args.db}")
    try:
        inv = find_demo(args.db)
    except ResetAborted as exc:
        print(f"ARRÊT : {exc}")
        return 2
    if inv.employee_id is None:
        print("Aucun salarié de démonstration dans la base : rien à faire.")
        return 0
    for line in inv.lines():
        print(f"  - {line}")
    answer = args.confirm if args.confirm is not None else input(f"\nPour confirmer, tapez {CONFIRMATION} : ")
    if answer.strip() != CONFIRMATION:
        print("Annulé : aucune modification.")
        return 1
    try:
        inv, saved = delete_demo(args.db, args.backup_dir, args.env_file)
    except ResetAborted as exc:
        print(f"ARRÊT : {exc}")
        return 2
    print("\nSuppression terminée : la base ne contient plus de données de démonstration.")
    print(f"  Sauvegarde vérifiée (pour revenir en arrière) : {saved}")
    print(f"  {args.env_file.name} : PAIE_SEED_DEMO=0")
    if inv.company_is_demo:
        print("\nAVERTISSEMENT : la fiche Entreprise est encore celle de la démonstration ; renseignez la société réelle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
