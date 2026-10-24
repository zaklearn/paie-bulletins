"""Procédure mensuelle : saisie, calcul, clôture, archivage, rectification.

Cycle de vie d'une paie (salarié × année × mois) :

    brouillon --calculer--> calculée --clôturer--> clôturée
        ^                      |                       |
        +------ modifier ------+         ouvrir une rectification (motif obligatoire)
                                                       v
                         nouvelle version (brouillon) ... clôturée ; l'ancienne -> remplacée

Une version clôturée n'est jamais modifiée ni supprimée (contrôlé ici et par la base).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from src.calculations.cumuls import compute_cumuls
from src.calculations.engine import compute_payslip
from src.calculations.money import ZERO
from src.models.entities import Employee
from src.models.payroll import (
    STATUT_BROUILLON, STATUT_CALCULEE, STATUT_CLOTUREE, STATUTS_OUVERTS, Cumuls, MonthlyInput,
    PayslipResult, period_key, period_label,
)
from src.pdf.bulletin import bulletin_filename, render_bulletin
from src.repositories import repos
from src.repositories.db import Database
from src.services.errors import PayrollError, ValidationFailed
from src.validation.validators import (
    AVERTISSEMENT, ERREUR, Issue, check_reliquat_vs_previous, has_errors, validate_monthly_input,
)

# Éléments considérés comme récurrents lors du préremplissage d'un nouveau mois.
RECURRING_FIELDS = ("salaire_base", "jours_declares", "prime_panier", "indemnite_transport",
                    "indemnite_representation", "conges_acquis")


@dataclass(frozen=True)
class Prefill:
    inputs: MonthlyInput
    source: str              # explication affichée à l'utilisateur
    warnings: list[Issue]


@dataclass(frozen=True)
class Preview:
    result: PayslipResult
    cumuls: Cumuls
    parameter_set: repos.ParameterSet


def _validate_period(year: int, month: int) -> None:
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise PayrollError("Période invalide.")


def _period_issues(emp: Employee, year: int, month: int) -> list[Issue]:
    """Contrôle la période au regard des dates d'embauche et de sortie."""
    issues: list[Issue] = []
    key = period_key(year, month)
    if emp.date_embauche and key < period_key(emp.date_embauche.year, emp.date_embauche.month):
        issues.append(Issue(ERREUR, "periode", "Période antérieure à la date d'embauche du salarié."))
    if emp.date_sortie and key > period_key(emp.date_sortie.year, emp.date_sortie.month):
        issues.append(Issue(ERREUR, "periode", "Période postérieure à la date de sortie du salarié."))
    if not emp.actif:
        issues.append(Issue(ERREUR, "salarie", "Salarié désactivé : réactivez sa fiche pour saisir une paie."))
    return issues


def _previous_closed(conn, employee_id: int, year: int, month: int) -> repos.PayslipRecord | None:
    """Dernière paie clôturée faisant foi strictement avant la période (toutes années)."""
    row = conn.execute(
        "SELECT id FROM payslips WHERE employee_id = ? AND status = ? "
        "AND (year < ? OR (year = ? AND month < ?)) ORDER BY year DESC, month DESC LIMIT 1",
        (employee_id, STATUT_CLOTUREE, year, year, month),
    ).fetchone()
    return repos.get_payslip(conn, row["id"]) if row else None


def previous_conges_solde(db: Database, employee_id: int, year: int, month: int):
    with db.read() as conn:
        prev = _previous_closed(conn, employee_id, year, month)
    return prev.result.conges_solde if prev and prev.result else None


def prefill_inputs(db: Database, employee_id: int, year: int, month: int) -> Prefill:
    """Valeurs proposées pour le formulaire de saisie, toujours modifiables."""
    _validate_period(year, month)
    with db.read() as conn:
        current = repos.get_open_payslip(conn, employee_id, year, month) \
            or repos.get_closed_payslip(conn, employee_id, year, month)
        if current:
            return Prefill(current.inputs, f"Saisie enregistrée (version {current.version}).", [])
        prev = _previous_closed(conn, employee_id, year, month)
    if prev is None:
        return Prefill(MonthlyInput(), "Aucune paie antérieure clôturée : saisie vierge.", [])
    values = {name: getattr(prev.inputs, name) for name in RECURRING_FIELDS}
    values["conges_reliquat"] = prev.result.conges_solde if prev.result else ZERO
    warnings = [Issue(AVERTISSEMENT, "prefill",
                      "Heures supplémentaires, autre prime et congés pris remis à zéro ; "
                      "le reliquat proposé est le solde du mois repris.")]
    expected = (year, month - 1) if month > 1 else (year - 1, 12)
    if (prev.year, prev.month) != expected:
        warnings.append(Issue(AVERTISSEMENT, "prefill",
                              f"Les valeurs proviennent de {period_label(prev.year, prev.month)}, "
                              "qui n'est pas le mois précédent : vérifiez chaque montant."))
    return Prefill(MonthlyInput(**values),
                   f"Éléments récurrents repris de {period_label(prev.year, prev.month)} (clôturé).",
                   warnings)


