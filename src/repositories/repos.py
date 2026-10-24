"""Dépôts de données : traduction entre lignes SQLite et objets métier.

Toutes les fonctions reçoivent une connexion ouverte : c'est le service appelant qui
délimite la transaction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from src.models.entities import Company, Employee
from src.models.parameters import PayrollParameters
from src.models.payroll import (
    STATUT_CLOTUREE, STATUTS_OUVERTS, Cumuls, MonthlyInput, PayslipResult,
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# --- Entreprise ------------------------------------------------------------------------

COMPANY_FIELDS = ("raison_sociale", "adresse", "ville", "ice", "cnss_employeur", "rc",
                  "identifiant_fiscal", "telephone", "email", "logo")


def get_company(conn: sqlite3.Connection) -> Company | None:
    row = conn.execute("SELECT * FROM company WHERE id = 1").fetchone()
    if row is None:
        return None
    return Company(**{f: row[f] for f in COMPANY_FIELDS})


def save_company(conn: sqlite3.Connection, company: Company) -> None:
    values = [getattr(company, f) for f in COMPANY_FIELDS]
    placeholders = ", ".join("?" for _ in COMPANY_FIELDS)
    updates = ", ".join(f"{f} = excluded.{f}" for f in COMPANY_FIELDS)
    conn.execute(
        f"INSERT INTO company (id, {', '.join(COMPANY_FIELDS)}, updated_at) "
        f"VALUES (1, {placeholders}, ?) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}, updated_at = excluded.updated_at",
        (*values, now_iso()),
    )


# --- Salariés ----------------------------------------------------------------------------

EMPLOYEE_FIELDS = (
    "matricule", "nom", "prenom", "date_naissance", "cin", "cnss", "situation_familiale",
    "nb_personnes_charge", "date_embauche", "date_sortie", "fonction", "departement", "cimr",
    "categorie", "banque", "compte_bancaire", "adresse", "mode_paiement", "actif",
)
DATE_FIELDS = ("date_naissance", "date_embauche", "date_sortie")


def _employee_from_row(row: sqlite3.Row) -> Employee:
    data = {f: row[f] for f in EMPLOYEE_FIELDS}
    for f in DATE_FIELDS:
        data[f] = _date_or_none(data[f])
    data["actif"] = bool(data["actif"])
    return Employee(id=row["id"], **data)


def _employee_values(emp: Employee) -> list:
    values = []
    for f in EMPLOYEE_FIELDS:
        value = getattr(emp, f)
        if f in DATE_FIELDS:
            value = value.isoformat() if value else None
        elif f == "actif":
            value = 1 if value else 0
        elif isinstance(value, str):
            value = value.strip()
        values.append(value)
    return values


def insert_employee(conn: sqlite3.Connection, emp: Employee) -> int:
    ts = now_iso()
    cur = conn.execute(
        f"INSERT INTO employees ({', '.join(EMPLOYEE_FIELDS)}, created_at, updated_at) "
        f"VALUES ({', '.join('?' for _ in EMPLOYEE_FIELDS)}, ?, ?)",
        (*_employee_values(emp), ts, ts),
    )
    return int(cur.lastrowid)


def update_employee(conn: sqlite3.Connection, emp: Employee) -> None:
    sets = ", ".join(f"{f} = ?" for f in EMPLOYEE_FIELDS)
    conn.execute(f"UPDATE employees SET {sets}, updated_at = ? WHERE id = ?",
                 (*_employee_values(emp), now_iso(), emp.id))


def get_employee(conn: sqlite3.Connection, employee_id: int) -> Employee | None:
    row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    return _employee_from_row(row) if row else None


def list_employees(conn: sqlite3.Connection, active_only: bool = False,
                   search: str = "") -> list[Employee]:
    sql = "SELECT * FROM employees WHERE 1 = 1"
    args: list = []
    if active_only:
        sql += " AND actif = 1"
    if search.strip():
        sql += " AND (matricule LIKE ? OR nom LIKE ? OR prenom LIKE ?)"
        pattern = f"%{search.strip()}%"
        args += [pattern, pattern, pattern]
    sql += " ORDER BY matricule"
    return [_employee_from_row(r) for r in conn.execute(sql, args)]


def find_duplicates(conn: sqlite3.Connection, emp: Employee) -> list[str]:
    """Champs (matricule, cin, cnss) déjà utilisés par un autre salarié."""
    conflicts = []
    for field_name in ("matricule", "cin", "cnss"):
        value = getattr(emp, field_name).strip()
        if not value:
            continue
        row = conn.execute(
            f"SELECT id FROM employees WHERE {field_name} = ? AND id IS NOT ?",
            (value, emp.id),
        ).fetchone()
        if row:
            conflicts.append(field_name)
    return conflicts


# --- Paramètres -------------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterSet:
    id: int
    valid_from: str
    label: str
    comment: str
    created_at: str
    created_by: str
    params: PayrollParameters


def _parameter_set_from_row(row: sqlite3.Row) -> ParameterSet:
    return ParameterSet(
        id=row["id"], valid_from=row["valid_from"], label=row["label"],
        comment=row["comment"], created_at=row["created_at"], created_by=row["created_by"],
        params=PayrollParameters.from_dict(json.loads(row["data"])),
    )


def insert_parameter_set(conn: sqlite3.Connection, valid_from: str, params: PayrollParameters,
                         label: str, comment: str, actor: str) -> int:
    cur = conn.execute(
        "INSERT INTO parameter_sets (valid_from, label, data, comment, created_at, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (valid_from, label, json.dumps(params.to_dict()), comment, now_iso(), actor),
    )
    return int(cur.lastrowid)


def list_parameter_sets(conn: sqlite3.Connection) -> list[ParameterSet]:
    rows = conn.execute("SELECT * FROM parameter_sets ORDER BY valid_from DESC")
    return [_parameter_set_from_row(r) for r in rows]


def parameter_set_for_period(conn: sqlite3.Connection, period: str) -> ParameterSet | None:
    """Version en vigueur pour la période « AAAA-MM » : la plus récente dont la date d'effet ≤ période."""
    row = conn.execute(
        "SELECT * FROM parameter_sets WHERE valid_from <= ? ORDER BY valid_from DESC LIMIT 1",
        (period,),
    ).fetchone()
    return _parameter_set_from_row(row) if row else None


