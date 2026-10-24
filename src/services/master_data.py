"""Entreprise, salariés et versions de paramètres."""

from __future__ import annotations

from dataclasses import fields

from src.calculations.defaults import DEFAULT_PARAMETERS
from src.models.entities import Company, Employee
from src.models.parameters import PayrollParameters, parameters_as_flat_dict
from src.models.payroll import STATUT_CLOTUREE, STATUTS_OUVERTS
from src.repositories import repos
from src.repositories.db import Database
from src.services.errors import PayrollError, ValidationFailed
from src.validation.validators import (
    AVERTISSEMENT, ERREUR, Issue, has_errors, validate_company, validate_employee,
    validate_parameters,
)

SENSITIVE_EMPLOYEE_FIELDS = {"cin", "cnss", "compte_bancaire", "date_naissance", "adresse", "banque", "cimr"}
INITIAL_PARAMETERS_PERIOD = "2000-01"


# --- Entreprise ------------------------------------------------------------------------

def get_company(db: Database) -> Company | None:
    with db.read() as conn:
        return repos.get_company(conn)


def save_company(db: Database, actor: str, company: Company) -> list[Issue]:
    issues = validate_company(company)
    if has_errors(issues):
        raise ValidationFailed(issues)
    with db.transaction() as conn:
        repos.save_company(conn, company)
        repos.log(conn, actor, "entreprise.modification", "company", 1)
    return issues


# --- Salariés ----------------------------------------------------------------------------

DUPLICATE_LABELS = {"matricule": "ce matricule", "cin": "ce n° CIN", "cnss": "ce n° CNSS"}


def _check_employee(conn, emp: Employee) -> list[Issue]:
    issues = validate_employee(emp)
    for field_name in repos.find_duplicates(conn, emp):
        issues.append(Issue(ERREUR, field_name,
                            f"Un autre salarié utilise déjà {DUPLICATE_LABELS[field_name]}."))
    if has_errors(issues):
        raise ValidationFailed(issues)
    return issues


def create_employee(db: Database, actor: str, emp: Employee) -> tuple[int, list[Issue]]:
    emp.id = None
    with db.transaction() as conn:
        issues = _check_employee(conn, emp)
        employee_id = repos.insert_employee(conn, emp)
        repos.log(conn, actor, "salarie.creation", "employee", employee_id,
                  {"matricule": emp.matricule})
    return employee_id, issues


def update_employee(db: Database, actor: str, emp: Employee) -> list[Issue]:
    """Modifie la fiche courante. Les paies clôturées gardent leur copie figée."""
    if emp.id is None:
        raise PayrollError("Salarié inconnu.")
    with db.transaction() as conn:
        before = repos.get_employee(conn, emp.id)
        if before is None:
            raise PayrollError("Salarié introuvable.")
        if before.matricule != emp.matricule and repos.list_payslips(conn, employee_id=emp.id):
            raise PayrollError("Le matricule ne peut plus changer : des paies existent pour ce salarié.")
        issues = _check_employee(conn, emp)
        repos.update_employee(conn, emp)
        changed = [f.name for f in fields(Employee)
                   if f.name != "id" and getattr(before, f.name) != getattr(emp, f.name)]
        # Le journal mentionne les champs modifiés, jamais leurs valeurs sensibles.
        repos.log(conn, actor, "salarie.modification", "employee", emp.id,
                  {"matricule": emp.matricule, "champs": changed})
    return issues


def set_employee_active(db: Database, actor: str, employee_id: int, active: bool) -> None:
    with db.transaction() as conn:
        emp = repos.get_employee(conn, employee_id)
        if emp is None:
            raise PayrollError("Salarié introuvable.")
        emp.actif = active
        repos.update_employee(conn, emp)
        repos.log(conn, actor, "salarie.activation" if active else "salarie.desactivation",
                  "employee", employee_id, {"matricule": emp.matricule})


def list_employees(db: Database, active_only: bool = False, search: str = "") -> list[Employee]:
    with db.read() as conn:
        return repos.list_employees(conn, active_only=active_only, search=search)


def get_employee(db: Database, employee_id: int) -> Employee | None:
    with db.read() as conn:
        return repos.get_employee(conn, employee_id)


# --- Paramètres -------------------------------------------------------------------------

def ensure_initial_parameters(db: Database) -> None:
    """Crée la première version (valeurs du classeur) si la base n'en contient aucune."""
    with db.transaction() as conn:
        if repos.list_parameter_sets(conn):
            return
        repos.insert_parameter_set(
            conn, INITIAL_PARAMETERS_PERIOD, DEFAULT_PARAMETERS,
            "Valeurs initiales du classeur de référence",
            "Reprise de la feuille Paramètres. À faire valider par un professionnel.", "système",
        )
        repos.log(conn, "système", "parametres.initialisation", "parameter_set", INITIAL_PARAMETERS_PERIOD)


def list_parameter_sets(db: Database) -> list[repos.ParameterSet]:
    with db.read() as conn:
        return repos.list_parameter_sets(conn)


def parameters_for_period(db: Database, year: int, month: int) -> repos.ParameterSet | None:
    with db.read() as conn:
        return repos.parameter_set_for_period(conn, f"{year:04d}-{month:02d}")


def create_parameter_version(db: Database, actor: str, year: int, month: int,
                             params: PayrollParameters, label: str, comment: str) -> list[Issue]:
    """Ajoute une version datée. Les paies clôturées ne sont jamais recalculées."""
    issues = validate_parameters(params)
    if not comment.strip():
        issues.append(Issue(ERREUR, "comment", "Indiquez le motif ou la source de la modification."))
    if has_errors(issues):
        raise ValidationFailed(issues)
    period = f"{year:04d}-{month:02d}"
    with db.transaction() as conn:
        if any(ps.valid_from == period for ps in repos.list_parameter_sets(conn)):
            raise PayrollError(f"Une version prend déjà effet en {period}. Choisissez un autre mois.")
        previous = repos.parameter_set_for_period(conn, period)
        closed_after = conn.execute(
            "SELECT COUNT(*) AS n FROM payslips WHERE status = ? AND printf('%04d-%02d', year, month) >= ?",
            (STATUT_CLOTUREE, period)).fetchone()["n"]
        open_after = conn.execute(
            f"SELECT COUNT(*) AS n FROM payslips WHERE status IN ({', '.join('?' for _ in STATUTS_OUVERTS)}) "
            "AND printf('%04d-%02d', year, month) >= ?", (*STATUTS_OUVERTS, period)).fetchone()["n"]
        set_id = repos.insert_parameter_set(conn, period, params, label.strip(), comment.strip(), actor)
        changed = []
        if previous:
            old, new = parameters_as_flat_dict(previous.params), parameters_as_flat_dict(params)
            changed = [k for k in new if old.get(k) != new[k]]
            if previous.params.bareme != params.bareme:
                changed.append("bareme")
        repos.log(conn, actor, "parametres.nouvelle_version", "parameter_set", set_id,
                  {"effet": period, "rubriques": changed, "motif": comment.strip()})
    if closed_after:
        issues.append(Issue(AVERTISSEMENT, "valid_from",
                            f"{closed_after} paie(s) clôturée(s) à partir de {period} ne sont pas "
                            "recalculées : elles conservent les paramètres appliqués."))
    if open_after:
        issues.append(Issue(AVERTISSEMENT, "valid_from",
                            f"{open_after} paie(s) non clôturée(s) à partir de {period} devront être "
                            "recalculées pour appliquer cette version."))
    return issues
