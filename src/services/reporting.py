"""Tableau de bord, récapitulatifs et exports.

Les exports ne contiennent ni CIN, ni n° CNSS, ni coordonnées bancaires, ni date de
naissance : seulement matricule, nom et montants.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd

from src.models.payroll import (
    STATUT_CLOTUREE, STATUTS_LIBELLES, STATUTS_OUVERTS, period_key,
)
from src.repositories import repos
from src.repositories.db import Database

AMOUNT_COLUMNS = {
    "salaire_brut": "Salaire brut",
    "total_cotisations_salariales": "Cotisations salariales",
    "total_cotisations_patronales": "Cotisations patronales",
    "net_imposable": "Net imposable",
    "ir_mensuel": "IR",
    "arrondi": "Arrondi",
    "net_a_payer": "Net à payer",
    "cout_employeur": "Coût employeur",
    "jours_declares": "Jours déclarés",
}


@dataclass(frozen=True)
class DashboardStats:
    nb_salaries_actifs: int
    nb_salaries_total: int
    mois_clotures: list[int]          # mois où tous les salariés concernés sont clôturés
    mois_ouverts: list[int]           # mois avec au moins une paie non clôturée
    nb_brouillons: int
    nb_calculees: int
    dernieres_paies: list[repos.PayslipRecord]
    alertes: list[str]


def dashboard(db: Database, year: int) -> DashboardStats:
    with db.read() as conn:
        employees = repos.list_employees(conn)
        slips = repos.list_payslips(conn, year=year)
        company = repos.get_company(conn)
        recent_rows = conn.execute(
            "SELECT id FROM payslips WHERE status = ? ORDER BY closed_at DESC, id DESC LIMIT 8", (STATUT_CLOTUREE,)
        ).fetchall()
        recent = [repos.get_payslip(conn, r["id"]) for r in recent_rows]
        has_params = bool(repos.list_parameter_sets(conn))
    open_months = sorted({s.month for s in slips if s.status in STATUTS_OUVERTS})
    closed_months = sorted({s.month for s in slips if s.status == STATUT_CLOTUREE} - set(open_months))
    alerts: list[str] = []
    if company is None or not company.raison_sociale:
        alerts.append("Les informations de l'entreprise ne sont pas renseignées.")
    elif not company.ice or not company.cnss_employeur:
        alerts.append("ICE ou n° CNSS employeur manquant sur la fiche entreprise.")
    if not has_params:
        alerts.append("Aucun paramètre de paie n'est défini.")
    active = [e for e in employees if e.actif]
    for emp in active:
        missing = [label for label, value in (("CIN", emp.cin), ("n° CNSS", emp.cnss),
                                              ("date d'embauche", emp.date_embauche)) if not value]
        if missing:
            alerts.append(f"Salarié {emp.matricule} : {', '.join(missing)} non renseigné(s).")
    for slip in slips:
        if slip.status in STATUTS_OUVERTS:
            alerts.append(f"Paie {period_key(slip.year, slip.month)} du salarié n° {slip.employee_id} "
                          f"non clôturée ({STATUTS_LIBELLES[slip.status].lower()}).")
    return DashboardStats(
        nb_salaries_actifs=len(active), nb_salaries_total=len(employees),
        mois_clotures=closed_months, mois_ouverts=open_months,
        nb_brouillons=sum(1 for s in slips if s.status == "brouillon"),
        nb_calculees=sum(1 for s in slips if s.status == "calculee"),
        dernieres_paies=recent, alertes=alerts,
    )


def payroll_journal(db: Database, year: int, month: int | None = None,
                    include_open: bool = False) -> pd.DataFrame:
    """Livre de paie : une ligne par paie faisant foi (clôturée), ou aussi les paies ouvertes."""
    statuses = (STATUT_CLOTUREE, *STATUTS_OUVERTS) if include_open else (STATUT_CLOTUREE,)
    with db.read() as conn:
        slips = repos.list_payslips(conn, year=year, month=month, statuses=statuses)
        employees = {e.id: e for e in repos.list_employees(conn)}
    rows = []
    for s in slips:
        if s.result is None:
            continue
        snap = s.employee_snapshot or {}
        emp = employees.get(s.employee_id)
        row = {
            "Période": period_key(s.year, s.month),
            "Matricule": snap.get("matricule", emp.matricule if emp else ""),
            "Nom": snap.get("nom", emp.nom if emp else ""),
            "Prénom": snap.get("prenom", emp.prenom if emp else ""),
            "Statut": STATUTS_LIBELLES[s.status],
            "Version": s.version,
        }
        for key, label in AMOUNT_COLUMNS.items():
            row[label] = float(getattr(s.result, key))
        rows.append(row)
    columns = ["Période", "Matricule", "Nom", "Prénom", "Statut", "Version", *AMOUNT_COLUMNS.values()]
    return pd.DataFrame(rows, columns=columns)


def monthly_summary(journal: pd.DataFrame) -> pd.DataFrame:
    """Totaux par mois (paies clôturées)."""
    if journal.empty:
        return journal
    totals = journal.groupby("Période")[list(AMOUNT_COLUMNS.values())].sum().round(2)
    totals.insert(0, "Nombre de paies", journal.groupby("Période").size())
    return totals.reset_index()


def annual_summary(journal: pd.DataFrame) -> pd.DataFrame:
    """Totaux annuels par salarié."""
    if journal.empty:
        return journal
    keys = ["Matricule", "Nom", "Prénom"]
    totals = journal.groupby(keys)[list(AMOUNT_COLUMNS.values())].sum().round(2)
    totals.insert(0, "Mois payés", journal.groupby(keys).size())
    return totals.reset_index()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV au format français (séparateur ;, virgule décimale), lisible par Excel."""
    return df.to_csv(index=False, sep=";", decimal=",", float_format="%.2f").encode("utf-8-sig")


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buffer.getvalue()


def audit_log(db: Database, limit: int = 500, action: str | None = None) -> pd.DataFrame:
    with db.read() as conn:
        rows = repos.list_audit(conn, limit=limit, action=action)
    return pd.DataFrame(rows, columns=["id", "ts", "actor", "action", "entity", "entity_id", "details"])