# --- Paies ------------------------------------------------------------------------------

@dataclass
class PayslipRecord:
    id: int
    employee_id: int
    year: int
    month: int
    version: int
    status: str
    inputs: MonthlyInput
    result: PayslipResult | None
    cumuls: Cumuls | None
    parameter_set_id: int | None
    parameters: PayrollParameters | None
    employee_snapshot: dict | None
    company_snapshot: dict | None
    replaces_id: int | None
    rectification_reason: str
    created_at: str
    updated_at: str
    calculated_at: str | None
    closed_at: str | None
    closed_by: str


def _json_or_none(value: str | None):
    return json.loads(value) if value else None


def _payslip_from_row(row: sqlite3.Row) -> PayslipRecord:
    result = _json_or_none(row["result"])
    cumuls = _json_or_none(row["cumuls"])
    params = _json_or_none(row["parameters"])
    return PayslipRecord(
        id=row["id"], employee_id=row["employee_id"], year=row["year"], month=row["month"],
        version=row["version"], status=row["status"],
        inputs=MonthlyInput.from_dict(json.loads(row["inputs"])),
        result=PayslipResult.from_dict(result) if result else None,
        cumuls=Cumuls.from_dict(cumuls) if cumuls else None,
        parameter_set_id=row["parameter_set_id"],
        parameters=PayrollParameters.from_dict(params) if params else None,
        employee_snapshot=_json_or_none(row["employee_snapshot"]),
        company_snapshot=_json_or_none(row["company_snapshot"]),
        replaces_id=row["replaces_id"], rectification_reason=row["rectification_reason"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        calculated_at=row["calculated_at"], closed_at=row["closed_at"], closed_by=row["closed_by"],
    )


def get_payslip(conn: sqlite3.Connection, payslip_id: int) -> PayslipRecord | None:
    row = conn.execute("SELECT * FROM payslips WHERE id = ?", (payslip_id,)).fetchone()
    return _payslip_from_row(row) if row else None


def get_open_payslip(conn, employee_id: int, year: int, month: int) -> PayslipRecord | None:
    row = conn.execute(
        f"SELECT * FROM payslips WHERE employee_id = ? AND year = ? AND month = ? "
        f"AND status IN ({', '.join('?' for _ in STATUTS_OUVERTS)})",
        (employee_id, year, month, *STATUTS_OUVERTS),
    ).fetchone()
    return _payslip_from_row(row) if row else None


def get_closed_payslip(conn, employee_id: int, year: int, month: int) -> PayslipRecord | None:
    row = conn.execute(
        "SELECT * FROM payslips WHERE employee_id = ? AND year = ? AND month = ? AND status = ?",
        (employee_id, year, month, STATUT_CLOTUREE),
    ).fetchone()
    return _payslip_from_row(row) if row else None


def list_payslip_versions(conn, employee_id: int, year: int, month: int) -> list[PayslipRecord]:
    rows = conn.execute(
        "SELECT * FROM payslips WHERE employee_id = ? AND year = ? AND month = ? ORDER BY version",
        (employee_id, year, month),
    )
    return [_payslip_from_row(r) for r in rows]


def list_payslips(conn, year: int | None = None, month: int | None = None,
                  employee_id: int | None = None, statuses: tuple[str, ...] | None = None
                  ) -> list[PayslipRecord]:
    sql, args = "SELECT * FROM payslips WHERE 1 = 1", []
    for column, value in (("year", year), ("month", month), ("employee_id", employee_id)):
        if value is not None:
            sql += f" AND {column} = ?"
            args.append(value)
    if statuses:
        sql += f" AND status IN ({', '.join('?' for _ in statuses)})"
        args += list(statuses)
    sql += " ORDER BY year, month, employee_id, version"
    return [_payslip_from_row(r) for r in conn.execute(sql, args)]


def closed_results_before(conn, employee_id: int, year: int, month: int) -> list[PayslipResult]:
    """Résultats des paies clôturées faisant foi, même année, mois strictement antérieurs."""
    rows = conn.execute(
        "SELECT result FROM payslips WHERE employee_id = ? AND year = ? AND month < ? "
        "AND status = ? ORDER BY month",
        (employee_id, year, month, STATUT_CLOTUREE),
    )
    return [PayslipResult.from_dict(json.loads(r["result"])) for r in rows]


def next_version(conn, employee_id: int, year: int, month: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM payslips "
        "WHERE employee_id = ? AND year = ? AND month = ?",
        (employee_id, year, month),
    ).fetchone()
    return int(row["v"])


def insert_payslip(conn, employee_id: int, year: int, month: int, version: int,
                   inputs: MonthlyInput, status: str, replaces_id: int | None = None,
                   rectification_reason: str = "") -> int:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO payslips (employee_id, year, month, version, status, inputs, replaces_id, "
        "rectification_reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (employee_id, year, month, version, status, json.dumps(inputs.to_dict()),
         replaces_id, rectification_reason, ts, ts),
    )
    return int(cur.lastrowid)