def check_inputs(db: Database, employee_id: int, year: int, month: int,
                 inputs: MonthlyInput) -> list[Issue]:
    """Toutes les vérifications de saisie, sans rien enregistrer."""
    _validate_period(year, month)
    emp = _require_employee(db, employee_id)
    issues = _period_issues(emp, year, month) + validate_monthly_input(inputs)
    issues += check_reliquat_vs_previous(inputs, previous_conges_solde(db, employee_id, year, month))
    return issues


def _require_employee(db: Database, employee_id: int) -> Employee:
    with db.read() as conn:
        emp = repos.get_employee(conn, employee_id)
    if emp is None:
        raise PayrollError("Salarié introuvable.")
    return emp


def save_draft(db: Database, actor: str, employee_id: int, year: int, month: int,
               inputs: MonthlyInput) -> tuple[int, list[Issue]]:
    """Enregistre la saisie en brouillon (création ou mise à jour de la version de travail)."""
    issues = check_inputs(db, employee_id, year, month, inputs)
    if has_errors(issues):
        raise ValidationFailed(issues)
    with db.transaction() as conn:
        open_slip = repos.get_open_payslip(conn, employee_id, year, month)
        if open_slip:
            repos.update_payslip_inputs(conn, open_slip.id, inputs, STATUT_BROUILLON)
            payslip_id, action = open_slip.id, "paie.brouillon.modification"
        else:
            if repos.get_closed_payslip(conn, employee_id, year, month):
                raise PayrollError("Cette paie est clôturée. Ouvrez une rectification pour la corriger.")
            version = repos.next_version(conn, employee_id, year, month)
            payslip_id = repos.insert_payslip(conn, employee_id, year, month, version, inputs,
                                              STATUT_BROUILLON)
            action = "paie.brouillon.creation"
        repos.log(conn, actor, action, "payslip", payslip_id, {"periode": period_key(year, month)})
    return payslip_id, issues


def _compute(conn, employee_id: int, year: int, month: int, inputs: MonthlyInput):
    """Calcul + cumuls à partir des données faisant foi en base."""
    pset = repos.parameter_set_for_period(conn, period_key(year, month))
    if pset is None:
        raise PayrollError(f"Aucun paramètre de paie en vigueur pour {period_label(year, month)}.")
    emp = repos.get_employee(conn, employee_id)
    if emp is None:
        raise PayrollError("Salarié introuvable.")
    result = compute_payslip(inputs, pset.params, emp.nb_personnes_charge)
    cumuls = compute_cumuls(repos.closed_results_before(conn, employee_id, year, month), result)
    return result, cumuls, pset, emp


def preview(db: Database, employee_id: int, year: int, month: int, inputs: MonthlyInput) -> Preview:
    """Prévisualisation sans enregistrement (formulaire de saisie)."""
    with db.read() as conn:
        result, cumuls, pset, _ = _compute(conn, employee_id, year, month, inputs)
    return Preview(result, cumuls, pset)


def calculate(db: Database, actor: str, payslip_id: int) -> repos.PayslipRecord:
    """Calcule une paie ouverte et fige provisoirement le contexte (paramètres, fiches)."""
    with db.transaction() as conn:
        slip = repos.get_payslip(conn, payslip_id)
        if slip is None or slip.status not in STATUTS_OUVERTS:
            raise PayrollError("Seule une paie en brouillon ou calculée peut être calculée.")
        company = repos.get_company(conn)
        if company is None or not company.raison_sociale:
            raise PayrollError("Renseignez d'abord les informations de l'entreprise.")
        result, cumuls, pset, emp = _compute(conn, slip.employee_id, slip.year, slip.month, slip.inputs)
        repos.save_calculation(conn, payslip_id, STATUT_CALCULEE, result, cumuls, pset.id,
                               pset.params, emp.snapshot(), company.snapshot())
        repos.log(conn, actor, "paie.calcul", "payslip", payslip_id,
                  {"periode": period_key(slip.year, slip.month), "parametres": pset.valid_from})
        return repos.get_payslip(conn, payslip_id)


