"""Contrôles de saisie. Les erreurs bloquent l'enregistrement ; les avertissements non.

Le classeur de référence n'a aucune validation (hors menu de mois) : les règles ci-dessous
sont des décisions de conception documentées dans docs/AUDIT_SOURCES.md (§7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.calculations.money import ZERO
from src.models.entities import MODES_PAIEMENT, SITUATIONS_FAMILIALES, Company, Employee
from src.models.parameters import METHODES_TOTAUX, PayrollParameters
from src.models.payroll import MonthlyInput

ERREUR = "erreur"
AVERTISSEMENT = "avertissement"

JOURS_MAX = Decimal(31)
JOURS_CNSS_USUELS = Decimal(26)
MONTANT_MAX = Decimal("10000000")


@dataclass(frozen=True)
class Issue:
    level: str
    field: str
    message: str


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == ERREUR for i in issues)


def _decimals(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _check_amount(issues: list[Issue], field: str, label: str, value: Decimal,
                  max_decimals: int = 2) -> None:
    if value < ZERO:
        issues.append(Issue(ERREUR, field, f"{label} : un montant négatif n'est pas accepté."))
    if _decimals(value) > max_decimals:
        issues.append(Issue(ERREUR, field, f"{label} : {max_decimals} décimales au maximum."))
    if value > MONTANT_MAX:
        issues.append(Issue(ERREUR, field, f"{label} : montant anormalement élevé."))


# --- Saisie mensuelle -----------------------------------------------------------------

MONTHLY_LABELS = {
    "salaire_base": "Salaire de base mensuel",
    "jours_declares": "Jours déclarés",
    "heures_sup": "Heures supplémentaires (montant)",
    "prime_panier": "Prime de panier",
    "indemnite_transport": "Indemnité de transport",
    "indemnite_representation": "Indemnité de représentation",
    "autre_prime": "Autre prime",
    "conges_reliquat": "Reliquat de congés",
    "conges_acquis": "Congés acquis",
    "conges_pris": "Congés pris",
}


def validate_monthly_input(inp: MonthlyInput) -> list[Issue]:
    issues: list[Issue] = []
    for name, label in MONTHLY_LABELS.items():
        _check_amount(issues, name, label, getattr(inp, name))
    if inp.salaire_base <= ZERO:
        issues.append(Issue(ERREUR, "salaire_base", "Le salaire de base doit être supérieur à 0."))
    if inp.jours_declares > JOURS_MAX:
        issues.append(Issue(ERREUR, "jours_declares", "Les jours déclarés ne peuvent pas dépasser 31."))
    elif inp.jours_declares > JOURS_CNSS_USUELS:
        issues.append(Issue(AVERTISSEMENT, "jours_declares",
                            "Plus de 26 jours déclarés : vérifier la déclaration CNSS."))
    if inp.jours_declares == ZERO and inp.salaire_base > ZERO:
        issues.append(Issue(AVERTISSEMENT, "jours_declares",
                            "Aucun jour déclaré alors qu'un salaire de base est saisi."))
    solde = inp.conges_reliquat + inp.conges_acquis - inp.conges_pris
    if solde < ZERO:
        issues.append(Issue(AVERTISSEMENT, "conges_pris",
                            f"Le solde de congés devient négatif ({solde} j)."))
    return issues


def check_reliquat_vs_previous(inp: MonthlyInput, previous_solde: Decimal | None) -> list[Issue]:
    """Avertit si le reliquat saisi diffère du solde du dernier mois clôturé (décision D5)."""
    if previous_solde is None or inp.conges_reliquat == previous_solde:
        return []
    return [Issue(AVERTISSEMENT, "conges_reliquat",
                  f"Le reliquat saisi ({inp.conges_reliquat} j) diffère du solde du dernier mois "
                  f"clôturé ({previous_solde} j). Le classeur source ne reporte pas le solde "
                  "automatiquement : vérifiez qu'il n'est ni oublié ni compté deux fois.")]


# --- Salarié ----------------------------------------------------------------------------

MATRICULE_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def validate_employee(emp: Employee, today: date | None = None) -> list[Issue]:
    issues: list[Issue] = []
    today = today or date.today()
    if not emp.matricule.strip():
        issues.append(Issue(ERREUR, "matricule", "Le matricule est obligatoire."))
    elif not MATRICULE_RE.match(emp.matricule.strip()):
        issues.append(Issue(ERREUR, "matricule",
                            "Matricule : lettres, chiffres, tiret ou souligné (20 caractères max)."))
    if not emp.nom.strip():
        issues.append(Issue(ERREUR, "nom", "Le nom est obligatoire."))
    if emp.situation_familiale not in SITUATIONS_FAMILIALES:
        issues.append(Issue(ERREUR, "situation_familiale", "Situation familiale inconnue."))
    if emp.mode_paiement not in MODES_PAIEMENT:
        issues.append(Issue(ERREUR, "mode_paiement", "Mode de paiement inconnu."))
    if emp.nb_personnes_charge < 0:
        issues.append(Issue(ERREUR, "nb_personnes_charge", "Nombre de personnes à charge négatif."))
    if emp.date_naissance and emp.date_naissance >= today:
        issues.append(Issue(ERREUR, "date_naissance", "La date de naissance doit être passée."))
    if emp.date_embauche and emp.date_naissance and emp.date_embauche <= emp.date_naissance:
        issues.append(Issue(ERREUR, "date_embauche", "La date d'embauche précède la naissance."))
    if emp.date_sortie and emp.date_embauche and emp.date_sortie < emp.date_embauche:
        issues.append(Issue(ERREUR, "date_sortie", "La date de sortie précède l'embauche."))
    if not emp.date_embauche:
        issues.append(Issue(AVERTISSEMENT, "date_embauche", "Date d'embauche non renseignée."))
    if not emp.cnss.strip():
        issues.append(Issue(AVERTISSEMENT, "cnss", "N° CNSS non renseigné."))
    if not emp.cin.strip():
        issues.append(Issue(AVERTISSEMENT, "cin", "N° CIN non renseigné."))
    if emp.mode_paiement == "Virement" and not emp.compte_bancaire.strip():
        issues.append(Issue(AVERTISSEMENT, "compte_bancaire",
                            "Paiement par virement sans compte bancaire renseigné."))
    return issues


def validate_company(company: Company) -> list[Issue]:
    issues: list[Issue] = []
    if not company.raison_sociale.strip():
        issues.append(Issue(ERREUR, "raison_sociale", "La raison sociale est obligatoire."))
    if company.ice and not company.ice.strip().isdigit():
        issues.append(Issue(ERREUR, "ice", "L'ICE ne doit contenir que des chiffres."))
    if not company.cnss_employeur.strip():
        issues.append(Issue(AVERTISSEMENT, "cnss_employeur", "N° CNSS employeur non renseigné."))
    if company.logo and len(company.logo) > 1_000_000:
        issues.append(Issue(ERREUR, "logo", "Logo trop volumineux (1 Mo maximum)."))
    return issues


# --- Paramètres --------------------------------------------------------------------------

RATE_FIELDS = (
    "cnss_salarial", "amo_salarial", "cnss_patronal", "amo_patronal", "participation_amo",
    "formation_pro", "allocations_familiales", "fp_taux_bas", "fp_taux_haut",
    "imposable_heures_sup", "imposable_prime_panier", "imposable_transport",
    "imposable_representation", "imposable_autre_prime",
)


def validate_parameters(params: PayrollParameters) -> list[Issue]:
    issues: list[Issue] = []
    for name in RATE_FIELDS:
        value = getattr(params, name)
        if value < ZERO or value > 1:
            issues.append(Issue(ERREUR, name, f"{name} : taux attendu entre 0 % et 100 %."))
    for name in ("plafond_cnss", "fp_seuil_annuel", "fp_plafond_annuel"):
        if getattr(params, name) <= ZERO:
            issues.append(Issue(ERREUR, name, f"{name} : valeur strictement positive attendue."))
    if params.deduction_par_personne < ZERO:
        issues.append(Issue(ERREUR, "deduction_par_personne", "Déduction négative."))
    if params.max_personnes < 0:
        issues.append(Issue(ERREUR, "max_personnes", "Nombre maximum négatif."))
    if params.methode_totaux not in METHODES_TOTAUX:
        issues.append(Issue(ERREUR, "methode_totaux", "Méthode des totaux inconnue."))
    issues.extend(validate_bareme(params))
    return issues


def validate_bareme(params: PayrollParameters) -> list[Issue]:
    issues: list[Issue] = []
    bareme = params.bareme
    if not bareme:
        return [Issue(ERREUR, "bareme", "Le barème de l'IR doit contenir au moins une tranche.")]
    if bareme[0].lower != ZERO:
        issues.append(Issue(ERREUR, "bareme", "La première tranche doit commencer à 0."))
    for i, tranche in enumerate(bareme):
        n = i + 1
        if tranche.rate < ZERO or tranche.rate > 1:
            issues.append(Issue(ERREUR, "bareme", f"Tranche {n} : taux hors de 0–100 %."))
        if tranche.deduction < ZERO:
            issues.append(Issue(ERREUR, "bareme", f"Tranche {n} : somme à déduire négative."))
        if tranche.upper is not None and tranche.upper < tranche.lower:
            issues.append(Issue(ERREUR, "bareme", f"Tranche {n} : borne haute < borne basse."))
        if i > 0:
            prev = bareme[i - 1]
            if tranche.lower <= prev.lower:
                issues.append(Issue(ERREUR, "bareme", f"Tranche {n} : bornes non croissantes."))
            if prev.upper is None:
                issues.append(Issue(ERREUR, "bareme", f"Tranche {i} : seule la dernière tranche peut être ouverte."))
            elif tranche.lower <= prev.upper:
                issues.append(Issue(ERREUR, "bareme", f"Tranches {i} et {n} : bornes qui se chevauchent."))
            elif tranche.lower - prev.upper > Decimal("0.01"):
                issues.append(Issue(AVERTISSEMENT, "bareme",
                                    f"Trou entre la tranche {i} et la tranche {n}."))
    if bareme[-1].upper is not None:
        issues.append(Issue(AVERTISSEMENT, "bareme", "La dernière tranche n'est pas ouverte (« et plus »)."))
    return issues