def update_payslip_inputs(conn, payslip_id: int, inputs: MonthlyInput, status: str) -> None:
    """Nouvelle saisie : le résultat précédent est invalidé."""
    conn.execute(
        "UPDATE payslips SET inputs = ?, status = ?, result = NULL, cumuls = NULL, "
        "parameters = NULL, parameter_set_id = NULL, employee_snapshot = NULL, "
        "company_snapshot = NULL, calculated_at = NULL, updated_at = ? WHERE id = ?",
        (json.dumps(inputs.to_dict()), status, now_iso(), payslip_id),
    )


def save_calculation(conn, payslip_id: int, status: str, result: PayslipResult, cumuls: Cumuls,
                     parameter_set_id: int, params: PayrollParameters,
                     employee_snapshot: dict, company_snapshot: dict) -> None:
    ts = now_iso()
    conn.execute(
        "UPDATE payslips SET status = ?, result = ?, cumuls = ?, parameter_set_id = ?, "
        "parameters = ?, employee_snapshot = ?, company_snapshot = ?, calculated_at = ?, "
        "updated_at = ? WHERE id = ?",
        (status, json.dumps(result.to_dict()), json.dumps(cumuls.to_dict()), parameter_set_id,
         json.dumps(params.to_dict()), json.dumps(employee_snapshot, ensure_ascii=False),
         json.dumps(company_snapshot, ensure_ascii=False), ts, ts, payslip_id),
    )


def mark_closed(conn, payslip_id: int, actor: str) -> None:
    ts = now_iso()
    conn.execute(
        "UPDATE payslips SET status = ?, closed_at = ?, closed_by = ?, updated_at = ? WHERE id = ?",
        (STATUT_CLOTUREE, ts, actor, ts, payslip_id),
    )


def mark_replaced(conn, payslip_id: int) -> None:
    conn.execute("UPDATE payslips SET status = 'remplacee' WHERE id = ?", (payslip_id,))


def delete_open_payslip(conn, payslip_id: int) -> None:
    conn.execute("DELETE FROM payslips WHERE id = ? AND status IN ('brouillon', 'calculee')",
                 (payslip_id,))


# --- Documents ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Document:
    id: int
    payslip_id: int
    filename: str
    content: bytes
    sha256: str
    created_at: str


def insert_document(conn, payslip_id: int, filename: str, content: bytes, sha256: str) -> int:
    cur = conn.execute(
        "INSERT INTO documents (payslip_id, filename, content, sha256, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (payslip_id, filename, content, sha256, now_iso()),
    )
    return int(cur.lastrowid)


def get_document(conn, payslip_id: int) -> Document | None:
    row = conn.execute("SELECT * FROM documents WHERE payslip_id = ?", (payslip_id,)).fetchone()
    if row is None:
        return None
    return Document(row["id"], row["payslip_id"], row["filename"], bytes(row["content"]),
                    row["sha256"], row["created_at"])


# --- Journal -----------------------------------------------------------------------------

def log(conn, actor: str, action: str, entity: str = "", entity_id: object = "",
        details: dict | None = None) -> None:
    """Journalise une opération. Ne jamais y placer de donnée personnelle ou bancaire."""
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, entity, entity_id, details) VALUES (?, ?, ?, ?, ?, ?)",
        (now_iso(), actor, action, entity, str(entity_id),
         json.dumps(details or {}, ensure_ascii=False)),
    )


def list_audit(conn, limit: int = 500, action: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM audit_log", []
    if action:
        sql += " WHERE action = ?"
        args.append(action)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]