def closure_checks(db: Database, payslip_id: int) -> list[Issue]:
    """Contrôles avant clôture. Erreurs = bloquant ; avertissements = confirmation requise."""
    with db.read() as conn:
        return _closure_checks(conn, payslip_id)


def _closure_checks(conn, payslip_id: int) -> list[Issue]:
    slip = repos.get_payslip(conn, payslip_id)
    if slip is None:
        return [Issue(ERREUR, "paie", "Paie introuvable.")]
    if slip.status == STATUT_CLOTUREE:
        return [Issue(ERREUR, "statut", "Cette paie est déjà clôturée.")]
    if slip.status != STATUT_CALCULEE or slip.result is None:
        return [Issue(ERREUR, "statut", "Calculez la paie avant de la clôturer.")]
    issues: list[Issue] = []
    emp = repos.get_employee(conn, slip.employee_id)
    issues += _period_issues(emp, slip.year, slip.month)
    issues += [i for i in validate_monthly_input(slip.inputs) if i.level == ERREUR]
    # Le calcul affiché doit être identique au calcul sur les données faisant foi.
    try:
        result, cumuls, pset, emp_now = _compute(conn, slip.employee_id, slip.year, slip.month, slip.inputs)
    except PayrollError as exc:
        return issues + [Issue(ERREUR, "calcul", str(exc))]
    company = repos.get_company(conn)
    if (result != slip.result or cumuls != slip.cumuls or pset.id != slip.parameter_set_id
            or emp_now.snapshot() != slip.employee_snapshot
            or company is None or company.snapshot() != slip.company_snapshot):
        issues.append(Issue(ERREUR, "calcul",
                            "Les paramètres, la fiche salarié, l'entreprise ou les cumuls ont changé "
                            "depuis le calcul : recalculez la paie avant de la clôturer."))
    # Mois antérieurs de l'année : aucune paie ouverte, mois manquants signalés.
    for m in range(1, slip.month):
        if repos.get_open_payslip(conn, slip.employee_id, slip.year, m):
            issues.append(Issue(ERREUR, "chronologie",
                                f"{period_label(slip.year, m)} n'est pas clôturé : clôturez les mois "
                                "dans l'ordre chronologique (cumuls)."))
        elif not repos.get_closed_payslip(conn, slip.employee_id, slip.year, m) \
                and _employed_during(emp, slip.year, m):
            issues.append(Issue(AVERTISSEMENT, "chronologie",
                                f"Aucune paie pour {period_label(slip.year, m)} alors que le salarié "
                                "était embauché : ce mois sera absent des cumuls."))
    later = conn.execute(
        "SELECT month FROM payslips WHERE employee_id = ? AND year = ? AND month > ? AND status = ?",
        (slip.employee_id, slip.year, slip.month, STATUT_CLOTUREE)).fetchall()
    if later:
        months = ", ".join(period_label(slip.year, r["month"]) for r in later)
        issues.append(Issue(AVERTISSEMENT, "cumuls",
                            f"Bulletins déjà clôturés après ce mois ({months}) : ils conservent les "
                            "cumuls tels qu'émis ; la correction apparaîtra sur les prochains bulletins."))
    if slip.replaces_id:
        issues.append(Issue(AVERTISSEMENT, "rectification",
                            f"Cette clôture remplace la version précédente (motif : {slip.rectification_reason})."))
    return issues


def _employed_during(emp: Employee, year: int, month: int) -> bool:
    key = period_key(year, month)
    if emp.date_embauche and key < period_key(emp.date_embauche.year, emp.date_embauche.month):
        return False
    if emp.date_sortie and key > period_key(emp.date_sortie.year, emp.date_sortie.month):
        return False
    return True


def close(db: Database, actor: str, payslip_id: int, confirm_warnings: bool,
          logo: bytes | None = None) -> repos.PayslipRecord:
    """Clôture, génère et archive le bulletin PDF, fige les cumuls — en une seule transaction."""
    with db.transaction() as conn:
        issues = _closure_checks(conn, payslip_id)
        if has_errors(issues):
            raise ValidationFailed(issues)
        if any(i.level == AVERTISSEMENT for i in issues) and not confirm_warnings:
            raise PayrollError("Des avertissements doivent être confirmés avant la clôture.")
        slip = repos.get_payslip(conn, payslip_id)
        if slip.replaces_id:
            repos.mark_replaced(conn, slip.replaces_id)
        repos.mark_closed(conn, payslip_id, actor)
        closed = repos.get_payslip(conn, payslip_id)
        if repos.get_document(conn, payslip_id) is not None:
            raise PayrollError("Un bulletin est déjà archivé pour cette version.")
        pdf = render_bulletin(closed, logo=logo, provisional=False)
        repos.insert_document(conn, payslip_id, bulletin_filename(closed), pdf,
                              hashlib.sha256(pdf).hexdigest())
        repos.log(conn, actor, "paie.cloture", "payslip", payslip_id,
                  {"periode": period_key(closed.year, closed.month), "version": closed.version,
                   "remplace": slip.replaces_id, "net_a_payer": str(closed.result.net_a_payer)})
        return closed


def open_rectification(db: Database, actor: str, payslip_id: int, reason: str) -> int:
    """Crée une nouvelle version de travail à partir d'une paie clôturée."""
    if len(reason.strip()) < 5:
        raise PayrollError("Indiquez un motif de rectification (5 caractères minimum).")
    with db.transaction() as conn:
        slip = repos.get_payslip(conn, payslip_id)
        if slip is None or slip.status != STATUT_CLOTUREE:
            raise PayrollError("Seule la version clôturée en vigueur peut être rectifiée.")
        if repos.get_open_payslip(conn, slip.employee_id, slip.year, slip.month):
            raise PayrollError("Une rectification est déjà en cours pour ce mois.")
        version = repos.next_version(conn, slip.employee_id, slip.year, slip.month)
        new_id = repos.insert_payslip(conn, slip.employee_id, slip.year, slip.month, version,
                                      slip.inputs, STATUT_BROUILLON, replaces_id=slip.id,
                                      rectification_reason=reason.strip())
        repos.log(conn, actor, "paie.rectification.ouverture", "payslip", new_id,
                  {"periode": period_key(slip.year, slip.month), "remplace": slip.id,
                   "motif": reason.strip()})
    return new_id


def delete_draft(db: Database, actor: str, payslip_id: int) -> None:
    with db.transaction() as conn:
        slip = repos.get_payslip(conn, payslip_id)
        if slip is None or slip.status not in STATUTS_OUVERTS:
            raise PayrollError("Seul un brouillon ou une paie calculée non clôturée peut être supprimé.")
        repos.delete_open_payslip(conn, payslip_id)
        repos.log(conn, actor, "paie.brouillon.suppression", "payslip", payslip_id,
                  {"periode": period_key(slip.year, slip.month), "version": slip.version})


def provisional_pdf(db: Database, payslip_id: int, logo: bytes | None = None) -> bytes:
    """Aperçu PDF d'une paie calculée non clôturée (filigrane « PROVISOIRE », non archivé)."""
    with db.read() as conn:
        slip = repos.get_payslip(conn, payslip_id)
    if slip is None or slip.result is None:
        raise PayrollError("Calculez la paie pour obtenir un aperçu.")
    return render_bulletin(slip, logo=logo, provisional=slip.status != STATUT_CLOTUREE)


def get_document(db: Database, payslip_id: int) -> repos.Document | None:
    with db.read() as conn:
        return repos.get_document(conn, payslip_id)


def get_payslip(db: Database, payslip_id: int) -> repos.PayslipRecord | None:
    with db.read() as conn:
        return repos.get_payslip(conn, payslip_id)


def list_payslips(db: Database, **filters) -> list[repos.PayslipRecord]:
    with db.read() as conn:
        return repos.list_payslips(conn, **filters)


def list_versions(db: Database, employee_id: int, year: int, month: int) -> list[repos.PayslipRecord]:
    with db.read() as conn:
        return repos.list_payslip_versions(conn, employee_id, year, month)


def current_payslip(db: Database, employee_id: int, year: int, month: int) -> repos.PayslipRecord | None:
    """Version de travail si elle existe, sinon version clôturée en vigueur."""
    with db.read() as conn:
        return repos.get_open_payslip(conn, employee_id, year, month) \
            or repos.get_closed_payslip(conn, employee_id, year, month)


def today_period() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month

